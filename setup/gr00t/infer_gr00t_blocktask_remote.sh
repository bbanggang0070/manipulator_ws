#!/usr/bin/env bash
# GR00T N1.6 블록 태스크 원격 추론 클라이언트 (Phase E: sim→real 전이) — 로봇 로컬, 추론 5090.
#
# 서버 먼저(5090): ~/serve_blocktask_n16_5090.sh  → 'Server is ready' 확인
# 방화벽(1회, 5090): sudo ufw allow from 192.168.0.11 to any port 5555 proto tcp
#
# ⚠️ 언어 지시 = 학습(sim)과 정확히 일치: "Pick up the block and place it in the box"
# ⚠️ 카메라 키 = 학습 modality와 일치: front=/dev/cam_top(=sim external_D455), wrist=/dev/cam_wrist(=sim ego)
# ⚠️ 시작 자세: goto_home_sim.py(=sim rest 자세)로 초기화 후 실행 — 실기 goto_home과 다름!
#    (사전 점검: 실기 goto_home은 shoulder_lift·elbow가 sim 학습 분포 밖 → OOD 시작 방지)
# ⚠️ max_relative_target=8: 안전 클램프. 무한 루프 — 측정 시 수동 타이밍, Ctrl+C 종료.
LAUNCH_DIR="$(cd "$(dirname "$0")" && pwd)/client"
cd "$(dirname "$0")/../../envs/lerobot" || exit 1

SERVER_HOST="${SERVER_HOST:-192.168.0.56}"   # 5090
MRT="${MRT:-8.0}"
HORIZON="${HORIZON:-16}"   # 청크(16) 실행 수 — covariate shift 완화 실측치
# 언어 지시문. 기본은 학습(sim)과 정확히 일치. 일반화 실험(색상/물체 변경) 시
# LANG_INSTRUCTION 환경변수로 덮어써서 조건별 지시문 사용:
#   LANG_INSTRUCTION="Pick up the red block and place it in the box" ./infer_gr00t_blocktask_remote.sh
LANG_INSTRUCTION="${LANG_INSTRUCTION:-Pick up the block and place it in the box}"

CAMS="{ front: {type: opencv, index_or_path: /dev/cam_top,  width: 640, height: 480, fps: 30, fourcc: MJPG},
        wrist: {type: opencv, index_or_path: /dev/cam_wrist, width: 640, height: 480, fps: 30, fourcc: MJPG}}"

cd "$LAUNCH_DIR"  # service.py 로컬 import 위해 client/ 에서 실행
exec uv run --project ../../../envs/lerobot python eval_lerobot.py \
  --robot.type=so101_follower \
  --robot.port=/dev/ttyFOLLOWER \
  --robot.id=follower \
  --robot.max_relative_target="$MRT" \
  --robot.cameras="$CAMS" \
  --policy_host="$SERVER_HOST" \
  --policy_port=5555 \
  --action_horizon="$HORIZON" \
  --lang_instruction="$LANG_INSTRUCTION"
