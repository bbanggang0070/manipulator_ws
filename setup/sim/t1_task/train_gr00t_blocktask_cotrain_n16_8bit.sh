#!/usr/bin/env bash
# Phase F co-training: sim(sim_so101_blocktask) + 실기(so101_blocktask_real) 혼합 N1.6 8-bit 학습.
# **5090에서 실행.** launch_cotrain.py(2번째 데이터셋 지원) 마운트. 하이퍼파라미터는 sim 학습과 동일.
# 사전: 두 데이터셋 모두 v2.1로 ~/gr00tn16_ws/sim_data/heongyu/ 에 존재해야 함
#   (sim: prepare_blocktask_gr00t.sh / 실기: prepare_blocktask_real_gr00t.sh)
# 사용법(5090): ~/train_gr00t_blocktask_cotrain_n16_8bit.sh [DATA_ROOT] [실기_mix_ratio]
#   예: ~/train_gr00t_blocktask_cotrain_n16_8bit.sh ~/gr00tn16_ws/sim_data 1.0
set -e
DATA_ROOT="${1:-$HOME/gr00tn16_ws/sim_data}"
MIX="${2:-1.0}"   # 실기 데이터 mix_ratio (실기가 희소하면 ↑ 고려: 1.5~2.0)
OUT_NAME="gr00t_blocktask_cotrain_n16_8bit"
LAUNCH="$HOME/gr00tn16_ws/launch_cotrain.py"
[ -f "$LAUNCH" ] || { echo "launch_cotrain.py 없음: $LAUNCH (배포 필요)"; exit 1; }
[ -d "$DATA_ROOT/heongyu/so101_blocktask_real/meta" ] || { echo "실기 v2.1 데이터 없음 — prepare_blocktask_real_gr00t.sh 먼저"; exit 1; }

docker rm -f gr00t-train8 2>/dev/null || true
docker run -d --name gr00t-train8 --rm --gpus all --network host --ipc=host \
  -e PYTHONUNBUFFERED=1 -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
  -e HF_TOKEN="$(cat $HOME/.cache/huggingface/token 2>/dev/null)" \
  -e GR00T_COTRAIN_DATASET=/data/heongyu/so101_blocktask_real \
  -e GR00T_COTRAIN_MIX="$MIX" \
  -v "$DATA_ROOT:/data" \
  -v "$HOME/gr00tn16_ws/checkpoints:/workspace/models" \
  -v "$HOME/gr00tn16_ws/hf_cache_container:/root/.cache/huggingface" \
  -v "$LAUNCH:/tmp/launch_cotrain.py:ro" \
  real-robot-train8 \
  bash -c "cd /Isaac-GR00T && python3 /tmp/launch_cotrain.py \
    --base-model-path nvidia/GR00T-N1.6-3B \
    --dataset-path /data/heongyu/sim_so101_blocktask \
    --modality-config-path examples/SO100/so100_config.py \
    --embodiment-tag NEW_EMBODIMENT --num-gpus 1 \
    --output-dir /workspace/models/$OUT_NAME \
    --save-steps 5000 --save-total-limit 5 --max-steps 20000 \
    --warmup-ratio 0.05 --weight-decay 1e-5 --learning-rate 1e-4 \
    --global-batch-size 2 --gradient-accumulation-steps 32 \
    --color-jitter-params brightness 0.3 contrast 0.4 saturation 0.5 hue 0.08 \
    --dataloader-num-workers 4"

echo "Phase F co-training 시작 (gr00t-train8). sim + 실기(mix=$MIX). 로그: docker logs -f gr00t-train8"
echo "출력: ~/gr00tn16_ws/checkpoints/$OUT_NAME"
echo "완주 후: serve_blocktask_n16_5090.sh 의 MODEL을 $OUT_NAME/checkpoint-20000 로 서빙 → 실기 재측정"
