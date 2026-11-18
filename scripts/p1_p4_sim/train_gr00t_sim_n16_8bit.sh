#!/usr/bin/env bash
# GR00T **N1.6** sim 학습 (8-bit Adam, 단일 5090) — NVIDIA 하이퍼파라미터 재현 시도. **5090에서 실행**.
#
# 배경(2026-07-22): 단일 32GB에서 N1.6 full FT는 기본 fp32 Adam으로 OOM(GitHub #536 = 우리와 동일,
#   미해결). optimizer 상태(Adam m,v fp32 + master)가 ~30GB 지배. → **8-bit Adam(paged_adamw_8bit)**로
#   옵티마이저 상태만 fp32→8bit 양자화(~12GB 절약, HF/논문상 fp32와 성능 거의 동일, 하이퍼파라미터 무변경).
#   목적: 어제 sim 평가한 사전학습 N1.6 체크포인트(60%)와 비슷한 성능이 나오는지 확인.
#
# 이미지: real-robot-train8 (real-robot + ffmpeg + torchcodec0.7 + bitsandbytes + gradient_checkpointing=True
#   + launch_finetune optim=paged_adamw_8bit). DeepSpeed offload는 미사용(CUDA13 vs torch12.8 컴파일 불가).
# 하이퍼파라미터: NVIDIA/워크숍과 동일 — global batch 64(=micro2×accum32), lr 1e-4, wd 1e-5, warmup 0.05,
#   20k steps, color jitter(b0.3 c0.4 s0.5 h0.08), tune 기본(projector+diffusion). **차이는 옵티마이저 8bit뿐**.
# 데이터: N1.5와 동일한 v2.1 변환본(gr00tn15_ws/sim_data). base 캐시: gr00tn16_ws/hf_cache_container.
set -e

DATA_ROOT="${1:-$HOME/gr00tn15_ws/sim_data}"
OUT_NAME="gr00t_vials75_n16_8bit"

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
    --dataset-path /data/sreetz-nv/so101_teleop_vials_rack_left \
    --modality-config-path examples/SO100/so100_config.py \
    --embodiment-tag NEW_EMBODIMENT --num-gpus 1 \
    --output-dir /workspace/models/$OUT_NAME \
    --save-steps 5000 --save-total-limit 5 --max-steps 20000 \
    --warmup-ratio 0.05 --weight-decay 1e-5 --learning-rate 1e-4 \
    --global-batch-size 2 --gradient-accumulation-steps 32 \
    --color-jitter-params brightness 0.3 contrast 0.4 saturation 0.5 hue 0.08 \
    --dataloader-num-workers 4"

echo "N1.6 8-bit 학습 시작 (컨테이너 gr00t-train8). 로그: docker logs -f gr00t-train8"
echo "출력: ~/gr00tn16_ws/checkpoints/$OUT_NAME"
