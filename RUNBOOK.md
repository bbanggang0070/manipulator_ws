# RUNBOOK — 양팔 분류 수집 → 학습 → 추론 → 평가 실행 순서

최종 과제(P6 양팔 분류: 오른팔 물체 분류 → 전달 → 왼팔 색 분류)를 **처음부터 같은 방법으로**
다시 돌리기 위한 명령 순서다. 과제 설명은 [README.md](README.md), 스크립트 지도는
[setup/README.md](setup/README.md), 기록과 근거는 [bi_manipulator_plan.md](manipulator_md/p6_real_bimanual/bi_manipulator_plan.md).

```
[로컬]  1 장치·캘리브레이션 → 2 계획표 → 3 수집 → 4 검증 ─┐
[5090]                                    5 전송·변환 → 6 학습 ─┐
[로컬]                         7 체크포인트 가져오기 → 8 서빙 → 9 평가 → 10 분석
```

- 로컬 = 리더·팔로워·카메라가 연결된 5070 Ti, 5090 = 학습 서버(ssh 별칭 `5090`).
- 명령은 모두 저장소 루트(`~/manipulator_ws`) 기준 경로로 적었다.
- 각 스크립트 머리말에 옵션과 그렇게 만든 이유가 있다 — 막히면 먼저 머리말을 본다.

---

## 0. 한 번만 하는 준비

### 로컬

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh          # uv
cd ~/manipulator_ws/envs/lerobot && uv sync              # lerobot 0.4.4 + torch 2.10 cu128
sudo apt install ffmpeg
cd ~/blocktask_ws/Sim-to-Real-SO-101-Workshop && ./docker/real/build.sh blackwell   # 서빙 이미지(real-robot)
```

### 5090

| 필요한 것 | 위치 | 비고 |
|---|---|---|
| 학습 이미지 `real-robot-train8` | docker | real-robot + bitsandbytes(8-bit 옵티마이저) |
| Isaac-GR00T 저장소 | `~/gr00t_remote/Isaac-GR00T` | 양팔 설정 2개를 `examples/BiSO100/` 에 둔다 (아래) |
| 학습·변환 보조 스크립트 | `~/gr00t_remote/scripts/` | `train_bi_cleanup.sh`, `fix_stats_for_gr00t.py` |

```bash
# 로컬에서 5090 으로 복사
ssh 5090 'mkdir -p ~/gr00t_remote/Isaac-GR00T/examples/BiSO100 ~/gr00t_remote/scripts'
scp setup/p6_real_bimanual/gr00t/bi_so100_config.py setup/p6_real_bimanual/gr00t/modality.json \
    5090:~/gr00t_remote/Isaac-GR00T/examples/BiSO100/
scp setup/p6_real_bimanual/gr00t/train_bi_cleanup.sh setup/gr00t/fix_stats_for_gr00t.py \
    5090:~/gr00t_remote/scripts/
```

---

## 1. 장치·캘리브레이션 (로컬)

### 1-1. 장치 이름 고정 (udev)

팔 4대·카메라 3대가 USB 순서와 상관없이 같은 이름으로 잡히게 한다.

```bash
setup/hardware/identify_devices.sh        # 연결된 장치의 시리얼 확인 → 99-lerobot.rules 에 채움
sudo cp setup/hardware/99-lerobot.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
ls -l /dev/ttyLEADER_L /dev/ttyLEADER_R /dev/ttyFOLLOWER_L /dev/ttyFOLLOWER_R \
      /dev/cam_top /dev/cam_wrist /dev/cam_wrist_right          # 7개 모두 보여야 한다
