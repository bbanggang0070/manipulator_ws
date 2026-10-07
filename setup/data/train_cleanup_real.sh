#!/usr/bin/env bash
# 실기 cleanup 1단계 학습 — **파운데이션 모델에서 새로**. 5090에서 실행.
#
# 출발점이 이 스크립트의 핵심이다.
#   sim 1단계에서 같은 280 에피소드로 두 번 학습했는데 결과가 갈렸다:
#     기존 모델에서 **이어서**  → 물체 선택 22.5% (우연 25%) · 기존 성능 27%p 손실
#     파운데이션에서 **새로**   → 47.5% → (10배) 52.5%
#   이미 언어를 무시하도록 굳은 모델은 데이터를 바꿔도 안 풀린다.
#   그래서 여기서는 **반드시 nvidia/GR00T-N1.6-3B 에서 시작**한다.
#   sim 학습본(gr00t_blocktask_langB*)을 base 로 주면 안 된다.
#
# 학습량 — **step 이 아니라 epoch 으로 지정한다**:
#   sim 곡선에서 6.5 epoch 부근에 이미 최대 격차가 나왔고 그 뒤로 5배를 더 써도
#   나아지지 않았다(레거시만 16.7%p 잃음). 그래서 기준은 epoch 이다.
#   ⚠️ step 을 박아 두면 데이터가 늘었을 때 **조용히 학습량이 줄어든다.**
#      v1(80ep·47,080f)에서 6,000 step = 8.2 epoch 이었는데, 같은 6,000 step 을
#      v2(250ep·168,687f)에 쓰면 **2.3 epoch** 밖에 안 된다. 여기서 계산한다.
#        step = EPOCHS × frames ÷ 64
#      v2 기준: 8 epoch ≈ 21,000 step ≈ 16시간 (1,333 step/h 실측)
#   save-steps 는 체크포인트가 8개쯤 남도록 자동으로 잡는다 — sim 에서 "어느
#   지점이 최적인가"를 조건 2개로만 재서 단정하지 못했다. 곡선을 공짜로 얻어 둔다.
#
# ⚠️ SMOKE=1 로 10 step 먼저 돌려 **출발점을 확인**할 것.
#    이어학습이 조용히 성공해 버리면(체크포인트를 잘못 지정하면) 19시간을 버린다.
#    실측 눈금: 파운데이션에서 시작 → step10 loss **약 1.05~1.13**
#               학습된 체크포인트에서 이어받음 → 약 0.1 (1/10)
#    1.0 근처면 정상, 0.1 근처면 base 지정이 틀렸다.
#
# 사용 (5090에서):
#   SMOKE=1 ./train_cleanup_real.sh        # 10 step 확인
#   ./train_cleanup_real.sh                # 본 학습 (EPOCHS=8 → 약 21k step, 16h)
#   EPOCHS=6 ./train_cleanup_real.sh       # epoch 지정
#   ./train_cleanup_real.sh 12000          # step 직접 지정(우선)
#   EDGE=448 ./train_cleanup_real.sh       # 입력 해상도 448 (기본 256)
set -e

EPOCHS="${EPOCHS:-8}"       # step 은 아래에서 frames 로부터 계산한다
STEPS="${1:-}"              # 직접 주면 EPOCHS 보다 우선
DATA_ROOT="${DATA_ROOT:-$HOME/gr00tn16_ws/sim_data}"
DSNAME="${DSNAME:-cleanup_real}"
OUT_NAME="${OUT_NAME:-gr00t_cleanup_real_n16_8bit}"
BASE="${BASE:-nvidia/GR00T-N1.6-3B}"      # ⚠️ 바꾸지 말 것 — 위 주석 참조
SMOKE="${SMOKE:-0}"
NAME="gr00t-train8"

DS="$DATA_ROOT/heongyu/$DSNAME"
CKPT_DIR="$HOME/gr00tn16_ws/checkpoints"

# ── 준비 확인 ────────────────────────────────────────────────────────────
[ -d "$DS/meta" ] || { echo "❌ 데이터셋 없음: $DS"; echo "   prepare_cleanup_real.sh 를 먼저 돌리세요"; exit 1; }
[ -f "$DS/meta/modality.json" ] || { echo "❌ modality.json 없음 — 변환 후처리 누락"; exit 1; }

# frames 를 먼저 읽어 EPOCHS → STEPS 로 환산한다
FRAMES=$(python3 -c "import json;print(json.load(open('$DS/meta/info.json'))['total_frames'])")
if [ -z "$STEPS" ]; then
  STEPS=$(python3 -c "print(round($EPOCHS*$FRAMES/64/500)*500)")
  echo "  학습량: EPOCHS=$EPOCHS × ${FRAMES} frames ÷ 64 = ${STEPS} step (500 단위 반올림)"
