"""로봇을 **sim 학습 rest 자세**로 이동 (sim→real 전이 평가 Phase E 초기화).

⚠️ goto_home.py(실기 T1 데이터용)와 다름 — 이건 **sim(blocktask) 데이터**에서 직접 계산한
각 에피소드 첫 프레임(rest) 평균 자세다. sim-정합 사전 점검(2026-07-27) 결과, 실기 goto_home과
shoulder_lift·elbow_flex가 ~7°(수 σ) 어긋나 sim 정책이 학습한 시작 분포 밖(OOD)에서 추론을
시작하게 되므로, sim 전이 평가에서는 이 홈으로 시작해 covariate shift 씨앗을 줄인다.

TARGET = sim v2.1 데이터(heongyu/sim_so101_blocktask, 75ep) 첫 프레임 state 평균:
  pan 3.6, lift -92.1, elbow 96.8, wrist_flex 70.2, wrist_roll 0.6, gripper 4.7
  (wrist_roll은 실기 goto_home 1.0과도 +0.2σ로 잘 정합 — 단위·프레임 일치 확인됨)
"""
import logging
import sys
import time

logging.disable(logging.WARNING)  # 이동 중 매 스텝 찍히는 클램프 경고 억제

from lerobot.robots.so_follower.so_follower import SOFollower
from lerobot.robots.so_follower.config_so_follower import SOFollowerRobotConfig

# sim(blocktask) 학습 데이터의 rest(에피소드 시작) 평균 자세
TARGET = {
    "shoulder_pan.pos": 3.6, "shoulder_lift.pos": -92.1, "elbow_flex.pos": 96.8,
    "wrist_flex.pos": 70.2, "wrist_roll.pos": 0.6, "gripper.pos": 4.7,
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
        print("sim-홈 도달 (최대 오차 {:.1f}°): ".format(worst)
              + ", ".join(f"{k.split('.')[0]}{v:+.1f}" for k, v in diffs.items()), flush=True)
        ok = worst < 5.0
        break
    except Exception as e:
        print(f"이동 재시도: {type(e).__name__}", flush=True)
        time.sleep(1)

r.disconnect()
sys.exit(0 if ok else 1)