```

| 이름 | 장치 |
|---|---|
| `/dev/ttyFOLLOWER_L` · `/dev/ttyFOLLOWER_R` | 왼팔·오른팔 팔로워 |
| `/dev/ttyLEADER_L` · `/dev/ttyLEADER_R` | 왼팔·오른팔 리더 |
| `/dev/cam_top` · `/dev/cam_wrist` · `/dev/cam_wrist_right` | top · 왼손목 · 오른손목 카메라 |

### 1-2. 캘리브레이션

```bash
cd ~/manipulator_ws/envs/lerobot
uv run lerobot-calibrate --robot.type=bi_so_follower \
  --robot.left_arm_config.port=/dev/ttyFOLLOWER_L --robot.right_arm_config.port=/dev/ttyFOLLOWER_R \
  --robot.id=bi_follower
uv run lerobot-calibrate --teleop.type=bi_so_leader \
  --teleop.left_arm_config.port=/dev/ttyLEADER_L --teleop.right_arm_config.port=/dev/ttyLEADER_R \
  --teleop.id=bi_leader
```

> ⚠️ **수집을 시작한 뒤에는 캘리브레이션을 다시 하지 않는다.** 바뀌면 같은 자세가 다른 숫자로 기록돼
> 데이터가 섞인다. 수집 스크립트가 시작할 때마다 캘리브레이션 지문을 대조해 바뀌었으면 멈춘다.

### 1-3. 양손 조작 연습 · 작업 공간 확인

한 사람이 양손에 리더를 하나씩 쥐고 조작한다. 본 수집 전에 10분 정도 연습하면서, 오른팔이 물체 영역 전체에,
왼팔이 칸 4개 전부에, 두 그리퍼가 전달 지점에서 만날 수 있는지 확인한다.

```bash
cd ~/manipulator_ws/envs/lerobot
uv run lerobot-teleoperate --robot.type=bi_so_follower \
  --robot.left_arm_config.port=/dev/ttyFOLLOWER_L --robot.right_arm_config.port=/dev/ttyFOLLOWER_R \
  --robot.id=bi_follower \
  --teleop.type=bi_so_leader \
  --teleop.left_arm_config.port=/dev/ttyLEADER_L --teleop.right_arm_config.port=/dev/ttyLEADER_R \
  --teleop.id=bi_leader
```

---

## 2. 수집 계획표 (로컬)

에피소드마다 **놓을 물체 · 지시 물체 · 목적지 칸 · 칸 색 배치**를 미리 정한다. 수집 중에는 화면에 뜬 대로만 놓는다.

**같은 데이터를 다시 모을 때** — 새로 만들지 않는다. 저장소의
`manipulator_md/p6_real_bimanual/bi_cleanup_plan.csv` 가 실제로 쓴 300행 계획표이고, 수집 스크립트의 기본값이다.

**새 계획표가 필요할 때** — 기존 파일을 덮어쓰지 않게 새 이름으로 만들고, 수집할 때 `PLAN=` 으로 지정한다.

```bash
cd ~/manipulator_ws/setup/p6_real_bimanual/data
python3 gen_bi_plan.py --episodes 300 --layout-every 50 \
  --out ~/manipulator_ws/manipulator_md/p6_real_bimanual/bi_cleanup_plan_new.csv
