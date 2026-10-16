# manipulator_ws — 양팔 SO-ARM101 언어 지시 분류 (Bimanual Handoff Sorting)

영어 지시문 한 문장 `Put the {물체} into the {색} bin` 을 받으면, 양팔 SO-ARM101 이
**오른팔로 지시한 물체를 골라 집고 → 그리퍼끼리 왼팔에 건네고 → 왼팔이 지시한 색의 칸에 넣는다.**
문장 하나가 두 팔을 동시에 조건화한다 — 오른팔은 **물체 분류**, 왼팔은 **색 분류**를 맡는다.
모델은 NVIDIA **GR00T N1.6**(3B VLA)을 12관절·카메라 3대에 맞춰 미세조정한다.

> 📘 파이프라인을 다른 태스크에 다시 쓰려면 [PIPELINE.md](PIPELINE.md),
> 발표·일정은 [PRESENTATION.md](PRESENTATION.md), 스크립트 지도는 [setup/README.md](setup/README.md).

---

## 프로젝트 흐름 (P1 → P6)

sim 에서 **물체 하나를 상자 하나에** 넣는 것부터 시작해, 막힐 때마다 원인을 찾아 고치며 과제를 넓혔다.
각 단계의 결론이 다음 단계의 출발점이고, 최종 과제는 **P6 양팔 분류**다.

| 단계 | 한 일 | 막힌 것 → 다음 단계로 | 최종 모델 |
|---|---|---|---|
| **P1** sim 기본 | Isaac Sim 빨간 큐브 → 검은 상자. teleop 75ep, GR00T N1.6 8-bit 학습 | sim 60% — 큐브 위에서 맴돌며 못 집음 | blocktask75 |
| **P2** 데이터 개선·실기 전이 | 원인은 모델이 아니라 데이터(mat 높이·교정 시연 부재) → v2 로 sim 80%. 실기 zero-shot 은 배포 루프(청크 앵커 지연·앙상블 과평활) 문제 → W 조정 후 sim+실기 50ep co-training | 실기 10% → **90%**. "남은 gap 은 데이터로 메운다" 확인 | cotrain |
| **P3** 일반화 | 위치·박스 DR(v3) → 블록-상자 근접 보강(v4_200) → 평가 B 15조건, 실기 박스 다양화 co-training v4 | sim OOD 82.5%·실기 80%. 그러나 **지시문을 바꿔도 행동이 같음** — 학습 데이터 지시문이 1종이었음 | cotrain_v4 |
| **P4** 언어 조건화 (sim) | 같은 장면·다른 지시문으로 수집, 언어 프로브·대응쌍 평가 | 이어학습은 언어를 못 배움 → **파운데이션에서 새로** 학습해야 함 | blocktask_lang |
| **P5** 실기 분류 단일팔 | 4색 칸 선반·물체 10종, 실기만으로 80 → 250 → 370ep, 앙상블 W 스윕, 칸 위치 교체 검증 | **목적지 96.1% · 물체 90%**. white 를 확신 못 할 때 왼쪽으로 가는 편향 → 칸 배치를 바꿔 가며 수집해야 함 | cleanup_real v3 |
| **P6** 실기 분류 양팔 | 오른팔 물체 분류 → 전달 → 왼팔 색 분류. 50ep 마다 칸 배치 교체 | 151ep: 전달 92%, 물체·목적지는 우연 수준 → **300ep 학습 중** | bi_cleanup 300ep |