fi

python3 - "$DS" "$STEPS" <<'PY' || exit 1
import json, sys
d, steps = sys.argv[1], int(sys.argv[2])
st = json.load(open(f"{d}/meta/stats.json"))
if "count" in st.get("observation.state", {}):
    sys.exit("❌ stats.json에 count가 남아 있다 — fix_stats_for_gr00t.py 미적용")
i = json.load(open(f"{d}/meta/info.json"))
frames = i["total_frames"]
# ⚠️ 이 게이트가 핵심이다. 지시문이 1종이면 언어 학습 신호가 0이라 학습이 무의미하다.
tasks = sum(1 for _ in open(f"{d}/meta/tasks.jsonl"))
print(f"  데이터셋: {i['codebase_version']} · {i['total_episodes']}ep · {frames:,} frames · 지시문 {tasks}종")
if tasks < 20:
    sys.exit(f"❌ 지시문이 {tasks}종뿐이다 — 변환이 태스크를 접었다. 학습해도 언어 신호가 0이다.")
ep = steps * 64 / frames
print(f"  {steps:,} step × batch 64 = {steps*64:,} 샘플 → {ep:.1f} epoch")
if ep > 14:
    print(f"  ⚠️  {ep:.1f} epoch 은 sim 권장(6~12)보다 많다 — 과적합 구간일 수 있다")
elif ep < 5:
    sys.exit(f"❌ {ep:.1f} epoch 은 너무 적다. EPOCHS 를 올리거나 STEPS 를 직접 줄 것 "
             f"(v1 에서 step 을 박아 둔 탓에 데이터가 3배로 늘자 학습량이 2.3 epoch 로 줄었다)")
PY

# ── 중복 실행 방지 ───────────────────────────────────────────────────────
if docker ps --format '{{.Names}}' | grep -q "^${NAME}$"; then
  echo "❌ $NAME 이 이미 실행 중입니다 (진행 중인 학습을 덮어쓰지 않도록 중단)."
  echo "   진행 상황: docker logs --tail 5 $NAME"
  exit 1
fi

# ── 입력 해상도 (실험 버튼) ──────────────────────────────────────────────
#   기본 256. 자세한 배경은 setup/gr00t/edge_patch.py 참조.
#   해상도를 올리면 호스트 RAM 이 병목이라 dataloader worker 를 내린다.
EDGE="${EDGE:-}"
EDGE_ARGS=(); WORKERS=8; PRE=""
if [ -n "$EDGE" ] && [ "$EDGE" != "256" ]; then
  _HERE="$(cd "$(dirname "$0")" && pwd)"
  PATCHER=""
  for _c in "${EDGE_PATCH:-}" "$_HERE/edge_patch.py" "$_HERE/../gr00t/edge_patch.py" \
            "$HOME/edge_patch.py" "$HOME/manipulator_ws/setup/gr00t/edge_patch.py"; do
    [ -n "$_c" ] && [ -f "$_c" ] && { PATCHER="$(cd "$(dirname "$_c")" && pwd)/$(basename "$_c")"; break; }
  done
  [ -n "$PATCHER" ] || { echo "❌ edge_patch.py 를 못 찾았습니다. scp 로 ~/ 에 두거나 EDGE_PATCH= 로 지정하세요"; exit 1; }
  EDGE_ARGS=(-e "GR00T_SHORTEST_EDGE=$EDGE" -v "$PATCHER:/tmp/edge_patch.py:ro")
  PRE="python3 /tmp/edge_patch.py --verify --ckpt $BASE && "
  WORKERS=2
  echo "  ⚠️ 입력 해상도 $EDGE (기본 256) · worker 8 → $WORKERS"
fi

# ── 저장 설정 ────────────────────────────────────────────────────────────
if [ "$SMOKE" = "1" ]; then
  STEPS=10; SAVE_STEPS=10; SAVE_LIMIT=1; OUT_NAME="${OUT_NAME}_smoke"
  echo
  echo "▶ 스모크 — 10 step. **초기 loss 로 출발점을 확인한다.**"
  echo "   파운데이션에서 시작 = 약 1.05~1.13 · 학습된 체크포인트 이어받음 = 약 0.1"
  echo "   1.0 근처면 정상. 0.1 근처면 base 지정이 틀렸다."
