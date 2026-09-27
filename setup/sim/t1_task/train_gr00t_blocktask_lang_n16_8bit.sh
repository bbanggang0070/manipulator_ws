#!/usr/bin/env bash
# 언어 조건화 복원 Run A — **굳은 모델을 이어학습으로 고칠 수 있는가**에 답한다.
#
# v4_200 학습과 다른 곳은 사실상 두 줄이다:
#   ① --base-model-path 가 HuggingFace 이름이 아니라 **로컬 체크포인트**다 (이어학습)
#   ② --save-steps 를 5000 → 2000 으로 줄인다
#      (언어가 몇 step에서 살아나는지 곡선을 공짜로 얻기 위함 — 복원 계획 §4-2)
# 나머지 하이퍼파라미터는 **일부러 그대로 둔다**. 한 번에 한 축만 바꾼다.
#
# 왜 Run A를 먼저 하나 (language_conditioning_sim_plan.md §6):
#   19시간이면 답이 나오고, 실패해도 "굳은 모델은 안 풀린다"는 결론 자체가 정보다.
#   성공하면 실기에서도 재학습이 아니라 **이어학습**으로 고칠 수 있다는 뜻이라 값어치가 크다.
#   Run B(base에서 60k, 45h)는 A가 실패했을 때 간다.
#
# ⚠️ 이어학습이 조용히 실패할 수 있다 — 체크포인트를 못 읽으면 base에서 시작해 버린다.
#    SMOKE=1 로 10 step만 돌려 초기 loss로 판별한다. 실측 눈금(2026-09-24):
#      base(nvidia/GR00T-N1.6-3B)에서 시작  → step10 loss **1.1275**
#      checkpoint-86000에서 이어받음        → step10 loss **0.1138**  (약 1/10)
#      v4_200이 86k에서 수렴한 지점         → loss 0.0044
#    0.11이 0.0044보다 높은 것은 정상이다 — 데이터셋이 새 씬·새 지시문으로 바뀌었다.
#    **1.1 근처면 실패**(base에서 시작), **0.1 근처면 성공**.
#
# 사용 (5090에서 실행):
#   SMOKE=1 ./train_gr00t_blocktask_lang_n16_8bit.sh      # 10 step 확인 (G4a)
#   ./train_gr00t_blocktask_lang_n16_8bit.sh              # 본 학습 25k (약 19h)
#   ./train_gr00t_blocktask_lang_n16_8bit.sh "" 40000     # 스텝 지정
set -e

DATA_ROOT="${1:-$HOME/gr00tn16_ws/sim_data}"
STEPS="${2:-25000}"
DSNAME="${DSNAME:-sim_so101_blocktask_lang}"
OUT_NAME="${OUT_NAME:-gr00t_blocktask_lang_n16_8bit}"
BASE_CKPT="${BASE_CKPT:-gr00t_blocktask_v4_200_n16_8bit/checkpoint-86000}"
SMOKE="${SMOKE:-0}"
NAME="gr00t-train8"

DS="$DATA_ROOT/heongyu/$DSNAME"
CKPT_DIR="$HOME/gr00tn16_ws/checkpoints"

# ── 준비 확인 ────────────────────────────────────────────────────────────
[ -d "$DS/meta" ] || { echo "❌ 데이터셋 없음: $DS (prepare_blocktask_lang.sh 먼저)"; exit 1; }
[ -f "$DS/meta/modality.json" ] || { echo "❌ modality.json 없음 — prepare의 변환 후처리 누락"; exit 1; }
# 출발점은 **로컬 체크포인트**(Run A) 또는 **HF 모델 이름**(Run B, base에서 새로 시작)이다.
#   Run B가 답하는 것: 언어 조건화가 사전학습된 base의 행동 헤드에서 출발하면 지켜지는가.
#   (Run A는 언어를 무시하도록 굳은 v4_200 헤드에서 출발했고 실패했다 — 2026-09-25)
if [ -d "$CKPT_DIR/$BASE_CKPT" ]; then
  BASE_ARG="/workspace/models/$BASE_CKPT"
