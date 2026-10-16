#!/usr/bin/env bash
# SmolVLA zero-shot 평가 — T1 (Pick-and-Place), 학습 없이 lerobot/smolvla_base 바로 추론
# 사용법: ./setup/smolvla/eval_smolvla_t1.sh [에피소드 수]      (기본 1 — dry-run)
#         ./setup/smolvla/eval_smolvla_t1.sh 10 push           (10회 측정 + Hub 업로드)
#
# ⚠️ SmolVLA는 3캠(camera1/2/3) 기대, 우리는 2캠 → 로봇 카메라 자체를 camera1/camera2로
#    명명해 데이터셋 스키마를 정책과 직접 일치시킴 (rename_map은 dataset 생성 시 반영 안 되어
#    make_policy() 검증을 통과 못 함 — 실측 확인). camera1=top, camera2=wrist.
# --policy.empty_cameras=1: camera3를 검은 패딩 이미지로 채워 3캠 구조 유지
#    (smolvla_aloha_sim과 동일 패턴, 라이브러리 공식 의도 사용법이라 유지).
#    ⚠️ 단, 2026-07-09 5회 실측 결과 이 설정이 "좌측 고정 후 무반응" 실패를
#    안정적으로 해결하진 못함(5회 중 4회 동일 실패 재현, 1회만 예외적 정상 —
#    배경 요소 차이 등 다른 변수였을 가능성). 근본 원인은 SO-101 하드웨어/카메라
#    구도가 SmolVLA 사전학습 분포에서 벗어난 OOD로 판단 — 02_SmolVLA.md 참조.
# ⚠️ leader 팔도 전원·연결 필요 (리셋 시 대기 자세 복귀용)
# 키보드: →(에피소드 종료·저장) / ESC(세션 종료)   ⚠️ 이상 동작 시 즉시 Ctrl+C
cd "$(dirname "$0")/../../envs/lerobot" || exit 1

NUM="${1:-1}"
PUSH="false"
[ "${2:-}" = "push" ] && PUSH="true"

CAMS='{ camera1: {type: opencv, index_or_path: /dev/cam_top,   width: 640, height: 480, fps: 30, fourcc: MJPG},
        camera2: {type: opencv, index_or_path: /dev/cam_wrist, width: 640, height: 480, fps: 30, fourcc: MJPG}}'

exec uv run lerobot-record \
  --robot.type=so101_follower --robot.port=/dev/ttyFOLLOWER --robot.id=follower \
  --robot.cameras="$CAMS" \
  --display_data=true \
  --dataset.repo_id=heongyu/eval_smolvla_so101_t1 \
  --dataset.num_episodes="$NUM" \
  --dataset.single_task="Pick up the red cube and place it in the black box" \
  --dataset.episode_time_s=60 \
  --dataset.reset_time_s=20 \
  --dataset.push_to_hub="$PUSH" \
  --dataset.private=true \
  --teleop.type=so101_leader --teleop.port=/dev/ttyLEADER --teleop.id=leader \
  --policy.path=lerobot/smolvla_base \
  --policy.empty_cameras=1 \
  --policy.device=cuda
