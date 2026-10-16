#!/usr/bin/env bash
# π0 LoRA FT 추론 클라이언트 (T1) — 5090의 파인튜닝 체크포인트 서빙
#
# 구조(async inference): 5090에서 policy_server가 π0를 GPU에 로드하고, 이 로컬 클라이언트가
#   실로봇 관측을 gRPC로 보내고 액션 청크를 받아 로봇에 실행한다.
#   서버 먼저 실행 필요 → 5090에서:  ~/pi0_remote/pi0-server.sh start   (포트 8080)
#   방화벽 허용 필요   → 5090에서:  sudo ufw allow from 192.168.0.11 to any port 8080 proto tcp
#
# 사용법: ./setup/pi0/infer_pi0_t1_remote.sh
#
# ⚠️ 실로봇이 실제로 움직이는 명령이다. 물체·그리드 배치 후 사람이 지켜보며 실행할 것.
# ⚠️ FT 체크포인트는 top/wrist·6차원에 적응됨 — zero-shot 키/차원 불일치 없음.
# ⚠️ max_relative_target=8: 스텝당 관절 이동을 8도로 제한(안전 클램프). 미설정 시 큰 점프로
#    위험한 급동작 발생(2026-07-14 실측) → SmolVLA 때와 동일하게 클램프 필수.
#    동작이 너무 굼뜨면 값을 키우고, 여전히 위험하면 낮춰 재시도.
LAUNCHER="$(cd "$(dirname "$0")" && pwd)/_robot_client_launcher.py"
cd "$(dirname "$0")/../../envs/lerobot" || exit 1

SERVER="${SERVER:-192.168.0.56:8080}"
# 클램프 조정(진단용): MRT=25 ./infer_...ft.sh. 0이면 클램프 해제(위험, 감시필수).
MRT="${MRT:-8.0}"
# 청크 aggregation: AGG=latest_only 로 블렌딩 제거(진동 원인 테스트). 기본 weighted_average.
AGG="${AGG:-weighted_average}"
# rerun 실시간 시각화: RERUN=1 기본. 카메라·state·action_cmd(명령)·action_sent(클램프후) 로깅.
export RERUN="${RERUN:-1}"
# 파일 로깅: 매 스텝 dt_ms(끊김 진단)+cmd+sent 를 CSV로 기록(분석용).
export LOGFILE="${LOGFILE:-$HOME/manipulator_ws/logs/pi0_infer/$(date +%Y%m%d_%H%M%S).csv}"

CAMS='{ top:   {type: opencv, index_or_path: /dev/cam_top,   width: 640, height: 480, fps: 30, fourcc: MJPG},
        wrist: {type: opencv, index_or_path: /dev/cam_wrist, width: 640, height: 480, fps: 30, fourcc: MJPG}}'

echo "로그 파일: $LOGFILE  (aggregate=$AGG, max_relative_target=$MRT)"
# NOTE: `python -m lerobot.async_inference.robot_client`는 so_follower 미등록으로
# --robot.type 선택지가 비어 에러남 → 로봇 config를 먼저 등록하는 런처로 우회.
exec uv run python "$LAUNCHER" \
  --server_address="$SERVER" \
  --robot.type=so101_follower --robot.port=/dev/ttyFOLLOWER --robot.id=follower \
  --robot.max_relative_target="$MRT" \
  --robot.cameras="$CAMS" \
  --task="Pick up the red cube and place it in the black box" \
  --policy_type=pi0 \
  --pretrained_name_or_path=/home/user_lerobot/work/train/pi0_t1_expert/checkpoints/last/pretrained_model \
  --policy_device=cuda \
  --actions_per_chunk=50 \
  --chunk_size_threshold=0.5 \
  --fps=30 \
  --aggregate_fn_name="$AGG" \
  --debug_visualize_queue_size=true