```

- `--layout-every 50`: 50ep 마다 칸 색 배치를 바꾼다(모든 색이 자리를 옮기도록). 색 ↔ 위치 결합을 끊기 위해서다.

---

## 3. 수집 (로컬)

```bash
cd ~/manipulator_ws/setup/p6_real_bimanual/data
./record_bi.sh                   # 처음이면 1행부터, 중단 후 다시 실행하면 이어서
#   START=11 ./record_bi.sh      # 특정 행부터
#   EP_TIME=120 ./record_bi.sh   # 에피소드 시간 늘리기 (기본 90초)
#   PLAN=<새 계획표.csv> ./record_bi.sh   # 2단계에서 새로 만든 계획표로 수집할 때
```

진행 순서 (스크립트가 안내한다):

1. 캘리브레이션 지문 대조 — 다르면 멈춘다.
2. 칸 배치가 바뀌는 행에서 **새 칸 배치**를 보여 준다 → 칸을 바꾸고 Enter.
3. 매 에피소드: 화면에 뜬 물체만 놓고 Enter → 리더가 rest 자세인지 확인(rest 게이트) → 녹화.
4. 시연: 오른팔로 지시 물체를 집어 → 왼팔 그리퍼에 건네고 → **왼팔이 확실히 쥔 뒤** 오른팔이 놓고 →
   왼팔이 지시 칸에 넣고 → **두 팔 모두** rest 로 돌아와 1~2초 멈춘다.

- 저장 위치: `~/blocktask_ws/Sim-to-Real-SO-101-Workshop/datasets/_train/bi_cleanup` (LeRobot v3.0, HF 업로드 안 함)
- 진행 기록: 같은 폴더의 `collect_progress.txt` — 계획표 몇 행까지 했는지
- **새 데이터셋으로 모을 때**: 기존 `bi_cleanup` 과 섞이지 않게 `DSNAME=<새 이름>` 을 붙인다.
  같은 값을 5번(`prepare_bi_cleanup.sh`)·6번(`train_bi_cleanup.sh`)에도 똑같이 붙여야 한다.
- 잘못 찍은 에피소드는 녹화 중 lerobot 재녹화 키로 다시 찍는다.

---

## 4. 수집본 검증 (로컬)

```bash
cd ~/manipulator_ws/envs/lerobot
DS=~/blocktask_ws/Sim-to-Real-SO-101-Workshop/datasets/_train/bi_cleanup
uv run python ../../setup/p6_real_bimanual/data/handoff_events.py --report $DS     # 에피소드마다 전달 시점·성공 검출
python3 ../../setup/p5_real_cleanup/calib_fingerprint.py --check $DS               # 수집 전후 캘리브레이션 일치
```

통과 기준: 전달이 모든 에피소드에서 검출되고(300/300), 캘리브레이션이 일치하고,
`meta/info.json` 의 에피소드 수가 계획표 진행 행 수와 같을 것.

---

## 5. 5090 전송·변환 (로컬에서 실행)

```bash
cd ~/manipulator_ws/setup/p6_real_bimanual/data
./prepare_bi_cleanup.sh all        # send → convert → check  (단계별: send | convert | check)
```

- **send**: 로컬 v3.0 → 5090 `~/gr00tn16_ws/sim_data/heongyu/bi_cleanup`
- **convert**: 5090 에서 GR00T 용 v2.1 로 변환, `modality.json`(카메라 3대 → top · wrist_left · wrist_right) 배치, stats 정리
- **check**: 학습 전 게이트 — **지시문 32종 · 목적지 4색 · 카메라 3대**가 모두 살아 있어야 통과.
  지시문이 1종으로 접혔다고 나오면 **학습하지 않는다**(언어 신호가 0인 데이터가 된다).

> WiFi 로 5GB 가 넘어 오래 걸린다(약 1MB/s). 이미 보낸 에피소드는 다시 보내지 않으므로 끊기면 다시 실행하면 된다.

---

## 6. 학습 (5090)

```bash
ssh 5090
cd ~/gr00t_remote/scripts
SMOKE=1 ./train_bi_cleanup.sh                                       # 10 step — 설정·데이터가 안 깨지는지 먼저
EPOCHS=10 OUT_NAME=gr00t_bi_cleanup300_n16_8bit ./train_bi_cleanup.sh # 본 학습 (백그라운드 컨테이너로 실행)
docker logs -f gr00t-train-bi                                       # 진행 확인 (Ctrl+C 로 빠져나와도 학습은 계속)
```

| 항목 | 값 |
|---|---|
| 출발점 | `nvidia/GR00T-N1.6-3B` — **항상 파운데이션에서 새로** (이어서 학습하면 언어를 못 배운다, P4) |
| 학습량 | epoch 로 지정 → step 자동 계산 (300ep·10 epoch = 52,000 step, 약 43시간) |
| 배치 | 2 × grad accum 32 = 64, lr 1e-4, 8-bit 옵티마이저 |
| 저장 | `~/gr00tn16_ws/checkpoints/<OUT_NAME>/checkpoint-<step>/` (8번 나눠 저장) |

---

## 7. 체크포인트 가져오기 (로컬)

> **자동으로 하려면** — 학습을 시작한 뒤 아래를 한 번 띄워 두면, 학습이 끝날 때 7·8번(가져오기·로컬 서빙)을 알아서 한다.
> ```bash
> cd ~/manipulator_ws/setup/gr00t
> setsid nohup ./auto_serve_after_train.sh gr00t_bi_cleanup300_n16_8bit checkpoint-52000 \
>     > ~/manipulator_ws/logs/auto_serve.log 2>&1 < /dev/null &
> tail -f ~/manipulator_ws/logs/auto_serve.log      # 진행 확인 · 중단: pkill -f auto_serve_after_train.sh
> ```

체크포인트 파일은 컨테이너가 root 로 만들어서, 먼저 5090 에서 읽기 권한을 열어 준다.
추론에는 optimizer·scheduler 가 필요 없으므로 빼고 받는다(약 9GB).

```bash
M=gr00t_bi_cleanup300_n16_8bit; C=checkpoint-52000
ssh 5090 "docker run --rm --entrypoint /bin/bash -v \$HOME/gr00tn16_ws/checkpoints:/c real-robot-train8 \
  -c 'chmod -R a+rX /c/$M/$C /c/$M/experiment_cfg /c/$M/processor'"
