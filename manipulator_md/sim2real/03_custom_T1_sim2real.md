# 08. 커스텀 T1 Sim-to-Real (빨간 큐브 → 검은 박스, GR00T N1.6)

> 워크숍 태스크(Vials-To-Rack)로 sim 파이프라인을 완전 검증(N1.6 8-bit 학습 sim SR **80%**,
> [02_sim_to_real_gr00t.md](02_sim_to_real_gr00t.md))한 것을 바탕으로, **우리 고유 T1 태스크**
> (실기와 동일: 빨간 큐브를 검은 박스에 넣기)를 Isaac Sim에 만들고 전체 sim-to-real 사이클을 돈다.
> 목표: sim에서 에셋 제작 → 리더암 데이터 수집 → GR00T N1.6 학습 → sim 추론 확인 → **실기 전이** →
> (성능 부족 시) **실기 시연 데이터 co-training**.
>
> 계획: [05_SimToReal.md](../../model_md/sim2real/05_SimToReal.md) | 실행 로그: [01_실행기록.md](01_실행기록.md)

작성: 2026-07-23

---

## 0. 전체 파이프라인 (6 Phase)

```
[Phase A] T1 sim 태스크·에셋 제작        빨간 큐브(프리미티브) + 검은 박스(컨테이너) + 성공판정
    ↓                                    → Lerobot-So101-T1-CubeBox(-DR/-Eval/-DR-Eval)
[Phase B] 리더암 teleop 데이터 수집       50ep(DR), 실기 T1 프로토콜(색 고정·위치 다양화·교정 시연)
    ↓
[Phase C] GR00T N1.6 학습 (8-bit Adam)   검증된 파이프라인 재사용(v2변환·modality·8bit·22.7GB)
    ↓
[Phase D] sim 추론 확인                   real-robot 서버 + 원본 클라이언트, 모니터 --rerun, SR 10회
    ↓
[Phase E] sim-to-real 전이                sim 학습본을 실기 SO-101로 zero-shot(카메라 매핑·goto_home)
    ↓
[Phase F] (성능 부족 시) co-training      sim 50ep + 실기 T1 50ep 혼합 재학습 → 실기 재측정
```

**왜 이 순서가 검증됐는가**: Phase C~D는 이미 vials 태스크로 완전 검증(8-bit N1.6 sim SR 80%,
fp32 사전학습본 60% 상회). T1은 **태스크·에셋만 교체**하고 학습·평가 인프라는 그대로 재사용한다.

### 0.1 실행 환경 배치 (2대 분리)

리더암(`/dev/ttyLEADER`)·실기 로봇이 **로컬 5070 Ti(16GB)**에 물려 있고, GR00T 학습은 **5090(32GB)**
에서만 가능하므로 아래처럼 분리한다. **환경(태스크·에셋)은 로컬에서 검증 후 5090에 적용**한다.

| Phase | 실행 위치 | 근거 |
|---|---|---|
| A 환경 검증(zero_agent) | **로컬 5070 Ti** | 빠른 반복·육안 확인 |
| B 리더암 teleop 수집 | **로컬 필수** | 리더암·GUI가 로컬 |
| C GR00T N1.6 8-bit 학습 | **5090 필수** | 32GB 필요(로컬 16GB 부족) |
| D sim 평가 | **5090 권장** | GR00T서버+sim 동시 ~15GB(로컬 빠듯) |
| E 실기 전이 | **로컬 필수** | 실기 로봇이 로컬 |
| F co-training | **5090** | 학습 |

- **이미지 파리티**: 양쪽 `teleop-docker` = Isaac Lab **2.3.2 동일**(2026-07-23 확인). 한쪽만 재빌드
  금지 — 동일 Dockerfile 유지 또는 `docker save|load`로 통일.
- **동기화**: `setup/sim/t1_task/deploy_t1.sh local|5090` (cfg/tray_black/reset/gym append, idempotent)
  + git. 로컬에서 cfg 수정 → 커밋 → `deploy_t1.sh 5090`로 반영.

---

## 1. 선례·사례 조사

