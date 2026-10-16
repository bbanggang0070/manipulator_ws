#!/usr/bin/env bash
# 5090 π0 원격 정책 서버 (async inference) — 컨테이너 detached 실행
# 배포 위치: 5090 ~/pi0_remote/pi0-server.sh  (repo가 정본, scp로 배포)
# 사용법(5090에서):
#   ~/pi0_remote/pi0-server.sh start     # 서버 시작 (포트 8080, GPU, HF캐시 마운트)
#   ~/pi0_remote/pi0-server.sh logs      # 실시간 로그
#   ~/pi0_remote/pi0-server.sh stop      # 서버 종료
#   ~/pi0_remote/pi0-server.sh status    # 상태 확인
# HF_HUB_OFFLINE=1: gated repo(paligemma) API 접근으로 401 나는 것 방지 —
#   pi0_base·paligemma 토크나이저 모두 캐시돼 있어 오프라인으로 동작.
# 클라이언트(로컬)에서 접속: setup/pi0/infer_pi0_t1_remote.sh (server_address=192.168.0.56:8080)
set -e
NAME=pi0-server
PORT=8080

case "${1:-start}" in
  start)
    docker rm -f "$NAME" 2>/dev/null || true
    docker run -d --name "$NAME" \
      --gpus all --shm-size 16gb \
      -p ${PORT}:${PORT} \
      -v "$HOME/.cache/huggingface:/home/user_lerobot/.cache/huggingface" \
      -v "$HOME/pi0_remote/work:/home/user_lerobot/work" \
      -e HF_HOME=/home/user_lerobot/.cache/huggingface \
      -e HF_HUB_OFFLINE=1 \
      -e TRANSFORMERS_OFFLINE=1 \
      lerobot-gpu:local \
      python -m lerobot.async_inference.policy_server --host=0.0.0.0 --port=${PORT}
    echo "π0 서버 시작됨 (컨테이너 $NAME, 포트 $PORT). 로그: $0 logs"
    ;;
  logs)    docker logs -f "$NAME" ;;
  stop)    docker rm -f "$NAME" && echo "서버 종료됨" ;;
  status)
    docker ps --filter "name=$NAME" --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
    ;;
  *) echo "사용법: $0 {start|logs|stop|status}"; exit 1 ;;
esac
