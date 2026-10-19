#!/usr/bin/env bash
# 양팔 파일럿 학습 — setup/p5_real_cleanup/train_cleanup_real.sh 의 bi 판. 5090에서 실행.
#
# 지금 단계(bi_manipulator_plan.md §5 step 6)는 **본 학습이 아니라 스모크
# 테스트**다 — modality config(bi_so100_config.py)·변환 파이프라인이 양팔
# 12차원·카메라 3대에서 안 깨지는지만 확인한다. 반드시 SMOKE=1로 먼저 돌릴 것.
#
# 단일팔과 다른 점:
#   · --modality-config-path 가 bi_so100_config.py (left_arm/left_gripper/
#     right_arm/right_gripper, video top/wrist_left/wrist_right)
#   · 데이터셋 bi_cleanup — 파일럿 50ep·61,067 frames(2026-10-15 기준)
#   · 출발점은 똑같이 **파운데이션에서 새로**(nvidia/GR00T-N1.6-3B) — 이유는
#     단일팔과 같다(이어학습은 언어 신호를 무시하도록 굳는다, 같은 스크립트 §주석)
#
# 사용 (5090에서):
#   SMOKE=1 ./train_bi_cleanup.sh        # 10 step 확인 — 먼저 이것부터
#   ./train_bi_cleanup.sh                # 본 학습(파일럿 결과 보고 결정한 뒤에만)
#   EDGE=448 ./train_bi_cleanup.sh       # 입력 해상도 448 (기본 256, 카메라 원본 640 이 상한)
#   TUNE_VISUAL=1 ./train_bi_cleanup.sh  # 비전 인코더 미세조정 (기본은 고정)
#     VIS_LR_MULT=0.1 (비전 학습률 = 1e-4 × 0.1) · VIS_TOP_LAYERS=8 (위쪽 8/27층만, 0=전체)
#   LLM_TOP_LAYERS=8 ./train_bi_cleanup.sh   # 언어 모델 위쪽 8/16층 학습 (기본 4)
#   SMOKE=1 SMOKE_STEPS=50 EDGE=448 ./train_bi_cleanup.sh   # 속도·메모리 측정용 짧은 실행
set -e

EPOCHS="${EPOCHS:-8}"
STEPS="${1:-}"
DATA_ROOT="${DATA_ROOT:-$HOME/gr00tn16_ws/sim_data}"
DSNAME="${DSNAME:-bi_cleanup}"
OUT_NAME="${OUT_NAME:-gr00t_bi_cleanup_n16_8bit}"
BASE="${BASE:-nvidia/GR00T-N1.6-3B}"
SMOKE="${SMOKE:-0}"
SMOKE_STEPS="${SMOKE_STEPS:-10}"
TUNE_VISUAL="${TUNE_VISUAL:-0}"
NAME="gr00t-train-bi"
MODALITY_CONFIG_PATH="${MODALITY_CONFIG_PATH:-examples/BiSO100/bi_so100_config.py}"

DS="$DATA_ROOT/heongyu/$DSNAME"
CKPT_DIR="$HOME/gr00tn16_ws/checkpoints"

[ -d "$DS/meta" ] || { echo "❌ 데이터셋 없음: $DS"; echo "   prepare_bi_cleanup.sh 를 먼저 돌리세요"; exit 1; }
[ -f "$DS/meta/modality.json" ] || { echo "❌ modality.json 없음 — 변환 후처리 누락"; exit 1; }
[ -f "$HOME/gr00t_remote/Isaac-GR00T/$MODALITY_CONFIG_PATH" ] || {
  echo "❌ $MODALITY_CONFIG_PATH 가 5090의 Isaac-GR00T repo에 없습니다 — 먼저 scp 하세요:"
  echo "   scp setup/p6_real_bimanual/gr00t/bi_so100_config.py 5090:~/gr00t_remote/Isaac-GR00T/examples/BiSO100/"
  echo "   scp setup/p6_real_bimanual/gr00t/modality.json       5090:~/gr00t_remote/Isaac-GR00T/examples/BiSO100/"
  exit 1
}

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
tasks = sum(1 for _ in open(f"{d}/meta/tasks.jsonl"))
print(f"  데이터셋: {i['codebase_version']} · {i['total_episodes']}ep · {frames:,} frames · 지시문 {tasks}종")
if tasks < 20:
    sys.exit(f"❌ 지시문이 {tasks}종뿐이다 — 변환이 태스크를 접었다. 학습해도 언어 신호가 0이다.")
ep = steps * 64 / frames
print(f"  {steps:,} step × batch 64 = {steps*64:,} 샘플 → {ep:.1f} epoch")
if ep > 14:
    print(f"  ⚠️  {ep:.1f} epoch 은 sim 권장(6~12)보다 많다 — 과적합 구간일 수 있다")
