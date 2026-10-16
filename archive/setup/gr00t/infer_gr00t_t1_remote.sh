#!/usr/bin/env bash
# GR00T N1.5 원격 추론 클라이언트 (T1 Pick-and-Place) — 로봇 로컬, 추론 5090(zmq:5555)
#
# 서버 먼저: 5090에서  ~/gr00t_remote/scripts/gr00t-server.sh t1
# 방화벽(1회): 5090에서 sudo ufw allow from 192.168.0.11 to any port 5555 proto tcp
#
# ⚠️ 카메라 키 = 학습 매핑과 일치 필수(pi0 #1 교훈): front=/dev/cam_top, wrist=/dev/cam_wrist
#    (modality.json에서 front←observation.images.top 으로 학습했음)
# ⚠️ max_relative_target=8: 안전 클램프(pi0/SmolVLA 공통 교훈). MRT=값 으로 조정.
# ⚠️ 무한 루프 스크립트 — 에피소드 개념 없음. 측정 시 수동 타이밍, Ctrl+C로 종료.
LAUNCH_DIR="$(cd "$(dirname "$0")" && pwd)/client"
cd "$(dirname "$0")/../../envs/lerobot" || exit 1

SERVER_HOST="${SERVER_HOST:-192.168.0.56}"
MRT="${MRT:-8.0}"
HORIZON="${HORIZON:-8}"   # 청크(16) 중 실행할 액션 수

CAMS="{ front: {type: opencv, index_or_path: /dev/cam_top,  width: 640, height: 480, fps: 30, fourcc: MJPG},
        wrist: {type: opencv, index_or_path: /dev/cam_wrist, width: 640, height: 480, fps: 30, fourcc: MJPG}}"

cd "$LAUNCH_DIR"  # service.py 로컬 import 위해 client/ 에서 실행
exec uv run --project ../../../envs/lerobot python eval_lerobot.py \
  --robot.type=so101_follower \
  --robot.port=/dev/ttyFOLLOWER \
  --robot.id=follower \
  --robot.max_relative_target="$MRT" \
  --robot.cameras="$CAMS" \
  --policy_host="$SERVER_HOST" \
  --policy_port=5555 \
  --action_horizon="$HORIZON" \
  --lang_instruction="Pick up the red cube and place it in the black box"