| 단계 | 문서 | 코드 |
|---|---|---|
| P1 | [plan.md](manipulator_md/p1_p2_sim_t1/plan.md) · [p1_p2_sim_t1/](manipulator_md/p1_p2_sim_t1/README.md) A~D · [deploy.md](manipulator_md/p1_p2_sim_t1/deploy.md)(sim 수집 환경 재현) | [setup/p1_p4_sim/t1_task/](setup/p1_p4_sim/t1_task/README.md) P1·P2 |
| P2 | [report2.md](manipulator_md/p1_p2_sim_t1/report2.md) · [E_sim2real_transfer.md](manipulator_md/p1_p2_sim_t1/E_sim2real_transfer.md) · [F_realdata_prep.md](manipulator_md/p1_p2_sim_t1/F_realdata_prep.md) | 위 + `setup/gr00t/` 서빙·추론 클라이언트·카메라 정렬 |
| P3 | [p3_generalization/README.md](manipulator_md/p3_generalization/README.md) · [2week_plan.md](manipulator_md/p3_generalization/2week_plan.md) · [sim2real_generalization_report.md](manipulator_md/p3_generalization/sim2real_generalization_report.md) · [datasets.md](manipulator_md/p3_generalization/datasets.md) | `setup/p1_p4_sim/t1_task/` P3 + `setup/gr00t/run_eval_real.sh` 등 |
| P4 | [language_conditioning_sim_plan.md](manipulator_md/p4_language_sim/language_conditioning_sim_plan.md) · [language_conditioning_execution_log.md](manipulator_md/p4_language_sim/language_conditioning_execution_log.md) | `setup/p1_p4_sim/t1_task/` P4 + `setup/gr00t/probe_language.py` |
| P5 | [collection_environment.md](manipulator_md/p5_real_cleanup/collection_environment.md) · [v3_plan.md](manipulator_md/p5_real_cleanup/v3_plan.md) · [v4_plan.md](manipulator_md/p5_real_cleanup/v4_plan.md) | `setup/p5_real_cleanup/` |
| **P6** | [bi_manipulator_plan.md](manipulator_md/p6_real_bimanual/bi_manipulator_plan.md) | `setup/p6_real_bimanual/` |

> 정리하며 지운 과거 파일(모델 비교, 중간 계획 등)은 태그 `pre-cleanup` 에서
> `git checkout pre-cleanup -- <경로>` 로 되살릴 수 있다.

---

## 과제 정의

### 한 시행의 흐름

```
지시문 "Put the {물체} into the {색} bin"
   │
   ├─ ① 오른팔 — 물체 분류: 테이블 위 1~4개 중 지시한 물체를 골라 집는다
   ├─ ② 전달   — 오른팔이 들고 와 왼팔 그리퍼에 직접 건넨다 (왼팔이 쥔 뒤 오른팔이 놓는다)
   ├─ ③ 왼팔   — 색 분류: 2×2 칸 중 지시한 색의 칸에 넣는다
   └─ ④ 양팔이 rest 로 돌아와 멈추면 종료
```

평가는 세 단계를 **따로** 기록한다 — ① 지시한 물체를 집었나 · ② 전달했나 · ③ 지시한 칸에 넣었나.
뭉쳐서 "성공/실패"로만 적으면 어느 단계가 약한지 가를 수 없다.

### 물체와 칸

| 구분 | 구성 | 비고 |
|---|---|---|
| 물체 (8종) | red marker · blue marker · black marker · yellow straw · glue stick · toothbrush · eraser · screwdriver | 한 시행에 1~4개. eraser 는 세워서 놓는다 |
| 칸 (4색) | black · cyan · pink · white — 2×2 보관함 | **50ep 마다 색 배치를 바꿔** 수집 (색 ↔ 위치 결합을 끊기 위해, P5 교훈) |
| 지시문 | `Put the {물체} into the {색} bin` | 8 × 4 = 32종 |

---

## 작업 환경

### 머신 구성 (2대 분리)

| 머신 | GPU | 역할 |
|---|---|---|
| **로컬** | RTX 5070 Ti (16GB) | 리더암 teleop **수집**, 실기 로봇 제어, **추론 서빙** |
| **원격 5090** | RTX 5090 (32GB) | GR00T **학습**, Isaac Sim 무인 평가(P1~P4) |

> 리더암·로봇이 로컬에 물려 있어 수집과 실기는 로컬에서만 하고, 16GB 로는 학습이 안 돼 학습은 5090 전용이다.
> 실기 추론은 로컬 서빙(`serve_local.sh`)이 기본 — 원격(WiFi)보다 지연이 낮고 안정적이다.

### 하드웨어

| 장비 | 사양 | 용도 |
|---|---|---|
| **팔로워** | SO-ARM101 ×2 (각 6-DOF + 그리퍼) | 오른팔 = 집기·전달, 왼팔 = 받기·넣기. 상태·행동 12차원 |
| **리더** | SO-ARM101 ×2 | 양팔 teleop 시연 |
| **카메라** | USB ×3 — top · 왼손목 · 오른손목 | 640×480 MJPG |
| **보관함** | 2×2 칸 (black · cyan · pink · white) | 왼팔 쪽 |

