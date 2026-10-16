#!/usr/bin/env bash
# 평가 B — sim 일반화. **v4_200(sim 단독 학습) 모델**로 어느 축이 약한지 훑는다.
#
# 왜 sim 단독 모델인가:
#   co-train 모델은 실기 분포가 섞여 있어 "sim에서 배운 표현이 얼마나 일반화되는가"를
#   묻는 이 평가의 질문과 다르다. 여기서 약한 축이 나오면 실기(평가 C)에서는 그 축만 본다.
#
# 실행 위치: **로컬에서 실행**한다. 계산은 5090에서 돌고(Isaac + 정책 서버 모두 필요),
#   조건이 끝날 때마다 곧바로 로컬로 가져온다 — 중간에 죽어도 끝난 조건은 남는다.
#
# ⚠️ 5090의 gr00t-srv(co-train 모델 실기 서빙)가 내려간다. 실기 추론과 동시에 못 쓴다.
#
# 사용:
#   ./run_evalB.sh                 # 7조건 × 45ep, seed 31
#   NUM=20 ./run_evalB.sh          # 짧게 예행
#   ONLY="L0 L3 L5" ./run_evalB.sh # 일부만
set -uo pipefail

SEED="${SEED:-31}"
NUM="${NUM:-45}"
MODEL="${MODEL:-gr00t_blocktask_v4_200_n16_8bit/checkpoint-86000}"
HOST="${HOST:-5090}"
# EVAL_PANEL=1 → 씬을 매번 새로 뽑지 않고 고정 10배치를 순서대로 재생한다(EVAL_PANEL_10).
#   위치 난이도를 조건 간 상수로 만들어, 성공률 차이가 오직 색·형상·문장에서만 오게 한다.
#   실측 근거: 같은 모델·같은 조건인데 시드만 바꾸니 70% ↔ 30%로 갈렸다(2026-08-12).
EVAL_PANEL="${EVAL_PANEL:-0}"
DEST="$HOME/manipulator_ws/inf_video/08_evalB_sim"
HERE="$(cd "$(dirname "$0")" && pwd)"
L0="Pick up the block and place it in the box"

# 태그|씬조건|지시문   — 우선순위 1~4의 7조건
# 언어 축(L0/L3/L5)은 **씬조건과 시드가 모두 같고 문장만 다르다**. 그래야 언어 효과가
# 씬 차이와 섞이지 않는다(그래서 blocktask_headless_scenes.sh에 TAG를 추가했다).
CONDS=(
  "L0|full|$L0"
  "L3|full|Grab the cube and put it in the container"
  "L5|full|Pick up the block and place it on the table"
  "|full+dist_blue_cube|$L0"
  "|full+obj_sphere|$L0"
  "|full+obj_small|$L0"
  "|full+color_white|$L0"
)
# 외형·방해물 축에 `full+`을 붙이는 이유:
#   단일 프리셋(color_white 등)은 DEFAULT에서 출발해 **박스가 고정되고 물리 DR도 꺼진다**.
#   그 상태로 재면 (a) 기준선 full(75.6%)과 씬 체제가 달라 비교가 성립하지 않고,
#   (b) 배포 조건이 아닌 v2 시절 씬에서 일반화를 재게 된다.
#   실측(seed 999): full 계열은 blk(0.242,0.322), 단일 프리셋 계열은 blk(0.260,-0.359)로
#   씬 자체가 갈렸다. full+X로 맞추면 L0가 네 축 전부의 공통 기준선이 된다.
#   ※ 방해물만은 난수를 더 소비해 씬이 완전히 일치하지 않는다(구조적 한계).

if [ -n "${ONLY:-}" ]; then
  sel=(); for c in "${CONDS[@]}"; do
    key="$(cut -d'|' -f1 <<<"$c")"; [ -z "$key" ] && key="$(cut -d'|' -f2 <<<"$c")"
    for w in $ONLY; do [ "$w" = "$key" ] && sel+=("$c"); done
  done
  CONDS=("${sel[@]}")
