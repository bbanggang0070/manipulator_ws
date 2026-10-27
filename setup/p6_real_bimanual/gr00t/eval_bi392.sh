#!/usr/bin/env bash
# 392ep 모델 2종(언어 모델 위 8층 / 위 4층 학습) 실기 평가 — 서빙 확인 → 평가 기록 → 요약.
#
# 300ep 때와 같은 평가 계획표·같은 결과 형식을 쓴다. 그래서 끝나면 300ep 두 모델과
# 네 조합(데이터 300/392 × 층 4/8)으로 바로 비교된다(compare_eval_bi.py).
#
#   모델                                      평가 이름 / 결과 csv
#   llm8 = gr00t_bi_cleanup392_llm8_n16_8bit  bi392llm8_A · bi392llm8_eval_A.csv
#   llm4 = gr00t_bi_cleanup392_n16_8bit       bi392_A     · bi392_eval_A.csv
#   (300ep 쪽 이름과 같은 규칙 — bi300 = 4층, bi300llm8 = 8층)
#
# 서빙은 **5090**(serve_bi_5090.sh)에서 한다 — 체크포인트를 로컬로 받지 않는다.
#   로봇·카메라·클라이언트는 그대로 로컬이고, 클라이언트만 SERVER_HOST=192.168.0.56 으로 붙는다.
#   (5090 응답 73ms ≈ 로컬 86ms 라 300ep 로컬 서빙 결과와 비교해도 된다 — serve_bi_5090.sh 머리말)
#   로컬 서빙으로 돌리려면 SERVE=local ./eval_bi392.sh llm8  (체크포인트가 로컬에 있어야 한다)
#
# 하는 일:
#   1) 5090 gr00t-srv 가 다른 모델이면 이 모델로 바꿔 띄운다(학습 중이면 멈춘다)
#   2) cleanup_eval_bi.py log 로 시행을 진행한다(이미 기록된 시행은 건너뛰고 이어서)
#   3) 끝나면 report 와 compare_eval_bi.py 요약을 출력한다
#
# 사용 (로컬, 로봇·카메라 연결 상태):
#   ./eval_bi392.sh llm8          # 평가 A 36시행
#   ./eval_bi392.sh llm4          # 4층 학습이 끝난 뒤
#   ./eval_bi392.sh llm8 B        # 평가 B 60시행 (앞 36시행은 같은 모델의 평가 A 결과를 가져와 37번부터)
#   ./eval_bi392.sh llm8 A --redo # 기록된 시행도 다시
#   ENSEMBLE_W=0.7 ./eval_bi392.sh llm8   # 앙상블 가중치 변경 — 같은 결과에 이어서 (값은 시행별 run.json 에 기록)
#   중간에 Ctrl+C 로 끊어도 된다 — 다시 실행하면 기록된 다음 시행부터 이어진다.
set -euo pipefail

WHICH="${1:?llm8 또는 llm4}"; EV="${2:-A}"; shift $(( $# >= 2 ? 2 : 1 ))
case "$WHICH" in
  llm8) M=gr00t_bi_cleanup392_llm8_n16_8bit; TAG=bi392llm8 ;;
  llm4) M=gr00t_bi_cleanup392_n16_8bit;      TAG=bi392 ;;
  *) echo "❌ 모델은 llm8 또는 llm4"; exit 1 ;;
esac
case "$EV" in A|B) ;; *) echo "❌ 평가는 A 또는 B"; exit 1 ;; esac
C="${CKPT:-checkpoint-69000}"
# 앙상블 가중치 — 결과 csv·영상 폴더는 그대로 이어 쓰고, 시행마다 run.json 의 ensemble_w 에 남는다
export ENSEMBLE_W="${ENSEMBLE_W:-0.8}"

HERE="$(cd "$(dirname "$0")" && pwd)"
G="$HERE/../../gr00t"                       # serve_local.sh
D="$HERE/../data"                           # cleanup_eval_bi.py · compare_eval_bi.py
R="$HOME/manipulator_ws/manipulator_md/p6_real_bimanual"
LC="$HOME/gr00tn16_ws/checkpoints"
SERVE="${SERVE:-5090}"
OUT="$R/${TAG}_eval_${EV}.csv"

# 1) 서빙
if [ "$SERVE" = 5090 ]; then
  "$HERE/serve_bi_5090.sh" "$M/$C" || exit 1
  export SERVER_HOST=192.168.0.56 SERVER_HOST_SSH=5090
else
  docker_q() { if docker ps >/dev/null 2>&1; then eval "$1"; else sg docker -c "$1"; fi; }
  [ -f "$LC/$M/$C/model.safetensors.index.json" ] || { echo "❌ 로컬에 $M/$C 없음"; exit 1; }
  cur="$(docker_q 'docker inspect gr00t-srv --format "{{join .Config.Cmd \" \"}}"' 2>/dev/null \
         | grep -oE '/workspace/models/[^ ]+' | head -1 || true)"
  [ "$cur" = "/workspace/models/$M/$C" ] || "$G/serve_local.sh" "$M/$C" || exit 1
  export SERVER_HOST=127.0.0.1
fi
echo "▶ 서버 $SERVER_HOST:5555 · 모델 $M/$C · ENSEMBLE_W $ENSEMBLE_W"

# 2) 평가
if [ "$EV" = B ]; then
  PLAN=(--plan "$R/bi_cleanup_eval_plan_B.csv")
  if [ ! -f "$OUT" ] && [ -f "$R/${TAG}_eval_A.csv" ]; then
    cp "$R/${TAG}_eval_A.csv" "$OUT"
    echo "▶ 평가 A 결과를 가져옴 → 37번부터 (같은 모델·같은 체크포인트)"
  fi
else
  PLAN=()
fi
echo "▶ 평가 ${EV} · 결과 $OUT · 영상 inf_video/07_real_eval_bi/${TAG}_${EV}/"
cd "$D"
python3 cleanup_eval_bi.py log "${PLAN[@]}" --eval-name "${TAG}_${EV}" --out "$OUT" --rerun "$@" || true

# 3) 요약
python3 cleanup_eval_bi.py report --out "$OUT"
python3 compare_eval_bi.py --eval "$EV"
