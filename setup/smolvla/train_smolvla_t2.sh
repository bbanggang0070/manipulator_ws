#!/usr/bin/env bash
# SmolVLA-T2 Few-episode Fine-tuning (Table Cleanup, 기존 30ep 재사용) — 야간 실행용
# 사용법: ./setup/smolvla/train_smolvla_t2.sh
#         nohup ./setup/smolvla/train_smolvla_t2.sh > ~/manipulator_ws/logs/smolvla_t2.log 2>&1 &
#
# train_smolvla_t1.sh와 동일 설정(batch16/steps20k) — T2 데이터가 T1보다 2.5배 커서
# (32,835 vs 13,032 프레임) 같은 step 기준 epoch은 더 낮음(~9.8 vs 24.55), ACT-T1/T2도
# 같은 step 수를 유지한 전례를 따름(§model_md/01_ACT.md).
cd "$(dirname "$0")/../../envs/lerobot" || exit 1

exec uv run lerobot-train \
  --dataset.repo_id=heongyu/so101_t2_cleanup \
  --policy.type=smolvla \
  --policy.pretrained_path=lerobot/smolvla_base \
  --policy.device=cuda \
  --policy.push_to_hub=true \
  --policy.repo_id=heongyu/smolvla_so101_t2 \
  --output_dir=outputs/train/smolvla_t2 \
  --job_name=smolvla_t2 \
  --batch_size=16 \
  --steps=20000 \
  --save_freq=5000 \
  --log_freq=200 \
  --wandb.enable=false
