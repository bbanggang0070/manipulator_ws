# Sim-to-Real 계획: Isaac Sim에서 4모델 학습·추론 → 실기 전이 (SO-101)

> 목표: **시뮬레이터에서 데이터 수집→학습→추론(평가)까지 완결한 뒤, 그 체크포인트를 실기
> SO-ARM101로 전이(sim-to-real)** 하는 실험을 ACT / SmolVLA / π0 / GR00T N1.5 4모델에서 수행.
> 기반: NVIDIA 공식 [Sim-to-Real SO-101 Workshop](https://github.com/isaac-sim/Sim-to-Real-SO-101-Workshop)
> (Isaac Sim + Isaac Lab, Docker, RTX 5090 공식 테스트) + [LeIsaac](https://wiki.seeedstudio.com/simulate_soarm101_by_leisaac/) 참고.

## 0. 선정 근거 (요약)

1. SO-101이 Isaac Sim **공식 내장 자산** / 2. NVIDIA 공식 워크숍이 SO-101+Isaac Lab+GR00T
전 과정 제공 / 3. **sim teleop → LeRobot 포맷 출력 = 4모델 기존 학습 파이프라인 그대로 재사용**
/ 4. sim+real co-training 근거(+38%, arXiv:2503.24361)

## 1. 아키텍처 (2 PC 분업, 사용자 확정)

```
[로컬 RTX 5070Ti 16GB]                    [원격 RTX 5090 32GB]
 sim(teleop-docker) + 실기 로봇/리더암      sim(teleop-docker) + 추론 컨테이너
 경량 모델 학습·추론: ACT, SmolVLA          대형 모델 학습·추론: π0, GR00T
 sim teleop 데이터 수집(리더암 입력)         (데이터는 rsync/HF로 동기화)
```

- 실기·리더암·카메라가 로컬에 물려 있으므로 **sim 데이터 수집과 실기 전이 평가는 로컬**,
  대형 모델 학습·서빙은 5090 (기존 π0/GR00T 원격 인프라 재사용)

## 2. 공통 파이프라인 (5단계)

### Phase 0 — 환경 (로컬 완료, 2026-07-20)
- [x] 양 PC Docker + NVIDIA Container Toolkit
- [x] 양 PC `teleop-docker`(Isaac Sim/Lab) 이미지 빌드 완료 — 로컬·원격 모두
  같은 git commit(`1d62ec5`)·같은 `FROM nvcr.io/nvidia/isaac-lab:2.3.2` 태그로 빌드해
  **버전 동일 확인**(Isaac Lab 2.3.2 / Isaac Sim 5.1.0-rc.19, 양쪽 이미지 내부 조회로 검증).
  Dockerfile이 베이스 이미지 태그·lerobot 커밋(`e670ac5`)·주요 패키지를 전부 고정하고 있어
  빌드 시점이 달라도 버전 드리프트 없음
- [x] sim 컨테이너 기동 + SO-101 씬 로드 확인 (`list_envs`) — 6개 환경
  (Base/Task/Vials-To-Rack/-DR/-Eval/-DR-Eval) 전부 정상 등록, Kit 앱 정상 기동(~38s)
- [x] `zero_agent`로 GUI 렌더링 육안 확인 (로컬) — SO-101 팔·바이알 2개·노란 랙·검은 매트·
  라이트박스 전부 정상 렌더링, RTX Real-Time 모드, IsaacLab 패널에 씬 오브젝트(Vial 1~3,
  Rack Left, Robot) 정상 바인딩
  - 명령: `zero_agent --task Lerobot-So101-Teleop-Vials-To-Rack --num_envs 1`
    (⚠️ `--task`는 필수 인자 — 생략 시 `AttributeError: 'NoneType' has no attribute 'split'`)
- [x] 원격 5090: git-lfs 설치 + `git lfs pull` + headless 씬 로드 검증 완료
  (`zero_agent --headless`, 에러 0건, GPU 정상 사용) — GUI 없이 학습·평가 서버용으로 사용
- [x] 로컬 리더암 teleop 연결 검증 (`lerobot_agent`) — 실물 리더암이 sim SO-101을 구동함 확인
- [ ] (필요 시) 5090 추론 컨테이너 `./docker/real/build.sh blackwell`

#### ⚠️ 함정: 컨테이너 실행 시 필수 마운트
entrypoint가 `set -e` 상태에서 `source /root/env`와 `pip install -e .../source/...`를 수행하므로
**`docker/env`와 `source` 마운트를 빠뜨리면 컨테이너가 즉시 exit 1**로 죽는다. 게다가
entrypoint의 `source /root/env 2>/dev/null`이 에러를 삼켜 **아무 출력 없이 종료**되므로
원인 파악이 어렵다. 최소 필수 마운트:
```
-v $(pwd)/docker/env:/root/env
-v $(pwd)/source:/workspace/Sim-to-Real-SO-101-Workshop/source
```

#### 리더암 teleop 시 calibration 경로 주의
컨테이너의 lerobot(핀 `e670ac5`)은 `calibration/teleoperators/**so101_leader**/leader.json`을
기대하는데, 실기 환경(lerobot 0.6.x)은 `**so_leader**/`에 저장한다. 포맷은 완전히 동일
(`id`/`drive_mode`/`homing_offset`/`range_min`/`range_max`)하므로 **복사본을 만들어 해결**:
```bash
docker exec teleop bash -c "cp /root/.cache/huggingface/lerobot/calibration/teleoperators/so_leader/leader.json \
  /root/.cache/huggingface/lerobot/calibration/teleoperators/so101_leader/leader.json"
```
(디렉터리가 컨테이너 root 권한으로 생성되므로 호스트에서 cp하면 Permission denied — 컨테이너 안에서 실행)

#### ⚠️ 함정: USD 에셋이 git-lfs 포인터로 남아있음
워크숍 저장소의 `.usd`/`.usda`는 전부 git-lfs 관리 대상인데, git-lfs 미설치 상태로 clone하면
**130바이트짜리 포인터 파일만** 받아진다. 이 상태로 실행하면:
```
FileNotFoundError: Unable to open the usd file at path:
  .../assets/usd/SO-ARM101-USD.usd
```
해결: `sudo apt install git-lfs && git lfs install && git lfs pull`
(로컬 처리 완료 — SO-ARM101 23MB 등 정상 수신. **5090은 미처리**, sim 학습 착수 전 필요)

### Phase 1 — sim 데이터 수집 (로컬)
- 워크숍 `lerobot_agent`(sim teleop): **실물 SO-101 리더암을 sim 입력으로 사용**
  (키보드 대안 있음) → **LeRobot 포맷 데이터셋 출력** → `lerobot_push_dataset`로 Hub 업로드
- 태스크: 워크숍 기본 `Lerobot-So101-Teleop-Vials-To-Rack` (+`-DR` 도메인 랜덤화 변형)
- 수집 규칙은 실기와 동일 철학: 성공으로 끝나는 에피소드만, 위치 다양화, idle 최소화
  (**GR00T idle 어트랙터 교훈** — 녹화 시작 즉시 동작 개시)

### Phase 2 — 4모델 학습
| 모델 | PC | 방법 (기존 스크립트 변형) |
|---|---|---|
| ACT | 5070Ti | `lerobot-train --policy.type=act` from-scratch (setup/act/ 패턴) |
| SmolVLA | 5070Ti | `smolvla_base` FT (setup/smolvla/ 패턴, batch16/20k~) |
| π0 | 5090 | expert-only FT (archive/setup/pi0/remote_5090/pi0-train.sh 패턴) |
| GR00T | 5090 | n1d5 FT — v2 변환+modality.json+트리밍 도구 재사용 (setup/gr00t/) |

- sim 데이터도 LeRobot v3로 나오면 GR00T용은 v3→v2 변환 필요 (도구 완비)
- **실기 실험에서 확정된 처방 선적용**: GR00T는 tune_visual, π0는 expert-only, idle 트리밍

### Phase 3 — sim 내 추론·평가 (closed-loop)
- GR00T: 워크숍 `lerobot_eval` + `-Eval`/`-DR-Eval` 환경으로 **공식 지원**
- ACT/SmolVLA/π0: 워크숍 eval은 GR00T 전제 → **lerobot 정책용 sim 평가 어댑터 제작 필요**
  (Isaac Lab env 관측 → lerobot 정책 입력 브리지; `lerobot_eval` 소스 참고해 작성)
- 지표: sim SR (task당 N회, 시드/초기위치 변화)

### Phase 4 — 실기 전이 (sim-to-real, 로컬)
- sim 학습 체크포인트를 **실기 평가 파이프라인 그대로** 실행
  (ACT/SmolVLA: lerobot-record eval, π0: async 서버, GR00T: zmq 서버 — 모두 기존 스크립트)
- 전이 조건: 실기 소품을 sim 태스크와 일치시킴 (바이알/랙 또는 T1 재현 여부는 미결 — 아래 D1)
- 측정: **zero-shot 전이 SR** (10회) → (선택) **sim+real co-training** 후 재측정
- 비교 기준: 실데이터 단독 학습 결과(기존 측정치) vs sim 단독 vs sim+real

### Phase 5 — 정리
- 4모델 × {real-only, sim-only(전이), sim+real} SR 매트릭스 → 종합 보고서

## 3. 확정 사항 (2026-07-20 사용자 결정)

| # | 결정 |
|---|---|
| **D1** | **(c)** 워크숍 태스크(Vials-To-Rack)로 파이프라인 검증 → T1은 **유사 환경**으로 구성 (완전 재현 아닌 근사) |
| **D2** | **환경별 적합 버전**: sim은 워크숍 스택의 최신 Isaac-GR00T 수용, 실기는 N1.5 유지 — 보고서에 버전 차이 명시 |
| **D3** | teleop 입력 = **실물 리더암** (수집은 로컬에서) |
| **D4** | **50ep + 도메인 랜덤화(DR) 태스크 사용** |
| **D5** | **4모델 전부 sim closed-loop 평가** — lerobot `policy_server`(act/smolvla/pi0 지원)를 컨테이너 밖 서버로 두고, sim 컨테이너 안에 **공용 클라이언트 어댑터 1개** 제작(워크숍 lerobot_eval 참고). GR00T는 워크숍 공식 경로. 예상 공수 1~2일 |
| **D6** | **zero-shot 전이 + co-training 둘 다** 검증 |
| **D7** | **GR00T 실기 완결 후** sim 착수 (5090 GPU 경합 회피) |

## 4. 리스크

| 리스크 | 대응 |
|---|---|
| 5070Ti에서 Isaac Sim 렌더+teleop 성능 | 해상도·물리 스텝 조정, 안 되면 수집도 5090에서(리더암 이동 필요) |
| 워크숍 GROOT_REF와 n1d5 비호환 | D2 결정에 따라 추론 컨테이너 GROOT_REF 오버라이드 시도 |
| sim 카메라 뷰 ↔ 실기 top/wrist 구도 차이 | sim 카메라 포즈를 실기와 유사하게 조정 + DR로 완화 |
| 캘리브레이션 좌표계(실기 전이 시) | goto_home/state 대조 도구 재사용 (GR00T 실기에서 검증됨) |
| ACT/π0/SmolVLA sim 평가 어댑터 공수 | D5에서 범위 결정, GR00T 우선 |

## 5. 설치 기록

- 양 PC clone: `~/Sim-to-Real-SO-101-Workshop`
- sim 이미지: `docker build -t teleop-docker -f docker/sim/Dockerfile .` (양쪽 빌드 진행 중)
- 로컬 함정 해결: claude-desktop apt GPG 만료(비활성화), 잔존 sshd 포트22 점유로
  openssh postinst 실패(정리), docker 그룹 미반영 셸은 `sg docker -c` 우회

## 6. 참고

- 워크숍: https://github.com/isaac-sim/Sim-to-Real-SO-101-Workshop
- 교육 문서: https://docs.nvidia.com/learning/physical-ai/sim-to-real-so-101/latest/index.html
- LeIsaac: https://wiki.seeedstudio.com/simulate_soarm101_by_leisaac/
- 모델/데이터셋 목록: https://docs.nvidia.com/learning/physical-ai/sim-to-real-so-101/latest/datasets-and-models.html
