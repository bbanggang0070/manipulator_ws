#!/usr/bin/env bash
# GR00T N1.5 학습본 **open-loop 검증** — 예측 액션 vs 정답 시연 MSE. **5090에서 실행**.
#
# closed-loop sim 평가(sim_eval_n1d5.sh)가 공유 5090 인프라 문제(n1d5 zmq 서버 미응답)로
# 막혔을 때, 서버·sim·도커 없이 모델만 직접 돌려 "학습이 됐는가"를 검증하는 경로.
# 실기 GR00T 검증에도 쓴 eval_policy.py 재사용.
#
# 결과 해석: Unnormalized Action MSE (낮을수록 좋음). 실기 GR00T ~2.24, N1.5 sim ~2.2 수준.
# 배포 위치(5090): ~/gr00tn15_ws/run_n15_openloop.sh (동일 내용)
set -e

CKPT="${1:-$HOME/gr00tn15_ws/checkpoints/gr00t_sim_vials75_n15/checkpoint-20000}"
DS="${2:-$HOME/gr00tn15_ws/sim_data/sreetz-nv/so101_teleop_vials_rack_left}"

cd ~/gr00t_remote/Isaac-GR00T-n1d5
source .venv/bin/activate
export HF_HOME=~/gr00tn15_ws/hf_home_airlab   # airlab 소유(쓰기가능) — 공용 캐시 filelock hang 회피
export PYTHONUNBUFFERED=1

exec python scripts/eval_policy.py \
  --model-path "$CKPT" \
  --dataset-path "$DS" \
  --data-config so100_dualcam \
  --embodiment-tag new_embodiment \
  --modality-keys single_arm gripper \
  --video-backend torchvision_av \
  --trajs 5 --steps 150 \
  --save-plot-path ~/gr00tn15_ws/n15_openloop_plot.png
