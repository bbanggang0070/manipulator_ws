"""로봇을 학습 평균 홈 자세로 이동 (GR00T 측정 시행 간 초기화).

학습 데이터(T1 v2 trimmed) 에피소드 초기 state 평균으로 이동해 시작 자세 변수를 통제.
클라이언트 종료 직후 시리얼이 일시적으로 불안정할 수 있어 connect/read 모두 재시도.
"""
import logging
import sys
import time

logging.disable(logging.WARNING)  # 이동 중 매 스텝 찍히는 클램프 경고 억제

from lerobot.robots.so_follower.so_follower import SOFollower
from lerobot.robots.so_follower.config_so_follower import SOFollowerRobotConfig

TARGET = {
    "shoulder_pan.pos": 0.6, "shoulder_lift.pos": -98.9, "elbow_flex.pos": 89.8,
    "wrist_flex.pos": 71.1, "wrist_roll.pos": 1.0, "gripper.pos": 3.5,
}

r = None
for attempt in range(6):  # 포트 해제 대기 겸 connect 재시도
    try:
        r = SOFollower(SOFollowerRobotConfig(
            port="/dev/ttyFOLLOWER", id="follower", cameras={}, max_relative_target=4.0))
        r.connect()
        break
    except Exception as e:
        print(f"connect 재시도 {attempt+1}/6: {type(e).__name__}", flush=True)
        r = None
        time.sleep(2)
if r is None:
    print("홈 복귀 실패: 로봇 연결 불가", flush=True)
    sys.exit(1)

ok = False
for _ in range(3):  # 이동도 재시도 (일시적 no-status-packet 대응)
    try:
        for _ in range(150):
            r.send_action(TARGET)
            time.sleep(0.03)
        obs = r.get_observation()
        diffs = {k: obs[k] - v for k, v in TARGET.items()}
        worst = max(abs(v) for v in diffs.values())
        print("홈 도달 (최대 오차 {:.1f}°): ".format(worst)
              + ", ".join(f"{k.split('.')[0]}{v:+.1f}" for k, v in diffs.items()), flush=True)
        ok = worst < 5.0
        break
    except Exception as e:
        print(f"이동 재시도: {type(e).__name__}", flush=True)
        time.sleep(1)

r.disconnect()
sys.exit(0 if ok else 1)
