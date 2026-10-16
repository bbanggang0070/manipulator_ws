#!/usr/bin/env bash
# SmolVLA-T1 Few-episode Fine-tuning v2 (Pick-and-Place, 50ep/5지점/소형 마킹 재수집) — 야간 실행용
# 사용법: ./setup/smolvla/train_smolvla_t1.sh
#         nohup ./setup/smolvla/train_smolvla_t1.sh > ~/manipulator_ws/logs/smolvla_t1_v2.log 2>&1 &
#
# 2026-07-10: 논문 프로토콜(50demo=5위치×10궤적)에 맞춰 T1 데이터를 3점/큰 마킹(30ep, v1) →
#   5점/소형 점 마킹(50ep, v2)으로 전면 재수집(§ model_md/02_SmolVLA.md, report/SmolVLA_report.md).
#   v1과 비교 가능하도록 batch_size/steps 등 학습 레시피는 동일하게 유지 — 데이터만 변경한 것이
#   결과 차이의 원인임을 격리하기 위함. 단, 프레임 수가 늘어(13,032→28,882) 동일 steps 기준
#   epoch은 v1(24.55)보다 낮아짐(~11.1) — 이 자체도 비교 대상.
#   하이퍼파라미터는 SmolVLAConfig 기본값(lr=1e-4 cosine decay, warmup=1000) 유지,
#   batch_size/steps는 커뮤니티 SO-101 FT 사례(ggando.com: RTX3090 24GB/batch64/20k step)를
#   우리 GPU(5070 Ti 16GB)에 맞춰 batch_size=16으로 축소, steps는 20k 그대로 유지.
# v1 체크포인트(heongyu/smolvla_so101_t1, SR 50%)는 보존하고 별도 repo(_v2)로 푸시.
# 카메라 키: 데이터셋의 top/wrist를 그대로 사용 — 파인튜닝은 모델이 우리 카메라 이름에
#   새로 적응하므로 camera1/2 리네이밍 불필요.
# VRAM 부족(OOM) 시 --batch_size를 8로 낮출 것.
cd "$(dirname "$0")/../../envs/lerobot" || exit 1

exec uv run lerobot-train \
  --dataset.repo_id=heongyu/so101_t1_pickplace \
  --policy.type=smolvla \
  --policy.pretrained_path=lerobot/smolvla_base \
  --policy.device=cuda \
  --policy.push_to_hub=true \
  --policy.repo_id=heongyu/smolvla_so101_t1_v2 \
  --output_dir=outputs/train/smolvla_t1_v2 \
  --job_name=smolvla_t1_v2 \
  --batch_size=16 \
  --steps=20000 \
  --save_freq=5000 \
  --log_freq=200 \
  --wandb.enable=false
