#!/usr/bin/env bash
# 블록 T1 GR00T N1.6 sim 추론을 **5090 모니터의 Isaac Sim GUI**로 보기 (headless 아님).
# blocktask_sim_eval.sh의 GUI 버전 — teleop-eval 컨테이너에 X11 전달 + --headless 제거.
# **5090의 물리 데스크톱 터미널에서 실행** (모니터 앞에서). SSH 원격은 X11 무거워 비권장.
#
# 최초 1회(5090 데스크톱): xhost +local:root   # 도커 컨테이너 GUI 접근 허용
# 사용법(5090에서):  ~/blocktask_sim_eval_gui.sh [MODEL_SUBPATH] [num_episodes] [eval|dr]
#   예: ~/blocktask_sim_eval_gui.sh gr00t_blocktask75_n16_8bit/checkpoint-20000 5 eval
set -uo pipefail

MODEL="${1:-gr00t_blocktask75_n16_8bit/checkpoint-20000}"
NUM="${2:-5}"
MODE="${3:-eval}"
TASK="Lerobot-So101-Teleop-Vials-To-Rack-Eval"
[ "$MODE" = "dr" ] && TASK="Lerobot-So101-Teleop-Vials-To-Rack-DR-Eval"

WORKSHOP="$HOME/blocktask_ws/Sim-to-Real-SO-101-Workshop"
cd "$WORKSHOP"
RENAME='{"external_D455": "front", "ego": "wrist"}'
LANG="Pick up the block and place it in the box"
SRV_LOG="$HOME/blocktask_eval_server.log"

cleanup() { docker rm -f gr00t-srv >/dev/null 2>&1 || true; }
trap cleanup EXIT
cleanup

echo "▶ [1/2] GR00T 서버 기동 (real-robot, 모델: $MODEL)"
docker run -d --name gr00t-srv --rm --network host --privileged --gpus all \
  -e PYTHONUNBUFFERED=1 \
  -v "$HOME/gr00tn16_ws/checkpoints:/workspace/models" \
  -v "$WORKSHOP/docker/real/scripts:/workspace/Isaac-GR00T/gr00t/eval/real_robot/SO100" \
  real-robot \
  bash -c "cd /Isaac-GR00T && python3 gr00t/eval/run_gr00t_server.py --model-path /workspace/models/$MODEL" \
  > /dev/null
docker logs -f gr00t-srv > "$SRV_LOG" 2>&1 &
echo "   서버 로딩 대기..."
for i in $(seq 1 120); do
  grep -q "Server is ready" "$SRV_LOG" 2>/dev/null && { echo "   ✅ 서버 준비"; break; }
  docker ps -q --filter name=gr00t-srv | grep -q . || { echo "   ❌ 서버 종료됨:"; tail -20 "$SRV_LOG"; exit 1; }
  sleep 3
done

echo "▶ [2/2] Isaac Sim GUI 평가 ($TASK, ${NUM}ep) — 5090 모니터에 뷰포트 표시"
docker run --name teleop-eval --rm -it --privileged --gpus all \
  -e ACCEPT_EULA=Y -e PRIVACY_CONSENT=Y -e DISPLAY="${DISPLAY:-:0}" --network host \
  -v /tmp/.X11-unix:/tmp/.X11-unix \
  -v "$WORKSHOP/docker/env:/root/env" \
  -v "$WORKSHOP/source:/workspace/Sim-to-Real-SO-101-Workshop/source" \
  -v "$WORKSHOP/outputs:/workspace/Sim-to-Real-SO-101-Workshop/outputs" \
  teleop-docker:latest \
  bash -c "lerobot_eval --task $TASK --num_envs 1 --num_episodes $NUM \
    --rename_map '$RENAME' --action_horizon 16 \
    --lang_instruction '$LANG'"
