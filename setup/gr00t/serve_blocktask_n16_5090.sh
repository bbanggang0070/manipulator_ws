#!/usr/bin/env bash
# 5090 GR00T N1.6 서버 — 블록 sim 체크포인트를 **실기 클라이언트**에 서빙 (Phase E: sim→real 전이).
# 배포 위치: 5090 (~/ 에 두고 실행). 정본은 이 repo.
#
# sim 평가(Eval 60% / DR-Eval 50%)를 돌린 run_gr00t_server.py 그대로 재사용.
# --network host → 5090 LAN IP(192.168.0.56):5555 로 실기 클라이언트가 접속.
# 표준 gr00t service.py(zmq REP, msgpack, endpoint get_action) 프로토콜 →
#   실기 클라이언트 setup/gr00t/client/eval_lerobot.py(ExternalRobotInferenceClient)와 호환.
#
# 사용법(5090에서):
#   ~/serve_blocktask_n16_5090.sh                 # 기본 체크포인트 서빙
#   ~/serve_blocktask_n16_5090.sh <MODEL_SUBPATH> # 다른 체크포인트
#   ~/serve_blocktask_n16_5090.sh '' logs         # 로그
#   ~/serve_blocktask_n16_5090.sh '' stop         # 종료
#
# 방화벽(최초 1회, 5090에서): sudo ufw allow from 192.168.0.11 to any port 5555 proto tcp
# 실기 클라이언트(로컬):        setup/gr00t/infer_gr00t_blocktask_remote.sh
# ⚠️ 학습과 동시 실행 금지(VRAM).
set -e

MODEL="${1:-gr00t_blocktask75_n16_8bit/checkpoint-20000}"
CMD="${2:-start}"
WORKSHOP="$HOME/blocktask_ws/Sim-to-Real-SO-101-Workshop"

if [ "$CMD" = "logs" ]; then exec docker logs -f gr00t-srv; fi
if [ "$CMD" = "stop" ]; then docker rm -f gr00t-srv 2>/dev/null && echo "서버 종료" || echo "서버 없음"; exit 0; fi

[ -d "$HOME/gr00tn16_ws/checkpoints/$MODEL" ] || { echo "체크포인트 없음: ~/gr00tn16_ws/checkpoints/$MODEL"; exit 1; }
[ -f "$HOME/blocktask_srv/serve_blocktask_realclient.py" ] || { echo "서버 스크립트 없음: ~/blocktask_srv/ (serve_blocktask_realclient.py + service.py 배포 필요)"; exit 1; }
docker rm -f gr00t-srv 2>/dev/null || true

# 실기 클라이언트 service.py 규약(BaseInferenceServer, handler(obs) 단일 positional)로 Gr00tPolicy 서빙.
# (run_gr00t_server.py=PolicyServer는 obs를 kwargs로 언팩해 실기 클라이언트의 평탄 키와 불일치)
docker run -d --name gr00t-srv --rm --network host --privileged --gpus all \
  -e PYTHONUNBUFFERED=1 \
  -v "$HOME/gr00tn16_ws/checkpoints:/workspace/models" \
  -v "$HOME/blocktask_srv:/srv:ro" \
  real-robot \
  bash -c "cd /Isaac-GR00T && python3 /srv/serve_blocktask_realclient.py --model-path /workspace/models/$MODEL --host 0.0.0.0 --port 5555" \
  > /dev/null

echo "GR00T N1.6 블록 서버 시작 ($MODEL, 포트 5555, 실기 클라이언트 호환)."
echo "  준비 확인: $0 '' logs  → 'Ready to serve real client' / 'Server is ready' 대기"
echo "  실기 클라이언트(로컬): setup/gr00t/infer_gr00t_blocktask_remote.sh"
