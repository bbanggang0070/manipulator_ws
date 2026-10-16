#!/usr/bin/env bash
# SmolVLA-T2 (파인튜닝, Table Cleanup) 정책 평가 — heongyu/smolvla_so101_t2_v3 사용
# T1 FT와 마찬가지로 카메라 리네이밍·empty_cameras·정규화 오버라이드 불필요
# (파인튜닝 체크포인트가 top/wrist·우리 데이터 스케일을 그대로 학습함).
#
# 사용법: ./setup/smolvla/eval_smolvla_t2_ft.sh [에피소드 수]      (기본 1 — dry-run)
#         ./setup/smolvla/eval_smolvla_t2_ft.sh 10 push           (10회 측정 + Hub 업로드)
#         ./setup/smolvla/eval_smolvla_t2_ft.sh 6 push resume     (기존 세션에 이어서)
#
# ⚠️ leader 팔도 전원·연결 필요 (리셋 시 대기 자세 복귀용)
# 시작 전: 빨강/노랑/초록 3개를 그리드 3지점에 모두 배치 (색 순서 무관)
# 리셋 절차: 3개 회수 → 색 셔플 재배치 → leader로 팔을 대기 자세로 → 손 빼기
# 키보드: →(에피소드 종료·저장, 다음 에피소드로) / ESC(세션 전체 종료 — 10개 다 채운 뒤에만!)
#   ⚠️ →와 ESC를 혼동하지 말 것: →는 "이 에피소드만 끝", ESC는 "세션 전체 끝"
cd "$(dirname "$0")/../../envs/lerobot" || exit 1

NUM="${1:-1}"
PUSH="false"
[ "${2:-}" = "push" ] && PUSH="true"
RESUME=""
[ "${3:-}" = "resume" ] && RESUME="--resume=true"

CAMS='{ top:   {type: opencv, index_or_path: /dev/cam_top,   width: 640, height: 480, fps: 30, fourcc: MJPG},
        wrist: {type: opencv, index_or_path: /dev/cam_wrist, width: 640, height: 480, fps: 30, fourcc: MJPG}}'

exec uv run lerobot-record \
  --robot.type=so101_follower --robot.port=/dev/ttyFOLLOWER --robot.id=follower \
  --robot.max_relative_target=8.0 \
  --robot.cameras="$CAMS" \
  --display_data=true \
  --dataset.repo_id=heongyu/eval_smolvla_ft_so101_t2_v3 \
  --dataset.num_episodes="$NUM" \
  --dataset.single_task="Put the red cube, the yellow cube, and the green cube in the black box" \
  --dataset.episode_time_s=90 \
  --dataset.reset_time_s=25 \
  --dataset.push_to_hub="$PUSH" \
  --dataset.private=true \
  --teleop.type=so101_leader --teleop.port=/dev/ttyLEADER --teleop.id=leader \
  --policy.path=heongyu/smolvla_so101_t2_v3 \
  --policy.device=cuda \
  $RESUME
