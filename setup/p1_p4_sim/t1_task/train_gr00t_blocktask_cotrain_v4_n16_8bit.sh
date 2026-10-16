#!/usr/bin/env bash
# co-training v4 — sim(v4_200) + 실기(real_v2) 혼합 N1.6 8-bit 학습. **5090에서 실행.**
#
# 기존 co-train 스크립트(train_gr00t_blocktask_cotrain_n16_8bit.sh)와의 차이:
#   sim  : sim_so101_blocktask_v2  →  **sim_so101_blocktask_v4_200** (200ep, 근접 54.5%)
#   실기 : so101_blocktask_real     →  **so101_blocktask_real_v2** (60ep, 박스 다양성)
#   스텝 : 20k                      →  **43k** (아래 epoch 산정)
#
# 왜 데이터셋을 둘 다 바꿨나:
#   · sim v2는 박스 고정·물리 DR 없음. 그 위에서 co-train한 모델이 실기 90%를 냈지만,
#     지금 목표는 **박스가 움직이는** 실기 배포다.
#   · 기존 실기 50ep는 **박스가 완전히 고정**이었다(50ep 전체에서 픽셀 중심 편차 x 7px, y 4px).
#     그대로 쓰면 박스 다양성이 0인 채로 실기 분포를 배운다.
#   · 게다가 카메라를 sim v4 구도로 재정렬해 real50과 **구도 자체가 다르다**
#     (era90 대비 세로 약 114px 이동). 섞으면 배포에서 쓰지 않을 구도를 함께 배운다.
#     → real50은 제외하고 real_v2만 쓴다.
#
# 스텝 산정: effective batch 64.
#   sim v4_200  82,951 frames → 86k에서 66.3 epoch (sim 단독 학습 기준)
#   실기 60ep   41,554 frames
#   co-train은 sim을 주 데이터셋으로 두고 실기를 mix_ratio로 섞는다.
#   기존 선례(sim 30,887f + 실기 21,175f, 20k)가 sim 기준 약 41 epoch이었다.
#   v4는 sim이 2.7배 크므로 같은 epoch을 맞추려면 약 **54k**, 선례와 같은 절대 스텝이면 20k.
#   → 기본 **43k**(sim 기준 약 33 epoch)로 두고, 결과를 보고 조정한다.
#   ※ 여기서 epoch을 무리하게 맞추지 않는 이유: co-train은 sim으로 이미 수렴한 표현을
#     실기 도메인에 적응시키는 단계라 sim 단독 학습만큼 돌 필요가 없다(선례 20k로 90% 달성).
#
# 사용법(5090): ~/train_gr00t_blocktask_cotrain_v4_n16_8bit.sh [DATA_ROOT] [실기_mix] [STEPS]
#   예: ~/train_gr00t_blocktask_cotrain_v4_n16_8bit.sh "" 1.0 43000
set -e
DATA_ROOT="${1:-$HOME/gr00tn16_ws/sim_data}"
[ -z "$DATA_ROOT" ] && DATA_ROOT="$HOME/gr00tn16_ws/sim_data"
MIX="${2:-1.0}"        # 실기 mix_ratio. 실기가 sim의 절반 규모라 1.0이 기본. 희소하면 1.5~2.0
STEPS="${3:-48000}"
OUT_NAME="gr00t_blocktask_cotrain_v4_n16_8bit"
SIM_DS="sim_so101_blocktask_v4_200"
REAL_DS="so101_blocktask_real_v2_57"   # 재시도 섞인 ep2·33·49 제외본
LAUNCH="$HOME/gr00tn16_ws/launch_cotrain.py"

[ -f "$LAUNCH" ] || { echo "❌ launch_cotrain.py 없음: $LAUNCH"; exit 1; }
for d in "$SIM_DS" "$REAL_DS"; do
  [ -d "$DATA_ROOT/heongyu/$d/meta" ] || { echo "❌ 데이터셋 없음: $d"; exit 1; }
  # 병합·변환 후처리를 빠뜨리면 학습이 한참 뒤에야 실패한다 → 선확인
  [ -f "$DATA_ROOT/heongyu/$d/meta/modality.json" ] || { echo "❌ $d: modality.json 없음"; exit 1; }
  python3 - "$DATA_ROOT/heongyu/$d" <<'PY' || exit 1
import json, sys
d = sys.argv[1]
if "count" in json.load(open(f"{d}/meta/stats.json")).get("observation.state", {}):
    sys.exit(f"❌ {d}: stats.json에 count가 남아 있다 (fix_stats_for_gr00t.py 미적용)")
i = json.load(open(f"{d}/meta/info.json"))
print(f"  ✅ {d.split('/')[-1]}: {i['codebase_version']} · {i['total_episodes']}ep · {i['total_frames']}f")
PY
done

if docker ps --format '{{.Names}}' | grep -q '^gr00t-train8$'; then
  echo "❌ gr00t-train8 이 이미 실행 중입니다 (진행 중인 학습을 덮어쓰지 않도록 중단)."
  echo "   진행 상황: docker logs --tail 5 gr00t-train8"
  exit 1
fi

echo "  스텝 $STEPS · 실기 mix $MIX"
docker run -d --name gr00t-train8 --rm --gpus all --network host --ipc=host \
  -e PYTHONUNBUFFERED=1 -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
  -e HF_TOKEN="$(cat $HOME/.cache/huggingface/token 2>/dev/null)" \
  -e GR00T_COTRAIN_DATASET=/data/heongyu/$REAL_DS \
  -e GR00T_COTRAIN_MIX="$MIX" \
  -v "$DATA_ROOT:/data" \
  -v "$HOME/gr00tn16_ws/checkpoints:/workspace/models" \
  -v "$HOME/gr00tn16_ws/hf_cache_container:/root/.cache/huggingface" \
  -v "$LAUNCH:/tmp/launch_cotrain.py:ro" \
  real-robot-train8 \
  bash -c "cd /Isaac-GR00T && python3 /tmp/launch_cotrain.py \
    --base-model-path nvidia/GR00T-N1.6-3B \
    --dataset-path /data/heongyu/$SIM_DS \
    --modality-config-path examples/SO100/so100_config.py \
    --embodiment-tag NEW_EMBODIMENT --num-gpus 1 \
    --output-dir /workspace/models/$OUT_NAME \
    --save-steps 5000 --save-total-limit 6 --max-steps $STEPS \
    --warmup-ratio 0.05 --weight-decay 1e-5 --learning-rate 1e-4 \
    --global-batch-size 2 --gradient-accumulation-steps 32 \
    --color-jitter-params brightness 0.3 contrast 0.4 saturation 0.5 hue 0.08 \
    --dataloader-num-workers 8"

echo
echo "co-training v4 시작 (gr00t-train8). sim=$SIM_DS + 실기=$REAL_DS (mix $MIX)"
echo "  로그: docker logs -f gr00t-train8"
echo "  출력: ~/gr00tn16_ws/checkpoints/$OUT_NAME"
echo
echo "완주 후 실기 배포:"
echo "  ~/serve_blocktask_n16_5090.sh $OUT_NAME/checkpoint-$STEPS start"
echo "  ⚠ 배포 전 카메라 정렬 확인: rerun_cam_align.py (기준 sim_v4)"
