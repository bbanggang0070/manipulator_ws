#!/usr/bin/env bash
# ACT-T2 학습 (Table Cleanup, 30ep, 3개 물체 연쇄 pick-place) — 야간 실행용
# 사용법: ./setup/act/train_act_t2.sh
#         nohup ./setup/act/train_act_t2.sh > ~/manipulator_ws/logs/act_t2.log 2>&1 &
#
# 참고: T2 데이터셋은 32,835프레임으로 T1(13,032)의 2.5배 — 동일 100k step 기준
#       epoch 수는 T1(~61)보다 적은 ~24epoch. 프레임당 정보량(3연쇄 pick)이 많아
#       상쇄될 것으로 예상, 필요 시 loss 추이 보고 steps 연장 검토.
cd "$(dirname "$0")/../../envs/lerobot" || exit 1

exec uv run lerobot-train \
  --dataset.repo_id=heongyu/so101_t2_cleanup \
  --policy.type=act \
  --policy.device=cuda \
  --policy.push_to_hub=true \
  --policy.repo_id=heongyu/act_so101_t2 \
  --output_dir=outputs/train/act_t2 \
  --job_name=act_t2 \
  --batch_size=8 \
  --steps=100000 \
  --save_freq=20000 \
  --log_freq=200 \
  --wandb.enable=false
