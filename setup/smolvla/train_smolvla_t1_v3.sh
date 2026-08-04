#!/usr/bin/env bash
# SmolVLA-T1 v3 Few-episode Fine-tuning (v2와 동일한 50ep/5지점/소형 마킹 데이터, steps만 증가)
# 사용법: ./setup/smolvla/train_smolvla_t1_v3.sh
#         nohup ./setup/smolvla/train_smolvla_t1_v3.sh > ~/manipulator_ws/logs/smolvla_t1_v3.log 2>&1 &
#
# 2026-07-13: v2(steps=20000, epoch=11.08, SR 30%)가 v1(steps=20000, epoch=24.55, SR 50%)보다
#   오히려 낮게 나온 원인이 "위치 다양화/마킹 변경" 때문인지 "데이터가 늘어 동일 step 기준
#   epoch이 줄어든 것" 때문인지 분리하기 위해, 데이터는 v2와 완전히 동일하게 두고 steps만
#   45,000으로 늘려 v1과 비슷한 epoch(24.93)을 맞춤 (§ model_md/02_SmolVLA.md).
#   45000 = 24.55(v1 epoch) * 28882(v2 frames) / 16(batch) 역산 후 반올림.
cd "$(dirname "$0")/../../envs/lerobot" || exit 1

exec uv run lerobot-train \
  --dataset.repo_id=heongyu/so101_t1_pickplace \
  --policy.type=smolvla \
  --policy.pretrained_path=lerobot/smolvla_base \
  --policy.device=cuda \
  --policy.push_to_hub=true \
  --policy.repo_id=heongyu/smolvla_so101_t1_v3 \
  --output_dir=outputs/train/smolvla_t1_v3 \
  --job_name=smolvla_t1_v3 \
  --batch_size=16 \
  --steps=45000 \
  --save_freq=5000 \
  --log_freq=200 \
  --wandb.enable=false