mkdir -p ~/gr00tn16_ws/checkpoints/$M
rsync -a --partial --exclude=optimizer.pt --exclude=scheduler.pt --exclude=rng_state.pth \
  5090:gr00tn16_ws/checkpoints/$M/$C 5090:gr00tn16_ws/checkpoints/$M/experiment_cfg \
  5090:gr00tn16_ws/checkpoints/$M/processor ~/gr00tn16_ws/checkpoints/$M/
```

---

## 8. 서빙 (로컬)

```bash
cd ~/manipulator_ws/setup/gr00t
./serve_local.sh gr00t_bi_cleanup300_n16_8bit/checkpoint-52000   # "준비 완료 — tcp://127.0.0.1:5555" 가 뜨면 OK
#   ./serve_local.sh '' stop    # 서버 끄기 · ./serve_local.sh '' logs  # 로그 보기
```

> 데이터셋을 바꿨다면 홈 자세(`setup/p6_real_bimanual/gr00t/home_pose_bi.py`)를 새 데이터의
> 첫 프레임 상태 중앙값으로 다시 계산한다 — 추론 시작 자세가 학습 시작 분포와 맞아야 한다.

---

## 9. 평가 (로컬)

평가 도구가 시행마다 **놓을 물체·지시문·정답**을 보여 주고, Enter 를 누르면 홈 자세로 이동 → 추론을 실행한다.
끝나면 rest 로 돌아오고, 본 대로 **집은 물체 · 전달 성공 · 들어간 칸** 세 가지를 입력한다.

```bash
cd ~/manipulator_ws/setup/p6_real_bimanual/data
R=~/manipulator_ws/manipulator_md/p6_real_bimanual

# 평가 A — 36시행 (151ep 모델과 같은 시행·같은 칸 배치로 비교)
python3 cleanup_eval_bi.py log --eval-name bi300_A --out $R/bi300_eval_A.csv --rerun

# 평가 B — 60시행 = 평가 A 36 + 학습에 없던 칸 배치 4종 × 6시행
#   앞 36시행은 평가 A 와 같으므로 결과를 복사해 두면 37번부터 이어서 한다 (같은 체크포인트일 때만)
cp $R/bi300_eval_A.csv $R/bi300_eval_B.csv
python3 cleanup_eval_bi.py log --plan $R/bi_cleanup_eval_plan_B.csv \
  --eval-name bi300_B --out $R/bi300_eval_B.csv --rerun
