#!/usr/bin/env bash
# P5 무인 평가 — 언어 조건화 판정. 조건 10개 × 30ep, 사람 0.
#
# 무엇을 보나 (language_conditioning_sim_plan.md §7-2·7-3):
#   **대응쌍**이 전부다. 1↔2(색), 3↔4(이름), 5↔6(목적지)는 같은 배치에서 문장만 다르다.
#   배치는 같은 계획표 + 같은 seed로 재현되므로, 성공률 차이의 출처가 오직 언어로 특정된다.
#
#   판정선 — 후보가 4개이므로 물체 선택의 우연은 25%, 박스 2개인 목적지는 50%다.
#     물체 선택률 (조건 1~4 합산 120시행)  ≥ 45%
#     목적지 선택률 (조건 5·6 합산 60시행) ≥ 65%
#     조건 9(레거시)                      기준선 9/10 대비 −2 이내  ← 기존 성능 보존
#     조건 10(모호)                       우연 수준이어야 정상
#
# 사용:
#   ./run_eval_lang.sh                       # 전 조건
#   MODEL=gr00t_blocktask_lang_n16_8bit/checkpoint-25000 ./run_eval_lang.sh
#   ONLY="1 2 3 4" ./run_eval_lang.sh        # 일부만
#   NUM=10 ./run_eval_lang.sh                # 예행
set -uo pipefail
cd "$(dirname "$0")"

SEED="${SEED:-4242}"
NUM="${NUM:-30}"
MODEL="${MODEL:-gr00t_blocktask_lang_n16_8bit/checkpoint-25000}"
HOST="${HOST:-5090}"
PLANDIR="${PLANDIR:-$(cd ../../../manipulator_md/sim && pwd)}"
# RUN 라벨 — 모델이 다르면 결과 폴더도 달라야 한다. 안 나누면 러너가 이전 실행의
#   scenes.csv를 집어 들어 **다른 모델의 숫자를 보고한다**(출력 이름이 모델을 안 담는다).
RUN="${RUN:-}"
DEST="${DEST:-$HOME/manipulator_ws/inf_video/10_eval_lang${RUN:+_$RUN}}"
ONLY="${ONLY:-}"

# 조건표 — 번호|패널|EVAL_TARGET|EVAL_DEST|지시문
#   조건 9는 언어 씬이 아니라 **기존 패널**(full + EVAL_PANEL=1)에서 돈다.
#   기준선 9/10이 그 조건에서 측정됐으므로, 같은 조건이어야 비교가 성립한다.
CONDS=(
  "1|P1|red_cube|black|Pick up the red block and place it in the box"
  "2|P1|blue_cube|black|Pick up the blue block and place it in the box"
  "3|P1|eraser|black|Pick up the eraser and place it in the box"
  "4|P1|marker|black|Pick up the marker and place it in the box"
  "5|P2|yellow_cube|black|Pick up the yellow block and place it in the black box"
  "6|P2|yellow_cube|brown|Pick up the yellow block and place it in the brown box"
  "7|P3|green_cube|gray|Put the green block into the gray box"
  "8|P1|blue_cube|black|Grab the blue cube and put it in the container"
  "9|LEGACY|||Pick up the block and place it in the box"
  "10|P1|red_cube|black|Pick up the cube and place it in the box"
)

mkdir -p "$DEST"
echo "▶ P5 언어 조건화 평가 · ${#CONDS[@]}조건 × ${NUM}ep · seed $SEED"
echo "  모델 $MODEL"
echo "  예상 $(( ${#CONDS[@]} * NUM * 70 / 60 ))분"
echo

# 계획표가 없으면 만든다
for p in P1 P2 P3; do
  [ -f "$PLANDIR/lang_eval_$p.csv" ] || {
    echo "  계획표 생성..."; python3 ./gen_lang_eval_plan.py --out-dir "$PLANDIR" --episodes "$NUM" >/dev/null; break; }
done

# 씬·러너·계획표를 5090으로. 사본이 뒤처지면 조용히 다르게 동작한다 —
# 전례: 씬을 배포하지 않아 v2 씬에서 측정한 무효 데이터를 만든 적이 있다.
for f in blocktask_headless_scenes.sh configure_scene.py; do
  scp -q "$f" "$HOST:~/$f" || { echo "❌ $f 전송 실패"; exit 1; }
done
# 씬 코드(mdp)도 보낸다. reset_lang_scene은 수집 때 **로컬에만** 추가했으므로
# 이것을 빼면 5090에서 ImportError로 죽는다(2026-09-26 실측).
rsync -a "$HOME/blocktask_ws/Sim-to-Real-SO-101-Workshop/source/sim_to_real_so101/mdp/" \
  "$HOST:~/blocktask_ws/Sim-to-Real-SO-101-Workshop/source/sim_to_real_so101/mdp/" \
  || { echo "❌ mdp 전송 실패"; exit 1; }
ssh "$HOST" "mkdir -p ~/lang_eval_plans && chmod +x ~/blocktask_headless_scenes.sh"
scp -q "$PLANDIR"/lang_eval_P?.csv "$HOST:~/lang_eval_plans/" || exit 1

