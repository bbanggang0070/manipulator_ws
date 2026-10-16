"""로봇을 **bi_cleanup(본 수집 300ep) 학습 rest 자세**로 이동 (양팔 추론 배포용 초기화).
setup/gr00t/goto_home_cleanup.py 의 양팔판 — 방식은 그대로, 관절이 12개로 늘었을 뿐이다.

⚠️ 데이터셋이 바뀌면(본 수집 300ep 완료 후) **이 파일도 반드시 갱신한다** —
   goto_home_cleanup.py 머리말의 교훈(실기 wrist_flex 18.3° 어긋남) 그대로.
   TARGET 재계산: bi_cleanup 데이터셋 parquet의 frame_index==0 observation.state 평균.

TARGET = bi_cleanup 본 수집 **300ep** 첫 프레임 state **중앙값**(괄호는 표준편차, 2026-10-16 재계산):
  left_shoulder_pan  +3.6(2.2) · left_shoulder_lift -98.0(0.2) · left_elbow_flex  +90.3(2.6)
  left_wrist_flex   +71.8(1.9) · left_wrist_roll     -2.6(2.9) · left_gripper     +2.1(0.3)
  right_shoulder_pan -0.4(1.3) · right_shoulder_lift -98.4(0.3) · right_elbow_flex +91.9(7.4)
  right_wrist_flex  +73.4(1.5) · right_wrist_roll    -0.2(3.0) · right_gripper    +1.8(0.1)
  평균이 아니라 중앙값인 이유: right_elbow_flex 가 두 갈래다(평균 96.6 · 중앙값 91.9) — 녹화 시작 순간
  오른팔 elbow 가 아직 처져 있던 ep 가 섞여 있다(리더 action 은 89.5±0.2 로 일정). 중앙값 = 대다수 ep 의 값.
  (이전 50ep 평균 TARGET 은 스크래치 백업 goto_home_bi.before_300ep.py 참고)

⚠️ 토크 유지(disable_torque_on_disconnect=False): 기본값(True)이면 홈 도달 후 disconnect 순간
   토크가 꺼져, 추론이 연결되기 전까지 오른팔 elbow 가 중력에 처진다 — 2026-10-16 ck21000 trial02 에서
   홈 오차 3° 이내로 맞췄는데 추론 시작 state 는 right_elbow 103.2°(목표 93.3°)였다.
   그 처진 자세가 STOP_ON_REST 의 기준(_rest0)이 되어 작업 후 rest 복귀가 판정되지 않았다.
"""
import logging
import os
import sys
import time

logging.disable(logging.WARNING)  # 이동 중 매 스텝 찍히는 클램프 경고 억제

from lerobot.robots.bi_so_follower.bi_so_follower import BiSOFollower
from lerobot.robots.bi_so_follower.config_bi_so_follower import BiSOFollowerConfig
from lerobot.robots.so_follower.config_so_follower import SOFollowerConfig

from home_pose_bi import TARGET  # eval_lerobot_bi.py 의 시행 끝 rest 복귀와 같은 값을 쓰기 위해 분리

r = None
for attempt in range(6):  # 포트 해제 대기 겸 connect 재시도
    try:
        r = BiSOFollower(BiSOFollowerConfig(
            id="bi_follower",
            left_arm_config=SOFollowerConfig(
                port="/dev/ttyFOLLOWER_L", cameras={}, max_relative_target=4.0,
                disable_torque_on_disconnect=False),
            right_arm_config=SOFollowerConfig(
                port="/dev/ttyFOLLOWER_R", cameras={}, max_relative_target=4.0,
                disable_torque_on_disconnect=False),
        ))
        r.connect()
        break
    except Exception as e:
        print(f"connect 재시도 {attempt+1}/6: {type(e).__name__}", flush=True)
        r = None
        time.sleep(2)
if r is None:
    print("홈 복귀 실패: 로봇 연결 불가", flush=True)
    sys.exit(1)

# goto_home_cleanup.py와 같은 이유로 **수렴할 때까지 반복**한다(한 라운드로 못 가면 더 보낸다).
TOL = float(os.environ.get("HOME_TOL", "5.0"))
ROUNDS = int(os.environ.get("HOME_ROUNDS", "6"))
ok = False
for rnd in range(ROUNDS):
    try:
        for _ in range(150):
            r.send_action(TARGET)
            time.sleep(0.03)
        obs = r.get_observation()
        diffs = {k: obs[k] - v for k, v in TARGET.items()}
        worst = max(abs(v) for v in diffs.values())
        # 출력 형식은 goto_home_cleanup.py와 동일("최대 오차 X.X°") → home_then_infer_bi.sh 파서 호환
        print("실기-홈 도달 (최대 오차 {:.1f}°): ".format(worst)
              + ", ".join(f"{k.split('.')[0]}{v:+.1f}" for k, v in diffs.items()), flush=True)
        if worst < TOL:
            ok = True
            break
    except Exception as e:
        print(f"이동 재시도: {type(e).__name__}", flush=True)
        time.sleep(1)

r.disconnect()
sys.exit(0 if ok else 1)
