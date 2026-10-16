#!/usr/bin/env bash
# 5090 GR00T N1.5 추론 서버 (zmq, n1d5 venv) — 파인튜닝 체크포인트 서빙
# 배포 위치: 5090 ~/gr00t_remote/scripts/gr00t-server.sh  (repo가 정본)
# 사용법(5090에서):
#   ~/gr00t_remote/scripts/gr00t-server.sh t1          # T1 체크포인트 서빙 (포트 5555)
#   ~/gr00t_remote/scripts/gr00t-server.sh t2
#   ~/gr00t_remote/scripts/gr00t-server.sh logs
#   ~/gr00t_remote/scripts/gr00t-server.sh stop
#
# 방화벽(1회, sudo): sudo ufw allow from 192.168.0.11 to any port 5555 proto tcp
# 클라이언트(로컬): setup/gr00t/infer_gr00t_t1_remote.sh
# ⚠️ 학습과 동시 실행 금지(VRAM) — 학습 종료 후 서빙.
set -e

CMD="${1:-t1}"
if [ "$CMD" = "logs" ]; then exec tail -f ~/gr00t_remote/server.log; fi
if [ "$CMD" = "stop" ]; then pkill -f inference_service.py && echo 서버종료 || echo 서버없음; exit 0; fi

case "$CMD" in
  t1) CKPT=~/gr00t_remote/checkpoints/gr00t_t1_vis2/checkpoint-10000 ;;   # v4: tune_visual + grad accum 8(유효batch32), loss~0.009/12.66ep. 이전: _vis(v3), _trim(v2), gr00t_t1(v1)
  t2) CKPT=~/gr00t_remote/checkpoints/gr00t_t2/checkpoint-10000 ;;
  *)  echo "사용법: $0 {t1|t2|logs|stop}"; exit 1 ;;
esac
[ -d "$CKPT" ] || { echo "체크포인트 없음: $CKPT"; exit 1; }

cd ~/gr00t_remote/Isaac-GR00T-n1d5
source .venv/bin/activate
export HF_HOME=~/.cache/huggingface

pkill -f inference_service.py 2>/dev/null || true
nohup python scripts/inference_service.py --server \
  --model_path "$CKPT" \
  --embodiment-tag new_embodiment \
  --data-config so100_dualcam \
  --denoising-steps 4 \
  --host 0.0.0.0 \
  --port 5555 \
  > ~/gr00t_remote/server.log 2>&1 &
echo "GR00T 서버 시작 ($CMD → $CKPT, 포트 5555, PID $!). 로그: $0 logs"
