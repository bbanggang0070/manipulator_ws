# bi-manipulator cleanup — 계획 점검

작성 2026-10-14 · 하드웨어 준비됨 · 전달 방식 = 그리퍼 대 그리퍼 직접

---

## 0. 조사한 것 — 좋은 소식과 나쁜 소식

**좋은 소식.** `lerobot`에 이미 `BiSOFollower`/`BiSOLeader`가 있다(`lerobot/robots/bi_so_follower`,
`lerobot/teleoperators/bi_so_leader`). 각각 독립된 `SOFollower`/`SOLeader` 두 개를
`left_`/`right_` 접두사로 묶는 얇은 래퍼라, **로봇 제어 레이어는 직접 짤 필요가 없다.**
CLI 인자도 확인했다 — `--robot.left_arm_config.port` / `--robot.right_arm_config.port`
(teleop 쪽도 동일 패턴).

GR00T도 `EmbodimentTag`에 GR1·Unitree G1 같은 양팔 로봇이 이미 있어 **아키텍처가
다중 관절그룹을 원천적으로 지원**한다.

**나쁜 소식.** NVIDIA가 내놓은 예제는 `examples/SO100/so100_config.py` 하나뿐이고
단일팔(`single_arm`+`gripper`, 6차원)이다. **양팔용 modality config는 없다 —
우리가 설계해야 한다.** 그리고 상태/액션 차원이 6→12로 바뀌므로, 지금 쓰는
`checkpoint-30000`에서 이어받을 수 없다 — **파운데이션에서 다시 새로** 시작해야
한다(지금까지 계속 지켜온 규칙과 같은 이유다).

udev 규칙도 지금은 USB 시리얼 1개씩(LEADER·FOLLOWER) 고정돼 있어, 장치 4개로
다시 짜야 한다.

---

## 1. 캘리브레이션·텔레오퍼레이션

### 1-1. udev — 장치 4개로 확장

```bash
# 각 팔을 하나씩 꽂아 시리얼을 알아낸다(기존 LEADER/FOLLOWER 잡을 때 쓴 방법과 동일)
udevadm info -a -n /dev/ttyACM0 | grep serial
```

`/etc/udev/rules.d/`에 4줄 추가:

```
SYMLINK+="ttyLEADER_L"   # 왼팔 리더
SYMLINK+="ttyLEADER_R"   # 오른팔 리더
SYMLINK+="ttyFOLLOWER_L" # 왼팔 팔로워
SYMLINK+="ttyFOLLOWER_R" # 오른팔 팔로워
```

⚠️ 기존 `ttyLEADER`/`ttyFOLLOWER`(단일팔)는 **건드리지 않는다** — 지금 돌아가는
파이프라인(v3 평가, 색지 교체 검증)이 계속 그 이름을 쓴다. 양팔용은 전부 새 이름으로.

### 1-2. 캘리브레이션

```bash
uv run lerobot-calibrate \
  --robot.type=bi_so_follower \
  --robot.left_arm_config.port=/dev/ttyFOLLOWER_L \
  --robot.right_arm_config.port=/dev/ttyFOLLOWER_R \
  --robot.id=bi_follower

uv run lerobot-calibrate \
  --teleop.type=bi_so_leader \
  --teleop.left_arm_config.port=/dev/ttyLEADER_L \
  --teleop.right_arm_config.port=/dev/ttyLEADER_R \
  --teleop.id=bi_leader
```

`BiSOFollower.name == "bi_so_follower"`라 캘리브레이션이 `calibration/robots/
bi_so_follower/`(팔로워), `calibration/teleoperators/bi_so_leader/`(리더)
아래 저장된다 — 단일팔 캘리브레이션과 폴더가 겹치지 않는다. 기존
`calib_fingerprint.py`는 `LIVE` 목록에 이 두 경로를 추가하면 그대로 재사용된다.

### 1-3. ⚠️ 확인이 필요한 것 — 한 사람이 양손으로 리더 2개를 동시에 조작

`BiSOLeader`는 한 텔레옵 객체가 두 팔을 동시에 읽는다. **물리적으로 한 사람이
양손에 리더암을 하나씩 쥐고 동시에 조작**해야 한다는 뜻이다. 특히 "전달" 구간은
두 팔이 **동시에, 서로 맞춰서** 움직여야 하는 가장 어려운 서브스킬이다 — 오른손으로
오른팔 리더를 옮기면서 동시에 왼손으로 왼팔 리더를 맞은편으로 가져가 그리퍼를
닫는 타이밍을 맞춰야 한다.