| 사례 | 시사점 |
|---|---|
| **NVIDIA 워크숍** (Vials-To-Rack) | 정확히 이 흐름(커스텀 태스크→sim 학습→sim 평가→실기 전이→co-training)의 **레퍼런스 구현**. 우리는 이 태스크 템플릿을 T1로 개조 |
| [**LeIsaac**](https://wiki.seeedstudio.com/simulate_soarm101_by_leisaac/) | SO-101 sim teleop→LeRobot 포맷. "everyday manipulation tasks"를 커스텀 에셋으로 만들어 수집하는 워크플로 |
| **우리 자체 검증** ([07](02_sim_to_real_gr00t.md)) | N1.6 8-bit 학습 **sim SR 80%** — Phase C~D 파이프라인이 이미 작동함을 입증. T1은 태스크만 다름 |
| sim+real co-training **+38%** ([arXiv:2503.24361](https://arxiv.org/abs/2503.24361)) | Phase F 근거. 실데이터 단독 대비 평균 +38% |
| 실기 GR00T covariate shift ([report/GR00T_report.md](../../model_md/report/GR00T_report.md) §3.2) | Phase B 수집 규칙: **교정(recovery) 시연 필수**(어긋남→복구→성공 궤적) |

**핵심**: 커스텀 태스크 sim-to-real은 워크숍이 이미 end-to-end로 증명한 경로다. 새로운 리스크는
"에셋 제작"과 "sim↔실기 카메라 구도 갭"뿐이며, 나머지(학습·평가)는 검증된 자산을 그대로 쓴다.

---

## 2. Phase A — T1 sim 태스크·에셋 제작

워크숍 `source/sim_to_real_so101/`를 개조. 정본은 우리 repo `setup/sim/patches/`에 patch로 보관.

### 2.1 에셋 (커스텀 mesh 스캔 불필요 — 프리미티브 활용)

| 물체 | 방법 | 근거 |
|---|---|---|
| **빨간 큐브** | Isaac Lab **프리미티브** `sim_utils.CuboidCfg`(한 변 ~0.025m, 빨강 visual material, RigidBody) — **USD 파일 불필요** | 실기 큐브(~2.5cm)와 크기 일치. mesh 스캔·모델링 없이 코드로 spawn |
| **검은 박스** | 컨테이너: 기존 `assets/usd/tray.usda`를 **검은 material로 재색** 또는 얇은 5판 open-box USD 조립 | tray가 이미 컨테이너 형태. 색만 바꿔 재사용이 가장 빠름 |
| 카메라·조명·매트 | 워크숍 base(`so101_env_cfg.py`)의 ego/external_D455·lightbox·mat 그대로 | 데이터 포맷·카메라 키를 vials와 동일하게 유지(파이프라인 재사용) |

### 2.2 태스크 env cfg

- `tasks/vials_to_rack_env_cfg.py` → **`t1_cube_box_env_cfg.py`** 복사·개조:
  - vial 3개 → **빨간 큐브 1개**(`RigidObjectCfg`, 위 프리미티브 or 큐브 USD)
  - rack → **검은 박스 1개**
  - `init_state.pos`: 큐브를 workspace 5지점 부근(실기 그리드 프로토콜 반영), 박스는 고정
- **성공 판정** (`mdp/terms.py`에 `cube_in_box` 신설): **위치 기반** — 큐브 중심이 박스 XY 경계 내
  + z가 박스 안(바닥 근처) + 속도 안정(settled). vials의 접촉+방향 판정보다 단순
  (`vial_placed_on_rack`을 참고해 큐브용으로 축소)
- **리셋** (`mdp/resets.py`에 `reset_cube` 신설): 큐브 위치를 workspace 내 무작위(5지점+주변).
  ⚠️ **교정 시연**은 teleop이 절대위치 추종이라 물체 위치만 무작위화(로봇 시작자세 무작위화는
  무효 — [06](01_실행기록.md) §4). 교정은 Phase B에서 사람이 수동 생성.
- **DR 이벤트**: 조명·매트·색 무작위화는 vials-DR 그대로. 큐브 위치 무작위 범위만 조정.

### 2.3 gym 등록 (`tasks/__init__.py`)

vials 6종 등록을 참고해 T1 4종 추가:
`Lerobot-So101-T1-CubeBox`, `-DR`, `-CubeBox-Eval`, `-DR-Eval` (Teleop용·평가용 분리).

### 2.4 검증

- `list_envs`로 T1 태스크 4종 등록 확인
- `zero_agent --task Lerobot-So101-T1-CubeBox`로 씬에 빨간 큐브·검은 박스·SO-101 렌더링 육안 확인
  (Phase 0에서 vials 씬 검증한 것과 동일 방식, [setup/sim/README.md](../../setup/sim/README.md))

> **✅ 체크포인트 A (게이트)**
> - **코드 게이트 (2026-07-23 통과 ✅, headless)**:
>   1. ✅ T1 4종(`Lerobot-So101-T1-CubeBox`/`-DR`/`-Eval`/`-DR-Eval`) gym 등록
>   2. ✅ `zero_agent --headless`로 씬 생성 — 빨간 큐브(프리미티브 CuboidCfg)·검은 박스(tray_black)·
>      로봇·`contact_grasp` 센서·카메라 전부 엔티티 바인딩, import/cfg 에러 없음(내부 로그 `/tmp/isaaclab/logs/`)
>   3. ✅ 리셋(`reset_cube_box`)·파지(`cube_grasped`)·배치(`cube_placed`, vials 함수 재사용 vertical_threshold=0)·
>      success 판정 배선 정상. 정본: [setup/sim/t1_task/](../../setup/sim/t1_task/)
>   - ⚠️ 헤드리스 콘솔 stdout은 버퍼링으로 64줄에서 멈춰 보임 → 실제 진행은 내부 로그로 확인
> - **육안 게이트 (모니터, 잔여)**: GUI `zero_agent`로 큐브 색/박스 위치 확인 + 큐브를 박스에 옮겨
>   success=True 확인 → 판정 경계(`BOX_LOCAL_*`)·`cube_pose_range`(도달범위) 튜닝. **이후 Phase B로.**

---

## 3. Phase B — 리더암 teleop 데이터 수집

- 도구: `setup/sim/record_sim.sh` 재사용(태스크명·언어만 T1으로):
  `--task Lerobot-So101-T1-CubeBox-DR`, `--task_name "Pick up the red cube and place it in the black box"`
- 규모: **50ep + DR**(워크숍 프로토콜, 실기 v2/v3와 규모 일치)
- **수집 규칙** (실기 교훈 반영):
  - 빨간색 **고정**(언어와 일치), 큐브 위치 **다양화**(5지점+주변), **성공 종결**만 저장
  - **정상 ~35ep + 교정(recovery) ~15ep**: 교정은 사람이 리더암으로 일부러 어긋나게 접근→복구→
    파지→배치까지 성공 종결 ([06](01_실행기록.md) §4, covariate shift 처방)
  - idle 최소화(녹화 즉시 동작 개시)
- 출력: LeRobot v3.0 데이터셋 → `~/gr00tn16_ws/`(또는 신규 `~/t1_sim_ws/`)에 저장

> **✅ 체크포인트 B (게이트)** — 다음이 모두 참이면 Phase C로:
> 1. 50ep 수집(정상 ~35 + 교정 ~15), 각 ep 성공 종결로 저장
> 2. `info.json` total_episodes=50, 카메라 키·언어 라벨 T1으로 정상
> 3. 무작위 3ep 재생 육안 확인(큐브 색 빨강 고정·위치 다양·idle 최소)

---

## 4. Phase C — GR00T N1.6 학습 (8-bit Adam)

**검증된 파이프라인 그대로 재사용** ([07](02_sim_to_real_gr00t.md) §3, sim SR 80% 달성 구성):

1. v3.0 → **v2.1 변환**(`convert_v3_to_v2.py`, ffmpeg 필요) + `_v3.0` 백업
2. `meta/modality.json`: `front←external_D455`, `wrist←ego` (변환 후 재생성)
3. `stats.json` count 제거(`fix_stats_for_gr00t.py`)
4. 학습: `setup/sim/train_gr00t_sim_n16_8bit.sh`(데이터 경로만 T1으로) —
   이미지 `real-robot-train8`(bitsandbytes+8bit), NVIDIA 하이퍼파라미터 동일(유효배치 64·lr 1e-4·
   20k·color jitter), **GPU 22.7GB로 단일 5090 학습**
5. 목표 loss ~0.005 (vials와 동일 수준)

> **✅ 체크포인트 C (게이트)** — 다음이 모두 참이면 Phase D로:
> 1. v2.1 변환 + modality.json(front←external_D455/wrist←ego) + stats 수정 완료
> 2. 8-bit 학습 20k steps 완주, **GPU < 32GB**(OOM 없음), 최종 loss ~0.005
> 3. `checkpoint-20000/`에 trainer_state 등 무결성 확인

---

## 5. Phase D — sim 추론 확인

- `setup/sim/sim_eval_gr00t.sh <T1_체크포인트> 10 eval` (real-robot 서버 + teleop-docker 클라이언트)
- 태스크: `Lerobot-So101-T1-CubeBox-Eval`
- ⚠️ **원본 클라이언트** 사용(N1.5 어댑터 패치 남으면 N1.6 서버와 충돌 — [07](02_sim_to_real_gr00t.md) §3.4).
  N1.6 평가 전 `cp lerobot_interface.py.bak_preadapter …`로 원본 복원 확인
- 5090 모니터에서 `--headless` 빼고 `--rerun` → Isaac Sim 뷰포트+rerun 육안 확인
- 지표: sim SR 10회(Eval), DR-Eval 10회(전이 예측력)

> **✅ 체크포인트 D (게이트)** — 다음이 모두 참이면 Phase E로:
> 1. 원본 클라이언트 복원 확인(어댑터 패치 잔존 없음 — N1.6 서버 충돌 방지)
> 2. closed-loop 정상 작동(파지·배치 행동 관측), Eval 10회 + DR-Eval 10회 SR 기록
> 3. 5090 모니터 `--rerun` 육안 확인 1회 이상
> 4. (판단) sim SR 낮으면 tune 범위·action_horizon 조정 후 재학습, 아니면 Phase E

---

## 6. Phase E — sim-to-real 전이 (실기 SO-101)

sim 학습 N1.6 체크포인트를 **실기 로봇**에 서빙해 zero-shot 추론.

- 서버: real-robot 컨테이너로 `run_gr00t_server.py --model-path <T1_sim_체크포인트>` (실기 로봇은 로컬)
- 클라이언트: 실기 GR00T 클라이언트(실기 GR00T 작업의 `eval_lerobot.py` 계열 재사용,
  [report/GR00T_report.md](../../model_md/report/GR00T_report.md) §3.2) — 실기 카메라로 관측→서버→액션
- ⚠️ **카메라 매핑 (핵심 리스크)**: sim은 `external_D455`(front)/`ego`(wrist),
  실기는 `top`/`wrist`. modality/rename으로 **실기 top→front, 실기 wrist→wrist** 일치시킴.
  단 **카메라 구도(sim vs 실기 pose)가 다른 것이 주된 sim-real 갭** — DR로 완화, 그래도 남으면 Phase F
- 프로토콜: `goto_home`(학습 평균 자세 복귀), 개입 금지, 5지점 그리드, 10회 측정
  (실기 GR00T 측정 프로토콜 재사용)

> **✅ 체크포인트 E (게이트)** — 다음이 모두 참이면 (필요 시) Phase F로:
> 1. 실기 카메라 매핑 검증(top→front/wrist→wrist), 좌/우 물체 dry-run 시각 그라운딩 판정
> 2. 실기 서버 로드 OK(모드 고정·정지 어트랙터 없음), zero-shot 10회 SR 기록
> 3. **판단 게이트**: SR 충분(예 ≥50%)이면 종료, 부족하면 Phase F(co-training)로

---

## 7. Phase F — (성능 부족 시) 실기 데이터 co-training

sim-only 전이 SR이 낮으면 **실기 시연 데이터를 학습에 추가**.

- 실기 T1 데이터 **이미 확보**: `heongyu/so101_t1_pickplace` = **50ep**(v2.1, top/wrist) — 재수집 불필요
- 혼합: GR00T `--dataset-path`는 **List 지원** → sim 50ep + 실기 50ep(또는 워크숍 co-train 레시피처럼
  sim 70~100ep + 실기 **5ep**) 함께 학습
- ⚠️ **카메라 키 정합**: 두 데이터셋 modality.json이 **동일 키(front/wrist)로 매핑**되어야 함 —
  sim: front←external_D455, wrist←ego / 실기: front←top, wrist←wrist. (뷰 구도는 달라도 키는 통일)
- 근거: sim+real co-training 실데이터 단독 대비 **+38%** (arXiv:2503.24361)
- 재측정: Phase E 실기 프로토콜로 10회

> **✅ 체크포인트 F (게이트)** — 종료 조건:
> 1. 두 데이터셋 modality.json 키 정합(front/wrist 통일) 확인
> 2. 혼합 8-bit 학습 완주, 실기 재측정 10회 SR 기록
> 3. 최종 매트릭스(sim / 실기 zero-shot / co-train) 채움 → §10 결과표 완성

---

## 8. 재사용 자산 (이미 만든 것 — 새로 만들 것 최소화)

| 자산 | 위치 | Phase |
|---|---|---|
| 8-bit 학습 이미지 `real-robot-train8` | 5090 (bitsandbytes+torchcodec+ffmpeg) | C |
| 학습 스크립트 `train_gr00t_sim_n16_8bit.sh` | `setup/sim/` (데이터 경로만 변경) | C |
| v2 변환·stats·modality 도구 | `setup/gr00t/`, `convert_v3_to_v2.py` | C |
| 녹화 스크립트 `record_sim.sh` | `setup/sim/` (태스크명만 변경) | B |
| sim 평가 `sim_eval_gr00t.sh` | `setup/sim/` (태스크명만 변경) | D |
| 실기 T1 데이터 50ep | `heongyu/so101_t1_pickplace` (v2.1) | F |
| 실기 GR00T 서빙·측정 도구 | `setup/gr00t/` (goto_home 등) | E |
| 워크숍 패치 모음 | `setup/sim/patches/` | 전반 |

**새로 만들 것**: T1 태스크 env cfg(`t1_cube_box_env_cfg.py`) + 성공판정(`cube_in_box`) +
리셋(`reset_cube`) + gym 등록 + 검은 박스 material. (에셋은 프리미티브라 mesh 제작 없음)

---

## 9. 리스크 & 대응

| 리스크 | 대응 |
|---|---|
| 검은 박스 컨테이너 형태(큐브가 담기는) 제작 | tray.usda 재색 우선, 안 되면 5판 open-box USD 조립 |
| 성공 판정(큐브 in 박스) 튜닝 | 위치 임계값(XY 경계·z·속도)을 zero_agent/teleop로 관찰하며 조정 |
| **sim↔실기 카메라 구도 갭** (주 리스크) | sim 카메라 pose를 실기(top/wrist)와 유사하게 배치 + DR + co-training(Phase F) |
| 교정 시연 수집 부담 | 물체 위치 무작위(자동) + 사람 수동 교정 궤적 15ep(실기 covariate shift 처방) |
| N1.5 어댑터 패치 잔존 → N1.6 서버 충돌 | 평가 전 원본 클라이언트 복원 확인(체크리스트화) |
| co-training 카메라 키 불일치 | 두 데이터셋 modality.json을 front/wrist로 통일 |

---

## 10. 결과 기록 (템플릿)

### Phase D — sim 평가 ✅ (2026-07-27, GR00T N1.6 8-bit 75ep)
| 환경 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | SR |
|---|---|---|---|---|---|---|---|---|---|---|---|
| T1-Eval (DR 없음) | ✅ | ✅ | ❌ | ✅ | ✅ | ❌ | ❌ | ✅ | ✅ | ❌ | **6/10 (60%)** |
| T1-DR-Eval | ❌ | ❌ | ✅ | ✅ | ❌ | ❌ | ✅ | ✅ | ❌ | ✅ | **5/10 (50%)** |

> ⚠️ 첫 평가는 0%였으나 이는 측정 버그(포크 Eval 환경에 성공 판정기 전체 누락). 원본 vials 배선
> (`contact_grasp`+`success` termination+subtask)을 블록에 이식 후 위 결과. 상세: [08_T1_sim2real/report.md](08_T1_sim2real/report.md) E절

### Phase E — 실기 전이 (zero-shot, 10회)
| 시행 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | SR |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 결과 | | | | | | | | | | | /10 |

### Phase F — co-training 후 실기 (10회)
| 시행 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | SR |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 결과 | | | | | | | | | | | /10 |

### 최종 매트릭스
| 구성 | sim SR | 실기 전이 SR | co-train 실기 SR |
|---|---|---|---|
| T1 GR00T N1.6 8-bit | 60% (Eval) / 50% (DR-Eval) | _(Phase E)_ | _(Phase F)_ |

---

*관련: [05_SimToReal.md](../../model_md/sim2real/05_SimToReal.md) 계획 · [02_sim_to_real_gr00t.md](02_sim_to_real_gr00t.md) 검증된 학습·평가 ·
[01_실행기록.md](01_실행기록.md) 함정 · [report/GR00T_report.md](../../model_md/report/GR00T_report.md) 실기 근본원인 ·
[report/ACT_report.md](../../model_md/report/ACT_report.md) 실기 T1 셋업*
