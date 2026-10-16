#!/usr/bin/env bash
# [진단용] SmolVLA T1 — 실제 3번째 카메라(side) 추가, empty_cameras 패딩 없이 3캠 전부 실사용
# 기본판(eval_smolvla_t1.sh, 2캠+검은 패딩)이 "좌측 고정 후 무반응"으로 반복 실패해
# camera3 슬롯에 진짜 정보를 채우면 달라지는지 확인하기 위한 테스트.
# camera1=top, camera2=wrist, camera3=side (2026-07-09 신규 추가, 작업공간 측면 각도)
cd "$(dirname "$0")/../../envs/lerobot" || exit 1

NUM="${1:-1}"
PUSH="false"
[ "${2:-}" = "push" ] && PUSH="true"

CAMS='{ camera1: {type: opencv, index_or_path: /dev/cam_top,   width: 640, height: 480, fps: 30, fourcc: MJPG},
        camera2: {type: opencv, index_or_path: /dev/cam_wrist, width: 640, height: 480, fps: 30, fourcc: MJPG},
        camera3: {type: opencv, index_or_path: /dev/cam_side,  width: 640, height: 480, fps: 30, fourcc: MJPG}}'

exec uv run lerobot-record \
  --robot.type=so101_follower --robot.port=/dev/ttyFOLLOWER --robot.id=follower \
  --robot.cameras="$CAMS" \
  --display_data=true \
  --dataset.repo_id=heongyu/eval_smolvla_so101_t1_3cam \
  --dataset.num_episodes="$NUM" \
  --dataset.single_task="Pick up the red cube and place it in the black box" \
  --dataset.episode_time_s=60 \
  --dataset.reset_time_s=20 \
  --dataset.push_to_hub="$PUSH" \
  --dataset.private=true \
  --teleop.type=so101_leader --teleop.port=/dev/ttyLEADER --teleop.id=leader \
  --policy.path=lerobot/smolvla_base \
  --policy.device=cuda