**먼저 돌려볼 것**: 본 수집 전에 `lerobot-teleoperate`로 10분 정도 혼자 양손
조작을 연습해 본다. 너무 어려우면 대안은 둘이다 — ① 두 사람이 한 팔씩 맡아
구두로 타이밍을 맞추는 방법(동작은 느려지지만 수집은 가능), ② 전달 방식을
"중간 스테이징"으로 바꾸는 방법(처음에 선택 안 하신 쪽이지만, 한 사람 조작이
너무 어려우면 재고할 만하다).

### 1-4. 작업공간 배치

오른팔의 집는 영역과 왼팔의 선반(4칸)이 모두 각자 리치 안에 있어야 하고,
**두 그리퍼가 만나는 전달 지점이 양팔 리치의 겹치는 구간**이어야 한다.
기존 리치 확인 도구(`view_cams.py`, 텔레옵으로 넣어보기)를 양팔 버전으로
그대로 쓸 수 있다 — 실제 배치하시면서 전달 지점이 자연스럽게 나오는지부터
확인해 주시면, 그 지점을 기준으로 카메라 위치를 잡겠다.

---

## 2. 태스크 설계

```
오른팔: 테이블 위 물체 중 지시한 것을 집는다
   ↓ (그리퍼 대 그리퍼 전달)
왼팔  : 전달받아 지시한 색 칸(4칸 선반, 기존 black·cyan·pink·white 그대로)에 넣는다
```

**지시문 하나가 양팔을 동시에 조건화한다** — 기존과 같은 한 문장
(`"Put the {물체} into the {색} bin"`)이 오른팔에는 "어떤 물체"를,
왼팔에는 "어느 칸"을 알려준다. 이건 지금까지 **따로 검증된 두 능력**
(물체 축 70~90%, 목적지 축 96%)을 **한 에피소드 안에서 동시에** 요구하는
구성이라, 복잡도가 자연스럽게 올라간다 — 새 능력을 추가하는 게 아니라
기존 두 능력을 한 파이프라인으로 합치는 것이다.

물체 10종·칸 4색은 **그대로 유지**를 권한다. 바뀌는 변수(양팔·전달)를
하나만 넣어야 뭐가 문제인지 구분된다 — 물체·색까지 같이 바꾸면 실패
원인이 양팔 때문인지 새 물체/색 때문인지 못 가른다(이 프로젝트가 매번
지켜온 원칙과 같다).

### 2-1. 카메라 — 최소 3대 제안

| 카메라 | 보는 곳 |
|---|---|
| top | 전체(오른팔 집는 영역 + 왼팔 선반 + 전달 지점) |
| wrist_right | 오른팔 파지 시점 |
| wrist_left | 왼팔 파지·배치 시점 |

비전 토큰이 2대→3대로 늘어 학습 시간이 다소 늘지만(해상도는 그대로 256이므로
640 실험 때처럼 급격하진 않다), 전달 순간을 양쪽 wrist가 다 보고 있어야
"잘 받았는지"를 모델도 판정기도 알 수 있다.

### 2-2. 판정 — 에피소드가 이제 3단계다

| 단계 | 판정 |
|---|---|
| 오른팔 파지 | 지시한 물체를 집었는가 (기존과 동일) |
| **전달** | 물체가 왼팔로 넘어갔는가 — **떨어뜨림**이 새로운 실패 유형 |
| 왼팔 배치 | 지시한 칸에 넣었는가 (기존과 동일) |

`cleanup_eval.py`의 "집은 물체"/"들어간 칸" 2칸 기록을 **3칸**으로 늘려야
한다 — `picked`(오른팔)·`handoff`(전달 성공 여부)·`landed`(왼팔). 전달
실패를 분모에서 빼는 것도 지금까지의 원칙(조작 실패를 분모에서 뺀다)과
같다 — 목적지 축은 "전달까지 성공한 시행 중" 비율로 재야 공정하다.

---

## 3. 데이터셋 수집 계획

### 3-1. 규모 — 파일럿 먼저

