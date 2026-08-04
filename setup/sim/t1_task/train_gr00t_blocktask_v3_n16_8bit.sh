#!/usr/bin/env bash
# GR00T N1.6 8-bit sim 학습 — blocktask **v3** (100ep, 위치 전역 + 물리 DR + 박스 위치·회전 무작위).
# **5090에서 실행.** train_gr00t_sim_n16_8bit.sh(v2)와 동일 하이퍼파라미터, 데이터/스텝만 v3용.
#   데이터: ~/gr00tn16_ws/sim_data/heongyu/sim_so101_blocktask_v3 (v2.1, prepare/merge 완료본)
#   증강: color jitter(b0.3 c0.4 s0.5 h0.08). 스텝: 40k(계획 30~50k, 100ep 다양성 반영).
# 사용법(5090): ~/train_gr00t_blocktask_v3_n16_8bit.sh [DATA_ROOT]
set -e
DATA_ROOT="${1:-$HOME/gr00tn16_ws/sim_data}"
OUT_NAME="gr00t_blocktask_v3_n16_8bit"
DS="$DATA_ROOT/heongyu/sim_so101_blocktask_v3"
[ -d "$DS/meta" ] || { echo "v3 데이터셋 없음: $DS (prepare/merge 먼저)"; exit 1; }

docker rm -f gr00t-train8 2>/dev/null || true
docker run -d --name gr00t-train8 --rm --gpus all --network host --ipc=host \
  -e PYTHONUNBUFFERED=1 -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
  -e HF_TOKEN="$(cat $HOME/.cache/huggingface/token 2>/dev/null)" \
  -v "$DATA_ROOT:/data" \
  -v "$HOME/gr00tn16_ws/checkpoints:/workspace/models" \
  -v "$HOME/gr00tn16_ws/hf_cache_container:/root/.cache/huggingface" \
  real-robot-train8 \
  bash -c "cd /Isaac-GR00T && python3 gr00t/experiment/launch_finetune.py \
    --base-model-path nvidia/GR00T-N1.6-3B \
    --dataset-path /data/heongyu/sim_so101_blocktask_v3 \
    --modality-config-path examples/SO100/so100_config.py \
    --embodiment-tag NEW_EMBODIMENT --num-gpus 1 \
    --output-dir /workspace/models/$OUT_NAME \
    --save-steps 5000 --save-total-limit 8 --max-steps 40000 \
    --warmup-ratio 0.05 --weight-decay 1e-5 --learning-rate 1e-4 \
    --global-batch-size 2 --gradient-accumulation-steps 32 \
    --color-jitter-params brightness 0.3 contrast 0.4 saturation 0.5 hue 0.08 \
    --dataloader-num-workers 4"

echo "v3 N1.6 8-bit 학습 시작 (gr00t-train8, 40k steps). 로그: docker logs -f gr00t-train8"
echo "출력: ~/gr00tn16_ws/checkpoints/$OUT_NAME"
