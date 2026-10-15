#!/usr/bin/env bash
# 양팔 실기 평가 시행 1회 — setup/gr00t/run_eval_real.sh 의 양팔판.
# 조건 이름만 주면 저장 경로·환경변수를 맞추고 home_then_infer_bi.sh 로 넘긴다.
#
# 단일팔판과 다른 점은 셋뿐이다:
#   1) 홈 스크립트가 하나뿐이라(goto_home_bi.py) HOME_SCRIPT 선택 로직이 없다
#      (home_then_infer_bi.sh 안에 이미 고정돼 있다)
#   2) SERVER_HOST 기본값이 127.0.0.1 — 양팔 서빙은 아직 로컬(5070 Ti)만 검증했다
#      (원격 5090 서빙은 setup/gr00t/serve_blocktask_n16_5090.sh 양팔판이 없다 — 필요해지면 만든다)
#   3) ENSEMBLE_W 기본 0.8 — 단일팔 cleanup 실측 스윕(2026-10-10) 최적값을 그대로 가져왔다.
#      양팔 전용 스윕은 아직 없다(필요하면 0.6/0.8 등으로 직접 비교할 것).
#
# 사용:
#   ./run_eval_real_bi.sh bi_cleanup trial01
#   (보통은 cleanup_eval_bi.py log 가 이 스크립트를 자동으로 호출한다 — 직접 돌릴 일은 적다)
#
# 저장: ~/manipulator_ws/inf_video/07_real_eval_bi/<평가>/<조건>_tNN/
set -euo pipefail

EVAL="${1:?평가 이름 필요 (예: bi_cleanup)}"
COND="${2:?조건 이름 필요 (예: trial01)}"

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$HOME/manipulator_ws/inf_video/07_real_eval_bi/$EVAL"
mkdir -p "$ROOT"

if [ "${ENSEMBLE:-1}" != "1" ]; then COND="${COND}_noens"; fi

n=1
while [ -d "$ROOT/${COND}_t$(printf %02d $n)" ]; do n=$((n+1)); done
OUT="$ROOT/${COND}_t$(printf %02d $n)"

export SERVER_HOST="${SERVER_HOST:-127.0.0.1}"
SERVER_HOST_SSH="${SERVER_HOST_SSH:-5090}"
export STEP_DT="${STEP_DT:-0.033}"
export ENSEMBLE="${ENSEMBLE:-1}"
export ENSEMBLE_W="${ENSEMBLE_W:-0.8}"
export VIDEO_FPS="${VIDEO_FPS:-10}"
export LOGDIR="$OUT"

if ! timeout 5 bash -c "exec 3<>/dev/tcp/${SERVER_HOST}/5555" 2>/dev/null; then
  echo "❌ ${SERVER_HOST}:5555 접속 불가 — 서버를 먼저 띄우세요:"
  echo "   cd ~/manipulator_ws/setup/gr00t && ./serve_local.sh <MODEL>/checkpoint-NNNNN"
  exit 1
fi

_INSPECT='docker inspect $(docker ps -q --filter name=gr00t-srv) --format "{{join .Config.Cmd \" \"}}"'
case "$SERVER_HOST" in
  127.0.0.1|localhost|::1)
    MODEL_PATH="$( (docker ps >/dev/null 2>&1 && eval "$_INSPECT" || sg docker -c "$_INSPECT") 2>/dev/null \
      | grep -oE '/workspace/models/[^ ]+' | head -1)" ;;
  *)
    MODEL_PATH="$(ssh -o ConnectTimeout=5 -o BatchMode=yes "$SERVER_HOST_SSH" \
      'docker inspect gr00t-srv --format "{{join .Config.Cmd \" \"}}"' 2>/dev/null \
      | grep -oE '/workspace/models/[^ ]+' | head -1)" ;;
esac
[ -z "$MODEL_PATH" ] && echo "⚠ 서빙 모델 경로를 못 읽었습니다 — run.json의 model이 빕니다"

mkdir -p "$OUT"
cat > "$OUT/run.json" <<META
{"eval":"$EVAL","cond":"$COND","trial":$n,"ensemble":"${ENSEMBLE}","ensemble_w":"${ENSEMBLE_W}",
 "max_sec":"${MAX_SEC:-0}","stop_on_rest":"${STOP_ON_REST:-0}",
 "step_dt":"${STEP_DT}","video_fps":"${VIDEO_FPS}","home":"goto_home_bi.py","server":"${SERVER_HOST}",
 "model":"${MODEL_PATH}","lang":"${LANG_INSTRUCTION:-Put the red marker into the black bin}",
 "started":"$(date -Is)"}
META

cat <<INFO

  평가 $EVAL · 조건 $COND · 시행 $(printf %02d $n)
  저장   $OUT
  서버   $SERVER_HOST:5555
  홈     goto_home_bi.py (양팔 전용, 선택지 없음)
  영상   ${VIDEO_FPS}fps
  ENSEMBLE_W  ${ENSEMBLE_W}  (단일팔 실측 최적값 — 양팔 스윕은 미실시)

  종료: Ctrl+C (mp4는 정상 마감된다)
        MAX_SEC=${MAX_SEC:-0} (0=무제한)

INFO

cd "$HERE"
exec ./home_then_infer_bi.sh