서브스킬이 하나 늘었으니(파지→**전달**→배치) 단일팔 370ep보다 더 필요할
가능성이 크다. 다만 바로 큰 수집에 들어가지 않는다 — 지금까지 이 프로젝트가
매번 그래왔듯, **작게 돌려 파이프라인 자체가 맞는지부터 확인**한다.

| 단계 | 규모 | 목적 |
|---|---|---|
| 파일럿 | **40~60ep** | modality config·변환·학습이 안 깨지는지, 전달 성공률이 수집 단계에서부터 합리적인지 |
| 본 수집 | 파일럿 결과 보고 결정(300~400ep 예상) | — |

파일럿에서 특히 봐야 하는 것: **전달 성공률 자체**(사람이 직접 조작해도
몇 %나 떨어뜨리는지). 이게 낮으면(예: 50% 미만) 데이터 자체가 "실패
시연"을 많이 포함하게 되어, 그걸로 학습해도 실패를 배운다 — 그 경우
1-3의 대안(중간 스테이징)으로 돌아가는 걸 고려해야 한다.

### 3-2. 계획표 구조 — 기존 자산 재사용

`gen_real_lang_plan.py`의 OBJECTS·EXCLUSIVE·SLOTS·대응쌍 로직을 그대로
가져온다. 바뀌는 건 **시연 규칙**뿐이다:

- 놓은 뒤 곧장 rest 복귀(이번에는 **양팔 다** rest로) — v3에서 겪은 "모델이
  멈추는 법을 못 배운다" 문제가 양팔에서는 **두 배로** 치명적일 수 있다
  (한쪽만 멈추고 한쪽은 계속 움직이는 경우가 새로 생길 수 있다)
- 전달 지점에서 **두 그리퍼가 확실히 맞물린 뒤** 오른팔이 놓는 것 —
  시연에서부터 서두르면 데이터에 "놓쳤다 다시 집는" 장면이 섞인다
  (기존 재파지 문제와 같은 종류, 이번엔 전달 단계에서)

### 3-3. 검증기 확장

`verify_real_lang_dataset.py`에 **전달 성공률**을 새 지표로 추가한다
(재파지율을 쟀던 것과 같은 방식 — 그리퍼 궤적에서 "오른팔 닫힘→왼팔
닫힘→오른팔 열림" 패턴을 찾는다). ⚠️ 그리퍼 궤적 기반 지표는 이 세션에서
**이미 네 번 틀렸다** — `episode_events.py`처럼 **정답 데이터로 먼저
검증**하지 않고는 게이트에 넣지 않는다.

---

## 4. 학습·추론 계획

### 4-1. modality config (신규 설계)

```python
bi_so100_config = {
    "video": ModalityConfig(delta_indices=[0],
        modality_keys=["top", "wrist_right", "wrist_left"]),
    "state": ModalityConfig(delta_indices=[0],
        modality_keys=["right_arm", "right_gripper", "left_arm", "left_gripper"]),
    "action": ModalityConfig(delta_indices=list(range(16)),
        modality_keys=["right_arm", "right_gripper", "left_arm", "left_gripper"],
        action_configs=[...동일 패턴 4개...]),
    "language": ModalityConfig(...),
}
```

`BiSOFollower`가 주는 키(`left_shoulder_pan.pos` 등)를 `right_arm`(5)·
`right_gripper`(1)·`left_arm`(5)·`left_gripper`(1)로 재배열하는 변환이
클라이언트(`eval_lerobot.py` 양팔판)와 수집측 둘 다에 필요하다.

### 4-2. 학습

```
출발점 : nvidia/GR00T-N1.6-3B (파운데이션에서 새로 — 필수)
EPOCHS : 8 로 시작(기존과 동일 근거) — 서브스킬이 늘었으니 결과 보고 조정
```

색 증강(`CJ_HUE=0.015`)·`--save-steps`로 체크포인트 곡선 남기기 등 기존
`train_cleanup_real.sh`의 교훈은 전부 그대로 가져온다. 카메라 3대로 늘어난
만큼 호스트 RAM 여유를 다시 재는 게 안전하다(640 해상도 실험 때 RAM이
병목이었던 전례가 있다).

### 4-3. 추론

로컬(5070 Ti) 서빙을 그대로 쓴다 — `serve_local.sh`는 체크포인트 경로만
바꾸면 재사용된다. 클라이언트(`eval_lerobot.py`)는 양팔판이 필요하다:
카메라 3대 읽기, 12차원 상태 전송, 12차원 액션을 양팔에 분배해 전송.
ensemble·`STOP_ON_REST`·`REST_BACK_JOINT` 로직은 그대로 두되, **양팔 모두**
rest 조건을 만족해야 종료되도록 확장해야 한다(한쪽만 보고 멈추면 다른 쪽이
계속 움직이는 채로 "완료" 처리될 위험).

평가 지표는 §2-2의 3단계를 그대로 따른다 — 물체축·전달성공률·목적지축을
**따로** 기록한다(이 프로젝트 전체를 관통하는 원칙).

---

## 5. 순서 요약

1. udev 4장치 확장 → 캘리브레이션 (§1-2)
2. **혼자 양손 텔레옵 연습 10분** → 되는지 먼저 확인 (§1-3, 안 되면 설계 재검토)
3. 작업공간 배치(오른팔 집는 영역·왼팔 선반·전달 지점) 확정
4. 계획표 생성기를 양팔용으로 확장(기존 로직 재사용)
5. 파일럿 40~60ep 수집 — **전달 성공률부터 확인**
6. modality config·변환 파이프라인 스모크 테스트(소량으로 학습 1step만 돌려 안 깨지는지)
7. 파일럿 결과 보고 본 수집 규모 결정
8. 본 수집 → 학습(파운데이션에서, 8 epoch 시작) → 평가(3단계 분리 측정)

2번이 사실상 전체 설계의 분기점이다 — 거기서 막히면 3-1의 대안으로 돌아간다.

---

## 6. 파일럿 결과 → 본 수집 규모 결정 (2026-10-15)

**파일럿 50ep 결과**: 전달 성공률 **100%**(`handoff_events.py --report`, 50/50 검출·
0건 실패) — 여유(gap) 최소 0.67s·중앙값 1.47s. §3-1이 걱정하던 "전달 실패 시연이
섞인다"(50% 미만이면 중간 스테이징 재고) 상황이 아니다. **1-3의 대안(중간
스테이징)은 불필요 — 그리퍼 대 그리퍼 직접 전달 그대로 간다.**