fi

mkdir -p "$DEST"
echo "▶ 평가 B · ${#CONDS[@]}조건 × ${NUM}ep · seed $SEED"
echo "  모델 $MODEL"
echo "  예상 $(( ${#CONDS[@]} * NUM * 70 / 3600 ))시간 $(( ${#CONDS[@]} * NUM * 70 % 3600 / 60 ))분"
echo "  저장 $DEST"
echo

# 두 파일 모두 올린다. 5090 사본이 뒤처지면 조용히 다르게 동작한다 —
#   headless 스크립트가 낡으면 TAG를 몰라 조건들이 한 디렉터리를 덮어쓰고,
#   configure_scene.py가 낡으면 `full+X` 조합에서 "알 수 없는 프리셋"으로 죽는다.
for f in blocktask_headless_scenes.sh configure_scene.py; do
  scp -q "$HERE/$f" "$HOST:~/$f" || { echo "❌ $f 전송 실패"; exit 1; }
done
ssh "$HOST" "chmod +x ~/blocktask_headless_scenes.sh"

T0=$(date +%s)
for c in "${CONDS[@]}"; do
  TAG="$(cut -d'|' -f1 <<<"$c")"
  COND="$(cut -d'|' -f2 <<<"$c")"
  LANG_I="$(cut -d'|' -f3- <<<"$c")"
  name="hl_${COND}${TAG:+_$TAG}_s${SEED}"
  printf "  %-28s " "$name"
  if [ -d "$DEST/$name" ] && [ -f "$DEST/$name/scenes.csv" ]; then echo "건너뜀 (이미 있음)"; continue; fi
  t0=$(date +%s)
  # 지시문에 아포스트로피가 섞여도 깨지지 않도록 %q로 감싼다.
  # (이 프로젝트에서 따옴표 중첩으로 지시문이 "Pick"으로 잘린 사고가 있었다.)
  ssh "$HOST" "TAG=$(printf %q "$TAG") LANG_INSTRUCTION=$(printf %q "$LANG_I") \
      MODEL=$(printf %q "$MODEL") EVAL_PANEL=$(printf %q "$EVAL_PANEL") \
      ~/blocktask_headless_scenes.sh $(printf %q "$COND") $NUM $SEED" \
      > "/tmp/evalB_${name}.log" 2>&1
  rsync -a "$HOST:~/blocktask_ws/Sim-to-Real-SO-101-Workshop/outputs/$name" "$DEST/" 2>/dev/null
  # 설정을 결과 옆에 남긴다. 원격 출력 디렉터리는 컨테이너가 root로 만들어 거기엔 못 쓴다.
  if [ -d "$DEST/$name" ]; then
    chmod u+w "$DEST/$name"
    cat > "$DEST/$name/run.json" <<META
{"cond":"$COND","tag":"$TAG","seed":$SEED,"episodes":$NUM,
 "model":"$MODEL","lang":"$LANG_I","finished":"$(date -Is)"}
META
  fi
  n=$(ls "$DEST/$name"/*.mp4 2>/dev/null | wc -l)
  if [ "$n" -gt 0 ]; then echo "✅ 영상 ${n}개 ($(( ($(date +%s)-t0)/60 ))분)"
  else echo "❌ 실패 — /tmp/evalB_${name}.log 확인"; fi
done

echo
echo "▶ 총 $(( ($(date +%s)-T0)/60 ))분 · $DEST"
echo
echo "분석:"
echo "  for d in $DEST/hl_*; do python3 $HERE/analyze_eval_scenes.py --label \"\$(basename \$d)\" \"\$d\"; done"
echo "  ※ L5는 자동 판정 의미가 뒤집혀 있다 — 육안 3분류(㉠박스에 넣음/㉡밖에 릴리스/㉢파지실패)"
