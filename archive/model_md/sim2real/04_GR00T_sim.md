# S4. GR00T — Sim-to-Real (워크숍 공식 경로, 5090)

> **역할**: 워크숍이 공식 지원하는 유일한 모델 — sim 경로의 기준 구현체이자, NVIDIA가 설계한
> sim-to-real 파이프라인의 성능 상한 확인. **sim은 워크숍 최신 스택, 실기 벤치마크는 N1.5**(D2).
> 상위 계획: [05_SimToReal.md](05_SimToReal.md) | 실기 결과: [report/GR00T_report.md](../report/GR00T_report.md)

## 모델 개요 (sim 경로)

| 항목 | 내용 |
|---|---|
| 학습 방식 | 워크숍 스택 `gr00t_finetune.py --data-config so100_dualcam --embodiment-tag new_embodiment` |
| 버전 | **워크숍 추론 컨테이너의 최신 Isaac-GR00T** (GROOT_REF) — 실기 N1.5와 다름, 보고서 명시 (D2) |
| 학습 위치 | **5090** (`~/gr00t_remote/` 인프라 또는 워크숍 컨테이너) |
| **필수 처방 (실기 실측)** | ① **idle 트리밍** ② **`tune_visual`** ③ **유효 batch ≥32** (grad accumulation) |
| sim 평가 | 워크숍 `lerobot_eval` + `-Eval` / `-DR-Eval` 환경 (**공식 지원** — 어댑터 불필요) |
| 실기 전이 | **워크숍 추론 컨테이너**(동일 버전)로 실기 서빙 — 버전 혼선 방지. 기존 zmq 클라이언트·계측 재사용 |

## 데이터 요구·처리 (실기에서 검증된 절차)

- [ ] sim 데이터가 v3면 v2 변환 (`convert_v3_to_v2.py`, `--root`는 상위 디렉터리)
- [ ] `modality.json` 확인 — sim 카메라 키에 맞춰 original_key 매핑 (워크숍 데이터면 이미 정합)
- [ ] stats `count` 버그 수정 (`fix_stats_for_gr00t.py`)
- [ ] **idle 트리밍** (`trim_idle_v2.py`) — 실측: 미적용 시 배포 초기 정지 어트랙터

## 진행 절차

- [ ] **1. 학습** (Phase 2)
  - [ ] 위 데이터 처리 4종 완료
  - [ ] 학습: tune_visual + 유효 batch 32 (OOM 시 batch4×accum8 — 실기 검증 구성)
  - [ ] loss 확인 (목표: freeze 구성의 0.008~0.010 수준 근접 — vis 구성으로는 실기 vis2 결과 참조: ____)
- [ ] **2. sim 평가** (Phase 3)
  - [ ] `lerobot_eval` + `Vials-To-Rack-Eval` 10회
  - [ ] `-DR-Eval` 10회 (**DR 유무별 SR 분리 기록** — 전이 예측력 확인)
- [ ] **3. 실기 전이** (Phase 4)
  - [ ] 워크숍 추론 컨테이너로 실기 서빙 dry-run (좌/우 물체 → 시각 그라운딩 확인, 실기 검증 절차 재사용)
  - [ ] zero-shot 전이 10회 (goto_home·개입금지)
- [ ] **4. co-training** → 실기 재측정 10회

## 완결 체크리스트 (게이트)

- [ ] sim SR (Eval/DR-Eval 각 10회) + 전이 10회 + co-train 10회
- [ ] 좌/우 시각 그라운딩 dry-run 판정 기록
- [ ] 대표 클립 / 요약 카드 / 백업
- [ ] **버전 차이(N1.7계 sim vs N1.5 실기) 명시** 및 비교 해석 주석

## 리스크 & 대응

| 리스크 | 대응 (실기 실측 기반) |
|---|---|
| idle 어트랙터 재발 | 수집 시 즉시 동작 개시 + 트리밍 게이트화 |
| 모드 고정(시각 무시) | tune_visual 필수 + 좌/우 dry-run 판정을 측정 전 게이트로 |
| 학습부족 (batch 4 함정) | 유효 batch 32 확보 확인 (loss로 검증) |
| 저장 중 행(hang) | checkpoint 무결성 확인 습관 (trainer_state 존재), resume 절차 확보됨 |
| sim/실기 버전 불일치 논란 | 전이 서빙을 sim과 동일 컨테이너로 통일, 보고서 명시 |

## 결과 기록

### 기준선 재현 — 워크숍 사전학습 체크포인트 (옵션 A, 2026-07-21)

파이프라인 검증 + 공개 기준선 재현을 위해, 재학습 없이 워크숍 사전학습 체크포인트를 그대로 sim 평가:
- 체크포인트: `aravindhs-NV/grootn16-finetune_sreetz-so101_teleop_vials_rack_left/checkpoint-10000`
  (**N1.6**, sim-only 75ep 학습 — `sreetz-nv/so101_teleop_vials_rack_left`)
- 실행: `setup/sim/sim_eval_gr00t.sh grootn16_sim75/checkpoint-10000 10 eval` (5090 headless)

