#!/usr/bin/env bash
# SmolVLA-T2 v3 Fine-tuning (v2와 동일한 50ep 데이터, steps 증가로 epoch 통제)
# 사용법: ./setup/smolvla/train_smolvla_t2_v3.sh
#         nohup ./setup/smolvla/train_smolvla_t2_v3.sh > ~/manipulator_ws/logs/smolvla_t2_v3.log 2>&1 &
#
# 2026-07-13: T1 v3와 동일 방법론 — v3는 "각 task의 v1 epoch에 맞춰 epoch 통제"로
#   데이터 변경 효과와 epoch 부족 효과를 분리한다.
#   T2 v1 epoch=9.75(30ep/steps20k). T2 데이터가 커서(67,823 프레임) v2는 steps20k에서
#   epoch 4.72로 급락 → v3는 steps=41,000으로 epoch을 v1 수준(≈9.67)에 맞춤.
#   41000 = 9.75(v1 epoch) * 67823(v2 frames) / 16(batch) 역산 후 반올림.
#   (T1 v3=24.9 대비 낮지만, T2 자체 v1과의 비교가 목적이므로 v1 epoch에 정렬.)
# v1/v2 체크포인트는 보존, 별도 repo(_v3)로 push.
cd "$(dirname "$0")/../../envs/lerobot" || exit 1

exec uv run lerobot-train \
  --dataset.repo_id=heongyu/so101_t2_cleanup \
  --policy.type=smolvla \
  --policy.pretrained_path=lerobot/smolvla_base \
  --policy.device=cuda \
  --policy.push_to_hub=true \
  --policy.repo_id=heongyu/smolvla_so101_t2_v3 \
  --output_dir=outputs/train/smolvla_t2_v3 \
  --job_name=smolvla_t2_v3 \
  --batch_size=16 \
  --steps=41000 \
  --save_freq=5000 \
  --log_freq=200 \
  --wandb.enable=false
