# manipulator_ws — 🧹 "말하면 치우는 로봇" Language-Guided Tabletop Cleanup

음성 명령(STT)을 통해 자연어 지시를 내리면, SO-ARM101 로봇이 테이블 위의
물체(펜, 지우개, 매직, 큐브 등)를 속성별로 분류하여 지정된 박스에 정리하고,
작업 상태를 음성(TTS)으로 피드백하는 **sim2real 파이프라인 프로젝트**.

> **핵심 시나리오**: 사용자가 _"빨간 물건은 왼쪽 상자에, 파란 물건은 오른쪽 상자에 넣어줘"_ 라고
> 말하면 로봇이 해당 물체만 골라 분류하고, 완료 시 _"정리가 완료되었습니다"_ 라고 응답합니다.

> **기반**: 2주 계획에서 확보한 **단일 빨간 큐브(20mm) → 검은 상자 pick-and-place** 파이프라인
> (sim SR ≥ 80%, OOD SR ≥ 70%)을 **다물체 + 언어 조건부 분류 + 음성 인터페이스**로 확장합니다.

> 📘 **파이프라인을 그대로 다른 태스크에 돌리려면**: [PIPELINE.md](PIPELINE.md)
> — 씬 정의부터 실기 평가까지 7단계를, **태스크에 종속된 부분 / 재사용되는 부분**으로 갈라 정리했다.

## 프로젝트 흐름 (P1 → P6)

sim 에서 **물체 하나를 상자 하나에** 넣는 것부터 시작해, 막힐 때마다 원인을 찾아 고치며 과제를 넓혔다.
각 단계의 결론이 다음 단계의 출발점이다.

| 단계 | 한 일 | 막힌 것 → 다음 단계로 | 최종 모델 |
|---|---|---|---|
| **P1** sim 기본 | Isaac Sim 빨간 큐브 → 검은 상자. teleop 75ep, GR00T N1.6 8-bit 학습 | sim 60% — 큐브 위에서 맴돌며 못 집음 | blocktask75 |
| **P2** 데이터 개선·실기 전이 | 원인은 모델이 아니라 데이터(mat 높이·교정 시연 부재) → v2 로 sim 80%. 실기 zero-shot 은 배포 루프(청크 앵커 지연·앙상블 과평활) 문제 → W 조정 후 sim+실기 50ep co-training | 실기 10% → **90%**. "남은 gap 은 데이터로 메운다" 확인 | cotrain |
| **P3** 일반화 | 위치·박스 DR(v3) → 블록-상자 근접 보강(v4_200) → 평가 B 15조건, 실기 박스 다양화 co-training v4 | sim OOD 82.5%·실기 80%. 그러나 **지시문을 바꿔도 행동이 같음** — 학습 데이터 지시문이 1종이었음 | cotrain_v4 |
| **P4** 언어 조건화 (sim) | 같은 장면·다른 지시문으로 수집, 언어 프로브·대응쌍 평가 | 이어학습은 언어를 못 배움 → **파운데이션에서 새로** 학습해야 함 | blocktask_lang |
| **P5** 실기 cleanup 단일팔 | 4색 칸 선반·물체 10종, 실기만으로 80 → 250 → 370ep, 앙상블 W 스윕, 칸 위치 교체 검증 | **목적지 96.1% · 물체 90%**. white 를 확신 못 할 때 왼쪽으로 가는 편향 → 칸 배치를 바꿔 가며 수집해야 함 | cleanup_real v3 |
| **P6** 실기 cleanup 양팔 | 오른팔 집기 → 그리퍼 간 전달 → 왼팔 넣기. 50ep 마다 칸 배치 교체 | 151ep: 전달 92%, 물체·목적지는 우연 수준 → **300ep 학습 중** | bi_cleanup 300ep |

| 단계 | 문서 | 코드 |
|---|---|---|
| P1 | [03_custom_T1_sim2real.md](manipulator_md/sim2real/03_custom_T1_sim2real.md) · [08_T1_sim2real/](manipulator_md/sim2real/08_T1_sim2real/README.md) A~D · [deploy.md](manipulator_md/sim2real/08_T1_sim2real/deploy.md)(수집 환경 재현) | [setup/sim/t1_task/](setup/sim/t1_task/README.md) P1·P2 |
| P2 | [report2.md](manipulator_md/sim2real/08_T1_sim2real/report2.md) · [E_sim2real_transfer.md](manipulator_md/sim2real/08_T1_sim2real/E_sim2real_transfer.md) · [F_realdata_prep.md](manipulator_md/sim2real/08_T1_sim2real/F_realdata_prep.md) | 위 + `setup/gr00t/` 서빙·추론 클라이언트·카메라 정렬 |
| P3 | [sim/README.md](manipulator_md/sim/README.md) · [2week_plan.md](manipulator_md/sim/2week_plan.md) · [sim2real_generalization_report.md](manipulator_md/sim/sim2real_generalization_report.md) · [datasets.md](manipulator_md/sim/datasets.md) | `setup/sim/t1_task/` P3 + `setup/gr00t/run_eval_real.sh` 등 |
| P4 | [language_conditioning_sim_plan.md](manipulator_md/sim/language_conditioning_sim_plan.md) · [language_conditioning_execution_log.md](manipulator_md/sim/language_conditioning_execution_log.md) | `setup/sim/t1_task/` P4 + `setup/gr00t/probe_language.py` |
| P5 | [collection_environment.md](manipulator_md/real/collection_environment.md) · [v3_plan.md](manipulator_md/real/v3_plan.md) · [v4_plan.md](manipulator_md/real/v4_plan.md) · [PRESENTATION.md](PRESENTATION.md) | `setup/data/` |
| P6 | [bi_manipulator_plan.md](manipulator_md/real/bi_manipulator_plan.md) | `setup/bi/` |

