#!/usr/bin/env bash
# P0 관문 ① — **박스 축소가 성공률을 떨어뜨리는가**를 수집 전에 잰다.
#
# 왜 필요한가 (language_conditioning_sim_plan.md §2-2):
#   언어 씬은 물체 4개와 박스 2개를 함께 놓기 위해 박스를 0.85 → 0.7배로 줄인다.
#   줄이면 놓을 자리가 좁아져 **언어와 무관한 실패**가 늘 수 있다. 그 경우
#   "언어 조건화가 안 됐다"와 "박스가 작아 못 넣었다"가 뒤섞여 판정이 불가능해진다.
#   5시간 수집 + 19시간 학습을 쓰기 전에 35분으로 확인한다.
#
# 통제: **한 번에 한 축만.** `box_small` 프리셋은 박스 scale과 성공 경계만 바꾼다
#   (물체·리셋은 그대로). 언어 씬(`lang`)으로 재면 축이 섞여 답이 안 나온다.
#
# 판정: 축소본이 기준선 대비 **−2 이내**면 통과(물리 DR 변동이 ±1이라 −2까지는 잡음).
#   크게 떨어지면 scale 0.8로 되돌리고 물체 간격을 좁힌다.
#
# 사용: ./run_gate_boxscale.sh            # 3조건 × 30ep (조건당 약 13분, 무인)
#   이미 끝난 조건은 건너뛴다(결과 폴더 존재 여부로 판단) — 새 배율만 추가로 잴 수 있다.
#       NUM=10 ./run_gate_boxscale.sh     # 예행
set -uo pipefail

SEED="${SEED:-100}"
NUM="${NUM:-30}"
MODEL="${MODEL:-gr00t_blocktask_v4_200_n16_8bit/checkpoint-86000}"
HOST="${HOST:-5090}"
DEST="$HOME/manipulator_ws/inf_video/09_gate_boxscale"
HERE="$(cd "$(dirname "$0")" && pwd)"
L0="Pick up the block and place it in the box"

# 태그|씬조건 — 기준선과 축소본. 지시문·시드·패널이 모두 같아 차이는 박스 크기뿐이다.
CONDS=("base085|full" "small070|full+box_small" "small080|full+box_080")

mkdir -p "$DEST"
echo "▶ 관문 ① 박스 축소 · ${#CONDS[@]}조건 × ${NUM}ep · seed $SEED · 패널 고정"
echo "  모델 $MODEL"
echo "  예상 $(( ${#CONDS[@]} * NUM * 70 / 60 ))분"
echo

# 두 파일 모두 올린다. 5090 사본이 뒤처지면 조용히 다르게 동작한다
# (configure_scene.py가 낡으면 box_small을 몰라 죽는다).
for f in blocktask_headless_scenes.sh configure_scene.py; do
  scp -q "$HERE/$f" "$HOST:~/$f" || { echo "❌ $f 전송 실패"; exit 1; }
done
ssh "$HOST" "chmod +x ~/blocktask_headless_scenes.sh"

T0=$(date +%s)
for c in "${CONDS[@]}"; do
  TAG="${c%%|*}"; COND="${c##*|}"
  name="hl_${COND}_${TAG}_s${SEED}"
  printf "  %-34s " "$name"
  if [ -d "$DEST/$name" ] && [ -f "$DEST/$name/scenes.csv" ]; then echo "건너뜀 (이미 있음)"; continue; fi
  t0=$(date +%s)
  ssh "$HOST" "TAG=$(printf %q "$TAG") LANG_INSTRUCTION=$(printf %q "$L0") \
      MODEL=$(printf %q "$MODEL") EVAL_PANEL=1 \
      ~/blocktask_headless_scenes.sh $(printf %q "$COND") $NUM $SEED" \
      > "/tmp/gate_${name}.log" 2>&1
  rsync -a "$HOST:~/blocktask_ws/Sim-to-Real-SO-101-Workshop/outputs/$name" "$DEST/" 2>/dev/null
  if [ -d "$DEST/$name" ]; then
    chmod u+w "$DEST/$name"
    cat > "$DEST/$name/run.json" <<META
{"gate":"boxscale","cond":"$COND","tag":"$TAG","seed":$SEED,"episodes":$NUM,
 "model":"$MODEL","lang":"$L0","eval_panel":"1","finished":"$(date -Is)"}
META
  fi
  n=$(ls "$DEST/$name"/*.mp4 2>/dev/null | wc -l)
  if [ "$n" -gt 0 ]; then echo "✅ 영상 ${n}개 ($(( ($(date +%s)-t0)/60 ))분)"
  else echo "❌ 실패 — /tmp/gate_${name}.log 확인"; fi
done

echo
echo "▶ 총 $(( ($(date +%s)-T0)/60 ))분 · $DEST"
echo
echo "판정:"
for d in "$DEST"/hl_*; do
  [ -f "$d/scenes.csv" ] || continue
  ok=$(awk -F, 'NR>1 && $2=="success"' "$d/scenes.csv" | wc -l)
  tot=$(($(wc -l < "$d/scenes.csv") - 1))
  echo "  $(basename "$d"): ${ok}/${tot}"
done
echo "  ※ scenes.csv의 outcome은 termination 기준이다. 차이가 −2 근방이면 영상으로 재확인할 것."
