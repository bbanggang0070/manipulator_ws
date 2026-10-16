#!/usr/bin/env bash
# ACT T1 (Pick-and-Place) 데이터 수집 — heongyu/so101_t1_pickplace
# 사용법: ./setup/data/record_t1.sh [에피소드 수]   (기본 10 — 세션 나눠 수집 권장)
#         ./setup/data/record_t1.sh 10 resume      (기존 데이터셋에 이어서)
#
# 키보드: →(오른쪽 화살표) 에피소드 조기 종료·저장 / ←(왼쪽) 재녹화 / ESC 세션 종료
# 규칙: 5지점(소형 점 마킹) 그리드 순환 배치, rerun 카메라 뷰만 보고 조작 (cheating 방지)
# 2026-07-10: 마킹을 큰 표시 -> 작은 점으로 교체, 3점 -> 5점으로 확장 (v2, 50ep 목표)
cd "$(dirname "$0")/../../envs/lerobot" || exit 1

NUM="${1:-10}"
RESUME=""
[ "${2:-}" = "resume" ] && RESUME="--resume=true"

CAMS='{ top:   {type: opencv, index_or_path: /dev/cam_top,   width: 640, height: 480, fps: 30, fourcc: MJPG},
        wrist: {type: opencv, index_or_path: /dev/cam_wrist, width: 640, height: 480, fps: 30, fourcc: MJPG}}'

exec uv run lerobot-record \
  --robot.type=so101_follower --robot.port=/dev/ttyFOLLOWER --robot.id=follower \
  --robot.cameras="$CAMS" \
  --teleop.type=so101_leader --teleop.port=/dev/ttyLEADER --teleop.id=leader \
  --display_data=true \
  --dataset.repo_id=heongyu/so101_t1_pickplace \
  --dataset.num_episodes="$NUM" \
  --dataset.single_task="Pick up the red cube and place it in the black box" \
  --dataset.episode_time_s=60 \
  --dataset.reset_time_s=15 \
  --dataset.private=true \
  $RESUME