elif ep < 5:
    sys.exit(f"❌ {ep:.1f} epoch 은 너무 적다. EPOCHS 를 올리거나 STEPS 를 직접 줄 것")
PY

if docker ps --format '{{.Names}}' | grep -q "^${NAME}$"; then
  echo "❌ $NAME 이 이미 실행 중입니다."
  echo "   진행 상황: docker logs --tail 5 $NAME"
  exit 1
fi

# 색 증강 — 지시문이 색 이름으로 물체·칸을 가리키므로 단일팔과 같은 이유로
# hue 는 좁게(±5.4°) 유지한다. setup/p5_real_cleanup/train_cleanup_real.sh §주석 참조.
CJ_BRI="${CJ_BRI:-0.3}"
CJ_CON="${CJ_CON:-0.4}"
CJ_SAT="${CJ_SAT:-0.25}"
CJ_HUE="${CJ_HUE:-0.015}"

# ── 입력 해상도 (단일팔 train_cleanup_real.sh 와 같은 방식) ──────────────
#   모델은 640×480 을 정사각형으로 letterbox 한 뒤 EDGE 로 줄인다 → 256 은 원본의 0.4배.
#   해상도를 올리면 호스트 RAM 이 병목이라 dataloader worker 를 내린다(단일팔 640·worker 8 에서 OOM).
EDGE="${EDGE:-}"
EDGE_ARGS=(); WORKERS="${WORKERS:-8}"; PRE=""
if [ -n "$EDGE" ] && [ "$EDGE" != "256" ]; then
  _HERE="$(cd "$(dirname "$0")" && pwd)"
  PATCHER=""
  for _c in "${EDGE_PATCH:-}" "$_HERE/edge_patch.py" "$_HERE/../../gr00t/edge_patch.py" \
            "$HOME/edge_patch.py" "$HOME/manipulator_ws/setup/gr00t/edge_patch.py"; do
    [ -n "$_c" ] && [ -f "$_c" ] && { PATCHER="$(cd "$(dirname "$_c")" && pwd)/$(basename "$_c")"; break; }
  done
  [ -n "$PATCHER" ] || { echo "❌ edge_patch.py 를 못 찾았습니다. scp 로 ~/ 에 두거나 EDGE_PATCH= 로 지정하세요"; exit 1; }
  EDGE_ARGS=(-e "GR00T_SHORTEST_EDGE=$EDGE" -v "$PATCHER:/tmp/edge_patch.py:ro")
  PRE="python3 /tmp/edge_patch.py --verify --ckpt $BASE && "
  [ "$EDGE" -ge 448 ] && WORKERS="${WORKERS_HI:-4}"
  echo "  ⚠️ 입력 해상도 $EDGE (기본 256) · dataloader worker $WORKERS"
fi
# ── 비전 인코더 미세조정 ─────────────────────────────────────────────────
#   GR00T 기본 --tune-visual 은 비전 인코더도 1e-4 로 움직인다(파라미터 그룹 1개).
#   vision_lr_patch.py 로 비전만 학습률 × VIS_LR_MULT, 위쪽 VIS_TOP_LAYERS 층만 푼다.
TV_ARGS=""; TV_MOUNT=(); LAUNCH="python3 gr00t/experiment/launch_finetune.py"
VIS_LR_MULT="${VIS_LR_MULT:-0.1}"; VIS_TOP_LAYERS="${VIS_TOP_LAYERS:-0}"; LLM_TOP_LAYERS="${LLM_TOP_LAYERS:-}"
if [ "$TUNE_VISUAL" = "1" ] || [ -n "$LLM_TOP_LAYERS" ]; then
  VP=""
  for _c in "${VIS_PATCH:-}" "$(cd "$(dirname "$0")" && pwd)/../../gr00t/vision_lr_patch.py" \
            "$HOME/vision_lr_patch.py" "$HOME/manipulator_ws/setup/gr00t/vision_lr_patch.py"; do
    [ -n "$_c" ] && [ -f "$_c" ] && { VP="$(cd "$(dirname "$_c")" && pwd)/$(basename "$_c")"; break; }
  done
  [ -n "$VP" ] || { echo "❌ vision_lr_patch.py 를 못 찾았습니다. scp 로 ~/ 에 두거나 VIS_PATCH= 로 지정하세요"; exit 1; }
  TV_MOUNT=(-v "$VP:/tmp/vision_lr_patch.py:ro" -e "VIS_LR_MULT=$VIS_LR_MULT" -e "VIS_TOP_LAYERS=$VIS_TOP_LAYERS" -e "LLM_TOP_LAYERS=$LLM_TOP_LAYERS")
  LAUNCH="python3 /tmp/vision_lr_patch.py gr00t/experiment/launch_finetune.py"
  [ "$TUNE_VISUAL" = "1" ] && { TV_ARGS="--tune-visual"; echo "  ⚠️ 비전 인코더 미세조정 — 학습률 × $VIS_LR_MULT · 위쪽 층 ${VIS_TOP_LAYERS/#0/전체}"; }
  [ -n "$LLM_TOP_LAYERS" ] && echo "  ⚠️ 언어 모델 위쪽 $LLM_TOP_LAYERS/16층 학습 (기본 4)"
