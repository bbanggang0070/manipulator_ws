#!/usr/bin/env bash
# GR00T 정책 서버를 **로컬 5070 Ti**에서 띄운다. 5090의 serve_blocktask_n16_5090.sh의 로컬판.
#
# 왜 로컬인가(2026-08-14):
#   지금까지 서버는 5090에만 있었고 실기 클라이언트가 WiFi로 붙었다. 그 지연이
#   **앙상블 동작을 좌우한다**는 것이 확인됐다 — 청크 도착 간격이 겹치는 청크 수를 정하고,
#   같은 W라도 결과가 달라진다(§3-3, §5-3). 로컬로 옮기면 그 변수가 사라지고,
#   5090을 학습에 쓸 수 있게 된다.
#
# 준비물:
#   · real-robot 이미지 (docker/real/build.sh blackwell)
#   · 체크포인트가 ~/gr00tn16_ws/checkpoints/ 아래에 있을 것
#     (추론에는 safetensors·config·experiment_cfg만 있으면 된다. optimizer.pt 등 학습 전용은 불필요)
#
# 사용:
#   ./serve_local.sh gr00t_blocktask_cotrain_v4_n16_8bit/checkpoint-48000
#   ./serve_local.sh <MODEL> stop
#   ./serve_local.sh '' logs
set -uo pipefail

MODEL="${1:-gr00t_blocktask_cotrain_v4_n16_8bit/checkpoint-48000}"
ACTION="${2:-start}"
NAME="gr00t-srv"          # 5090판과 같은 이름 — run_eval_real.sh가 이 이름으로 모델을 조회한다
CKPT="$HOME/gr00tn16_ws/checkpoints"
W="$HOME/blocktask_ws/Sim-to-Real-SO-101-Workshop"

docker_run() { if docker ps >/dev/null 2>&1; then eval "$1"; else sg docker -c "$1"; fi; }

case "$ACTION" in
  stop)  docker_run "docker rm -f $NAME" >/dev/null 2>&1; echo "중지됨"; exit 0 ;;
  logs)  docker_run "docker logs -f $NAME"; exit 0 ;;
esac

[ -d "$CKPT/$MODEL" ] || { echo "❌ 체크포인트 없음: $CKPT/$MODEL"; exit 1; }
for f in config.json experiment_cfg; do
  [ -e "$CKPT/$MODEL/$f" ] || { echo "❌ $MODEL: $f 없음 — 복사가 덜 됐을 수 있다"; exit 1; }
done

docker_run "docker rm -f $NAME" >/dev/null 2>&1
# ⚠ run_gr00t_server.py를 직접 쓰면 안 된다.
#   그 PolicyServer는 관측을 **kwargs로 언팩**하는데, 실기 클라이언트는 `video.front` 같은
#   **평탄 키**를 보낸다 → `get_action() got an unexpected keyword argument 'video.front'`.
#   5090도 같은 이유로 래퍼(serve_blocktask_realclient.py)를 쓴다. 그 래퍼가 평탄 키를
#   중첩 구조로 바꿔 등록한다("Registered 'get_action' (flat->nested transform)").
SRV="$HOME/blocktask_srv"
[ -f "$SRV/serve_blocktask_realclient.py" ] || {
  echo "❌ 래퍼 없음: $SRV/serve_blocktask_realclient.py"
  echo "   5090에서 가져오세요: rsync -a 5090:'~/blocktask_srv/' ~/blocktask_srv/"; exit 1; }

docker_run "docker run -d --name $NAME --rm --network host --privileged --gpus all \
  -e PYTHONUNBUFFERED=1 \
  -v '$CKPT:/workspace/models' \
  -v '$SRV:/srv:ro' \
  -v '$W/docker/real/scripts:/workspace/Isaac-GR00T/gr00t/eval/real_robot/SO100' \
  real-robot \
  bash -c 'cd /Isaac-GR00T && python3 /srv/serve_blocktask_realclient.py \
     --model-path /workspace/models/$MODEL --host 0.0.0.0 --port 5555'" \
  > /dev/null || { echo "❌ 컨테이너 기동 실패"; exit 1; }

echo "▶ 로컬 서버 기동 ($MODEL)"
for i in $(seq 1 90); do
  docker_run "docker logs $NAME 2>&1" | grep -qa "Server is ready" && {
    echo "   ✅ 준비 완료 — tcp://127.0.0.1:5555"
    echo
    echo "   클라이언트: SERVER_HOST=127.0.0.1 ./run_eval_real.sh C <조건>"
    exit 0; }
  docker_run "docker ps -q --filter name=$NAME" | grep -q . || {
    echo "   ❌ 서버 종료됨:"; docker_run "docker logs $NAME 2>&1" | tail -20; exit 1; }
  sleep 5
done
echo "   ⚠ 90회(450초) 대기했지만 준비 신호가 없다. ./serve_local.sh '' logs 로 확인."