| 지표 | 값 |
|---|---|
| **sim SR (Eval, DR 없음)** | **6/10 = 60%** (랙 배치 성공 6회 확정) |
| 워크숍 공식 기대치 | 50~70% → **범위 정중앙, 재현 성공** |
| 누적 SR 추이 | ep1~10: 0→100→100→66.7→75→60→50→57→62.5→**60%** |

**의의**: ① real-robot 추론 서버(N1.6 로드) + teleop-docker 평가 클라이언트 + Isaac Sim
렌더링 end-to-end 파이프라인 검증 완료 ② 우리 자체 데이터 학습 결과를 해석할 **대조군 확보**.
빌드 함정(torch nightly 드리프트)은 `setup/sim/patches/dockerfile_blackwell_flashattn.patch`로 해결.

### 워크숍 데이터 자체 학습 검증 — **N1.5 open-loop** (옵션 1, 2026-07-22)

N1.6 단일 GPU 학습 벽으로 N1.5(n1d5)로 전환해 워크숍 75ep로 직접 학습(20k steps, loss 0.005).
closed-loop sim 평가는 공유 5090의 인프라 문제(HF 캐시 filelock hang은 해결했으나 n1d5 zmq
서버가 액션 요청에 미응답 — 자체 테스트 클라이언트도 타임아웃)로 막혀, **open-loop 평가**로 검증.

| 지표 | 값 |
|---|---|
| **Unnormalized Action MSE** (5궤적 평균) | **2.18** — 실기 GR00T(2.24) 수준 |
| 궤적 추종 | 예측 vs 정답 6축(팔5+그리퍼) 모두 근접, 파지 전환(그리퍼 급하강)까지 정확 재현 |
| 도구 | `eval_policy.py` (서버·sim·도커 불필요, 모델 직접 추론) |
| 플롯 | `~/n15_openloop_plot.png` (5090) |

**결론**: 데이터 다운로드→v2.1 변환→학습→태스크 학습 모델까지 **파이프라인 전구간 정상 작동 검증**.

### Sim closed-loop 평가 — **N1.5, SR 1/10** (2026-07-22, 어댑터 해결 후)

closed-loop이 막혔던 원인은 서버가 아니라 ① 백그라운드 서버가 ssh 끊김에 로딩 중 종료(세션 유지 시 정상)
② 워크숍 클라이언트가 N1.6 서버 전용 프로토콜이라 n1d5 서버와 형식 불일치. **어댑터 패치**(관측 평면화·
직접 전송·action.* 디코딩·reset 선택적, `setup/sim/patches/n1d5_client_adapter.patch`)로 해결.
(전송계층 msgpack numpy는 원래 호환.) 씬 hang도 GPU 경합이었고 서버 선로딩 후 1.5s로 해소.

| 지표 | 값 |
|---|---|
| **Eval SR (DR 없음, 10회)** | **1/10 = 10%** (ep1만 완전 성공) |
| 태스크 행동 | 파지 15회 / 랙 배치 4회 (10ep 동안) — 대부분 파지·배치 시도, 완전 성공만 드묾 |
| open-loop 대비 | MSE 2.18(양호)인데 closed-loop 10% → **자기 액션 오차 누적**(open/closed 격차) |
| **워크숍 N1.6 사전학습본 대비** | 60%(6/10) vs 우리 N1.5 10% — 아키텍처(N1.5 vs N1.6)·tune설정(top-4 LLM 미tune) 차이 |
| **N1.6 8bit 자체학습(2026-07-23)** | **8/10 = 80%** — 단일 5090 8-bit Adam으로 fp32 사전학습본(60%) 동등/상회. 양자화 저하 없음 확증. §07 |

**의의**: 서버·클라이언트·어댑터·Isaac Sim·rerun까지 closed-loop 전구간 작동 확인, 5090 모니터 육안
확인 가능. 정량 SR 확보. 개선 여지: tune 범위(top-LLM), action_horizon, co-training.

| 환경 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | SR |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Eval (DR 없음) | ✅ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | **1/10** |
| DR-Eval | | | | | | | | | | | (미측정) |

### Real zero-shot 전이 (10회)
| 시행 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | SR |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 결과 | | | | | | | | | | | /10 |

### Co-training 후 실기 (10회)
| 시행 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | SR |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 결과 | | | | | | | | | | | /10 |

### 요약 카드
- **수치**: sim __/10 (DR __/10), 전이 __/10, co-train __/10 (기준 real-only: vis2 판정 후 기입)
- **관찰 메모** / **갭 해석**:

## 참고 자료

- 워크숍(공식): https://github.com/isaac-sim/Sim-to-Real-SO-101-Workshop + [교육 문서](https://docs.nvidia.com/learning/physical-ai/sim-to-real-so-101/latest/index.html)
- GR00T N1.5 SO-101 튜닝: https://huggingface.co/blog/nvidia/gr00t-n1-5-so101-tuning
- 실기 실측(트리밍·tune_visual·batch 처방의 출처): [report/GR00T_report.md](../report/GR00T_report.md)
- co-training +38%: arXiv:2503.24361
