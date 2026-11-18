"""로봇을 **실기 학습 rest 자세**로 이동 (co-train 모델 실기 배포용 초기화).

⚠️ goto_home_sim.py(옛 v1 sim rest, elbow +96.8)와 다름 — 이건 **실기 데이터
(so101_blocktask_real, 50ep)의 에피소드 첫 프레임(rest) 평균 자세**다.

배경(2026-08-03): goto_home_sim의 elbow +96.8°는 co-train 모델이 학습한 시작 분포
(v2 sim +92.6 / 실기 +89.5)보다 4~7° 높아 **OOD 시작**이 됐고, 그 결과 추론 초반에
정책이 분포 안으로 흘러내릴 때까지 오래 rest(맴돎)하는 지연이 관찰됨. 실기 rest에서
출발하면 처음부터 분포 안이라 이 지연이 사라진다.

TARGET = so101_blocktask_real 50ep 첫 프레임 state 평균:
  pan 6.4, lift -92.3, elbow 89.8, wrist_flex 76.5, wrist_roll -1.9, gripper 4.3
  (elbow std 0.71로 매우 안정 — rest 자세가 잘 정의됨)
"""
import logging
import sys
import time

logging.disable(logging.WARNING)  # 이동 중 매 스텝 찍히는 클램프 경고 억제

from lerobot.robots.so_follower.so_follower import SOFollower
from lerobot.robots.so_follower.config_so_follower import SOFollowerRobotConfig

# 실기(so101_blocktask_real) 학습 데이터의 rest(에피소드 시작) 평균 자세
TARGET = {
    "shoulder_pan.pos": 6.4, "shoulder_lift.pos": -92.3, "elbow_flex.pos": 89.8,
    "wrist_flex.pos": 76.5, "wrist_roll.pos": -1.9, "gripper.pos": 4.3,
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
        # 출력 형식은 goto_home_sim.py와 동일("최대 오차 X.X°") → home_then_infer.sh 파서 호환
        print("실기-홈 도달 (최대 오차 {:.1f}°): ".format(worst)
              + ", ".join(f"{k.split('.')[0]}{v:+.1f}" for k, v in diffs.items()), flush=True)
        ok = worst < 5.0
        break
    except Exception as e:
        print(f"이동 재시도: {type(e).__name__}", flush=True)
        time.sleep(1)

r.disconnect()
sys.exit(0 if ok else 1)