```

시행 중 조작:

| 상황 | 동작 |
|---|---|
| 가망이 없는 시행 | **`q` 한 번** — 그 시행만 끝내고 결과 입력으로 |
| 위험한 동작 | Ctrl+C (그 자리 정지 → rest 복귀) 또는 e-stop |
| 칸 배치가 바뀌는 시행 (평가 B) | 노란 안내가 뜬다 → 칸을 바꾸고 Enter |
| 시행 종료 | 양팔이 rest 근처에서 2초 멈추면 자동 종료, 150초가 지나도 종료 |

- 어떤 이유로 끝나든 팔은 그 자리에 멈춘 뒤 천천히 rest 로 돌아가고 **토크를 유지**한다(떨어지지 않음).
- `--rerun`: 카메라·관절·명령을 실시간으로 본다. 오래 켜 두면 메모리가 쌓이니 중간중간 rerun 창을 닫는다.
- 원격(5090) 서버로 돌리려면 명령 앞에 `SERVER_HOST=<5090 IP>` 를 붙인다(WiFi 지연이 앙상블 동작에 영향을 준다).
- 앙상블 가중치는 `ENSEMBLE_W=0.8`(기본) — 바꿔 비교할 때는 `--eval-name`·`--out` 을 값마다 다르게 준다.
- 영상·csv·`run.json` 은 `inf_video/07_real_eval_bi/<eval-name>/trialNN_tNN/` 에 남는다.

---

## 10. 결과 분석 (로컬)

```bash
cd ~/manipulator_ws/setup/p6_real_bimanual/data
python3 cleanup_eval_bi.py report --out ~/manipulator_ws/manipulator_md/p6_real_bimanual/bi300_eval_A.csv
python3 cleanup_eval_bi.py report --out ~/manipulator_ws/manipulator_md/p6_real_bimanual/bi300_eval_B.csv
```

| 출력 | 읽는 법 |
|---|---|
| 조작/전달 | 무언가 집음 · 전달 성공 · 칸에 넣음 — 언어와 무관한 모터 신뢰도 |
| 물체 축 | 지시한 물체를 집은 비율 vs 우연(화면 물체 수로 계산) |
| 목적지 축 | 지시 × 착지 표, 우연 25% 대비 검정, 한 칸 쏠림 경고 |
| 배치별 (평가 B) | 학습에 있던 배치 vs 없던 배치, **착지 위치(칸 번호) 분포** — 색이 아니라 자리로 가면 여기서 쏠린다 |
| 대응쌍 | 같은 배치에서 지시만 바꿨을 때 결과가 달라졌는가 — 지시문을 따랐다는 직접 신호 |

판정과 다음 수는 [PRESENTATION.md §3 W6](PRESENTATION.md) 의 판정표를 따른다.

---

## 자주 겪는 문제

| 증상 | 원인 · 조치 |
|---|---|
| 카메라 영상이 깨지거나 멈춤 | `fourcc: MJPG` 확인, 카메라 3대를 같은 USB 허브에 몰지 않는다 |
| 수집 시작 시 "캘리브레이션 불일치" | 수집 중 캘리브레이션이 바뀜 — 의도한 교체가 아니면 원래 파일로 되돌린다 |
| 홈 이동이 오차 기준에 계속 못 미침 | `TOL=4.0` 처럼 허용치를 올려 실행하거나, 팔이 걸린 곳이 없는지 확인 |
| 추론 시작 시 오른팔 elbow 처짐 | 홈 이동 뒤 토크가 유지되는지 확인 (`goto_home_bi.py` 의 `disable_torque_on_disconnect=False`) |
| 서버 접속 불가 (5555) | `./serve_local.sh '' logs` 로 서버 준비 여부 확인, 이전 컨테이너가 남아 있으면 `stop` 후 재기동 |
| rsync Permission denied | 7번의 chmod 를 먼저 실행 |
| 변환 검사에서 지시문 1종 | 변환이 지시문을 하나로 접음 — 학습하지 말고 변환 단계부터 다시 |
