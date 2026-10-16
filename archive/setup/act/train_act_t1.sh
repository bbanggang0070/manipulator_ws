#!/usr/bin/env bash
# ACT-T1 학습 (Pick-and-Place, 30ep) — 야간 실행용
# 사용법: ./setup/act/train_act_t1.sh          — 포그라운드
#         nohup ./setup/act/train_act_t1.sh > ~/manipulator_ws/logs/act_t1.log 2>&1 &   — 밤새 실행
#
# 체크포인트: outputs/train/act_t1/checkpoints/ (20k 스텝마다) + 종료 시 HF Hub push
cd "$(dirname "$0")/../../envs/lerobot" || exit 1

exec uv run lerobot-train \
  --dataset.repo_id=heongyu/so101_t1_pickplace \
  --policy.type=act \
  --policy.device=cuda \
  --policy.push_to_hub=true \
  --policy.repo_id=heongyu/act_so101_t1 \
  --output_dir=outputs/train/act_t1 \
  --job_name=act_t1 \
  --batch_size=8 \
  --steps=100000 \
  --save_freq=20000 \
  --log_freq=200 \
  --wandb.enable=false
