#!/usr/bin/env bash
# SO-101 teleoperation (3캠 + rerun 뷰어)
# 사용법: ./scripts/hardware/teleop.sh          — 카메라 포함 (기본)
#         ./scripts/hardware/teleop.sh nocam    — 카메라 없이 팔만
#
# ⚠️ fourcc: MJPG 필수 — YUYV 기본값은 USB 대역폭 포화로 wrist 영상 깨짐 (README §3)
# side(belly) 카메라는 2026-07-09 추가 (SmolVLA 3캠 테스트용, /dev/cam_side)
cd "$(dirname "$0")/../../envs/lerobot" || exit 1

CAMS='{ top:   {type: opencv, index_or_path: /dev/cam_top,   width: 640, height: 480, fps: 30, fourcc: MJPG},
        wrist: {type: opencv, index_or_path: /dev/cam_wrist, width: 640, height: 480, fps: 30, fourcc: MJPG},
        side:  {type: opencv, index_or_path: /dev/cam_side,  width: 640, height: 480, fps: 30, fourcc: MJPG}}'

if [ "${1:-}" = "nocam" ]; then
  exec uv run lerobot-teleoperate \
    --robot.type=so101_follower --robot.port=/dev/ttyFOLLOWER --robot.id=follower \
    --teleop.type=so101_leader --teleop.port=/dev/ttyLEADER --teleop.id=leader
else
  exec uv run lerobot-teleoperate \
    --robot.type=so101_follower --robot.port=/dev/ttyFOLLOWER --robot.id=follower \
    --robot.cameras="$CAMS" \
    --teleop.type=so101_leader --teleop.port=/dev/ttyLEADER --teleop.id=leader \
    --display_data=true
fi
