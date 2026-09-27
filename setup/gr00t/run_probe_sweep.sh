#!/usr/bin/env bash
# 체크포인트 여러 개에 언어 프로브를 돌려 **언어가 언제 살아나는가** 곡선을 만든다.
#
# 각 체크포인트마다: 5090에 서버 기동 → 준비 대기 → 로컬에서 프로브 → 서버 종료.
# 관측은 항상 **같은 로컬 v3.0 데이터셋**을 쓴다 — 비교가 성립하려면 관측이 같아야 한다.
#
# 사용:
#   ./run_probe_sweep.sh                                  # 보관본 6개
#   CKPTS="2000 25000" ./run_probe_sweep.sh                # 일부만
#   MODELDIR=gr00t_blocktask_lang_n16_8bit ./run_probe_sweep.sh   # 원본 폴더로
set -uo pipefail
cd "$(dirname "$0")"

HOST="${HOST:-5090}"
HOSTIP="${HOSTIP:-192.168.0.56}"
MODELDIR="${MODELDIR:-gr00t_blocktask_lang_n16_8bit_keep}"
CKPTS="${CKPTS:-2000 4000 6000 10000 16000 25000}"
DATASET="${DATASET:-$HOME/blocktask_ws/Sim-to-Real-SO-101-Workshop/datasets/sim_so101_blocktask_lang}"
OUT="${OUT:-$HOME/manipulator_ws/manipulator_md/sim/probe_language.json}"
EPISODES="${EPISODES:-8}"
FRACS="${FRACS:-0.05,0.15,0.30}"
REPEATS="${REPEATS:-3}"
VENV="$HOME/manipulator_ws/envs/lerobot"

echo "▶ 프로브 곡선 · 체크포인트 $(echo $CKPTS | wc -w)개"
echo "  모델 폴더: $MODELDIR"
echo "  관측     : $(basename "$DATASET")  ${EPISODES}ep × ${FRACS} × 반복 ${REPEATS}"
echo "  기록     : $OUT"
echo

for c in $CKPTS; do
  echo "── checkpoint-$c ──"
  ssh "$HOST" "~/serve_blocktask_n16_5090.sh $MODELDIR/checkpoint-$c start" >/dev/null 2>&1 \
    || { echo "  ❌ 서버 기동 실패"; continue; }

  ready=0
  for i in $(seq 1 40); do
    if ssh "$HOST" 'docker logs gr00t-srv 2>&1 | grep -qi "Server is ready"' 2>/dev/null; then ready=1; break; fi
    ssh "$HOST" 'docker ps --format "{{.Names}}" | grep -q "^gr00t-srv$"' 2>/dev/null \
      || { echo "  ❌ 서버가 죽었다"; break; }
    sleep 10
  done
  [ "$ready" = "1" ] || { ssh "$HOST" '~/serve_blocktask_n16_5090.sh "" stop' >/dev/null 2>&1; continue; }

  (cd "$VENV" && uv run python "$HOME/manipulator_ws/setup/gr00t/probe_language.py" \
      --dataset "$DATASET" --host "$HOSTIP" --port 5555 \
      --episodes "$EPISODES" --fracs "$FRACS" --repeats "$REPEATS" \
      --label "${LABEL:-$(echo "$MODELDIR" | sed 's/gr00t_blocktask_//;s/_n16_8bit_keep//;s/_n16_8bit//')}@${c}" --out "$OUT" 2>&1) | grep -E "색|이름|목적지|잡음|패러|기록:"

  ssh "$HOST" '~/serve_blocktask_n16_5090.sh "" stop' >/dev/null 2>&1
  echo
done

echo "▶ 곡선 요약"
python3 - "$OUT" <<'PY'
import json, sys
h = json.load(open(sys.argv[1]))
keys = ["잡음 하한 (같은 문장 2회)", "색 (red ↔ blue)", "이름 (eraser ↔ marker)",
        "목적지 (black ↔ brown box)", "패러프레이즈 (동의어)"]
short = ["잡음", "색", "이름", "목적지", "패러프"]
print(f"  {'체크포인트':<22}" + "".join(f"{s:>9}" for s in short))
print("  " + "─" * (22 + 9 * len(short)))
for rec in h:
    r = rec["results"]
    row = "".join(f"{r[k]['mean_deg']:9.2f}" if k in r else f"{'—':>9}" for k in keys)
    print(f"  {rec['label']:<22}{row}")
print("\n  판정선: 색·이름·목적지 ≥5° · 눈금: 영상 교체 18.9°")
PY