> 음성 입력(STT)·피드백(TTS)은 아직 하지 않았다. 아래 "핵심 시나리오"와 Phase 2 그림은 처음 세운 계획이고,
> 실제로는 상자 2개 대신 **색 칸 4개 선반**, 음성 대신 **영어 지시문**(`Put the {물체} into the {색} bin`)으로 구현했다.
> 정리하며 지운 과거 파일(모델 비교, 중간 계획 등)은 태그 `pre-cleanup` 에서 `git checkout pre-cleanup -- <경로>` 로 되살릴 수 있다.

---

## 프로젝트 개요

### 목표
GR00T N1.6 VLA(Vision-Language-Action)의 비전-언어-행동 통합 능력을 활용하여,
**다물체 + 언어 조건부 분류**를 sim2real 파이프라인으로 구현한다.

### 확장 경로

<a href="docs/diagrams/D5_phase_roadmap.png"><img src="docs/diagrams/D5_phase_roadmap.png" width="600" alt="D5 확장 경로 Phase 1 → Phase 2"></a>

<sub>클릭하면 원본 크기 · 📐 편집: [Figma — D5 확장 경로 Phase 1 → Phase 2](https://www.figma.com/board/4iKjT0Ngfm8IKmiFttKaKc?node-id=5-177)</sub>

```
Phase 1 (완료)                          Phase 2 (현재)
─────────────────────────              ─────────────────────────
단일 빨간 큐브 → 검은 상자              다물체(펜/지우개/매직/큐브)
고정 지시문 1종                     →   가변 지시문 (음성 입력)
1회 pick-place                          N회 순차 pick-place
sim-only → co-training                  음성 양방향 (STT+TTS)
```

### 대상 물체
| 물체 | 형태 | 비고 |
|---|---|---|
| 펜 | 원통형(가늘고 긴) | 그립 난이도 높음 |
| 지우개 | 직육면체(소형) | 표준 pick 대상 |
| 매직(마커) | 원통형(중간) | 펜보다 굵음 |
| 큐브 | 정육면체(3cm) | Phase 1 기본 대상 |
| 원통 | 원기둥(2.5×4cm) | 형상 분류용 |

> ⚠️ **Phase 1 실측 경고**: sim 평가 B에서 정책이 **물체 기하에 그리퍼를 맞추지 못함**이 확인됨
> (28mm 큐브 2/10, 지우개 40×20×12mm 4/10 — 긴 변이 턱 사이에 오면 실패).
> Phase 2 대상(펜·매직·지우개)이 정확히 이 축이므로, **크기·형상 다양성 수집이 전제 조건**이다.

---

## 작업 환경

> 📐 **작업 환경 다이어그램**: [Figma — D8 물리적 작업 공간](https://www.figma.com/board/4iKjT0Ngfm8IKmiFttKaKc?node-id=9-270)

### 머신 구성 (2대 분리)

| 머신 | GPU | 역할 |
|---|---|---|
| **로컬** | RTX 5070 Ti (sm_120) | 리더암 teleop **데이터 수집**, 실기 로봇 제어, 씬 검증, **로컬 서빙(선택)** |
| **원격 (5090)** | RTX 5090 | GR00T **학습**, Isaac Sim **평가**, 모델 **서빙** |

> 두 머신 간 통신은 SSH + rsync. 실기 추론은 **5090 원격 서빙** 또는 **로컬 서빙**
> (`serve_local.sh`, real-robot 이미지 로컬 빌드) 둘 다 가능.
> 실측: 로컬 서빙이 추론 지연 중앙 **73ms**로 원격(115~171ms, 지터 최대 824ms)보다
> 낮고 안정적이다. 로컬 서빙 시 5090은 학습 전용으로 쓸 수 있다.

### 하드웨어 (로컬)

| 장비 | 사양 | 용도 |
|---|---|---|
| **로봇** | SO-ARM101 (6-DOF + 그리퍼) | 매니퓰레이션 실행 (팔로워) |
| **리더암** | SO-ARM101 (리더) | Teleop 시연 데이터 수집 |
| **카메라** | USB 카메라 ×2 (top + wrist) | 시각 입력 (640×480, MJPG 필수) |
| **양팔 구성** | 팔로워 ×2 · 리더 ×2 · 카메라 ×3 (top + 왼손목 + 오른손목) | 양팔 cleanup (`setup/bi/`) — 12관절 |
| **마이크** | USB 마이크 | STT 음성 입력 (Phase 2 신규) |
| **스피커** | 3.5mm / USB 스피커 | TTS 음성 출력 (Phase 2 신규) |

### 소프트웨어 스택

| 레이어 | 기술 | 버전/비고 |
|---|---|---|
| **시뮬레이션** | Isaac Sim / Isaac Lab | 2.3.2, `teleop-docker` 컨테이너 |
| **VLA 모델** | GR00T N1.6 (3B, 8-bit) | `paged_adamw_8bit`(옵티마이저 상태만 8-bit), cosine LR |
| **데이터 수집** | LeRobot | v3.0 포맷으로 수집 |
| **학습 데이터** | GR00T 파이프라인 | v2.1 포맷으로 변환 후 학습 |
| **STT** | Whisper (medium) | OpenAI Whisper (Phase 2 신규) |
| **TTS** | gTTS / Piper | Phase 2 신규 |
| **로봇 제어** | lerobot 0.4.4 | HuggingFace, uv 관리 |
| **런타임** | Python 3.10 + PyTorch 2.10 (cu128) | 로봇 제어 env 기준. **서빙 이미지(real-robot)는 torch 2.8.0 고정** |

### 물리적 작업 공간 (Phase 2)

<a href="docs/diagrams/D8_workspace.png"><img src="docs/diagrams/D8_workspace.png" width="640" alt="D8 물리적 작업 공간"></a>

<sub>클릭하면 원본 크기 · 📐 편집: [Figma — D8 물리적 작업 공간](https://www.figma.com/board/4iKjT0Ngfm8IKmiFttKaKc?node-id=9-270)</sub>

```
┌───────────────────────────────────────────┐
│                 테이블 (60×40cm)            │
│                                           │
│   📦 LEFT BOX           📦 RIGHT BOX     │
│   (왼쪽 상자)            (오른쪽 상자)      │
│                                           │
│      🖊️ 펜    ✏️ 지우개                    │
│          🖍️ 매직    🟥 큐브    🖊️ 펜       │
│   (물체 3~5개, 위치 랜덤 배치)              │
│                                           │
│   📷 top cam                              │
│              🤖 SO-101 (팔로워)            │
│                 📷 wrist cam              │
│   🎤 마이크       🤖 리더암    🔊 스피커    │
└───────────────────────────────────────────┘
```

---

## 시스템 아키텍처

> 📐 **시스템 아키텍처 블록 다이어그램**: [Figma — D3 추론 파이프라인](https://www.figma.com/board/4iKjT0Ngfm8IKmiFttKaKc?node-id=41-476) · [D2 학습 파이프라인](https://www.figma.com/board/4iKjT0Ngfm8IKmiFttKaKc?node-id=2-50)

### 추론(배포) 파이프라인

<a href="docs/diagrams/D3_infer_pipeline.png"><img src="docs/diagrams/D3_infer_pipeline.png" width="880" alt="D3 추론(배포) 파이프라인"></a>

<sub>클릭하면 원본 크기 · 📐 편집: [Figma — D3 추론(배포) 파이프라인](https://www.figma.com/board/4iKjT0Ngfm8IKmiFttKaKc?node-id=41-476)</sub>

```
┌─ 로컬 머신 (RTX 5070 Ti) ──────────────────────────────────┐
│                                                             │
│  [🎤 마이크] → [STT: Whisper] → 텍스트 지시문                │
│               "빨간 펜을 왼쪽 상자에 넣어줘"                  │
│                         │                                   │
│                         ▼                                   │
│               [지시문 → 영어 변환]                            │
│               "Pick up the red pen and place it             │
│                in the left box"                             │
│                         │                                   │
│  [📷 top cam] ──┐       │                                   │
│  [📷 wrist cam]─┤       │                                   │
│                 ▼       ▼                                   │
│  ┌──────────────────────────────┐                           │
│  │ GR00T 클라이언트              │                           │
│  │ (client/eval_lerobot.py)     │ ← 이미지 + 언어 지시       │
│  │ → 서빙 서버 (로컬/5090)       │ → 16-step 행동 시퀀스       │
│  └──────────────┬───────────────┘                           │
│                 ▼                                           │
│  [🦾 SO-101 팔로워] → 관절 제어 (모터 드라이버)               │
│                 │                                           │
│                 ▼                                           │
│  [📊 완료 판정] → [상태 메시지 생성]                          │
│                         │                                   │
│                         ▼                                   │
│  [🔊 스피커] ← [TTS: gTTS/Piper]                             │
│              "빨간 펜 정리 완료"                               │
└─────────────────────────────────────────────────────────────┘

┌─ 서빙 (택 1) ──────────────────────────────┐
│  로컬:  serve_local.sh (5070 Ti, 73ms)      │
│  원격:  serve_blocktask_n16_5090.sh (5090)  │
│  이미지+언어 → 행동 시퀀스 반환                │
└────────────────────────────────────────────┘
```

### 학습 파이프라인

<a href="docs/diagrams/D2_train_pipeline.png"><img src="docs/diagrams/D2_train_pipeline.png" width="620" alt="D2 학습 파이프라인 (머신 경계)"></a>

<sub>클릭하면 원본 크기 · 📐 편집: [Figma — D2 학습 파이프라인 (머신 경계)](https://www.figma.com/board/4iKjT0Ngfm8IKmiFttKaKc?node-id=2-50)</sub>

```
┌─ 로컬 (수집) ──────────────────────────────────────────────┐
│                                                            │
│  [리더암] → [팔로워(SO-101)] + [📷×2]                       │
│     teleop 시연                                            │
│         │                                                  │
│         ▼                                                  │
│  [LeRobot v3.0 수집]                                       │
│  datasets/sim_so101_blocktask_*/                           │
│         │                                                  │
│         ▼ rsync                                            │
└─────────┬──────────────────────────────────────────────────┘
          │
┌─────────▼──── 원격 5090 (학습) ────────────────────────────┐
│                                                            │
│  [v3.0 → v2.1 변환]                                        │
│  datasets/_train/<버전>/                                    │
│         │                                                  │
│         ▼                                                  │
│  [GR00T N1.6 학습]                                         │
│  3B, 8-bit, paged_adamw                                    │
│  cosine LR, color jitter                                   │
│         │                                                  │
│         ▼                                                  │
│  [Isaac Sim 평가]                                           │
│  teleop-docker 컨테이너                                     │
│  headless 무인 평가 + scenes.csv                            │
└────────────────────────────────────────────────────────────┘
```

### sim2real 전이 흐름 (Phase 1 실측 기반)

<a href="docs/diagrams/D4_sim2real_flow.png"><img src="docs/diagrams/D4_sim2real_flow.png" width="820" alt="D4 sim2real 전이 흐름"></a>

<sub>클릭하면 원본 크기 · 📐 편집: [Figma — D4 sim2real 전이 흐름](https://www.figma.com/board/4iKjT0Ngfm8IKmiFttKaKc?node-id=4-138)</sub>

```
[sim 학습]  ──→  [sim 평가: SR≥80%, OOD≥70%]
                         │
                         ▼
              [실기 zero-shot 테스트]
              (Phase 1 실측: SR 0% — 고정자세 붕괴)
                         │
                         ▼
              [co-training: sim + 실기 데이터]
              (Phase 1 실측: v4 co-train → 실기 80%, n=5)
                         │
                         ▼
              [실기 배포 + 음성 통합]
```

> **Phase 1 교훈**: sim-only 모델의 zero-shot은 기대하지 않는다.
> sim에서 일반화를 확보하는 목적은 **co-training의 출발점을 좋게 만드는 것**이다.

---

## 데이터 흐름 (블록 간 전송)

> 📐 **상세 데이터 흐름도**: [Figma — D3 추론 파이프라인](https://www.figma.com/board/4iKjT0Ngfm8IKmiFttKaKc?node-id=41-476) · [D2 학습 파이프라인](https://www.figma.com/board/4iKjT0Ngfm8IKmiFttKaKc?node-id=2-50)

### 추론 시 데이터 흐름

| From → To | 데이터 형식 | 내용 | 전송 방식 |
|---|---|---|---|
| 마이크 → STT | PCM audio (16kHz, mono) | 사용자 음성 원본 | PyAudio stream |
| STT → 지시문 변환 | `str` (한국어 텍스트) | `"빨간 펜을 왼쪽 상자에 넣어줘"` | 함수 호출 |
| 지시문 변환 → GR00T 클라이언트 | `str` (영어 지시문) | `"Pick up the red pen and place it in the left box"` | 함수 호출 |
| 카메라 ×2 → GR00T 클라이언트 | `ndarray` (RGB 480×640×3) ×2 | top cam + wrist cam 프레임 | USB → OpenCV |
| GR00T 클라이언트 → 서빙 | 이미지(JPEG 직렬화) + 언어 지시 | 추론 요청 | ZMQ tcp:5555 (로컬/원격) |
| 서빙 → 클라이언트 | `ndarray` (관절 각도, 16-step chunk) | 행동 시퀀스 | ZMQ tcp:5555 |
| 클라이언트 → SO-101 | 관절 각도 명령 | 모터 제어 | 시리얼 (USB) |
| 완료 판정 → TTS | `str` (상태 메시지) | `"빨간 펜 정리 완료"` | 함수 호출 |
| TTS → 스피커 | PCM audio | 합성된 음성 | PyAudio / ALSA |

### 학습 시 데이터 흐름

| From → To | 데이터 형식 | 내용 | 전송 방식 |
|---|---|---|---|
| 리더암 + 팔로워 → LeRobot | 관절 각도 + RGB ×2 | teleop 시연 에피소드 | LeRobot v3.0 |
| LeRobot v3.0 → v2.1 변환 | parquet + mp4 | 포맷 변환 (GR00T 호환) | 변환 스크립트 |
| 변환 데이터 → GR00T 학습 | v2.1 데이터셋 | `ShardedMixtureDataset` | 로컬 디스크 (5090) |
| 학습 → 체크포인트 | 모델 가중치 | checkpoint-{steps} | 5090 로컬 저장 |
| 체크포인트 → 서빙 | 모델 로드 | 추론 서버 기동 | 셸 스크립트 (원격/로컬) |

---

## 음성 파이프라인 (STT ↔ TTS, Phase 2 신규)

### STT (Speech-to-Text) — 입력 방향
- 엔진: OpenAI Whisper (medium/large)
- 한국어 음성 → 한국어 텍스트 → 영어 지시문 변환
- 실시간 스트리밍 또는 push-to-talk 방식

### TTS (Text-to-Speech) — 출력 방향
- 엔진: gTTS / Piper TTS
- 상태 피드백 예시:
  - `"빨간 펜을 집고 있습니다"`
  - `"왼쪽 상자에 놓았습니다"`
  - `"정리가 완료되었습니다. 총 3개 물체를 정리했습니다"`
  - `"지시하지 않은 물체 2개는 그대로 두었습니다"`

> **참고**: GR00T N1.6 VLA는 **언어+이미지를 함께 인코딩**하여 행동을 출력하므로,
> 별도 NLU/물체 탐지기가 필요 없다 — 는 것이 설계 전제였다.
> **그러나 Phase 1 실측에서 언어를 사실상 쓰지 않는 현상이 확인됐다**
> (sim L5 의미충돌 10/10 무시, `red` 명시 무효, 실기 L5 동일 — sim·실기 양쪽 확인).
> 원인은 수집 257ep 전체가 **단일 지시문**이라 언어 입력이 상수였던 것.
> → Phase 2 수집은 **같은 씬에서 문장이 다르면 정답 행동도 달라지는** 구성이어야 하며
> (LIBERO-Object형), Level 1에서 언어 조건화부터 검증한다.
> 상세: `manipulator_md/sim/sim2real_generalization_report.md` §9

---

## 프로젝트 진행 플로우차트

<a href="docs/diagrams/D6_project_flowchart.png"><img src="docs/diagrams/D6_project_flowchart.png" width="500" alt="D6 프로젝트 진행 플로우차트"></a>

<sub>클릭하면 원본 크기 · 📐 편집: [Figma — D6 프로젝트 진행 플로우차트](https://www.figma.com/board/4iKjT0Ngfm8IKmiFttKaKc?node-id=6-193)</sub>

```mermaid
flowchart TD
    A["Phase 1 완료 ✅\n단일 큐브 pick-place\nSim OOD 82.5%\nreal co-training 80%"] --> B["Phase 2-1\n시뮬레이션 환경 설계\n다물체 + 상자 2개 씬\nIsaac Sim / Isaac Lab"]
    B --> C["Phase 2-2\n음성 파이프라인 구축\nSTT(Whisper) + TTS(gTTS)\n한→영 지시문 변환"]
    C --> D["Phase 2-3\n데이터 수집 (teleop)\nLevel 1→2→3 커리큘럼\n합계 500ep"]
    D --> E["Phase 2-4\n학습(5090) + Sim 검증\nGR00T N1.6 50k steps\n무인 평가 + scenes.csv"]
    E --> F{"Sim SR\n합격?"}
    F -->|"L1≥80%\nL2≥70%"| G["Phase 2-5\nSim2Real 전이\n실기 데이터 수집\nco-training"]
    F -->|"미달"| H["보정 수집\n+50ep 타깃 수집\n+10k steps"] --> E
    G --> I["Phase 2-6\n음성 통합 테스트\nSTT→VLA→TTS\n실기 end-to-end"]
    I --> J["Phase 2-7\n최종 데모\n영상 촬영 + 리포트"]
```

---

## 난이도별 커리큘럼

| Level | 물체 수 | 지시 유형 | 동작 | Sim SR 목표 | Real SR 목표 |
|---|---|---|---|---|---|
| **L1** 기본 | 2개 | 단일 색상 분류 | 1회 pick-place | ≥ 80% | ≥ 70% |
| **L2** 순차 | 3개 | 다색상 순차 | 3회 순차 pick-place | ≥ 70% | ≥ 50% |
| **L3** 선택적 | 5개 | 선택적 분류+무시 | 타겟만 정리 | ≥ 60% | ≥ 40% |
| **L4** 도전 | 5개 | 형상 기반 분류 | 큐브/원통 분류 | 보너스 | — |

---

## Phase 1 성과 (기반 파이프라인)

### 성능

| 지표 | Sim | Real (co-training 후) |
|---|---|---|
| 학습 분포 내 SR | v3 61~67% → **v4_200 근접 보강으로 해소** (고정 패널 L0 9/10) | 80% (n=5, CI 27~86%) |
| OOD SR | **82.5%** (v3 시점) ✅ | 80% (n=5, CI 27~86%) |
| Zero-shot | — | **0%** (고정자세 붕괴) |
| 일반화 (평가 B) | **15조건 중 11 견고** · 취약 2축: 물체 식별·물체 기하 | 언어 미사용 재확인 (L5) |

### 핵심 발견
- **블록-박스 근접**이 SR의 주된 병목 (39% vs 83%, 44%p 차)
- 수집 필터가 유효 근접 구간까지 걸러냄 (학습 19.2% vs 자연 43.2%)
- → 타깃 수집(65ep, 근접 55/65)으로 보강, v4_200(200ep, 근접 54.5%) 재학습
- **앙상블 결함**: 행동 앙상블이 움직임을 상쇄, 10~50초 정지 유발 (끄면 2/5→4/5)
- **언어 미사용**: 현 정책은 언어를 입력으로 쓰지 않음 → cleanup task에서 재검증 필수
- **물체 기하 실패**: 28mm 2/10, 지우개 4/10 — 크기·자세에 그리퍼를 못 맞춤
  → Phase 2 대상(펜·매직)이 이 축이므로 크기·형상 다양 수집 필수
- 상세: `manipulator_md/sim/sim2real_generalization_report.md`

### 데이터셋 계보

| 데이터셋 | ep / frames | 구성 | 학습 모델 |
|---|---|---|---|
| `sim_so101_blocktask` | 75 / 25k | 초기 | `blocktask75` 20k |
| `..._v2` | 100 / 31k | 박스 고정 | `v2` 20k |
| `..._v3` | 100 / 39k | v3 씬 (위치·박스·물리 DR) | `v3` 40k |
| `..._v4_200` | 200 / 83k | **근접 보강** | `v4_200` 86k |
| `so101_blocktask_real` | 50 / 21k | 실기 (박스 고정) | co-training (v2 시절) |
| `..._real_v2_57` | 57 / 38k | 실기 (박스 다양성) | **cotrain_v4** 48k |

---

## 다이어그램 (Figma)

문서의 ASCII·mermaid 블록을 FigJam 보드 한 장에 옮겨 두었다. 코드블록은 터미널·grep용으로 남겨 둔다.

**보드 전체**: [manipulator_ws — 아키텍처 다이어그램](https://www.figma.com/board/4iKjT0Ngfm8IKmiFttKaKc)

이미지는 `docs/diagrams/`에 PNG로 함께 두었다 — 문서에서 바로 보이고, 편집은 Figma에서 한다.

| # | 다이어그램 | 출처 | 이미지 | 편집 |
|---|---|---|---|---|
| D1 | 파이프라인 S1~S7 | `PIPELINE.md` §0 | [PNG](docs/diagrams/D1_pipeline.png) | [Figma](https://www.figma.com/board/4iKjT0Ngfm8IKmiFttKaKc?node-id=16-341) |
| D2 | 학습 파이프라인 (머신 경계) | README | [PNG](docs/diagrams/D2_train_pipeline.png) | [Figma](https://www.figma.com/board/4iKjT0Ngfm8IKmiFttKaKc?node-id=2-50) |
| D3 | 추론(배포) 파이프라인 | README | [PNG](docs/diagrams/D3_infer_pipeline.png) | [Figma](https://www.figma.com/board/4iKjT0Ngfm8IKmiFttKaKc?node-id=41-476) |
| D4 | sim2real 전이 흐름 | README | [PNG](docs/diagrams/D4_sim2real_flow.png) | [Figma](https://www.figma.com/board/4iKjT0Ngfm8IKmiFttKaKc?node-id=4-138) |
| D5 | 확장 경로 Phase 1 → Phase 2 | README | [PNG](docs/diagrams/D5_phase_roadmap.png) | [Figma](https://www.figma.com/board/4iKjT0Ngfm8IKmiFttKaKc?node-id=5-177) |
| D6 | 프로젝트 진행 플로우차트 | README | [PNG](docs/diagrams/D6_project_flowchart.png) | [Figma](https://www.figma.com/board/4iKjT0Ngfm8IKmiFttKaKc?node-id=6-193) |
| D7 | 코드가 사는 곳 (포크 vs 저장소) | `PIPELINE.md` §2 | [PNG](docs/diagrams/D7_code_layout.png) | [Figma](https://www.figma.com/board/4iKjT0Ngfm8IKmiFttKaKc?node-id=7-258) |
| D8 | 물리적 작업 공간 | README | [PNG](docs/diagrams/D8_workspace.png) | [Figma](https://www.figma.com/board/4iKjT0Ngfm8IKmiFttKaKc?node-id=9-270) |
| D9 | 일정 간트차트 (상세) | `PRESENTATION.md` §2.1 | [PNG](docs/diagrams/D9_gantt.png) | [Figma](https://www.figma.com/board/4iKjT0Ngfm8IKmiFttKaKc?node-id=21-302) |
| D10 | 일정 간트차트 (요약) | `PRESENTATION.md` §2.1 | [PNG](docs/diagrams/D10_gantt_summary.png) | [Figma](https://www.figma.com/board/4iKjT0Ngfm8IKmiFttKaKc?node-id=23-393) |

---

## 프로젝트 구조

```
manipulator_ws/
├─ README.md · PIPELINE.md · PRESENTATION.md   # 개요 · 파이프라인 해부(S1~S7) · 발표 자료
├─ docs/
│  ├─ diagrams/                # 아키텍처 다이어그램 PNG (편집은 Figma)
│  └─ figures/                 # 결과 그림·영상 (PRESENTATION.md 등에서 사용)
├─ manipulator_md/             # 진행 기록
│  ├─ STATUS.md                #   전체 진행 현황
│  ├─ sim/                     #   sim 학습·일반화·언어 조건화 계획과 실행 기록
│  ├─ sim2real/                #   sim→real 실행 기록, 08_T1_sim2real/ (deploy.md = sim 수집 환경 재현 가이드)
│  └─ real/                    #   실기 cleanup: 수집 환경·계획 CSV·평가 결과
│     ├─ collection_environment.md · v3_plan.md · v4_plan.md   # 단일팔
│     └─ bi_manipulator_plan.md · bi_*.csv                     # 양팔
├─ setup/                      # 재현용 스크립트
│  ├─ hardware/                # udev rules, 장치 식별, 카메라 점검, teleop
│  ├─ data/                    # 실기 cleanup(단일팔): 수집·검증·준비·학습·평가
│  │  ├─ check_setup.sh · view_cams.py · check_joints.py · calib_fingerprint.py   # 수집 전 점검
│  │  ├─ gen_real_lang_plan.py · record_real_lang.sh · rest_gate.py               # 계획표 → 수집
│  │  ├─ verify_real_lang_dataset.py · episode_events.py · drop_episode.sh        # 수집 후 검증
│  │  ├─ prepare_cleanup_real.sh · train_cleanup_real.sh                         # 5090 전송·변환 → 학습
│  │  └─ cleanup_eval.py                                                          # 평가 계획·기록·분석
│  ├─ bi/                      # 실기 cleanup(양팔)
│  │  ├─ data/                 #   gen_bi_plan.py · record_bi.sh · handoff_events.py · prepare_bi_cleanup.sh · cleanup_eval_bi.py
│  │  └─ gr00t/                #   bi_so100_config.py · train_bi_cleanup.sh · home_then_infer_bi.sh · client/eval_lerobot_bi.py
│  ├─ gr00t/                   # GR00T 서빙·실기 공용 도구
│  │  ├─ serve_local.sh · serve_blocktask_n16_5090.sh · serve_blocktask_realclient.py   # 로컬/5090 서빙
│  │  ├─ client/eval_lerobot.py · run_eval_real.sh · home_then_infer.sh               # 단일팔 추론
│  │  ├─ goto_home_cleanup.py · goto_home_real.py · goto_home_sim.py                  # 홈 자세
│  │  ├─ real_pose_align.py · rerun_cam_align.py · pose_ref*/                          # 카메라 정렬
│  │  └─ probe_language.py · analyze_real_run.py                                      # 언어 프로브 · 시행 분석
│  └─ sim/                     # Isaac Sim (T1 블록 태스크)
│     ├─ train_gr00t_sim_n16_8bit.sh · patches/   #   8-bit 학습 레시피, 워크숍 저장소 패치
│     └─ t1_task/              #   P1~P4 단계별 스크립트 (README 에 단계별 표)
├─ envs/
│  └─ lerobot/                 # uv 프로젝트 (lerobot 0.4.4 + torch 2.10 cu128). GR00T 는 도커 이미지에서 실행
├─ inf_video/                  # (git 제외) 단계별 최종 모델의 추론 영상·chunks/actions.csv·run.json
│  ├─ 10_eval_lang_*/          #   P4 sim 언어 평가 — B6kfix(새 학습)·fix/v4fix(대조)·B60(최종)·gen·dest*
│  ├─ 07_real_eval/            #   P5 단일팔 — cleanup(v3 ckpt-30000 평가)·success(성공 영상)
│  └─ 07_real_eval_bi/         #   P6 양팔 — bi151_ck28000
└─ logs/                       # (git 제외) evalA(P3 cotrain_v4 실기)·v4_zeroshot(P3 sim 단독 실기 zero-shot)
```

---

## 환경 재현

```bash
# 1. uv 설치
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. 의존성 설치 (Python 3.10 자동 고정)
cd envs/lerobot && uv sync

# 3. udev rules 설치 (장치 경로 고정)
sudo cp setup/hardware/99-lerobot.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger

# 4. 시스템 의존성
sudo apt install ffmpeg   # torchcodec(학습 영상 디코딩) 필수

# 5. 음성 파이프라인 의존성 (Phase 2)
pip install openai-whisper gtts pyaudio

# 6-a. 실기 추론 — 원격 서빙 (5090)
ssh 5090 '~/serve_blocktask_n16_5090.sh <model>/checkpoint-<step> start'
cd setup/gr00t && ./run_eval_real.sh C <조건>

# 6-b. 실기 추론 — 로컬 서빙 (지연 73ms, 지터 없음. 5090은 학습에 사용 가능)
cd ~/blocktask_ws/Sim-to-Real-SO-101-Workshop && ./docker/real/build.sh blackwell  # 최초 1회
cd ~/manipulator_ws/setup/gr00t && ./serve_local.sh <model>/checkpoint-<step>
SERVER_HOST=127.0.0.1 ./run_eval_real.sh C <조건>

# 7. sim 데이터 수집 환경 (Isaac Sim T1) — 단계별 안내는 문서 참고
#    manipulator_md/sim2real/08_T1_sim2real/deploy.md
```

## 실기 cleanup 실행

학습은 5090, 수집·추론은 로컬에서 한다. 5090 쪽 스크립트(`train_*.sh`)는 5090의 작업 폴더에 복사해서 실행한다.
각 스크립트 머리말에 옵션과 이유가 자세히 적혀 있다.

### 단일팔

```bash
cd setup/data
./check_setup.sh cams                         # 선반·카메라 화각 점검 (teleop 모드로 리치 확인)
python3 gen_real_lang_plan.py                 # 수집 계획표 (물체·지시문·칸)
./record_real_lang.sh                         # 계획표 순서대로 수집 (중단 후 재실행하면 이어서)
(cd ../../envs/lerobot && uv run python ../../setup/data/verify_real_lang_dataset.py <데이터셋 경로>)  # 수집본 검증
./prepare_cleanup_real.sh all                 # 5090 전송 → v2.1 변환 → 지시문 수 게이트
#  (5090) EPOCHS=8 ./train_cleanup_real.sh    # 파운데이션 N1.6-3B 에서 새로 학습

cd ../gr00t && ./serve_local.sh gr00t_cleanup_real_n16_8bit/checkpoint-30000
cd ../data && python3 cleanup_eval.py log     # 평가 시행마다 로봇 실행 + 결과 입력
python3 cleanup_eval.py report                # 물체 축 · 목적지 축 분석
```

### 양팔

```bash
cd setup/bi/data
python3 gen_bi_plan.py --episodes 300 --layout-every 50   # 계획표 (50ep마다 칸 색 배치 교체)
./record_bi.sh                                # 오른팔 집기 → 전달 → 왼팔 넣기 시연
(cd ../../../envs/lerobot && uv run python ../../setup/bi/data/handoff_events.py --report <데이터셋 경로>)  # 전달 성공·시점 검사
./prepare_bi_cleanup.sh all                   # 5090 전송 → 변환 → 검사(지시문 32종·4색·카메라 3대)
#  (5090) SMOKE=1 ./train_bi_cleanup.sh 로 먼저 확인 → EPOCHS=10 OUT_NAME=<이름> ./train_bi_cleanup.sh

cd ../../gr00t && ./serve_local.sh <모델>/checkpoint-<step>
cd ../bi/data
python3 cleanup_eval_bi.py log --eval-name <이름> --out <결과.csv> --rerun
python3 cleanup_eval_bi.py report --out <결과.csv>
#  평가 B(학습에 없던 칸 배치 포함 60시행): --plan ~/manipulator_ws/manipulator_md/real/bi_cleanup_eval_plan_B.csv
```

- 추론 중 `q` 한 번으로 그 시행을 끝내고 결과 입력으로 넘어간다. 어떤 이유로 끝나든 팔은 그 자리에 멈춘 뒤 천천히 rest 로 돌아가고 토크를 유지한다.
- 원격(5090) 서버를 쓸 때는 `SERVER_HOST=<5090 IP>` 를 앞에 붙인다.

## 데이터·모델

데이터셋과 체크포인트는 용량 때문에 저장소에 넣지 않았다.
데이터셋은 로컬 `~/blocktask_ws/Sim-to-Real-SO-101-Workshop/datasets/_train/` 에, 체크포인트는 `~/gr00tn16_ws/checkpoints/` (로컬·5090) 에 있다.

| 데이터셋 | 규모 | 모델 (checkpoint) |
|---|---|---|
| `cleanup_real` (단일팔) | 370ep · 지시문 40종 | `gr00t_cleanup_real_n16_8bit` (checkpoint-30000, v3) |
| `bi_cleanup` (양팔) | 300ep · 331,455 frames · 지시문 32종 · 칸 배치 6종 | `gr00t_bi_cleanup151_n16_8bit` (151ep, checkpoint-28000) · `gr00t_bi_cleanup300_n16_8bit` (300ep, 학습 중) |
| `sim_so101_blocktask_v4_200` + `..._real_v2_57` (T1) | sim 200ep + 실기 57ep | `gr00t_blocktask_cotrain_v4_n16_8bit` (checkpoint-48000) |

## 주의사항

- 카메라 설정에 **반드시 `fourcc: MJPG`** — YUYV는 USB 대역폭 포화로 영상 깨짐
- RTX 5070 Ti(Blackwell sm_120)는 CUDA 12.8+ / torch 2.10+cu128 필요 (lerobot env 기준)
- **서빙 이미지(real-robot) 빌드 재현성**: torch nightly 미고정이면 flash-attn 컴파일이 깨진다
  — `Dockerfile.blackwell`은 torch==2.8.0+cu128 + flash-attn 2.8.3 **사전 wheel**로 고정됨
- 카메라 udev rule은 물리 포트 기준 — USB 포트 이동 시 rule 수정 필요
- 마이크/스피커 장치 확인: `arecord -l` / `aplay -l`
- **데이터 포맷 주의**: 수집은 LeRobot v3.0, 학습은 v2.1 — 변환 누락 시 학습 실패
- **씬 배포 검증 필수**: 로컬에서 씬 수정 후 5090에 rsync 누락 → 무효 측정 발생 (Phase 1 경험)
- **카메라 정렬 필수**: 실기 배포 전 `rerun_cam_align.py`로 확인 — 구도가 곧 입력 분포
- **영상 코덱**: 평가 영상은 `mpeg4`로 저장돼 웹(Notion 등)에서 재생 불가 —
  업로드 전 `ffmpeg -c:v libx264 -pix_fmt yuv420p -movflags +faststart`로 변환
- **run.json이 근거**: 어떤 모델·지시문·설정으로 돌렸는지는 조건 이름이 아니라
  각 결과 디렉터리의 `run.json`으로 증명한다 (Phase 1 교훈)
