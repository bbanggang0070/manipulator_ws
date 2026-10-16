#!/usr/bin/env bash
# 5090 GR00T N1.5 파인튜닝 (n1d5 브랜치, host venv) — SO-101 T1/T2
# 배포 위치: 5090 ~/gr00t_remote/scripts/gr00t-train.sh  (repo가 정본, scp로 배포)
# 사용법(5090에서):
#   ~/gr00t_remote/scripts/gr00t-train.sh t1            # T1 FT (기본 10k steps)
#   ~/gr00t_remote/scripts/gr00t-train.sh t2 10000      # T2, steps 지정
#   ~/gr00t_remote/scripts/gr00t-train.sh logs t1       # 로그
#   ~/gr00t_remote/scripts/gr00t-train.sh stop t1       # 중단
#
# 설계 근거(pi0 교훈 반영):
# - full FT(기본: tune_projector+tune_diffusion_model) — pi0 LoRA 용량부족 교훈으로 LoRA 회피
# - data_config=so100_dualcam: video.front/wrist + 6-dim single_arm/gripper — 우리 modality.json과 일치
#   (front ← observation.images.top 매핑, pi0 #1 실패였던 카메라 키를 정식 해결)
# - video_backend=torchvision_av: 5090 호스트에 ffmpeg 없음 → torchcodec 로드 불가 우회(pyav 내장)
# - 데이터셋은 v3→v2 변환본(GR00T는 LeRobot v2 요구), 변환 후 meta/modality.json 존재 필수
# - 환경: ~/gr00t_remote/Isaac-GR00T-n1d5/.venv (torch 2.8+cu128 오버라이드 — Blackwell sm_120)
set -e

CMD="${1:-t1}"
if [ "$CMD" = "logs" ]; then exec tail -f ~/gr00t_remote/train_${2:-t1}.log; fi
if [ "$CMD" = "stop" ]; then pkill -f "gr00t_finetune.*gr00t_${2:-t1}" && echo 중단됨; exit 0; fi

TASK="$CMD"
STEPS="${2:-10000}"
case "$TASK" in
  t1) DS=~/.cache/huggingface/lerobot/heongyu/so101_t1_pickplace ;;
  t2) DS=~/.cache/huggingface/lerobot/heongyu/so101_t2_cleanup ;;
  *) echo "사용법: $0 {t1|t2|logs|stop} [steps|task]"; exit 1 ;;
esac

[ -f "$DS/meta/modality.json" ] || { echo "오류: $DS/meta/modality.json 없음 (v2 변환 후 재복사 필요)"; exit 1; }

cd ~/gr00t_remote/Isaac-GR00T-n1d5
source .venv/bin/activate
export HF_HOME=~/.cache/huggingface

OUT=~/gr00t_remote/checkpoints/gr00t_${TASK}
mkdir -p "$OUT"

nohup python scripts/gr00t_finetune.py \
  --dataset-path "$DS" \
  --num-gpus 1 \
  --output-dir "$OUT" \
  --max-steps "$STEPS" \
  --save-steps 2500 \
  --batch-size 32 \
  --data-config so100_dualcam \
  --embodiment-tag new_embodiment \
  --video-backend torchvision_av \
  --report-to tensorboard \
  > ~/gr00t_remote/train_${TASK}.log 2>&1 &
echo "GR00T $TASK FT 시작 (steps=$STEPS, PID $!). 로그: $0 logs $TASK"
echo "출력: $OUT"
