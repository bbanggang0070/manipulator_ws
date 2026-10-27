#!/usr/bin/env bash
# 양팔 GR00T 서버를 **5090**에 띄운다 — 로컬에서 ssh 로 조작. setup/gr00t/serve_local.sh 의 5090판.
#
# serve_local.sh 와 같은 이미지(real-robot)·같은 래퍼(serve_blocktask_realclient.py)·같은 마운트를 쓴다.
#   · 5090·로컬의 real-robot 이미지는 GR00T 코드가 같다(커밋 ead5283, gr00t/*.py 해시 일치 — 2026-10-26 확인)
#   · 응답 지연(카메라 3대 JPEG, 20회): 5090 중앙 73ms · 로컬 86ms → 청크 도착 간격이 로컬과 같은 범위라
#     앙상블 동작(새 청크 8스텝마다)이 바뀌지 않는다. 300ep(로컬 서빙) 결과와 비교해도 된다.
#
# 사용 (로컬에서):
#   ./serve_bi_5090.sh gr00t_bi_cleanup392_llm8_n16_8bit/checkpoint-69000
#   ./serve_bi_5090.sh '' stop
#   ./serve_bi_5090.sh '' logs
# 클라이언트는 SERVER_HOST=192.168.0.56 (eval_bi392.sh 가 알아서 넣는다)
set -uo pipefail

MODEL="${1:-}"
ACTION="${2:-start}"
REMOTE="${REMOTE:-5090}"
NAME="gr00t-srv"          # run_eval_real_bi.sh 가 이 이름으로 서빙 모델을 조회한다(run.json 의 model)
S="ssh -o ConnectTimeout=20 $REMOTE"

case "$ACTION" in
  stop) $S "docker rm -f $NAME" >/dev/null 2>&1; echo "5090 서버 중지됨"; exit 0 ;;
  logs) exec $S "docker logs -f $NAME" ;;
esac
[ -n "$MODEL" ] || { echo "❌ 모델 경로 필요 (예: gr00t_bi_cleanup392_llm8_n16_8bit/checkpoint-69000)"; exit 1; }

# 학습과 동시 실행 금지(VRAM) — 학습 컨테이너가 돌고 있으면 멈춘다
if $S "docker ps --format '{{.Names}}'" | grep -q '^gr00t-train'; then
  echo "❌ 5090에서 학습 컨테이너가 돌고 있다 — 학습이 끝난 뒤 서빙할 것"; exit 1
fi
$S "test -f ~/gr00tn16_ws/checkpoints/$MODEL/model.safetensors.index.json && test -d ~/gr00tn16_ws/checkpoints/$MODEL/experiment_cfg" \
  || { echo "❌ 5090에 체크포인트 없음: $MODEL"; exit 1; }

cur=$($S "docker inspect $NAME --format '{{join .Config.Cmd \" \"}}'" 2>/dev/null | grep -oE '/workspace/models/[^ ]+' | head -1)
if [ "$cur" = "/workspace/models/$MODEL" ] && $S "docker logs $NAME 2>&1" | grep -qa "Server is ready"; then
  echo "▶ 5090 서빙 중: $MODEL (그대로 사용)"; exit 0
fi

$S "docker rm -f $NAME" >/dev/null 2>&1
$S "docker run -d --name $NAME --rm --network host --privileged --gpus all \
  -e PYTHONUNBUFFERED=1 \
  -v \$HOME/gr00tn16_ws/checkpoints:/workspace/models \
  -v \$HOME/blocktask_srv:/srv:ro \
  -v \$HOME/blocktask_ws/Sim-to-Real-SO-101-Workshop/docker/real/scripts:/workspace/Isaac-GR00T/gr00t/eval/real_robot/SO100 \
  real-robot \
  bash -c 'cd /Isaac-GR00T && python3 /srv/serve_blocktask_realclient.py \
     --model-path /workspace/models/$MODEL --host 0.0.0.0 --port 5555'" >/dev/null \
  || { echo "❌ 5090 컨테이너 기동 실패"; exit 1; }

echo "▶ 5090 서버 기동 ($MODEL)"
for i in $(seq 1 90); do
  if $S "docker logs $NAME 2>&1" | grep -qa "Server is ready"; then
    echo "   ✅ 준비 완료 — tcp://192.168.0.56:5555"; exit 0
  fi
  $S "docker ps -q --filter name=$NAME" | grep -q . || {
    echo "   ❌ 서버 종료됨:"; $S "docker logs $NAME 2>&1" | tail -20; exit 1; }
  sleep 5
done
echo "   ⚠ 450초 대기했지만 준비 신호가 없다. ./serve_bi_5090.sh '' logs 로 확인."; exit 1
