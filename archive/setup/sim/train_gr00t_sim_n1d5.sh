#!/usr/bin/env bash
# GR00T **N1.5** sim 학습 (n1d5 host venv) — 워크숍 75ep 데이터로 우리 파이프라인 검증. **5090에서 실행**.
#
# 배경(2026-07-21): N1.6 단일 GPU 학습이 하드웨어 벽(optimizer 상태 ~30GB 고정, CPU offload는
#   DeepSpeed CUDA 13 vs torch 12.8 불일치로 컴파일 실패)에 막혀, 실기에서 검증된 N1.5 스택으로 전환.
#   N1.5는 같은 5090에서 3B FT 성공 이력(도커·shm·CUDA 불일치 없음, host venv 직접 실행).
#   60% baseline은 이미 사전학습 N1.6 체크포인트로 확보 — 여기선 우리 학습 파이프라인 검증이 목적.
#
# 데이터: v3→v2.1 변환한 워크숍 75ep (~/gr00tn15_ws/sim_data/sreetz-nv/so101_teleop_vials_rack_left).
#   meta/modality.json: front←external_D455, wrist←ego (so100_dualcam data-config와 정합).
# 레시피: 워크숍에 맞춤 — 20k steps, lr 1e-4, 유효 배치 64(batch4×accum16). tune는 N1.5 기본
#   (projector+diffusion, visual/llm freeze) — 워크숍 체크포인트 tune_visual=False와 근접.
set -e

DS="${1:-$HOME/gr00tn15_ws/sim_data/sreetz-nv/so101_teleop_vials_rack_left}"
STEPS="${2:-20000}"
OUT=~/gr00tn15_ws/checkpoints/gr00t_sim_vials75_n15

[ -f "$DS/meta/modality.json" ] || { echo "오류: $DS/meta/modality.json 없음"; exit 1; }

cd ~/gr00t_remote/Isaac-GR00T-n1d5
source .venv/bin/activate
export HF_HOME=~/.cache/huggingface
mkdir -p "$OUT"

nohup python scripts/gr00t_finetune.py \
  --dataset-path "$DS" \
  --num-gpus 1 \
  --output-dir "$OUT" \
  --max-steps "$STEPS" \
  --save-steps 5000 \
  --batch-size 4 \
  --gradient-accumulation-steps 16 \
  --learning-rate 1e-4 \
  --data-config so100_dualcam \
  --embodiment-tag new_embodiment \
  --video-backend torchvision_av \
  --report-to tensorboard \
  > ~/gr00t_remote/train_sim_vials75.log 2>&1 &
echo "GR00T N1.5 sim FT 시작 (steps=$STEPS, 유효배치 64, PID $!)."
echo "로그: tail -f ~/gr00t_remote/train_sim_vials75.log"
echo "출력: $OUT"
