# T1 Sim-to-Real 실행 리포트 — 빨간 큐브 → 검은 박스 (GR00T N1.6)

> Isaac Sim에 T1 태스크(빨간 큐브를 검은 오픈박스에 넣기) 씬을 만들고, 리더암 teleop으로
> 학습 데이터를 수집해 GR00T N1.6를 학습하기까지의 실행 기록.
> 계획: [../08_custom_T1_sim2real.md](../08_custom_T1_sim2real.md) · Phase별 상세: [README.md](README.md)

작성: 2026-07-25

| Phase | 내용 | 상태 |
|---|---|---|
| **A** | T1 씬·에셋 제작 | ✅ 완료 |
| **B** | 리더암 teleop 데이터 수집 (75ep) | ✅ 완료 |
| **C** | GR00T N1.6 8-bit 학습 | 🔄 진행 중 |

---

## A. 씬·에셋 제작

coworker 포크의 블록 씬을 **별도 클론**(`~/blocktask_ws`)으로 가져와 기존 vials 환경과 분리해
사용했다(포크의 `MANAGING_MULTIPLE_ENVIRONMENTS.md` Method 1 — 안전). 빨간 큐브(20mm 프리미티브),
검은 오픈박스(`basket_box.usda`), 흰 평면 바닥(kinematic), 보라색 SO-101로 구성.

### 실행 스크립트

```bash
# 런처: setup/sim/t1_task/blocktask_run.sh
./blocktask_run.sh view      # zero_agent로 씬 육안 확인 (로봇 0액션)
./blocktask_run.sh record    # 리더암 teleop 녹화 (학습 데이터 수집)
./blocktask_run.sh clear     # 데이터셋 폴더 초기화 (재녹화 전)
```

- 태스크 ID: `Lerobot-So101-Teleop-Vials-To-Rack-DR` (coworker가 이 등록을 블록 씬으로 덮어씀)
- 씬 정의: `~/blocktask_ws/.../tasks/vials_to_rack_env_cfg.py`
- 5090 동기화: `setup/sim/t1_task/deploy_t1.sh 5090`

### 씬 (external_D455 / front 카메라 시점)

![T1 씬 — 보라색 SO-101, 빨간 큐브, 검은 오픈박스, 흰 바닥](assets/scene_front.jpg)

> 보라색 SO-101, 빨간 큐브(20mm), 검은 오픈박스(100×200×75mm), 밝은 흰색 평면 바닥.
> 실기 셋업과 동일한 pick&place 구도.

---

## B. 리더암 teleop 데이터 수집

리더암(`/dev/ttyLEADER`)으로 블록 씬을 조종하며, 가상 카메라 시점을 **rerun**으로 실시간
확인하면서 75ep을 수집했다.

### 결과 데이터셋

| 항목 | 값 |
|---|---|
| repo_id | `heongyu/sim_so101_blocktask` |
| 포맷 | LeRobot **v3.0** (recorder 기본, lerobot 0.4.3) |
| 에피소드 | **75ep** |
| 프레임 | 25,549 @ 30fps |
| 관측(state) / 행동(action) | 각 6-DoF float32 (SO-101 관절) |
| 카메라 | `ego`(wrist, 480×640) · `external_D455`(front, 480×640) |
| 언어 태스크 | 빨간 큐브 → 검은 박스 pick&place |

### 데이터셋 샘플 (한 에피소드 궤적: 접근 → 파지 → 이송)

**front (external_D455)** — 전역 시점:
![front 카메라 샘플 3프레임](assets/sample_front.jpg)

**wrist (ego)** — gripper 장착 시점:
![wrist 카메라 샘플 3프레임](assets/sample_ego.jpg)

> wrist 뷰에서 gripper 집게가 **정면(upright)** 으로 나오는 것은 관절 매핑 수정(§Phase B 상세)의
> 결과 — 실기 학습 데이터의 wrist 카메라 구도와 일치시킨 것.

---

## C. GR00T N1.6 8-bit 학습

### C.1 데이터 준비 — 왜 v3.0 → v2.1로 변환하는가

| 구분 | LeRobot **v3.0** (수집 원본) | LeRobot **v2.1** (GR00T 입력) |
|---|---|---|
| 생성 주체 | lerobot 0.4.3 recorder **기본 포맷** | GR00T N1.5/N1.6 학습 파이프라인이 **요구**하는 포맷 |
| 데이터 저장 | 에피소드들을 **consolidated parquet/mp4**로 묶음 | **에피소드별 개별 parquet/mp4** (`episode-XXXXXX`) |
| 메타 | `tasks.parquet` 등 신형 스키마 | 레거시 `episodes.jsonl` · `episodes_stats.jsonl` |