else
  # 체크포인트가 8개쯤 남도록 — 곡선을 얻기 위한 것이다
  SAVE_STEPS="${SAVE_STEPS:-$(python3 -c "print(max(round($STEPS/8/500)*500,500))")}"
  SAVE_LIMIT="${SAVE_LIMIT:-10}"
  # 체크포인트 1개 = 약 13GB(가중치 9.8 + optimizer 3.3)
  NEED=$(( (STEPS / SAVE_STEPS + 1) * 13 ))
  AVAIL=$(df -BG --output=avail "$CKPT_DIR" 2>/dev/null | tail -1 | tr -dc '0-9')
  echo "  체크포인트 여유: ${AVAIL}G (필요 약 ${NEED}G — 13GB × $((STEPS / SAVE_STEPS)) 개)"
  [ -n "$AVAIL" ] && [ "$AVAIL" -lt "$NEED" ] && { echo "❌ 공간 부족. 오래된 체크포인트를 지우고 다시 실행하세요."; exit 1; }
fi

echo
echo "  출발점       : $BASE"
echo "  데이터셋     : $DSNAME"
echo "  출력         : $OUT_NAME"
echo "  저장         : --save-steps $SAVE_STEPS --save-total-limit $SAVE_LIMIT"
echo

# SMOKE 는 **붙어서** 돌리고 로그를 남긴다. -d --rm 이면 컨테이너가 사라지며
# 로그도 날아가 loss 를 못 본다 — 그러면 스모크를 돌린 의미가 없다(실제로 겪음).
# ⚠️ `${SMOKE:+... | tee ...}` 같은 확장은 **파이프를 만들지 못한다**(쉘이 확장 결과를
#    재파싱하지 않는다). 반드시 if 로 갈라 써야 한다. 이것도 한 번 당했다.
run_docker() {
  docker run "$@" --name "$NAME" --rm --gpus all --network host --ipc=host \
    -e PYTHONUNBUFFERED=1 -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
    -e HF_TOKEN="$(cat $HOME/.cache/huggingface/token 2>/dev/null)" \
    -v "$DATA_ROOT:/data" \
    -v "$CKPT_DIR:/workspace/models" \
    -v "$HOME/gr00tn16_ws/hf_cache_container:/root/.cache/huggingface" \
    ${EDGE_ARGS[@]+"${EDGE_ARGS[@]}"} \
    real-robot-train8 \
    bash -c "$PRE cd /Isaac-GR00T && python3 gr00t/experiment/launch_finetune.py \
      --base-model-path $BASE \
      --dataset-path /data/heongyu/$DSNAME \
      --modality-config-path examples/SO100/so100_config.py \
      --embodiment-tag NEW_EMBODIMENT --num-gpus 1 \
      --output-dir /workspace/models/$OUT_NAME \
      --save-steps $SAVE_STEPS --save-total-limit $SAVE_LIMIT --max-steps $STEPS \
      --warmup-ratio 0.05 --weight-decay 1e-5 --learning-rate 1e-4 \
      --global-batch-size 2 --gradient-accumulation-steps 32 \
      --color-jitter-params brightness 0.3 contrast 0.4 saturation 0.5 hue 0.08 \
      --dataloader-num-workers $WORKERS"
}

if [ "$SMOKE" = "1" ]; then
  LOG=/tmp/cleanup_smoke.log
  run_docker 2>&1 | tee "$LOG"
  echo
  L=$(grep -oE "'loss': [0-9.]+" "$LOG" | tail -1 | grep -oE "[0-9.]+" || true)
  [ -n "$L" ] || { echo "❌ loss 를 못 읽었다 — $LOG 확인"; exit 1; }
  echo "  ▶ step10 loss = $L"
  # 파운데이션 시작 ≈ 1.05~1.13 · 학습된 체크포인트 이어받음 ≈ 0.1
  if awk "BEGIN{exit !($L > 0.5)}"; then
    echo "  ✅ 파운데이션에서 시작한 것이 맞다 (기대 1.05~1.13)"
    echo "     정리: rm -rf $CKPT_DIR/$OUT_NAME"
    exit 0
  else
    echo "  ❌❌ loss 가 너무 낮다 — **학습된 체크포인트에서 이어받고 있다.**"
    echo "       sim 1단계에서 이어학습은 우연 수준(22.5%)이었다. BASE 를 확인하고 다시 할 것."
    exit 3
  fi
fi

run_docker -d

echo "실기 cleanup 학습 시작 ($NAME, ${STEPS} steps)"
echo "  로그: docker logs -f $NAME"
echo "  약 $((STEPS / 1333))시간 (1,333 step/h 실측) · 체크포인트 $((STEPS / SAVE_STEPS))개"
echo
echo "  ▶ 끝나면 평가: 같은 배치에 목적지만 다른 **대응쌍 12그룹**으로 목적지 축을 잰다."
echo "    물체 축과 목적지 축을 **따로 기록**할 것 — 곱으로 보면 또 오독한다(sim §14)."
