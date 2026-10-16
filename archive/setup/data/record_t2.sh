#!/usr/bin/env bash
# ACT T2 (Table Cleanup) 데이터 수집 — heongyu/so101_t2_cleanup
# 사용법: ./setup/data/record_t2.sh [에피소드 수]   (기본 10 — 세션 나눠 수집 권장)
#         ./setup/data/record_t2.sh 10 resume      (기존 데이터셋에 이어서)
#
# 에피소드 구성: 1회 = 빨강 집기→넣기 → 노랑 집기→넣기 → 초록 집기→넣기 → 종료(→키)
#   (물체 3개를 한 에피소드 안에서 순차로 모두 박스에 정리)
# 2026-07-10: 마킹 소형화 + 3점 -> 5점 확장(v2, 50ep 목표). 물체는 기존과 동일 3개(빨/노/초).
#   매 에피소드: 5지점 중 3곳을 무작위 선택 + 색 무작위 배치, 5곳 사용 횟수가 최대한
#   균등하도록(각 지점 약 30회) 수기로 체크하며 진행 (§ report/SmolVLA_report.md 편향 검증용)
# 리셋 시: 3개 물체 모두 회수 후 5지점 중 무작위 3곳에 재배치(색 배치도 매 에피소드 셔플),
#          leader로 팔 대기 자세 복귀
# 키보드: → 에피소드 종료·저장 / ← 재녹화 / ESC 세션 종료
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
  --dataset.repo_id=heongyu/so101_t2_cleanup \
  --dataset.num_episodes="$NUM" \
  --dataset.single_task="Put the red cube, the yellow cube, and the green cube in the black box" \
  --dataset.episode_time_s=90 \
  --dataset.reset_time_s=25 \
  --dataset.private=true \
  $RESUME