**변환이 필요한 이유**: GR00T 데이터 로더는 v2.1 스키마(에피소드별 파일 + 레거시 JSONL + `modality.json`)를
전제로 작성돼 있어, v3.0을 그대로 넣으면 로드되지 않는다. 그래서 학습 전 반드시 변환한다.

`setup/sim/t1_task/prepare_blocktask_gr00t.sh`가 수행하는 4단계:
1. **v3.0 → v2.1 변환** (`convert_v3_to_v2.py`): consolidated → 에피소드별 파일 복원, `_v3.0` 백업
2. **`modality.json` 배치**: 카메라 키 매핑 — **front ← external_D455**, **wrist ← ego**
   (GR00T가 카메라를 논리 이름으로 참조하므로 필수)
3. **`stats.json`의 count 제거**: GR00T 호환(count 필드가 있으면 로더가 거부)
4. 검증: `codebase_version: v2.1 | episodes: 75 | modality.json: True | stats count: False` ✅

변환 결과 위치(5090): `~/gr00tn16_ws/sim_data/heongyu/sim_so101_blocktask`

### C.2 학습 하이퍼파라미터

스크립트: `5090:~/gr00tn16_ws/train_gr00t_blocktask_n16_8bit.sh`
(vials로 sim SR 80% 달성한 `train_gr00t_sim_n16_8bit.sh`에서 데이터 경로·출력명만 교체)

| 항목 | 값 | 비고 |
|---|---|---|
| base-model | `nvidia/GR00T-N1.6-3B` | |
| optimizer | `paged_adamw_8bit` (bitsandbytes) | **단일 5090(32GB)** 학습 위해 8-bit |
| learning-rate | 1e-4 | |
| max-steps | 20,000 | |
| global-batch-size | 2 | |
| gradient-accumulation | 32 | 유효 배치 = 2 × 32 = **64** |
| num-gpus | 1 | RTX 5090 단일 |
| modality-config | `examples/SO100/so100_config.py` | front/wrist |
| embodiment-tag | `NEW_EMBODIMENT` | |
| 컨테이너 | `gr00t-train8` (bitsandbytes+8bit 이미지) | detached |
| 출력 | `~/gr00tn16_ws/checkpoints/gr00t_blocktask75_n16_8bit` | |

> **왜 8-bit Adam인가**: fp32 Adam optimizer state는 3B 모델에서 VRAM을 크게 잡아 로컬은 물론
> 5090 32GB에도 빠듯하다. `paged_adamw_8bit`로 optimizer state를 8-bit로 양자화해 단일 5090에서
> OOM 없이 학습(vials 검증 시 22.7GB). 성능은 fp32 대비 동등하거나 상회(vials sim SR 80%).

---

## D. 학습 지표 (학습 완주 후 채움) 🔲

### D.1 손실 함수 그래프

<!-- 학습 완주 후: docker logs에서 loss 파싱 → assets/loss_curve.png 생성 후 아래에 삽입 -->
> _학습 완주 후 손실 곡선 이미지를 여기에 삽입 (`assets/loss_curve.png`)_

### D.2 학습 지표 요약

| 지표 | 값 |
|---|---|
| 최종 loss | _(채움, 목표 ~0.005)_ |
| 총 step | 20,000 |
| 학습 시간 | _(채움)_ |
| 최대 GPU 사용 | _(채움, < 32GB)_ |
| 체크포인트 | `checkpoint-20000/` 무결성 _(채움)_ |

---

## E. 추론 결과 (Phase D — sim 평가 후 채움) 🔲

### E.1 sim 성공률

| 환경 | 시행 | 성공 | SR |
|---|---|---|---|
| T1-Eval (DR 없음) | 10 | | /10 |
| T1-DR-Eval | 10 | | /10 |

### E.2 추론 영상

<!-- sim 평가 시 --rerun 화면 녹화 또는 뷰포트 캡처 → assets/inference_*.mp4 / .gif -->
> _sim closed-loop 추론 영상(파지→이송→배치)을 여기에 삽입 (`assets/inference.gif` 등)_

---

*관련: [Phase 상세 A](A_scene_asset.md) · [B](B_data_collection.md) · [C](C_training.md) ·
계획 [08_custom_T1_sim2real.md](../08_custom_T1_sim2real.md) · 검증 파이프라인 [07_sim_to_real_gr00t.md](../07_sim_to_real_gr00t.md)*
