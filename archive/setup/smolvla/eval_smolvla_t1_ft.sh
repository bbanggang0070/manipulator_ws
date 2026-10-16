#!/usr/bin/env bash
# SmolVLA-T1 (파인튜닝) 정책 평가 — heongyu/smolvla_so101_t1 사용
# zero-shot용 eval_smolvla_t1.sh와 달리 카메라 리네이밍(camera1/2)·empty_cameras·정규화
# 오버라이드가 전혀 필요 없음 — 파인튜닝 체크포인트가 top/wrist 이름과 우리 데이터
# 정규화 스케일을 그대로 학습했기 때문(§ report/SmolVLA_report.md 참조).
#
# 사용법: ./setup/smolvla/eval_smolvla_t1_ft.sh [에피소드 수]      (기본 1 — dry-run)
#         ./setup/smolvla/eval_smolvla_t1_ft.sh 10 push           (10회 측정 + Hub 업로드)
#         ./setup/smolvla/eval_smolvla_t1_ft.sh 6 push resume     (기존 세션에 6회 이어서)
#
# ⚠️ leader 팔도 전원·연결 필요 (리셋 시 대기 자세 복귀용)
# 리셋 절차: 큐브 재배치 → leader로 팔을 대기 자세로 → 손 빼기
# 키보드: →(에피소드 종료·저장) / ESC(세션 종료)   ⚠️ 이상 동작 시 즉시 Ctrl+C
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
  --robot.cameras="$CAMS" \
  --display_data=true \
  --dataset.repo_id=heongyu/eval_smolvla_ft_so101_t1 \
  --dataset.num_episodes="$NUM" \
  --dataset.single_task="Pick up the red cube and place it in the black box" \
  --dataset.episode_time_s=60 \
  --dataset.reset_time_s=20 \
  --dataset.push_to_hub="$PUSH" \
  --dataset.private=true \
  --teleop.type=so101_leader --teleop.port=/dev/ttyLEADER --teleop.id=leader \
  --policy.path=heongyu/smolvla_so101_t1 \
  --policy.device=cuda \
  $RESUME
