# SO-ARM101 × 4모델 학습/Zero-shot 비교 — 진행 가이드라인

> 목적: 단일 SO-ARM101에서 4개 모델(ACT / SmolVLA / π0 / GR00T N1.5)을 순차 시연하여
> ① 추론 파이프라인 전구간 검증 ② 기준선(zero-shot) 수치 확보 ③ 파인튜닝 필요성의 실측 근거 확보.
>
> 기반 문서 (Notion):
> - [단일 SO-ARM101 실습용 모델 비교 조사 보고서](https://app.notion.com/p/393d17f8526781218f1ae16b917018f7)
> - [Zero-shot 추론 시연 계획서 — SO-ARM101 × 3모델 × 2 Task](https://app.notion.com/p/395d17f8526781efa8d3d2236b3cb6d0)
> - [Zero-shot 시연 일별 계획 (7/7~7/16)](https://app.notion.com/p/395d17f85267819aa7c4f6a97554e2b1)

---

## 1. 진행 원칙 (반드시 지킬 것)

1. **모델 단위 완결(closure)**: 순서는 **ACT → SmolVLA → π0 → GR00T N1.5**.
   각 모델은 2개 task 시연 + 산출물 체크리스트를 **모두 채운 뒤에만** 다음 모델로 넘어간다.
   (task 단위가 아니라 모델 단위로 닫는다 — 모델 전환이 가장 비싼 컨텍스트 스위치)
2. **ACT는 zero-shot이 아니다**: 사전학습 체크포인트가 없어 zero-shot 불가 →
   예외적으로 **파인튜닝(FT) 후 시연**. 모든 표·클립에 **FT/ZS 라벨을 명시**하고,
   "FT 상한 참조군 vs ZS 하한 기준선" 프레임으로만 해석한다.
3. **게이트 예외 1개**: GR00T 환경 설치(flash-attn 다운로드·컴파일)는 측정과 무관한
   백그라운드 작업이므로 앞 모델 진행 중 병행 허용.

## 2. 모델 파일

| 순서 | 파일 | 모델 | 방식 | 기대치 |
|---|---|---|---|---|
| 1 | [01_ACT.md](01_ACT.md) | ACT (~52M) | ⚠️ FT 후 시연 | FT 참조군 — 최고 SR 예상 |
| 2 | [02_SmolVLA.md](02_SmolVLA.md) | SmolVLA (450M) | Zero-shot | ZS 3종 중 최고 기대 (SO-ARM 계열 사전학습) |
| 3 | [03_Pi0.md](03_Pi0.md) | π0 (3B) | Zero-shot | 중간 — jerky motion 주의 |
| 4 | [04_GR00T_N1.5.md](04_GR00T_N1.5.md) | GR00T N1.5 (3B) | Zero-shot | OOD로 최저 예상 — 파이프라인 검증이 주목적 |
| 5 | [05_SimToReal.md](sim2real/05_SimToReal.md) | (4모델 공통) | Sim-to-Real | Isaac Sim 학습·평가 → 실기 전이 + co-training (2026-07-20 확정 계획) |
|   | [sim2real/](sim2real/) | 모델별 개별 페이지 | Sim-to-Real | S1~S4: 절차 체크박스·게이트·결과 기록표 |

## 3. 하드웨어 & 공통 환경

- **로봇**: SO-ARM101 follower 1 + leader 1 (ACT 데이터 수집·캘리브레이션용)
- **카메라**: 2캠 — `wrist` + `top` (실제 장착 기준), 640×480@30fps, udev로 `/dev/cam_top`·`/dev/cam_wrist` 고정
- ⚠️ **카메라 설정에 반드시 `fourcc: MJPG` 포함** (teleop/record/eval 전부):
  기본 YUYV 무압축은 2캠 295Mbps로 공유 허브(480Mbps)를 포화시켜 **wrist 영상 깨짐**(가로선) 발생.
  2026-07-08 실측 확정 — MJPG 강제 시 풀부하에서도 아티팩트 0회.
- **OS/GPU**: Ubuntu 24.04, RTX 5070 Ti 16GB (Blackwell sm_120 → CUDA 12.8+ / 최신 PyTorch 필수)
- **환경 관리**: uv 프로젝트 2개 분리
  - `envs/lerobot/` — `lerobot[smolvla]` + ACT + π0 (수집·학습·배포 공통)
  - `envs/gr00t/` — Isaac-GR00T (flash-attn 등 무거운 의존성 → 반드시 격리)
  - `uv python pin 3.10` (시스템 Python 3.12 의존 금지)
- **공유 채널**: HF Hub private repo (데이터셋·체크포인트·결과), git (uv.lock, udev rules)
- **원격 학습**: π0 LoRA FT는 공용 RTX 5090(32GB)에서 Docker로 수행 → 체크포인트 회수

### 카메라 네이밍 규칙 (양팔 확장 대비)
- **확정 네이밍**: `top` (상단 뷰) / `wrist` (손목) — 수집·학습·추론 전 구간에서 이 이름만 사용.
- 양팔 확장 시 `wrist_left`/`wrist_right` 재수집 비용이 발생하므로 네이밍 규칙을 처음부터 문서로 고정한다.
- ⚠️ GR00T는 **카메라 이름이 수집 당시와 정확히 일치**해야 함 (실패 원인 1순위).
  GR00T `so100_dualcam` data-config의 기대 key와 다르면 `modality.json`에서 매핑으로 해결.

## 4. 대상 Task (2종)

| Task | 설정 | 언어 명령 예시 | 레퍼런스 데이터셋 |
|---|---|---|---|
| **T1. Pick-and-Place** | 큐브 1개 → 그릇/상자 | "Pick up the cube and place it in the box" | `lerobot/svla_so101_pickplace` |
| **T2. Table Cleanup** | 물체 3개를 용기로 수납 | "Put the [object] in the container" | `youliangtan/so101-table-cleanup` |

- 레퍼런스 데이터셋을 [Dataset Visualizer](https://huggingface.co/spaces/lerobot/visualize_dataset)로
  관찰해 물체·배치·조명을 최대한 재현한다. ACT 학습 데이터도 동일 셋업에서 수집.

## 5. 평가 프로토콜 (전 모델 공통)

- 조건당 **10회 시행**: 4모델 × 2task × 10회 = **80회** + 예비 ≈10회
  (GR00T 레포도 실행 간 5~6% 분산 경고 → 10회 미만은 노이즈)
- **초기조건**: 3지점 그리드 순환(테이핑), 전 모델 동일 순서
- **시행 제한**: T1 60초, T2 물체당 60초
- **1인 운영**: 전 시행 녹화를 기록 보조로, 시행 직후 로그 즉시 기입

### 측정 지표
| 지표 | 정의 |
|---|---|
| SR | 성공률 |
| PR | 부분 진행률: 접근 0.25 → 파지 0.5 → 이동 0.75 → 배치 1.0 |
| 지연 | 추론 지연(ms), 제어 주기 안정성 |
| VRAM | 피크 사용량 |
| 실패 유형 | 오인식 / 오파지 / 타임아웃 / 발산 |

## 6. 모델별 완결 체크리스트 (공통 게이트)

각 모델 종료 시점에 아래 산출물이 **전부** 있어야 다음 모델 착수 가능:

- [ ] 시행 로그 20회분 (2task × 10회): SR/PR/지연/VRAM/실패유형
- [ ] task별 대표 클립 각 1개 (성공 또는 최고 PR 시행) + 실패 대표 클립 1개
- [ ] 모델 요약 카드 (반 페이지): 셋업 특이사항, 수치 요약, 관찰 메모, 다음 단계 시사점
- [ ] (ACT만) 학습 로그·체크포인트 HF Hub 업로드, 수집 데이터셋 push
- [ ] 로그·클립 HF Hub / 공유 저장소 백업

## 7. 전체 진행 체크리스트 (일별 계획 기준: 7/7~7/16)

- [x] **D1 (완료 7/8)** 환경 구축: uv 2개 프로젝트, Blackwell PyTorch 검증, udev rules, HF private repo
  - 게이트: ✅ 더미학습 1스텝 (ACT 51.6M, VRAM 1.08GB) + ✅ 2캠 동시 30fps 스트림
  - 확정 사항: torch 2.10.0+cu128 / lerobot 0.4.4 / HF 계정 `heongyu`
  - 고정 경로: `/dev/ttyLEADER`(5AE6054948) `/dev/ttyFOLLOWER`(5AE6083400) `/dev/cam_top`(1-5.3) `/dev/cam_wrist`(1-5.4.1)
  - Private repo: `heongyu/so101_t1_pickplace`, `heongyu/so101_t2_cleanup` (dataset), `heongyu/so101_checkpoints` (model)
  - ⚠️ 미설치: git (팀 공유용 — `sudo apt install git` 필요), GR00T 의존성(D4~D6 병행 예정)
- [x] **D2 (완료 7/8)** 로봇 검증 + 측정 준비 + ACT T1 수집 시작
  - 게이트: ✅ T1 20ep 수집·검증 완료 (평균 ~14초/ep, NaN 0, 그리드 순환 정상)
  - 확정 셋업: 물체 = **빨간 큐브**, 용기 = **검은 박스**, 언어 명령 = "Pick up the red cube and place it in the black box"
  - 캘리브레이션 완료 (follower/leader), wrist 카메라 초점 조정 완료
  - ⚠️ 트러블슈팅 기록: wrist 영상 깨짐 = YUYV 대역폭 포화 → **fourcc MJPG로 해결** / 데이터셋 영상은 AV1 인코딩 → 학습 전 `sudo apt install ffmpeg` 필요 (torchcodec 의존)
  - 헬퍼 스크립트: `setup/hardware/teleop.sh`, `setup/hardware/check_cameras.sh`, `setup/data/record_t1.sh`, `setup/data/reset_dataset.sh`
- [x] **D3 (완료 7/9)** T2(Table Cleanup, 색 3개 셔플 배치) 30ep 수집 완료 (32,835프레임, NaN 0)
  - 물체: 빨강/노랑/초록 큐브, 1에피소드=3개 연쇄 pick-place, 5종 이상 배치 패턴 확인
  - Hub: `heongyu/so101_t2_cleanup` (3개 청크 push 완료)
  - 게이트: 학습 기동 + loss 하강 확인
- [ ] **D4 (7/10)** ACT-T2 학습(오전) → T1·T2 각 10회 측정 → **ACT 완결** ([01_ACT.md](01_ACT.md))
- [ ] **7/11 (토, 선택)** 버퍼 / GR00T 설치 착수
- [ ] **D5 (7/13)** SmolVLA dry-run → 20회 → 산출물 → **SmolVLA 완결** ([02_SmolVLA.md](02_SmolVLA.md))
- [ ] **D6 (7/14)** π0 dry-run → 20회 → 산출물 → **π0 완결** ([03_Pi0.md](03_Pi0.md))
- [ ] **D7 (7/15)** GR00T server-client → 20회 → 산출물 → **GR00T 완결 or 제외 판정** ([04_GR00T_N1.5.md](04_GR00T_N1.5.md))
- [ ] **D8 (7/16)** 통합 비교표(FT/ZS 구분 열) · 본 시연 · 파인튜닝 go/no-go 판단문

### 시간 배분 참고 (1인 기준)
- 데이터 수집: 30ep ≈ 2~2.5시간 (리셋 포함)
- ACT 학습: task당 수 시간 (12GB 3080에서 ~4h 사례, 16GB 여유) → 야간 슬롯 활용
- 측정 20회: 시행+리셋+로그 ≈ 5분/회 → 약 2시간 + dry-run·정리 = 반나절

### 비상 계획
| 상황 | 대응 |
|---|---|
| ACT 학습이 D4 오전까지 안 끝남 | T2 학습을 D4 야간으로 → D4 오후 T1 측정만 완결 → T2 측정은 D5 오전 1시간 편입 |
| GR00T가 D7 오전까지 안 붙음 | 제외 판정 기록 → D7은 예비측정·비교표 선행 작성 (3모델로도 시연 성공 기준 충족) |
| 하루 통째 증발 (장비 고장 등) | ① 토 버퍼 소진 → ② 시행 10→8회 → ③ GR00T 제외. **ACT·SmolVLA 완결은 최후까지 사수** |

## 8. 데이터 포맷 전략 (한 번 수집, 4모델 재사용)

기본 수집은 **LeRobotDataset 하나로 충분**하되, 모델별 메타데이터 변형만 추가:

| 모델 | 베이스 포맷 | 추가 요구사항 | 난이도 |
|---|---|---|---|
| ACT | LeRobotDataset | 없음 (언어 필드 불필요) | 없음 |
| SmolVLA | LeRobotDataset | 에피소드별 자연어 task 설명 필드 | 없음 (수집 시 포함) |
| π0/π0.5 | LeRobotDataset | norm stats, `meta/info.json` 스키마 정합 | 낮음 (스크립트 제공) |
| GR00T N1.5 | GR00T-LeRobot | `meta/modality.json` 추가 + embodiment tag | 낮음 (파일 1개 복사/수정) |

⚠️ **수집 전 확인**: LeRobot 데이터셋 버전(v2.1/v3.0)과 각 모델 레포가 기대하는 버전이
다를 수 있음 — 타겟 모델의 요구 버전을 먼저 확인할 것.

## 9. 최종 산출물

- 모델 4종 요약 카드 + 통합 비교표 (FT/ZS 구분 열 포함)
- 시행 로그 80회+ / 대표 클립 모음 / 본 시연 영상
- ACT 데이터셋·체크포인트 (HF Hub) — 이후 파인튜닝 단계의 데이터 자산
- 파인튜닝 단계 go/no-go 판단문 + 관찰 기반 데이터 수집 계획 초안