T0=$(date +%s)
for c in "${CONDS[@]}"; do
  IFS='|' read -r N PAN TGT DST LANG <<< "$c"
  [ -n "$ONLY" ] && ! grep -qw "$N" <<< "$ONLY" && continue
  GLOB="hl_*lang${RUN:+_$RUN}_c${N}_s${SEED}"
  printf "  조건 %-2s %-22s " "$N" "${TGT:-legacy}${DST:+ → $DST}"
  ex=$(ls -d "$DEST"/$GLOB 2>/dev/null | head -1); [ -n "$ex" ] && [ -f "$ex/scenes.csv" ] && { echo "건너뜀 (이미 있음)"; continue; }
  t0=$(date +%s)

  if [ "$PAN" = "LEGACY" ]; then
    # 기존 패널 — 언어 씬을 쓰지 않는다. 기준선이 측정된 바로 그 조건.
    ENVS="TAG=$(printf %q "lang${RUN:+_$RUN}_c$N") LANG_INSTRUCTION=$(printf %q "$LANG") MODEL=$(printf %q "$MODEL") EVAL_PANEL=1"
    COND="full"
  else
    ENVS="TAG=$(printf %q "lang${RUN:+_$RUN}_c$N") LANG_INSTRUCTION=$(printf %q "$LANG") MODEL=$(printf %q "$MODEL") \
          EVAL_TARGET=$(printf %q "$TGT") EVAL_DEST=$(printf %q "$DST") \
          LANG_PLAN=\$HOME/lang_eval_plans/lang_eval_${PAN}.csv"
    COND="full+lang"
  fi

  ssh "$HOST" "$ENVS ~/blocktask_headless_scenes.sh $COND $NUM $SEED" \
    > "/tmp/eval_lang_c${N}.log" 2>&1
  src="hl_${COND//+/_}_lang_c${N}_s${SEED}"
  rsync -a "$HOST:~/blocktask_ws/Sim-to-Real-SO-101-Workshop/outputs/hl_${COND}_lang${RUN:+_$RUN}_c${N}_s${SEED}" "$DEST/" 2>/dev/null
  found=$(ls -d "$DEST"/$GLOB 2>/dev/null | head -1)
  if [ -n "$found" ] && [ -f "$found/scenes.csv" ]; then
    chmod -R u+w "$found" 2>/dev/null
    printf '{"cond":%s,"panel":"%s","target":"%s","dest":"%s","lang":"%s","seed":%s,"episodes":%s,"model":"%s","finished":"%s"}\n' \
      "$N" "$PAN" "$TGT" "$DST" "$LANG" "$SEED" "$NUM" "$MODEL" "$(date -Is)" > "$found/run.json"
    ok=$(awk -F, 'NR>1 && $2=="success"' "$found/scenes.csv" | wc -l)
    tot=$(($(wc -l < "$found/scenes.csv") - 1))
    echo "✅ ${ok}/${tot}  ($(( ($(date +%s)-t0)/60 ))분)"
  else
    echo "❌ 실패 — /tmp/eval_lang_c${N}.log 확인"
  fi
done

echo
echo "▶ 총 $(( ($(date +%s)-T0)/60 ))분 · $DEST"
echo
python3 - "$DEST" "$SEED" <<'PY'
import glob, os, sys, csv
dest, seed = sys.argv[1], sys.argv[2]
res = {}
for d in glob.glob(f"{dest}/hl_*_c*_s{seed}"):
    n = int(os.path.basename(d).rsplit("_c", 1)[1].split("_s")[0])
    f = f"{d}/scenes.csv"
    if not os.path.exists(f):
        continue
    rows = list(csv.reader(open(f)))[1:]
    res[n] = (sum(1 for r in rows if len(r) > 1 and r[1] == "success"), len(rows))

def rate(ns):
    a = sum(res[n][0] for n in ns if n in res); b = sum(res[n][1] for n in ns if n in res)
    return a, b, (100.0 * a / b if b else 0.0)

print("=" * 70)
print(" 조건별 성공률")
print("=" * 70)
for n in sorted(res):
    ok, tot = res[n]
    print(f"  조건 {n:>2}: {ok:>3}/{tot:<3} = {100.0*ok/tot if tot else 0:5.1f}%")

print("\n" + "=" * 70)
print(" 판정 (§7-3)")
print("=" * 70)
a, b, r = rate([1, 2, 3, 4])
print(f"  물체 선택률  (조건 1~4)  {a}/{b} = {r:5.1f}%   우연 25% · 합격 45%   "
      f"{'✅' if r >= 45 else '❌'}")
a, b, r = rate([5, 6])
print(f"  목적지 선택률(조건 5·6)  {a}/{b} = {r:5.1f}%   우연 50% · 합격 65%   "
      f"{'✅' if r >= 65 else '❌'}")
if 9 in res:
    ok, tot = res[9]
    print(f"  기존 성능    (조건 9)    {ok}/{tot}         기준선 9/10 대비 −2 이내   "
          f"{'✅' if ok >= 7 * tot / 10 else '❌'}")
if 10 in res:
    ok, tot = res[10]
    print(f"  모호 대조    (조건 10)   {ok}/{tot} = {100.0*ok/tot if tot else 0:5.1f}%   "
          f"우연 수준이어야 정상")
print("\n  ※ scenes.csv의 outcome은 termination 기준이다. 경계값이면 영상으로 재확인할 것.")
PY
