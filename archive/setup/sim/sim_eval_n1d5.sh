#!/usr/bin/env bash
# GR00T **N1.5** sim 평가 — n1d5 host 추론 서버 + teleop-docker lerobot_eval 클라이언트. **5090에서 실행**.
#
# 어제 옵션A(sim_eval_gr00t.sh)는 real-robot 컨테이너(N1.6) 서버를 썼지만, 우리 학습본은
# gr00t_n1_5라 N1.6 서버로 로드 불가 → n1d5 host venv 서버(inference_service.py)로 서빙.
# 클라이언트(lerobot_eval)는 포트 5555의 아무 GR00T 서버에나 붙으므로 조합 가능.
#
# 카메라: 학습 시 modality.json으로 front←external_D455, wrist←ego 매핑 → 모델은 front/wrist 기대.
#   클라이언트가 --rename_map으로 sim의 ego/external_D455를 front/wrist로 변환해 보냄(정합).
#
# 사용법(5090에서): ~/sim_eval_n1d5.sh <CKPT_경로> [num_episodes] [eval|dr]
set -uo pipefail

CKPT="${1:-$HOME/gr00tn15_ws/checkpoints/gr00t_sim_vials75_n15/checkpoint-20000}"
NUM="${2:-10}"
MODE="${3:-eval}"
TASK="Lerobot-So101-Teleop-Vials-To-Rack-Eval"
[ "$MODE" = "dr" ] && TASK="Lerobot-So101-Teleop-Vials-To-Rack-DR-Eval"

WORKSHOP="$HOME/Sim-to-Real-SO-101-Workshop"
RENAME='{"external_D455": "front", "ego": "wrist"}'
LANG="Pick up the vial and place it in the yellow rack"
SRV_LOG="$HOME/sim_eval_n1d5_server.log"
CLI_LOG="$HOME/sim_eval_n1d5_client_$(date +%Y%m%d_%H%M%S).log"

cleanup() { pkill -f inference_service.py 2>/dev/null || true; docker rm -f teleop-eval 2>/dev/null || true; }
trap cleanup EXIT
cleanup; sleep 2

echo "▶ [1/2] n1d5 추론 서버 기동 (host venv, 모델: $CKPT)"
cd "$HOME/gr00t_remote/Isaac-GR00T-n1d5"
source .venv/bin/activate
export HF_HOME="$HOME/gr00tn15_ws/hf_home_airlab"  # airlab 소유(쓰기가능) — 공용 캐시(UID 1001)의 filelock hang 회피
  mkdir -p "$HF_HOME"
nohup python scripts/inference_service.py --server \
  --model_path "$CKPT" \
  --embodiment-tag new_embodiment \
  --data-config so100_dualcam \
  --denoising-steps 4 \
  --host 0.0.0.0 --port 5555 > "$SRV_LOG" 2>&1 &

echo "   서버 로딩 대기..."
for i in $(seq 1 100); do
  grep -q "Server is ready\|running on\|listening" "$SRV_LOG" 2>/dev/null && { echo "   ✅ 서버 준비"; break; }
  pgrep -f inference_service.py >/dev/null || { echo "   ❌ 서버 종료됨:"; tail -15 "$SRV_LOG"; exit 1; }
  sleep 3
done
sleep 5  # 여유

echo "▶ [2/2] sim 평가 클라이언트 (teleop-docker, $TASK, ${NUM}ep, headless)"
docker rm -f teleop-eval 2>/dev/null || true
docker run --name teleop-eval --rm --privileged --gpus all \
  -e ACCEPT_EULA=Y -e PRIVACY_CONSENT=Y --network host \
  -v "$WORKSHOP/docker/env:/root/env" \
  -v "$WORKSHOP/source:/workspace/Sim-to-Real-SO-101-Workshop/source" \
  -v "$WORKSHOP/outputs:/workspace/Sim-to-Real-SO-101-Workshop/outputs" \
  teleop-docker:latest \
  bash -c "lerobot_eval --task $TASK --num_envs 1 --num_episodes $NUM \
    --rename_map '$RENAME' --action_horizon 16 \
    --lang_instruction '$LANG' --headless" 2>&1 | tee "$CLI_LOG"

echo; echo "=== 결과 요약 ==="
grep -i "Success Rate" "$CLI_LOG" || grep -aoE "success: [0-9.]+%" "$CLI_LOG" | tail -1 || echo "(로그 확인: $CLI_LOG)"
