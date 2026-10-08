"""로봇을 **cleanup_real(v2) 학습 rest 자세**로 이동 (실기 cleanup 모델 배포용 초기화).

⚠️ 데이터셋이 바뀌면 **이 파일도 반드시 갱신한다.** v1 에서 이 한 줄을 안 해서
   goto_home_real.py(옛 so101_blocktask_real 기준)로 평가를 돌렸고, 학습 시작
   분포와 wrist_flex 가 18.3° 어긋난 채 출발해 모델이 물체를 집지 못했다.
   2026-08-03 에 goto_home_sim 의 elbow 가 4~7° 높아 겪은 것과 같은 실패다.
   값은 verify_real_lang_dataset.py 가 "배포용 홈 자세" 로 찍어 준다.

TARGET = cleanup_real v3 **370ep** 첫 프레임 state 평균 (괄호는 표준편차):
  pan +2.0 (1.9) · lift -97.1 (3.2) · elbow +92.5 (4.2)
  wrist_flex +69.5 (4.4) · wrist_roll +0.8 (2.7) · gripper +1.9 (0.3)
  ✅ 전 관절 5° 미만 — rest_gate.py 가 매 에피소드 리더 자세를 대조한 덕분이다.
  (v2 250ep 기준값과는 1° 안쪽 차이다 — rest 가 안정적으로 유지됐다는 뜻)
"""
import logging
import os
import sys
import time

logging.disable(logging.WARNING)  # 이동 중 매 스텝 찍히는 클램프 경고 억제

from lerobot.robots.so_follower.so_follower import SOFollower
from lerobot.robots.so_follower.config_so_follower import SOFollowerRobotConfig

# cleanup_real v3 370ep 의 rest(에피소드 시작) 평균 자세 — 실측값이다.
#   재계산: 데이터셋 parquet 의 frame_index==0 인 observation.state 평균.
TARGET = {
    "shoulder_pan.pos": 2.0, "shoulder_lift.pos": -97.1, "elbow_flex.pos": 92.5,
    "wrist_flex.pos": 69.5, "wrist_roll.pos": 0.8, "gripper.pos": 1.9,
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

# ⚠️ **수렴할 때까지 반복해야 한다.** max_relative_target=4.0 이라 한 번의
#    send_action 이 관절당 4° 까지만 움직인다. 150회면 가까운 데서는 충분하지만,
#    추론이 끝난 자리(보통 칸 위)에서 출발하면 모자란다 — 실측으로 shoulder_lift
#    가 36° 남은 채 "도달"로 찍히고 rc=1 로 끝났다(2026-10-08).
#    한 라운드로 못 가면 그냥 더 보낸다. 가까워질수록 금방 수렴한다.
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
        # 출력 형식은 goto_home_sim.py와 동일("최대 오차 X.X°") → home_then_infer.sh 파서 호환
        print("실기-홈 도달 (최대 오차 {:.1f}°): ".format(worst)
              + ", ".join(f"{k.split('.')[0]}{v:+.1f}" for k, v in diffs.items()), flush=True)
        if worst < TOL:
            ok = True
            break
        # 아직 멀다 — 더 보낸다(예외가 아니므로 조용히 다음 라운드)
    except Exception as e:
        print(f"이동 재시도: {type(e).__name__}", flush=True)
        time.sleep(1)

r.disconnect()
sys.exit(0 if ok else 1)
