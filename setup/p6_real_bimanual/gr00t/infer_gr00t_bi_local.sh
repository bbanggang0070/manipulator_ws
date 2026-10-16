#!/usr/bin/env bash
# GR00T N1.6 양팔 cleanup 추론 — 로컬 서버(serve_local.sh)판.
# setup/gr00t/infer_gr00t_blocktask_remote.sh 의 양팔판 — 다른 건 카메라 3대·로봇 타입뿐이다.
#
# 서버 먼저(로컬 5070 Ti): cd ../.. && ./serve_local.sh gr00t_bi_cleanup_n16_8bit/checkpoint-7500
# ⚠️ 시작 자세: goto_home_bi.py(=bi_cleanup 학습 rest 자세)로 초기화 후 실행할 것 —
#    home_then_infer_bi.sh 를 쓰면 자동으로 해 준다(직접 이 스크립트만 돌리지 말 것).
set -u
LAUNCH_DIR="$(cd "$(dirname "$0")" && pwd)/client"
cd "$(dirname "$0")/../../../envs/lerobot" || exit 1

SERVER_HOST="${SERVER_HOST:-127.0.0.1}"
MRT="${MRT:-8.0}"
HORIZON="${HORIZON:-16}"
LANG_INSTRUCTION="${LANG_INSTRUCTION:-Put the red marker into the black bin}"

# record_bi.sh 와 정확히 같은 카메라 장치(§bi_manipulator_plan.md 2-1): top+wrist(왼팔) · wrist(오른팔)
# (단일팔 infer_gr00t_blocktask_remote.sh 와 같은 이유로 env override 없이 고정값으로 둔다 —
#  중첩 중괄호를 ${VAR:-...} 기본값에 넣으면 bash 파싱이 깨지기 쉽다)
CAMS_L='{ top:   {type: opencv, index_or_path: /dev/cam_top,         width: 640, height: 480, fps: 30, fourcc: MJPG},
          wrist: {type: opencv, index_or_path: /dev/cam_wrist,       width: 640, height: 480, fps: 30, fourcc: MJPG}}'
CAMS_R='{ wrist: {type: opencv, index_or_path: /dev/cam_wrist_right, width: 640, height: 480, fps: 30, fourcc: MJPG}}'

cd "$LAUNCH_DIR"  # service.py(단일팔 client/ 의 것, 상대경로로 import)를 쓰기 위함
exec uv run --project ../../../../envs/lerobot python eval_lerobot_bi.py \
  --robot.type=bi_so_follower \
  --robot.left_arm_config.port=/dev/ttyFOLLOWER_L \
  --robot.right_arm_config.port=/dev/ttyFOLLOWER_R \
  --robot.id=bi_follower \
  --robot.left_arm_config.max_relative_target="$MRT" \
  --robot.right_arm_config.max_relative_target="$MRT" \
  --robot.left_arm_config.cameras="$CAMS_L" \
  --robot.right_arm_config.cameras="$CAMS_R" \
  --policy_host="$SERVER_HOST" \
  --policy_port=5555 \
  --action_horizon="$HORIZON" \
  --lang_instruction="$LANG_INSTRUCTION"
