"""로봇을 **cleanup_real 학습 rest 자세**로 이동 (실기 cleanup 모델 배포용 초기화).

⚠️ goto_home_real.py(so101_blocktask_real 50ep 기준)와 다르다. 데이터셋이 바뀌면
   rest 자세도 바뀌는데, 그걸 갱신하지 않으면 **정책이 학습 시작 분포 밖에서
   출발한다.** 2026-08-03에 goto_home_sim의 elbow가 4~7° 높아 추론 초반에
   오래 맴도는 지연이 났던 것과 **같은 실패**다.

실측 차이 (goto_home_real.py 대비, cleanup_real 80ep 첫 프레임 평균):
  wrist_flex  -18.3°  ← 가장 크다
  gripper     +10.7°  (수집 시 그리퍼가 더 열린 상태에서 출발했다)
  pan -6.3  ·  lift -6.0  ·  elbow +5.5  ·  wrist_roll +0.8

TARGET = cleanup_real 80ep 첫 프레임 state 평균 (괄호는 표준편차):
  pan 0.1 (2.5) · lift -98.3 (2.0) · elbow 95.3 (5.5)
  wrist_flex 58.2 (14.3) · wrist_roll -1.1 (9.0) · gripper 15.0 (11.0)
  ⚠️ wrist_flex·wrist_roll·gripper는 편차가 크다 — rest가 그만큼 느슨하게
     정의됐다는 뜻이다. 다음 수집에서는 시작 자세를 더 일관되게 잡을 것.
"""
import logging
import sys
import time

logging.disable(logging.WARNING)  # 이동 중 매 스텝 찍히는 클램프 경고 억제

from lerobot.robots.so_follower.so_follower import SOFollower
from lerobot.robots.so_follower.config_so_follower import SOFollowerRobotConfig

# cleanup_real 80ep 의 rest(에피소드 시작) 평균 자세 — 실측값이다.
#   재계산: 데이터셋 parquet 의 frame_index==0 인 observation.state 평균.
TARGET = {
    "shoulder_pan.pos": 0.1, "shoulder_lift.pos": -98.3, "elbow_flex.pos": 95.3,
    "wrist_flex.pos": 58.2, "wrist_roll.pos": -1.1, "gripper.pos": 15.0,
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
