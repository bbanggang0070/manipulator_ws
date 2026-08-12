#!/usr/bin/env bash
# 실기 평가 시행 1회 — 조건 이름만 주면 저장 경로·홈 자세·환경변수를 알아서 맞춘다.
#
# 왜 래퍼가 필요한가:
#   평가 A는 10회(in-dist 5 + OOD 5), 평가 C는 그 이상이다. 매번 LOGDIR을 손으로 치면
#   오타 하나로 이전 시행을 덮어쓴다. 조건 이름만 받고 나머지는 고정한다.
#
# 사용:
#   ./run_eval_real.sh A indist_p1        # 평가 A, in-dist 자세 1
#   ./run_eval_real.sh A ood_o3           # 평가 A, OOD O3
#   ./run_eval_real.sh C L3_grab          # 평가 C, 지시문 L3
#   LANG_INSTRUCTION="Grab the cube and put it in the container" ./run_eval_real.sh C L3_grab
#
# 저장: ~/manipulator_ws/inf_video/07_real_eval/<평가>/<조건>_tNN/
#         video.mp4 (VIDEO_FPS=10) · chunks.csv · actions.csv
#   같은 조건을 다시 돌리면 t01 → t02 … 로 **자동 증가**한다(덮어쓰기 없음).
set -euo pipefail

EVAL="${1:?평가 이름 필요 (예: A, B, C)}"
COND="${2:?조건 이름 필요 (예: indist_p1, ood_o3, L3_grab)}"

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$HOME/manipulator_ws/inf_video/07_real_eval/$EVAL"
mkdir -p "$ROOT"

# 시행 번호 자동 증가 — 이전 결과를 덮어쓰지 않는다
n=1
while [ -d "$ROOT/${COND}_t$(printf %02d $n)" ]; do n=$((n+1)); done
OUT="$ROOT/${COND}_t$(printf %02d $n)"

# co-training 모델은 **실기 rest 자세**로 시작해야 한다. sim-only 모델용 goto_home_sim.py와
# 다르며, 잘못 쓰면 학습 분포 밖에서 출발한다.
export HOME_SCRIPT="${HOME_SCRIPT:-goto_home_real.py}"
export SERVER_HOST="${SERVER_HOST:-192.168.0.56}"
export STEP_DT="${STEP_DT:-0.033}"
export ENSEMBLE="${ENSEMBLE:-1}"
export ENSEMBLE_W="${ENSEMBLE_W:-0.3}"
export VIDEO_FPS="${VIDEO_FPS:-10}"
export LOGDIR="$OUT"

# 서버가 살아 있는지 먼저 본다 — Isaac 없이 붙는 구조라 실패가 늦게 드러난다
if ! timeout 5 bash -c "exec 3<>/dev/tcp/${SERVER_HOST}/5555" 2>/dev/null; then
  echo "❌ ${SERVER_HOST}:5555 접속 불가 — 5090에서 서버를 먼저 띄우세요:"
  echo "   ssh 5090 '~/serve_blocktask_n16_5090.sh <MODEL>/checkpoint-NNNNN start'"
  exit 1
fi

cat <<INFO

  평가 $EVAL · 조건 $COND · 시행 $(printf %02d $n)
  저장   $OUT
  서버   $SERVER_HOST:5555
  홈     $HOME_SCRIPT   ← co-train 모델은 goto_home_real.py 가 맞다
  영상   ${VIDEO_FPS}fps (기존 4fps → 파지 순간 확인용으로 상향)

  종료: Ctrl+C (mp4는 정상 마감된다)

INFO

cd "$HERE"
exec ./home_then_infer.sh
