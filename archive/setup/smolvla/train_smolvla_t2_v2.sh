#!/usr/bin/env bash
# SmolVLA-T2 v2 Few-episode Fine-tuning (Table Cleanup, 50ep/5지점/소형 마킹 재수집) — 야간 실행용
# 사용법: ./setup/smolvla/train_smolvla_t2_v2.sh
#         nohup ./setup/smolvla/train_smolvla_t2_v2.sh > ~/manipulator_ws/logs/smolvla_t2_v2.log 2>&1 &
#
# 2026-07-13: T1과 동일하게 3점/큰 마킹(30ep, v1, 엄격 SR 0/8·부분진행 6/8) -> 5점/소형 점
#   마킹(50ep, v2)으로 재수집한 heongyu/so101_t2_cleanup으로 재학습. v1 체크포인트는 보존하고
#   별도 repo(_v2)로 push — batch_size/steps 등 학습 레시피는 v1과 동일하게 유지해 데이터
#   변경만이 성능 차이의 원인임을 격리.
#   T2 데이터가 T1보다 커서(67,823 vs 28,882 프레임) 같은 step 기준 epoch은 더 낮음.
cd "$(dirname "$0")/../../envs/lerobot" || exit 1

exec uv run lerobot-train \
  --dataset.repo_id=heongyu/so101_t2_cleanup \
  --policy.type=smolvla \
  --policy.pretrained_path=lerobot/smolvla_base \
  --policy.device=cuda \
  --policy.push_to_hub=true \
  --policy.repo_id=heongyu/smolvla_so101_t2_v2 \
  --output_dir=outputs/train/smolvla_t2_v2 \
  --job_name=smolvla_t2_v2 \
  --batch_size=16 \
  --steps=20000 \
  --save_freq=5000 \
  --log_freq=200 \
  --wandb.enable=false
