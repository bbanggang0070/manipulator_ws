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
#   워커: dataloader 8 (v3는 4. v3 학습 중 GPU util 19%로 로딩 병목 관찰 → 상향)
#
# ⚠️ **동일 스텝 ≠ 동일 epoch** — 결과 해석 시 반드시 고려할 것.
#   effective batch = 2 × grad_accum 32 = 64 samples/step 이므로 40k steps = 2.56M 샘플.
#     v3(100ep, 38,906 frames)  → 약 65.8 epoch
#     v3_200(200ep, 83,222 f)   → 약 30.8 epoch   ← 절반 이하!
#   따라서 v3_200의 SR이 v3보다 낮게 나와도 "데이터가 많아서 나빠진 것"이라 단정할 수 없고,
#   **epoch 부족(언더핏)** 일 가능성이 있다.
#
#   진단 순서 (싼 것부터):
#    1) **최종 loss 비교** — 추가 학습 없이 즉시 가능. v3_200@40k loss가 v3@40k보다 뚜렷이
#       높으면 언더핏 쪽. 비슷하면 수렴은 된 것이므로 SR 차이는 데이터 효과(또는 노이즈).
#    2) **신뢰구간 확인** — N=20이면 ±약 11%p. 10%p 안팎 차이는 노이즈일 수 있다.
#    3) 위로도 애매하면 **스텝을 늘려 epoch 정합**: v3의 65.8 epoch에 맞추려면 약 **86k steps**.
#         ~/train_gr00t_blocktask_v3_200_n16_8bit.sh "" 86000
#
#   ※ 이어서 학습(resume)에 대하여: launch_finetune.py는 resume_from_checkpoint를 지원하지만,
#     LR이 **cosine decay(peak 1e-4 → 40k에서 ~0)** 라 40k 체크포인트에서 max_steps만 늘려
#     재개하면 LR이 새 코사인 곡선의 중간값(~5e-5)으로 **되튀는 warm-restart**가 된다.
#     단일 코사인으로 깔끔히 비교하려면 **처음부터 86k로 새로 학습**하는 편이 해석이 명확하다
#     (대신 시간이 더 듦: 86k × ~2.7s ≈ 65시간).
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