**규모: 300ep로 결정** (파일럿 50 + 추가 250) — 400이 아니라 300을 고른 이유:

- 전달 자체는 **매 에피소드마다** 한 번씩 나온다(물체·칸처럼 조합별로 쪼개지지
  않는다) — 300ep만 돼도 전달 장면은 300번 노출된다. 파일럿에서 이미 깨끗하게
  나온 서브스킬을 위해 수를 더 불릴 근거가 없다.
- 병목은 여전히 물체(8종)×칸(4색) = 32조합이다. 단일팔 v3(370ep·40조합·
  조합당 9~10회)와 **같은 밀도**로 맞추면 32조합×9.4 ≈ 300 — `gen_bi_plan.py`로
  실제 생성해 확인(조합당 최소 9·최대 10회, 칸·물체 분포 균등, 쌍/상호배제
  위반 0건).
- 이 프로젝트가 늘 그래온 방식(v1→v2 250→v3 370, 평가 보고 120 추가)과 같다 —
  처음부터 400을 쏘지 않고 **보수적으로 시작해, 본 수집 학습·평가 후 특정
  병목이 보이면 그때 더 추가**한다.

**계획표**: `gen_bi_plan.py`에 `--base`/`--keep-head`를 추가(`gen_real_lang_plan.py`와
동일한 이어짜기 방식)해 `bi_cleanup_plan.csv`(300행, 앞 50행은 `bi_pilot_plan.csv`와
바이트 단위로 동일)를 생성했다. 이어서 수집:

```bash
cd ~/manipulator_ws/setup/bi/data
PLAN=~/manipulator_ws/manipulator_md/real/bi_cleanup_plan.csv ./record_bi.sh
#   → "51행부터 재개" 가 떠야 정상(collect_progress.txt에 이미 50개 있음)
```

수집은 기존 `bi_cleanup` 데이터셋 디렉터리에 이어서 쌓인다(새 데이터셋 이름
불필요 — v2→v3가 그랬듯 같은 이름으로 이어간다). 50ep마다
`handoff_events.py --report`로 전달 성공률이 유지되는지 중간 점검할 것.

---

## 7. 평가 파이프라인 (2026-10-15) — 50ep 체크포인트로 먼저 추론

