#!/usr/bin/env bash
# [진단용] SmolVLA T1 — 카메라 매핑을 반대로(wrist→camera1, top→camera2) 테스트
# 기본판(eval_smolvla_t1.sh)이 작업공간 밖으로 팔이 고정되는 문제를 보여
# 카메라 슬롯 순서가 원인인지 배제하기 위한 1회성 진단 스크립트.
# 결과가 정상이면 eval_smolvla_t1.sh의 매핑을 이 순서로 교체할 것.
cd "$(dirname "$0")/../../envs/lerobot" || exit 1

NUM="${1:-1}"
PUSH="false"
[ "${2:-}" = "push" ] && PUSH="true"

CAMS='{ camera1: {type: opencv, index_or_path: /dev/cam_wrist, width: 640, height: 480, fps: 30, fourcc: MJPG},
        camera2: {type: opencv, index_or_path: /dev/cam_top,   width: 640, height: 480, fps: 30, fourcc: MJPG}}'

exec uv run lerobot-record \
  --robot.type=so101_follower --robot.port=/dev/ttyFOLLOWER --robot.id=follower \
  --robot.cameras="$CAMS" \
  --display_data=true \
  --dataset.repo_id=heongyu/eval_smolvla_so101_t1_camswap \
  --dataset.num_episodes="$NUM" \
  --dataset.single_task="Pick up the red cube and place it in the black box" \
  --dataset.episode_time_s=60 \
  --dataset.reset_time_s=20 \
  --dataset.push_to_hub="$PUSH" \
  --dataset.private=true \
  --teleop.type=so101_leader --teleop.port=/dev/ttyLEADER --teleop.id=leader \
  --policy.path=lerobot/smolvla_base \
  --policy.device=cuda