fi

if [ "$SMOKE" = "1" ]; then
  STEPS=$SMOKE_STEPS; SAVE_STEPS=100000; SAVE_LIMIT=1; OUT_NAME="${OUT_NAME}_smoke"
  echo
  echo "▶ 스모크 — $STEPS step. **출발점(파운데이션)과 파이프라인이 안 깨지는지 확인.**"
  echo "   파운데이션에서 시작 = 약 1.05~1.13 · 학습된 체크포인트 이어받음 = 약 0.1"
else
  SAVE_STEPS="${SAVE_STEPS:-$(python3 -c "print(max(round($STEPS/8/500)*500,500))")}"
  SAVE_LIMIT="${SAVE_LIMIT:-10}"
  NEED=$(( (STEPS / SAVE_STEPS + 1) * 13 ))
  AVAIL=$(df -BG --output=avail "$CKPT_DIR" 2>/dev/null | tail -1 | tr -dc '0-9')
  echo "  체크포인트 여유: ${AVAIL}G (필요 약 ${NEED}G)"
  [ -n "$AVAIL" ] && [ "$AVAIL" -lt "$NEED" ] && { echo "❌ 공간 부족."; exit 1; }
fi

echo
echo "  출발점       : $BASE"
echo "  데이터셋     : $DSNAME"
echo "  출력         : $OUT_NAME"
echo "  modality cfg : $MODALITY_CONFIG_PATH"
echo "  저장         : --save-steps $SAVE_STEPS --save-total-limit $SAVE_LIMIT"
echo

run_docker() {
  docker run "$@" --name "$NAME" --rm --gpus all --network host --ipc=host \
    -e PYTHONUNBUFFERED=1 -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
    -e HF_TOKEN="$(cat $HOME/.cache/huggingface/token 2>/dev/null)" \
    -v "$DATA_ROOT:/data" \
    -v "$CKPT_DIR:/workspace/models" \
    -v "$HOME/gr00tn16_ws/hf_cache_container:/root/.cache/huggingface" \
    -v "$HOME/gr00t_remote/Isaac-GR00T/examples/BiSO100:/Isaac-GR00T/examples/BiSO100:ro" \
    ${EDGE_ARGS[@]+"${EDGE_ARGS[@]}"} ${TV_MOUNT[@]+"${TV_MOUNT[@]}"} \
    real-robot-train8 \
    bash -c "$PRE cd /Isaac-GR00T && $LAUNCH \
      --base-model-path $BASE \
      --dataset-path /data/heongyu/$DSNAME \
      --modality-config-path $MODALITY_CONFIG_PATH \
      --embodiment-tag NEW_EMBODIMENT --num-gpus 1 \
      --output-dir /workspace/models/$OUT_NAME \
      --save-steps $SAVE_STEPS --save-total-limit $SAVE_LIMIT --max-steps $STEPS \
      --warmup-ratio 0.05 --weight-decay 1e-5 --learning-rate 1e-4 \
      --global-batch-size 2 --gradient-accumulation-steps 32 \
      --color-jitter-params brightness $CJ_BRI contrast $CJ_CON saturation $CJ_SAT hue $CJ_HUE \
      --dataloader-num-workers $WORKERS $TV_ARGS"
}

if [ "$SMOKE" = "1" ]; then
  LOG=/tmp/bi_cleanup_smoke.log
  run_docker 2>&1 | tee "$LOG"
  echo
  L=$(grep -oE "'loss': [0-9.]+" "$LOG" | tail -1 | grep -oE "[0-9.]+" || true)
  [ -n "$L" ] || { echo "❌ loss 를 못 읽었다 — $LOG 확인"; exit 1; }
  echo "  ▶ step$STEPS loss = $L"
  if awk "BEGIN{exit !($L > 0.5)}"; then
    echo "  ✅ 파이프라인 정상 — 파운데이션에서 시작한 것도 확인됨 (기대 1.05~1.13)"
    echo "     정리: rm -rf $CKPT_DIR/$OUT_NAME"
    exit 0
  else
    echo "  ❌❌ loss 가 너무 낮다 — base 지정 확인할 것"
    exit 3
  fi
fi

run_docker -d
echo "양팔 파일럿 학습 시작 ($NAME, ${STEPS} steps)"
echo "  로그: docker logs -f $NAME"