300ep 본 수집을 기다리지 않고, **지금 가진 50ep 체크포인트(`checkpoint-7500`)로
먼저 추론해 방향이 맞는지 판단**하기로 했다(나머지 250ep는 수집 계속 진행).
§4-3이 남겨둔 "양팔판 eval_lerobot.py가 필요하다"를 여기서 채운다.

**만든 것** (모두 `setup/gr00t/`의 단일팔 자산을 최대한 재사용 — 로봇별 부분만 교체):

| 파일 | 역할 | 단일팔 원본과 다른 점 |
|---|---|---|
| `setup/bi/gr00t/goto_home_bi.py` | 추론 전 rest 복귀 | TARGET을 bi_cleanup 50ep frame0 평균(12관절)으로 재계산 |
| `setup/bi/gr00t/client/eval_lerobot_bi.py` | 추론 클라이언트 | 카메라 3대→top/wrist_left/wrist_right 재매핑, state 12차원→4그룹 분리. ensemble·async·rerun·STOP_ON_REST 로직은 **그대로 재사용**(robot_state_keys 12개를 그대로 돌기 때문에 바꿀 필요가 없었다 — 양팔 모두 rest 복귀해야 끝나는 것도 공짜로 보장됨) |
| `setup/bi/gr00t/infer_gr00t_bi_local.sh` | 추론 실행 | record_bi.sh와 같은 카메라 장치(`/dev/cam_top`·`/dev/cam_wrist`·`/dev/cam_wrist_right`) |
| `setup/bi/gr00t/home_then_infer_bi.sh` | 홈 복귀 후 추론 자동 시작 | 그대로 패턴만 이식 |

**서버(`serve_local.sh`)는 수정 없이 그대로 재사용된다** — `serve_blocktask_realclient.py`가
체크포인트의 `processor/` 에 저장된 modality config를 읽어 쓰므로(학습 시 등록한
`bi_so100_config.py`를 다시 import할 필요가 없다), 모델 경로만 바꾸면 양팔 체크포인트도
그대로 서빙된다 — 실제로 Gr00tPolicy 생성자 코드를 확인해 검증함.

**체크포인트 이동**: 5090(학습)→로컬 5070 Ti(서빙) rsync 13GB, WiFi 링크라 느리다
(실측 1.3~1.8MB/s, 완료까지 약 2시간) — 백그라운드로 진행.

**사용법**:
```bash
# 1) 체크포인트 동기화 완료 후, 로컬에서 서버 기동
cd ~/manipulator_ws/setup/gr00t
./serve_local.sh gr00t_bi_cleanup_n16_8bit/checkpoint-7500

# 2) 양팔 로봇 연결 상태에서 홈 복귀 + 추론 자동 시작
cd ~/manipulator_ws/setup/bi/gr00t
SERVER_HOST=127.0.0.1 ./home_then_infer_bi.sh
#   기본 지시문: "Put the red marker into the black bin" (LANG_INSTRUCTION으로 바꿀 것)
```

**3단계 분리 판정기 (2026-10-15 추가)** — `setup/bi/data/cleanup_eval_bi.py`
(`cleanup_eval.py`의 양팔판) + 시행 러너 `setup/bi/gr00t/run_eval_real_bi.sh`.
- `plan`: 계획표 `bi_cleanup_eval_plan.csv` (12그룹=36시행, dest 4연속 6·obj 쌍 6) — 물체 8종·칸 4색·문형은 `gen_bi_plan.py`와 동일
- `log`: 시행마다 터미널에 **놓을 물체(오른팔 영역)·지시문·정답**을 띄우고 Enter 시 로봇 자동 실행 →
  끝나면 rest 복귀 → `picked`(우완)·`handoff`(성공/실패)·`landed`(좌완) 3칸 입력
- `report`: 조작/전달 신뢰도(집음→전달→넣음, 각 단계 분모는 직전 단계 성공) · 물체 축 · 목적지 축
  (**분모 = 전달까지 성공한 시행**) · 대응쌍
- 기본값: `STOP_ON_REST=1`, `RERUN=0`, `--max-sec 150`(단일팔 60s보다 여유 — **실측 전 추정**),
  `ENSEMBLE_W=0.8`(단일팔 cleanup 실측 최적값을 그대로 채택 — 원본 기본 0.1은 옛 청크 비중이 커 얼어붙음.
  양팔 전용 스윕은 미실시)