### 소프트웨어 스택

| 레이어 | 기술 | 비고 |
|---|---|---|
| **VLA 모델** | GR00T N1.6 (3B) | 파운데이션에서 새로 미세조정, `paged_adamw_8bit` |
| **양팔 설정** | `bi_so100_config.py` · `modality.json` | left/right arm·gripper 4그룹, 영상 top·wrist_left·wrist_right |
| **로봇 제어·수집** | lerobot 0.4.4 (`bi_so_follower`) | LeRobot v3.0 으로 수집 → GR00T v2.1 로 변환해 학습 |
| **시뮬레이터** | Isaac Sim / Isaac Lab 2.3.2 | P1~P4 단계에서 사용 |
| **런타임** | Python 3.10 + PyTorch 2.10 (cu128) | 로봇 제어 env. 서빙 이미지(real-robot)는 torch 2.8.0 고정 |

### 물리적 작업 공간

> 📐 **다이어그램 다시 작성 예정** — 두 팔의 배치, 물체 영역(오른팔 쪽), 2×2 보관함(왼팔 쪽),
> 전달 위치, 카메라 3대의 위치와 화각을 한 장에.

---

## 시스템 아키텍처

> 📐 **블록도 다시 작성 예정** — 아래 두 흐름을 그린다. 편집 보드: [Figma](https://www.figma.com/board/4iKjT0Ngfm8IKmiFttKaKc)

### 추론(배포) 흐름

로컬 한 대에서 끝난다. 카메라 3장 + 두 팔의 관절 상태(12차원) + 지시문이 GR00T 정책 서버로 가고,
서버가 돌려준 16-step 행동 청크를 클라이언트가 시간 앙상블로 다듬어 두 팔에 보낸다.
양팔이 rest 근처에서 멈추면 종료하고, 어떤 이유로 끝나든 그 자리에 멈춘 뒤 천천히 rest 로 돌아간다.

### 학습 흐름

로컬에서 계획표 순서대로 양팔 시연을 모으고(검증·전달 검사 포함), 5090 으로 보내 v2.1 로 변환한 뒤
파운데이션 N1.6-3B 에서 epoch 기준(현재 10 epoch)으로 학습한다. 체크포인트는 로컬로 받아 서빙한다.

---

## 데이터 흐름

### 추론 시

| From → To | 데이터 | 내용 | 전송 |
|---|---|---|---|
| 카메라 ×3 → 클라이언트 | RGB 480×640×3 ×3 | top · wrist_left · wrist_right | USB → OpenCV |
| 팔로워 ×2 → 클라이언트 | 관절 각도 12 | left/right arm(5) + gripper(1) | 시리얼 (USB) |
| 클라이언트 → 서버 | 영상(JPEG) + 상태 + 지시문 | 추론 요청 | ZMQ tcp:5555 |
| 서버 → 클라이언트 | 행동 청크 16 step × 12 | 다음 동작 | ZMQ tcp:5555 |
| 클라이언트 → 팔로워 ×2 | 관절 목표 12 | 앙상블된 명령 | 시리얼 (USB) |

### 학습 시

| From → To | 데이터 | 내용 | 방식 |
|---|---|---|---|
| 리더 ×2 + 팔로워 ×2 → LeRobot | 관절 12 + RGB ×3 | 양팔 시연 에피소드 | LeRobot v3.0 |
| v3.0 → v2.1 변환 | parquet + mp4 | GR00T 호환 포맷, 지시문 32종·4색·카메라 3대 검사 | `prepare_bi_cleanup.sh` (5090) |
| 변환 데이터 → 학습 | v2.1 데이터셋 | 프레임 단위로 섞어 학습 | 5090 |
| 학습 → 서빙 | 체크포인트 | 로컬로 받아 `serve_local.sh` | rsync |

---

## 프로젝트 구조

```
manipulator_ws/
├─ README.md · PIPELINE.md · PRESENTATION.md   # 개요 · 파이프라인 해부(S1~S7) · 발표 자료
├─ docs/
│  ├─ diagrams/                # 아키텍처 다이어그램 (다시 작성 예정, 편집은 Figma)
│  └─ figures/                 # 결과 그림·영상 (PRESENTATION.md 등에서 사용)
├─ manipulator_md/             # 진행 기록 — 프로젝트 흐름 단계별
│  ├─ STATUS.md                #   전체 진행 현황
│  ├─ p1_p2_sim_t1/            #   P1·P2 sim T1 → 실기 co-training (plan · A~F · report · report2 · deploy.md)
│  ├─ p3_generalization/       #   P3 sim 일반화·co-training v4
│  ├─ p4_language_sim/         #   P4 sim 언어 조건화
│  ├─ p5_real_cleanup/         #   P5 실기 분류 단일팔
│  └─ p6_real_bimanual/        #   P6 실기 분류 양팔 (계획, 수집·평가 계획표, 평가 결과)
├─ setup/                      # 재현용 스크립트 — 단계별 지도는 setup/README.md
│  ├─ hardware/                # [공통] udev rules, 장치 식별, 카메라 점검, teleop
│  ├─ gr00t/                   # [공통] GR00T 서빙·실기 추론 클라이언트·카메라 정렬
│  ├─ p1_p4_sim/               # P1~P4 Isaac Sim T1
│  ├─ p5_real_cleanup/         # P5 실기 분류 단일팔
│  └─ p6_real_bimanual/        # P6 실기 분류 양팔: data/(계획표·수집·전달 검사·평가) · gr00t/(설정·학습·추론)
├─ envs/
│  └─ lerobot/                 # uv 프로젝트 (lerobot 0.4.4 + torch 2.10 cu128). GR00T 는 도커 이미지에서 실행
├─ inf_video/                  # (git 제외) 단계별 최종 모델의 추론 영상·chunks/actions.csv·run.json
│  ├─ 10_eval_lang_*/          #   P4 sim 언어 평가
│  ├─ 07_real_eval/            #   P5 단일팔
│  └─ 07_real_eval_bi/         #   P6 양팔
└─ logs/                       # (git 제외) P3 실기 평가 기록
```

---

## 환경 재현

```bash
# 1. uv 설치
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. 의존성 설치 (Python 3.10 자동 고정)
cd envs/lerobot && uv sync

# 3. udev rules 설치 (장치 경로 고정 — 팔 4대·카메라 3대)
setup/hardware/identify_devices.sh               # 연결된 장치의 식별 정보 확인 → rules 에 채움
sudo cp setup/hardware/99-lerobot.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger

# 4. 시스템 의존성
sudo apt install ffmpeg   # torchcodec(학습 영상 디코딩) 필수

# 5. 서빙 이미지 (로컬, 최초 1회)
cd ~/blocktask_ws/Sim-to-Real-SO-101-Workshop && ./docker/real/build.sh blackwell

# 6. sim 데이터 수집 환경 (P1~P4 재현할 때만) — manipulator_md/p1_p2_sim_t1/deploy.md
```

## 실행 — 양팔 분류 (P6)

학습은 5090, 수집·추론은 로컬에서 한다. 5090 쪽 스크립트(`train_*.sh`)는 5090 작업 폴더에 복사해서 실행한다.
각 스크립트 머리말에 옵션과 이유가 있다.

```bash
cd setup/p6_real_bimanual/data
python3 gen_bi_plan.py --episodes 300 --layout-every 50   # 계획표 (50ep마다 칸 색 배치 교체)
./record_bi.sh                                # 오른팔 집기 → 전달 → 왼팔 넣기 시연 (중단 후 재실행하면 이어서)
(cd ../../../envs/lerobot && uv run python ../../setup/p6_real_bimanual/data/handoff_events.py --report <데이터셋 경로>)  # 전달 성공·시점 검사
./prepare_bi_cleanup.sh all                   # 5090 전송 → 변환 → 검사(지시문 32종·4색·카메라 3대)
#  (5090) SMOKE=1 ./train_bi_cleanup.sh 로 먼저 확인 → EPOCHS=10 OUT_NAME=<이름> ./train_bi_cleanup.sh

cd ../../gr00t && ./serve_local.sh <모델>/checkpoint-<step>
cd ../p6_real_bimanual/data
python3 cleanup_eval_bi.py log --eval-name <이름> --out <결과.csv> --rerun     # 평가 A (36시행)
python3 cleanup_eval_bi.py report --out <결과.csv>
#  평가 B (학습에 없던 칸 배치 포함 60시행): --plan ~/manipulator_ws/manipulator_md/p6_real_bimanual/bi_cleanup_eval_plan_B.csv
```

- 추론 중 `q` 한 번으로 그 시행을 끝내고 결과 입력으로 넘어간다. 어떤 이유로 끝나든 팔은 그 자리에 멈춘 뒤 천천히 rest 로 돌아가고 토크를 유지한다.
- 원격(5090) 서버를 쓸 때는 `SERVER_HOST=<5090 IP>` 를 앞에 붙인다.

### 이전 단계 재현 — 단일팔 분류 (P5)

```bash
cd setup/p5_real_cleanup
./check_setup.sh cams                         # 선반·카메라 화각 점검 (teleop 모드로 리치 확인)
python3 gen_real_lang_plan.py                 # 수집 계획표 (물체·지시문·칸)
./record_real_lang.sh                         # 계획표 순서대로 수집
./prepare_cleanup_real.sh all                 # 5090 전송 → v2.1 변환 → 지시문 수 게이트
#  (5090) EPOCHS=8 ./train_cleanup_real.sh
cd ../gr00t && ./serve_local.sh gr00t_cleanup_real_n16_8bit/checkpoint-30000
cd ../p5_real_cleanup && python3 cleanup_eval.py log && python3 cleanup_eval.py report
```

## 데이터·모델

데이터셋과 체크포인트는 용량 때문에 저장소에 넣지 않았다.
데이터셋은 로컬 `~/blocktask_ws/Sim-to-Real-SO-101-Workshop/datasets/_train/` 에, 체크포인트는 `~/gr00tn16_ws/checkpoints/` (로컬·5090) 에 있다.

| 데이터셋 | 규모 | 모델 (checkpoint) |
|---|---|---|
| **`bi_cleanup` (양팔, P6)** | 300ep · 331,455 frames · 지시문 32종 · 칸 배치 6종 | `gr00t_bi_cleanup151_n16_8bit` (151ep, checkpoint-28000) · **`gr00t_bi_cleanup300_n16_8bit`** (300ep, 학습 중) |
| `cleanup_real` (단일팔, P5) | 370ep · 지시문 40종 | `gr00t_cleanup_real_n16_8bit` (checkpoint-30000, v3) |
| `sim_so101_blocktask_v4_200` + `..._real_v2_57` (T1, P3) | sim 200ep + 실기 57ep | `gr00t_blocktask_cotrain_v4_n16_8bit` (checkpoint-48000) |

## 주의사항

- 카메라 설정에 **반드시 `fourcc: MJPG`** — YUYV는 USB 대역폭 포화로 영상 깨짐 (카메라 3대면 더 민감)
- RTX 5070 Ti(Blackwell sm_120)는 CUDA 12.8+ / torch 2.10+cu128 필요 (lerobot env 기준)
- **서빙 이미지(real-robot) 빌드 재현성**: `Dockerfile.blackwell`은 torch==2.8.0+cu128 + flash-attn 2.8.3 **사전 wheel**로 고정됨
- 카메라·팔 udev rule은 물리 포트 기준 — USB 포트 이동 시 rule 수정 필요
- **캘리브레이션 지문**: 수집 도중 캘리브레이션이 바뀌면 데이터가 섞인다 — `calib_fingerprint.py --check` 로 수집 전후 대조
- **홈 자세·토크**: 추론 시작 자세는 `home_pose_bi.py`(300ep 첫 프레임 중앙값). 토크를 끄면 오른팔 elbow 가 처져 시작 자세가 어긋난다
- **데이터 포맷**: 수집은 LeRobot v3.0, 학습은 v2.1 — 변환 후 지시문 수 검사가 1종으로 접혔으면 학습하지 않는다
- **영상 코덱**: 평가 영상은 `mpeg4`로 저장돼 웹(Notion 등)에서 재생 불가 —
  업로드 전 `ffmpeg -c:v libx264 -pix_fmt yuv420p -movflags +faststart`로 변환
- **run.json이 근거**: 어떤 모델·지시문·설정으로 돌렸는지는 각 결과 디렉터리의 `run.json`으로 증명한다
