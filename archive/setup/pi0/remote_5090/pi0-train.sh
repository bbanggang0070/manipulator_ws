#!/usr/bin/env bash
# 5090 π0 LoRA 파인튜닝 (Docker, detached) — SO-101 T1/T2
# 배포 위치: 5090 ~/pi0_remote/pi0-train.sh  (repo가 정본, scp로 배포)
# 사용법(5090에서):
#   ~/pi0_remote/pi0-train.sh t1            # T1 LoRA FT 시작 (기본 30k steps)
#   ~/pi0_remote/pi0-train.sh t2 40000      # T2, steps 지정
#   ~/pi0_remote/pi0-train.sh logs t1       # 로그 보기
#   ~/pi0_remote/pi0-train.sh stop t1       # 중단
#
# 설계 근거 (2026-07-14 개정 — LoRA → expert-only):
# - 1차 LoRA FT(어댑터 1.4M만 학습)는 loss가 0.074에서 정체하며 SO-101 시각-운동 매핑을
#   못 배움(큐브 미접근). LoRA 용량 부족으로 판정.
# - train_expert_only=true + freeze_vision_encoder=true: VLM 백본은 freeze(32GB 수용)하되
#   action expert 전체를 학습 — SmolVLA가 50% 낸 것과 동일 레시피(용량 수백 배↑).
# - bf16 + gradient_checkpointing: VRAM 절감. push_to_hub=false(토큰 미사용), 로컬 서빙.
# - HF_HUB_OFFLINE=1: gated paligemma 토크나이저 캐시만 사용. 정규화 stats는 데이터셋 meta 자동.
# - 출력은 pi0_<task>_expert (1차 LoRA 결과 pi0_<task>는 비교용 보존).
set -e
cd "$HOME"

CMD="${1:-t1}"

# logs/stop 서브커맨드
if [ "$CMD" = "logs" ]; then docker logs -f "pi0-train-${2:-t1}"; exit 0; fi
if [ "$CMD" = "stop" ]; then docker rm -f "pi0-train-${2:-t1}" && echo "중단됨"; exit 0; fi

TASK="$CMD"
# 기본 50k steps: 28,882프레임/batch8 → epoch≈13.9 (LoRA 30k=8.3보다 충분히 학습)
STEPS="${2:-50000}"
case "$TASK" in
  t1) REPO="heongyu/so101_t1_pickplace"; TASKSTR="Pick up the red cube and place it in the black box" ;;
  t2) REPO="heongyu/so101_t2_cleanup";  TASKSTR="Put the red cube, the yellow cube, and the green cube in the black box" ;;
  *)  echo "사용법: $0 {t1|t2|logs|stop} [steps|task]"; exit 1 ;;
esac

NAME="pi0-train-$TASK"
docker rm -f "$NAME" 2>/dev/null || true
mkdir -p "$HOME/pi0_remote/work/train"; chmod 777 "$HOME/pi0_remote/work/train"

docker run -d --name "$NAME" \
  --gpus all --shm-size 16gb \
  -v "$HOME/.cache/huggingface:/home/user_lerobot/.cache/huggingface" \
  -v "$HOME/pi0_remote/work:/home/user_lerobot/work" \
  -e HF_HOME=/home/user_lerobot/.cache/huggingface \
  -e HF_LEROBOT_HOME=/home/user_lerobot/.cache/huggingface/lerobot \
  -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 \
  lerobot-gpu:local \
  lerobot-train \
    --dataset.repo_id="$REPO" \
    --policy.type=pi0 \
    --policy.pretrained_path=lerobot/pi0_base \
    --policy.device=cuda \
    --policy.dtype=bfloat16 \
    --policy.gradient_checkpointing=true \
    --policy.push_to_hub=false \
    --policy.train_expert_only=true \
    --policy.freeze_vision_encoder=true \
    --output_dir="/home/user_lerobot/work/train/pi0_${TASK}_expert" \
    --job_name="pi0_${TASK}_expert" \
    --batch_size=8 \
    --steps="$STEPS" \
    --save_freq=10000 \
    --log_freq=200 \
    --wandb.enable=false

echo "π0 $TASK expert-only FT 시작됨 (컨테이너 $NAME, steps=$STEPS). 로그: $0 logs $TASK"
echo "출력: ~/pi0_remote/work/train/pi0_${TASK}_expert  (호스트 영속)"