- `home_then_infer_bi.sh`: TOL 기본 2.0→**3.0**(12관절 동시 수렴이 어려움), 홈 이동 로그 실시간 출력(tee)

```bash
cd ~/manipulator_ws/setup/gr00t && ./serve_local.sh gr00t_bi_cleanup_n16_8bit/checkpoint-7500
cd ~/manipulator_ws/setup/bi/data && python3 cleanup_eval_bi.py log
python3 cleanup_eval_bi.py report
```

## 8. 50ep 추론 결과 → 칸 배치 교체 수집 (2026-10-15)

**50ep 체크포인트 추론**: 성공 0회(시행 1번을 6회 반복, 결과 CSV 미기록). 로그로 본 것 —
추론 80~90ms·12관절 명령 정상(파이프라인 문제 아님), 오른팔은 매번 물체 쪽으로 크게 뻗음,
t03·t05는 왼팔도 크게 움직임(전달 시도로 추정, 영상 미확인). → 데이터 부족으로 판단, 수집 재개.

**칸 배치 교체**: 색이 아니라 **위치를 외우는 느낌**(사용자 관찰) — 단일팔 색지 교체 검증에서
"왼쪽 기본값"으로 결론 난 것과 같은 종류의 위험. 그래서 **50ep마다 칸 색 배치를 바꾼다.**
- 파일럿 1~50행 실제 배치 = `1번 black · 2번 white · 3번 pink · 4번 cyan` (사용자 확인) —
  위치 번호는 현재 칸 배치를 보고 새로 매긴 것이라 기존 계획표의 slot 번호(cyan=2·white=4)와는 무관하다.
  1~50행 slot은 이 번호 체계에 맞춰 다시 적었다(색은 그대로, 학습 데이터에는 slot이 들어가지 않음)
- `gen_bi_plan.py --layout-every 50 --base-layout black,white,pink,cyan` — 블록 간 **모든 색이 자리를 옮기고**
  (완전순열), 색×위치가 고르게(6블록에서 색마다 각 위치 1~2블록), 같은 이웃 쌍 반복을 피하도록 고른다
  (순환 이동만 쓰면 "black 옆엔 white" 같은 상대 순서가 남아 외울 수 있다)
- 배치는 그룹(대응쌍) 중간에서 바꾸지 않는다 — 블록 경계를 다음 NEW 행으로 미룸
- 물체·타깃·지시문·그룹은 기존 300행 계획과 **동일**(slot 번호와 `layout` 열만 추가/변경)
- `record_bi.sh`: 배치가 바뀌는 행(+세션 첫 행)에서 배너를 띄우고 Enter로 확인받는다

| 행 | 칸 배치 |
|---|---|
| 1~50 | 1 black · 2 white · 3 pink · 4 cyan (수집 완료) |
| 51~101 | 1 cyan · 2 pink · 3 white · 4 black |
| 102~150 | 1 black · 2 cyan · 3 pink · 4 white |
| 151~200 | 1 white · 2 pink · 3 black · 4 cyan |
| 201~251 | 1 cyan · 2 black · 3 white · 4 pink |
| 252~300 | 1 pink · 2 white · 3 cyan · 4 black |

⚠️ 평가도 배치를 바꿔 가며 해야 위치 암기와 색 읽기를 가를 수 있다 — `cleanup_eval_bi.py`에는
아직 배치 교체가 없다(단일팔 `cleanup_eval.py`의 `layout_hint` 배너 방식을 가져오면 된다).

## 9. 151ep 중간 학습 (2026-10-15)

300ep를 다 모으기 전에 **151ep(178,519 frames)로 한 번 학습**한다 — 나머지 149ep는 2026-10-16에 이어서 수집.
- 151ep 구성: 배치 블록 1~3 전부 + 4번째 블록(1 white · 2 pink · 3 black · 4 cyan) 첫 행 1개.
  (88·89번 ep는 잘못 저장돼 삭제 후 재수집 — info.json·stats.json·진행 기록을 남은 ep 기준으로 바로잡음)
- 파운데이션에서 새로, lr 1e-4, batch 64는 50ep 학습과 같고 **EPOCHS만 8→10**(사용자 결정).
  10 epoch = 28,000 step(3,500 step마다 저장). 50ep 실측 속도(1,000 step당 약 48분)로 **약 22시간**.