elif [[ "$BASE_CKPT" == */* && "$BASE_CKPT" != /* ]]; then
  BASE_ARG="$BASE_CKPT"        # HuggingFace 모델 이름 — 컨테이너의 HF 캐시에서 읽는다
else
  echo "❌ 출발점을 못 찾음: $CKPT_DIR/$BASE_CKPT (로컬도 아니고 HF 이름 형식도 아님)"; exit 1
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
if tasks < 50:
    sys.exit(f"❌ 지시문이 {tasks}종뿐이다 — 변환이 태스크를 접었다. 학습해도 언어 신호가 0이다.")
ep = steps * 64 / frames
print(f"  {steps:,} step × batch 64 = {steps*64:,} 샘플 → {ep:.1f} epoch")
PY

# ── 중복 실행 방지 ───────────────────────────────────────────────────────
if docker ps --format '{{.Names}}' | grep -q "^${NAME}$"; then
  echo "❌ $NAME 이 이미 실행 중입니다 (진행 중인 학습을 덮어쓰지 않도록 중단)."
  echo "   진행 상황: docker logs --tail 5 $NAME"
  echo "   정말 교체하려면: docker rm -f $NAME  후 다시 실행하세요."
  exit 1
fi

# ── 저장 용량 ────────────────────────────────────────────────────────────
#   체크포인트 1개 = **13GB** (실측 2026-09-24: 가중치 9.8GB + optimizer.pt 3.3GB).
#   계획서의 "9.2GB, optimizer 없음"은 틀렸다 — optimizer.pt가 들어 있다.
#   학습 중 유지분 10개 = 130GB, ckpt_keep.sh 보관본 6개(optimizer 제외) = 59GB → 약 190GB.
if [ "$SMOKE" != "1" ]; then
  AVAIL=$(df -BG --output=avail "$CKPT_DIR" | tail -1 | tr -dc '0-9')
  echo "  체크포인트 여유: ${AVAIL}G (필요 약 190G — 유지 130G + 보관 59G)"
  [ "$AVAIL" -lt 200 ] && { echo "❌ 공간 부족. 오래된 체크포인트를 지우고 다시 실행하세요."; exit 1; }
fi

if [ "$SMOKE" = "1" ]; then
  STEPS=10; SAVE_STEPS=10; SAVE_LIMIT=1; OUT_NAME="${OUT_NAME}_smoke"
  echo
  echo "▶ 스모크 (G4a) — 10 step. **초기 loss를 본다.**"
  echo "   실측 눈금: base 시작 = 1.1275 · checkpoint-86000 이어받음 = 0.1138"
  echo "   1.1 근처면 이어학습 실패(base에서 시작), 0.1 근처면 성공."
else
  SAVE_STEPS=2000; SAVE_LIMIT=10
fi

echo
echo "  출발          : $BASE_ARG"
echo "  출력           : $OUT_NAME"
echo "  저장           : --save-steps $SAVE_STEPS --save-total-limit $SAVE_LIMIT"
echo

docker run -d --name "$NAME" --rm --gpus all --network host --ipc=host \
  -e PYTHONUNBUFFERED=1 -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
  -e HF_TOKEN="$(cat $HOME/.cache/huggingface/token 2>/dev/null)" \
  -v "$DATA_ROOT:/data" \
  -v "$CKPT_DIR:/workspace/models" \
  -v "$HOME/gr00tn16_ws/hf_cache_container:/root/.cache/huggingface" \
  real-robot-train8 \
  bash -c "cd /Isaac-GR00T && python3 gr00t/experiment/launch_finetune.py \
    --base-model-path $BASE_ARG \
    --dataset-path /data/heongyu/$DSNAME \
    --modality-config-path examples/SO100/so100_config.py \
    --embodiment-tag NEW_EMBODIMENT --num-gpus 1 \
    --output-dir /workspace/models/$OUT_NAME \
    --save-steps $SAVE_STEPS --save-total-limit $SAVE_LIMIT --max-steps $STEPS \
    --warmup-ratio 0.05 --weight-decay 1e-5 --learning-rate 1e-4 \
    --global-batch-size 2 --gradient-accumulation-steps 32 \
    --color-jitter-params brightness 0.3 contrast 0.4 saturation 0.5 hue 0.08 \
    --dataloader-num-workers 8"

echo "언어 조건화 Run A 시작 ($NAME, ${STEPS} steps)"
echo "  로그: docker logs -f $NAME"
if [ "$SMOKE" = "1" ]; then
  echo
  echo "  ▶ 확인할 것: 첫 로그의 loss. 낮게 시작하면 이어학습 성공."
  echo "    끝나면 rm -rf $CKPT_DIR/$OUT_NAME 로 스모크 산출물을 지울 것."
else
  echo "  약 $((STEPS / 1333))시간 (1,333 step/h 실측)"
  echo
  echo "  ▶ 6,000 step 체크포인트가 나오면 **멈추지 말고** 프로브를 돌려 G4b를 본다:"
  echo "     probe_language.py --label lang@6k  →  색 비교가 2° 미만이면 중단하고 Run B로"
  echo "  ▶ 보관: ckpt_keep.sh 로 {2k,4k,6k,10k,16k,25k}를 따로 복사"
fi
