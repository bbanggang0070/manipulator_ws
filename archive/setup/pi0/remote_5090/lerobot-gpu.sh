#!/usr/bin/env bash
# 5090 lerobot-gpu 컨테이너 실행 헬퍼 (대화형/단발 명령용 — 서버가 아닌 임시 작업용)
# 배포 위치: 5090 ~/pi0_remote/lerobot-gpu.sh  (repo가 정본, scp로 배포)
# 사용법(5090에서):
#   ~/pi0_remote/lerobot-gpu.sh                      # 대화형 셸
#   ~/pi0_remote/lerobot-gpu.sh <명령...>            # 단발 명령 실행 (예: python xxx.py)
# HF 캐시를 호스트 ~/.cache/huggingface 에 영속화 (체크포인트/데이터셋 재사용)
set -e
mkdir -p "$HOME/.cache/huggingface"
mkdir -p "$HOME/pi0_remote/work"   # 스크립트/산출물 공유 폴더

ARGS=(-it)
[ "$#" -gt 0 ] && ARGS=()

exec docker run "${ARGS[@]}" --rm \
  --gpus all \
  --shm-size 16gb \
  -v "$HOME/.cache/huggingface:/home/user_lerobot/.cache/huggingface" \
  -v "$HOME/pi0_remote/work:/home/user_lerobot/work" \
  -e HF_HOME=/home/user_lerobot/.cache/huggingface \
  lerobot-gpu:local "$@"
