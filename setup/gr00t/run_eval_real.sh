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

# 앙상블을 끈 시행은 조건 이름에 박아둔다. 평가 A에서 tNN은 이미 박스 방향(t01=세로,
# t02=가로)을 뜻하므로, 표식이 없으면 t03이 "세 번째 방향"인지 "앙상블 끔"인지 구분되지 않는다.
if [ "${ENSEMBLE:-1}" != "1" ]; then COND="${COND}_noens"; fi

# 시행 번호 자동 증가 — 이전 결과를 덮어쓰지 않는다
n=1
while [ -d "$ROOT/${COND}_t$(printf %02d $n)" ]; do n=$((n+1)); done
OUT="$ROOT/${COND}_t$(printf %02d $n)"

# co-training 모델은 **실기 rest 자세**로 시작해야 한다. sim-only 모델용 goto_home_sim.py와
# 다르며, 잘못 쓰면 학습 분포 밖에서 출발한다.
export HOME_SCRIPT="${HOME_SCRIPT:-goto_home_real.py}"
export SERVER_HOST="${SERVER_HOST:-192.168.0.56}"
# 추론은 IP로 붙지만, 서빙 중인 체크포인트를 조회할 때는 ssh 별칭이 필요하다(둘이 다르다).
SERVER_HOST_SSH="${SERVER_HOST_SSH:-5090}"
export STEP_DT="${STEP_DT:-0.033}"
export ENSEMBLE="${ENSEMBLE:-1}"
# 액션 앙상블 가중치. **실측으로 정한 값이다 — 이론 보간을 믿지 말 것.**
#
#   설정        평균 정지   최장 정지   튐 99%tile   성공
#   W=0.3        24.8s      14.0s      2.55°      7/10 (in-dist)
#   W=0.6        42.9s      14.1s      2.34°      1/5  (평가 C L0) ← 최악
#   W=0.8        11.0s       5.1s      3.36°      4/5  (OOD)
#   ENSEMBLE=0    6.5s       2.8s      9.02°      4/5  (in-dist 세로)
#   교시 데이터     6.4s       2.2s      2.99°       —
#
# W=0.6은 **튐 99%tile을 교시 데이터(2.99°)에 맞춰 역산**한 값이었다. 그 지표만 보면
# 2.34°로 목표에 맞았지만 정지가 42.9초로 폭증해 1/5까지 떨어졌다.
# 튐과 정지는 **반대 방향으로 움직이는 지표**인데 한쪽만 최적화한 것이 잘못이었고,
# 무엇보다 **실기에서 검증하지 않은 보간값을 기본값으로 넣은 것**이 문제였다.
#
# W=0.8: 최신 청크 비중 94%. 정지를 교시 수준 근처(11.0s)로 유지하면서
# OFF의 튐(9.02°, 교시의 3배)을 피한다. 앙상블을 유지하려면 이 값이 실측 최적이다.
export ENSEMBLE_W="${ENSEMBLE_W:-0.6}"
export VIDEO_FPS="${VIDEO_FPS:-10}"
export LOGDIR="$OUT"

# 서버가 살아 있는지 먼저 본다 — Isaac 없이 붙는 구조라 실패가 늦게 드러난다
if ! timeout 5 bash -c "exec 3<>/dev/tcp/${SERVER_HOST}/5555" 2>/dev/null; then
  echo "❌ ${SERVER_HOST}:5555 접속 불가 — 서버를 먼저 띄우세요:"
  echo "   원격(5090): ssh 5090 '~/serve_blocktask_n16_5090.sh <MODEL>/checkpoint-NNNNN start'"
  echo "   로컬:       ./serve_local.sh <MODEL>/checkpoint-NNNNN   (SERVER_HOST=127.0.0.1 로 실행)"
  exit 1
fi

# 어떤 체크포인트가 서빙 중인지 **서버에 물어서** 기록한다.
#   모델은 서버가 정하고 클라이언트는 모른다. 그래서 지금까지 결과물만 보고는
#   "어느 체크포인트로 돌렸는가"를 증명할 수 없었다(2026-08-12 확인).
#   실패하면 빈 값으로 두고 계속 진행한다 — 기록 때문에 평가를 막지는 않는다.
#   로컬 서버(127.0.0.1)면 ssh 없이 이 기계에서 바로 조회한다.
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

# 설정을 함께 남긴다 — 나중에 로그만 보고 어떤 조건이었는지 되짚을 수 있어야 한다
mkdir -p "$OUT"
cat > "$OUT/run.json" <<META
{"eval":"$EVAL","cond":"$COND","trial":$n,"ensemble":"${ENSEMBLE}","ensemble_w":"${ENSEMBLE_W}",
 "step_dt":"${STEP_DT}","video_fps":"${VIDEO_FPS}","home":"${HOME_SCRIPT}","server":"${SERVER_HOST}",
 "model":"${MODEL_PATH}","host_kind":"$(echo)${SERVER_HOST}","lang":"${LANG_INSTRUCTION:-Pick up the block and place it in the box}",
 "started":"$(date -Is)"}
META

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
