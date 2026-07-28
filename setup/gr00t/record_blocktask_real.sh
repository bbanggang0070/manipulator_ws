#!/usr/bin/env bash
# Phase F: 실기 블록 시연 수집 (현재 카메라 구도로 재수집 — 기존 so101_t1_pickplace는 카메라 각도 달라 못 씀).
# sim 데이터(heongyu/sim_so101_blocktask)와 co-training 할 것이므로 언어·태스크를 sim과 일치시킴.
#
# 사용법: ./setup/gr00t/record_blocktask_real.sh [에피소드 수]        (기본 10 — 세션 나눠 수집)
#         ./setup/gr00t/record_blocktask_real.sh 10 resume           (이어서 수집)
# 키보드: →(오른쪽) 조기 종료·저장 / ←(왼쪽) 재녹화 / ESC 세션 종료
# 규칙: 5지점 그리드 순환, rerun 뷰만 보고 조작(cheating 방지), 성공 종결만 저장.
#   ⚠️ 카메라를 지금 위치에 고정하고 수집(이후 배포도 같은 위치). 정상 ~70% + 교정(recovery) ~30% 권장.
cd "$(dirname "$0")/../../envs/lerobot" || exit 1

NUM="${1:-10}"
RESUME=""
[ "${2:-}" = "resume" ] && RESUME="--resume=true"

# 현재 배포와 동일한 카메라 (front←top, wrist←wrist)
CAMS='{ top:   {type: opencv, index_or_path: /dev/cam_top,   width: 640, height: 480, fps: 30, fourcc: MJPG},
        wrist: {type: opencv, index_or_path: /dev/cam_wrist, width: 640, height: 480, fps: 30, fourcc: MJPG}}'

exec uv run lerobot-record \
  --robot.type=so101_follower --robot.port=/dev/ttyFOLLOWER --robot.id=follower \
  --robot.cameras="$CAMS" \
  --teleop.type=so101_leader --teleop.port=/dev/ttyLEADER --teleop.id=leader \
  --display_data=true \
  --dataset.repo_id=heongyu/so101_blocktask_real \
  --dataset.num_episodes="$NUM" \
  --dataset.single_task="Pick up the block and place it in the box" \
  --dataset.episode_time_s=60 \
  --dataset.reset_time_s=15 \
  --dataset.private=true \
  --dataset.push_to_hub=false \
  $RESUME
