#!/usr/bin/env bash
# GR00T N1.6 8-bit sim 학습 — blocktask **v3_200** (200ep 선별본).
# **5090에서 실행.** train_gr00t_blocktask_v3_n16_8bit.sh(100ep)와 동일 하이퍼파라미터.
# 유일한 차이 = **데이터 양(100ep → 200ep)** → "100ep가 부족했나?"를 교란 없이 비교.
#
#   데이터: ~/gr00tn16_ws/sim_data/heongyu/sim_so101_blocktask_v3_200
#           (231ep 수집분에서 품질 선별: 길이 이상치 6개 + 시작 idle 큰 25개 제외)
#           분포는 v3(100ep)와 동일 — 위치 전역 + 물리 DR + 박스 위치·회전 무작위
#   증강: color jitter(b0.3 c0.4 s0.5 h0.08) — v3와 동일
#   스텝: 40k (v3와 동일하게 두어 "데이터 양"만 변수로 유지)
#         ※ 데이터가 2배이므로 스텝을 올리고 싶다면 STEPS 인자로 조정(비교는 흐려짐)
#   워커: dataloader 8 (v3는 4. v3 학습 중 GPU util 19%로 로딩 병목 관찰 → 상향)
#
# 사용법(5090): ~/train_gr00t_blocktask_v3_200_n16_8bit.sh [DATA_ROOT] [STEPS]
set -e
DATA_ROOT="${1:-$HOME/gr00tn16_ws/sim_data}"
STEPS="${2:-40000}"
OUT_NAME="gr00t_blocktask_v3_200_n16_8bit"
DS="$DATA_ROOT/heongyu/sim_so101_blocktask_v3_200"
[ -d "$DS/meta" ] || { echo "v3_200 데이터셋 없음: $DS (병합 먼저)"; exit 1; }

# ⚠️ 학습 컨테이너가 이미 돌고 있으면 중단시키지 않고 알림만 (v3 학습 중 실수 방지)
if docker ps --format '{{.Names}}' | grep -q '^gr00t-train8$'; then
  echo "❌ gr00t-train8 이 이미 실행 중입니다 (진행 중인 학습을 덮어쓰지 않도록 중단)."
  echo "   진행 상황: docker logs --tail 5 gr00t-train8"
  echo "   정말 교체하려면: docker rm -f gr00t-train8  후 이 스크립트를 다시 실행하세요."
  exit 1
fi

docker run -d --name gr00t-train8 --rm --gpus all --network host --ipc=host \
  -e PYTHONUNBUFFERED=1 -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
  -e HF_TOKEN="$(cat $HOME/.cache/huggingface/token 2>/dev/null)" \
  -v "$DATA_ROOT:/data" \
  -v "$HOME/gr00tn16_ws/checkpoints:/workspace/models" \
  -v "$HOME/gr00tn16_ws/hf_cache_container:/root/.cache/huggingface" \
  real-robot-train8 \
  bash -c "cd /Isaac-GR00T && python3 gr00t/experiment/launch_finetune.py \
    --base-model-path nvidia/GR00T-N1.6-3B \
    --dataset-path /data/heongyu/sim_so101_blocktask_v3_200 \
    --modality-config-path examples/SO100/so100_config.py \
    --embodiment-tag NEW_EMBODIMENT --num-gpus 1 \
    --output-dir /workspace/models/$OUT_NAME \
    --save-steps 5000 --save-total-limit 8 --max-steps $STEPS \
    --warmup-ratio 0.05 --weight-decay 1e-5 --learning-rate 1e-4 \
    --global-batch-size 2 --gradient-accumulation-steps 32 \
    --color-jitter-params brightness 0.3 contrast 0.4 saturation 0.5 hue 0.08 \
    --dataloader-num-workers 8"

echo "v3_200 N1.6 8-bit 학습 시작 (gr00t-train8, ${STEPS} steps). 로그: docker logs -f gr00t-train8"
echo "출력: ~/gr00tn16_ws/checkpoints/$OUT_NAME"
echo "평가: ~/blocktask_ood_sweep.sh $OUT_NAME/checkpoint-${STEPS} 20"
