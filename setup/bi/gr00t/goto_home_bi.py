"""로봇을 **bi_cleanup(파일럿 50ep) 학습 rest 자세**로 이동 (양팔 추론 배포용 초기화).
setup/gr00t/goto_home_cleanup.py 의 양팔판 — 방식은 그대로, 관절이 12개로 늘었을 뿐이다.

⚠️ 데이터셋이 바뀌면(본 수집 300ep 완료 후) **이 파일도 반드시 갱신한다** —
   goto_home_cleanup.py 머리말의 교훈(실기 wrist_flex 18.3° 어긋남) 그대로.
   TARGET 재계산: bi_cleanup 데이터셋 parquet의 frame_index==0 observation.state 평균.

TARGET = bi_cleanup 파일럿 **50ep** 첫 프레임 state 평균(괄호는 표준편차, 2026-10-15 실측):
  left_shoulder_pan  +5.1(2.7) · left_shoulder_lift -98.1(0.2) · left_elbow_flex  +93.3(3.0)
  left_wrist_flex   +70.2(2.8) · left_wrist_roll     -1.4(3.7) · left_gripper     +2.1(0.4)
  right_shoulder_pan -0.6(1.6) · right_shoulder_lift -98.7(0.3) · right_elbow_flex +93.3(5.3)
  right_wrist_flex  +73.5(2.1) · right_wrist_roll    -1.3(3.1) · right_gripper    +1.7(0.1)
  50ep뿐이라 표준편차가 단일팔 370ep 기준(5° 미만)보다 다소 크다(elbow·wrist_roll 3~5°) —
  본 수집 뒤 재계산하면 더 좁아질 것으로 기대한다.
"""
import logging
import os
import sys
import time

logging.disable(logging.WARNING)  # 이동 중 매 스텝 찍히는 클램프 경고 억제

from lerobot.robots.bi_so_follower.bi_so_follower import BiSOFollower
from lerobot.robots.bi_so_follower.config_bi_so_follower import BiSOFollowerConfig
from lerobot.robots.so_follower.config_so_follower import SOFollowerConfig

TARGET = {
    "left_shoulder_pan.pos": 5.1, "left_shoulder_lift.pos": -98.1, "left_elbow_flex.pos": 93.3,
    "left_wrist_flex.pos": 70.2, "left_wrist_roll.pos": -1.4, "left_gripper.pos": 2.1,
    "right_shoulder_pan.pos": -0.6, "right_shoulder_lift.pos": -98.7, "right_elbow_flex.pos": 93.3,
    "right_wrist_flex.pos": 73.5, "right_wrist_roll.pos": -1.3, "right_gripper.pos": 1.7,
}

r = None
for attempt in range(6):  # 포트 해제 대기 겸 connect 재시도
    try:
        r = BiSOFollower(BiSOFollowerConfig(
            id="bi_follower",
            left_arm_config=SOFollowerConfig(
                port="/dev/ttyFOLLOWER_L", cameras={}, max_relative_target=4.0),
            right_arm_config=SOFollowerConfig(
                port="/dev/ttyFOLLOWER_R", cameras={}, max_relative_target=4.0),
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