- 출력 이름을 `gr00t_bi_cleanup151_n16_8bit`로 분리 — 50ep 체크포인트(`gr00t_bi_cleanup_n16_8bit`)를 덮지 않는다.
- 5090의 `heongyu/bi_cleanup`은 `prepare_bi_cleanup.sh`가 151ep로 **교체**한다(50ep 학습은 이미 끝났으므로 영향 없음).

```bash
cd ~/manipulator_ws/setup/bi/data && ./prepare_bi_cleanup.sh all          # 로컬: 전송·변환·검증
ssh 5090 'cd ~/gr00t_remote/scripts && EPOCHS=10 OUT_NAME=gr00t_bi_cleanup151_n16_8bit ./train_bi_cleanup.sh'
```

**2026-10-16 할 일**
1. 152행부터 수집 재개(4번째 배치 블록 1 white · 2 pink · 3 black · 4 cyan) → 300ep까지.
2. 151ep 모델 추론 — 두 체크포인트를 간단히 비교:
   - `checkpoint-28000` (10 epoch, 최종)
   - `checkpoint-21000` (7.5 epoch — 8 epoch에 가장 가까운 저장본. 22,400 step에 가장 가까움)
   - ⚠️ `checkpoint-21000`은 "8 epoch으로 끝까지 학습한 모델"과 같지 않다 — 학습률이 아직 다 줄지
     않은 중간 상태다. 그래도 epoch 수에 따른 경향을 보기에는 충분하다.
   - 체크포인트는 5090→로컬 rsync(각 약 10GB, WiFi 약 2시간) 필요 — 학습 종료 전이라도 21000은 먼저 받을 수 있다.

## 10. 151ep 추론 중 발견한 문제와 수정 (2026-10-16)

| 문제 | 원인 | 수정 |
|---|---|---|
| 작업을 끝내고 rest 로 돌아왔는데 150s 타임아웃까지 대기 (ck21000 trial02) | 자동 종료가 "시작 자세 6° 이내" 기준 — 시작 순간 처진 오른팔 elbow(103°)가 기준이 됨. 300ep 사람 시연도 이 기준이면 43%만 통과 | `eval_lerobot_bi.py`: "크게 움직인 뒤 시작 자세 20° 이내 + 2s 동안 전 관절 움직임 < 1.5°" 로 변경 (`REST_BACK_DEG`·`REST_STILL_DEG`·`REST_HOLD_SEC`). 기존 로그 재생 시 trial01 69→46s, trial02 150→52s |
| 추론 시작 시 오른팔 elbow 처짐 | `goto_home_bi.py` 종료 시 disconnect 가 토크를 끔(lerobot 기본 `disable_torque_on_disconnect=True`) → 추론 연결 전까지 중력에 처짐 | 토크 유지 + 홈 자세를 300ep 첫 프레임 중앙값으로 재계산(`home_pose_bi.py` 로 분리, 두 스크립트 공용) |
| 타임아웃 등으로 시행이 끝나면 팔이 바닥으로 떨어짐 | 추론 프로세스 종료 시 `Robot.__del__` → disconnect → 토크 해제 | 모든 종료 경로(q·타임아웃·자동 종료·Ctrl+C·예외)에서 **그 자리 정지 0.5s → 관절 직선 보간으로 rest 복귀(약 30°/s, `REST_DEG_PER_STEP`) → 토크 유지**. 복귀 실패 시 종료 코드 3 → `cleanup_eval_bi.py` 가 "팔 받치고 Enter" 안내 |
| 가망 없는 시행도 타임아웃까지 기다려야 함 | — | 추론 중 `q` 한 번(Enter 불필요)으로 시행 종료 → 위 정지·복귀 후 결과 입력. Ctrl+C 도 배치를 끊지 않고 같은 경로 |
| Ctrl+C 한 번에 SIGINT 두 번 도착 | `uv run` 이 터미널 SIGINT 를 자식에 한 번 더 전달(uv 0.11 실측) | 0.5s 안의 중복 SIGINT 무시. 복귀 중 다시 누른 Ctrl+C 는 복귀를 멈추고 그 자리 토크 유지 |

- 남은 위험: rest 복귀는 관절 공간 직선 경로라 선반·칸 안에 팔이 있으면 스칠 수 있다(장애물 회피 없음) — 첫 시행들은 e-stop 에 손을 둘 것.
- 시행이 모두 끝나도 팔은 rest 에서 토크 유지 상태로 남는다(떨어지지 않음).
