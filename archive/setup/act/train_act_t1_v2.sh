#!/usr/bin/env bash
# ACT-T1 v2 학습 (Pick-and-Place, 50ep/5지점/소형 마킹 재수집) — 야간 실행용
# 사용법: ./setup/act/train_act_t1_v2.sh          — 포그라운드
#         nohup ./setup/act/train_act_t1_v2.sh > ~/manipulator_ws/logs/act_t1_v2.log 2>&1 &   — 밤새 실행
#
# 2026-07-11: SmolVLA-T1과 동일하게 3점/큰 마킹(30ep, v1, SR 80%) -> 5점/소형 점 마킹
#   (50ep, v2)으로 재수집한 heongyu/so101_t1_pickplace로 재학습. v1 체크포인트(SR 80%)는
#   보존하고 별도 repo(_v2)로 push — 데이터 변경만이 성능 차이의 원인임을 격리하기 위해
#   batch_size/steps 등 학습 레시피는 v1과 동일하게 유지.
#
# 체크포인트: outputs/train/act_t1_v2/checkpoints/ (20k 스텝마다) + 종료 시 HF Hub push
cd "$(dirname "$0")/../../envs/lerobot" || exit 1

exec uv run lerobot-train \
  --dataset.repo_id=heongyu/so101_t1_pickplace \
  --policy.type=act \
  --policy.device=cuda \
  --policy.push_to_hub=true \
  --policy.repo_id=heongyu/act_so101_t1_v2 \
  --output_dir=outputs/train/act_t1_v2 \
  --job_name=act_t1_v2 \
  --batch_size=8 \
  --steps=100000 \
  --save_freq=20000 \
  --log_freq=200 \
  --wandb.enable=false
