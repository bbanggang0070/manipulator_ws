#!/usr/bin/env bash
# 블록 T1 GR00T N1.6 sim 평가 (Phase D). sim_eval_gr00t.sh(vials)의 블록 버전.
# **5090에서 실행**한다(블록 포크 소스가 5090에 배포돼 있어야 함 — 아래 deploy 참고).
#
# 사용법(5090에서):  ~/blocktask_sim_eval.sh [MODEL_SUBPATH] [num_episodes] [eval|dr]
#   예: ~/blocktask_sim_eval.sh gr00t_blocktask75_n16_8bit/checkpoint-20000 10 eval
#       ~/blocktask_sim_eval.sh gr00t_blocktask75_n16_8bit/checkpoint-20000 10 dr
#
# 사전 배포(로컬에서 1회): 블록 포크 전체를 5090으로 rsync (env cfg + 손목 관절 매핑이 든
#   utils/lerobot_interface.py 포함 → 학습 데이터와 동일 렌더링 보장)
#   rsync -a ~/blocktask_ws/Sim-to-Real-SO-101-Workshop/ 5090:~/blocktask_ws/Sim-to-Real-SO-101-Workshop/
#
# 동작: (1) real-robot 컨테이너로 GR00T 서버(5555) 기동 → ready 대기
#       (2) teleop-docker로 블록 lerobot_eval 클라이언트 headless 실행 → SR 출력
#       (3) 서버 정리
set -uo pipefail

MODEL="${1:-gr00t_blocktask75_n16_8bit/checkpoint-20000}"
NUM="${2:-10}"
MODE="${3:-eval}"
TASK="Lerobot-So101-Teleop-Vials-To-Rack-Eval"          # 포크가 블록 씬으로 덮어쓴 등록
[ "$MODE" = "dr" ] && TASK="Lerobot-So101-Teleop-Vials-To-Rack-DR-Eval"

WORKSHOP="$HOME/blocktask_ws/Sim-to-Real-SO-101-Workshop"  # 5090의 블록 포크(배포본)
cd "$WORKSHOP"

RENAME='{"external_D455": "front", "ego": "wrist"}'       # vials와 동일
LANG="Pick up the block and place it in the box"          # 녹화 시 사용한 지시와 일치
SRV_LOG="$HOME/blocktask_eval_server.log"
CLI_LOG="$HOME/blocktask_eval_client_$(date +%Y%m%d_%H%M%S).log"

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

echo "   서버 로딩 대기 (모델 로드 ~1-2분)..."
for i in $(seq 1 120); do
  grep -q "Server is ready" "$SRV_LOG" 2>/dev/null && { echo "   ✅ 서버 준비 완료"; break; }
  if ! docker ps -q --filter name=gr00t-srv | grep -q .; then
    echo "   ❌ 서버 컨테이너 종료됨. 로그:"; tail -20 "$SRV_LOG"; exit 1
  fi
  sleep 3
done

echo "▶ [2/2] 블록 sim 평가 ($TASK, ${NUM}ep, headless)"
docker run --name teleop-eval --rm --privileged --gpus all \
  -e ACCEPT_EULA=Y -e PRIVACY_CONSENT=Y --network host \
  -v "$WORKSHOP/docker/env:/root/env" \
  -v "$WORKSHOP/source:/workspace/Sim-to-Real-SO-101-Workshop/source" \
  -v "$WORKSHOP/outputs:/workspace/Sim-to-Real-SO-101-Workshop/outputs" \
  teleop-docker:latest \
  bash -c "lerobot_eval --task $TASK --num_envs 1 --num_episodes $NUM \
    --rename_map '$RENAME' --action_horizon 16 \
    --lang_instruction '$LANG' --headless \
    ${SAVE_VIDEO_DIR:+--save_video_dir $SAVE_VIDEO_DIR}" 2>&1 | tee "$CLI_LOG"

echo
echo "=== 결과 요약 ==="
grep -i "Success Rate" "$CLI_LOG" || echo "(성공률 라인 미검출 — 로그 확인: $CLI_LOG)"
