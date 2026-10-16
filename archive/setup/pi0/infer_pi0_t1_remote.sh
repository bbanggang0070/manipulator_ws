#!/usr/bin/env bash
# π0 원격 추론 클라이언트 (T1 Pick-and-Place) — 로봇은 로컬, 추론은 5090 GPU
#
# 구조(async inference): 5090에서 policy_server가 π0를 GPU에 로드하고, 이 로컬 클라이언트가
#   실로봇 관측을 gRPC로 보내고 액션 청크를 받아 로봇에 실행한다.
#   서버 먼저 실행 필요 → 5090에서:  ~/pi0_remote/pi0-server.sh start   (포트 8080)
#   방화벽 허용 필요   → 5090에서:  sudo ufw allow from 192.168.0.11 to any port 8080 proto tcp
#
# 사용법: ./setup/pi0/infer_pi0_t1_remote.sh
#
# ⚠️ 실로봇이 실제로 움직이는 명령이다. 물체·그리드 배치 후 사람이 지켜보며 실행할 것.
# ⚠️ zero-shot(lerobot/pi0)은 SO-101 미학습 임바디먼트라 SmolVLA처럼 정규화/카메라 키
#    불일치로 이상 동작 가능성 있음 — 첫 실행은 반드시 dry-run 감시 하에.
# ⚠️ 카메라 키(top/wrist)가 π0 기대 키와 다르면 rename_map 필요할 수 있음(dry-run에서 확인).
LAUNCHER="$(cd "$(dirname "$0")" && pwd)/_robot_client_launcher.py"
cd "$(dirname "$0")/../../envs/lerobot" || exit 1

SERVER="${SERVER:-192.168.0.56:8080}"

CAMS='{ top:   {type: opencv, index_or_path: /dev/cam_top,   width: 640, height: 480, fps: 30, fourcc: MJPG},
        wrist: {type: opencv, index_or_path: /dev/cam_wrist, width: 640, height: 480, fps: 30, fourcc: MJPG}}'

# NOTE: `python -m lerobot.async_inference.robot_client`는 so_follower 미등록으로
# --robot.type 선택지가 비어 에러남 → 로봇 config를 먼저 등록하는 런처로 우회.
exec uv run python "$LAUNCHER" \
  --server_address="$SERVER" \
  --robot.type=so101_follower --robot.port=/dev/ttyFOLLOWER --robot.id=follower \
  --robot.cameras="$CAMS" \
  --task="Pick up the red cube and place it in the black box" \
  --policy_type=pi0 \
  --pretrained_name_or_path=lerobot/pi0_base \
  --policy_device=cuda \
  --actions_per_chunk=50 \
  --chunk_size_threshold=0.5 \
  --fps=30 \
  --aggregate_fn_name=weighted_average \
  --debug_visualize_queue_size=true
