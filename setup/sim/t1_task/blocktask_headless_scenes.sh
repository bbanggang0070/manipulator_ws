#!/usr/bin/env bash
# 조건별 **무인(headless)** 추론 — 영상 + 씬 좌표(scenes.csv)를 남기고, 판정은 나중에 영상으로.
#
# 왜 필요한가:
#   GUI 육안 측정은 조건당 10~25분간 사람이 붙어 있어야 해서 표본을 늘리기 어렵다.
#   원인 변수(블록 각도 등)를 검증하려면 N=60~100이 필요한데, 그건 무인으로 돌리고
#   나중에 영상만 확인하는 편이 훨씬 싸다.
#
# GUI판(blocktask_gui_cond.sh)과의 차이:
#   · DISPLAY/rerun 없음, --headless → 사람이 지켜볼 필요 없음
#   · R 키 스킵 불가 → 겹침 씬은 scenes.csv의 block_box_dist로 사후 제외
#   · 시드별로 폴더가 갈려 여러 배치를 누적할 수 있음
#
# 사용법(5090):
#   ~/blocktask_headless_scenes.sh <조건> [에피소드수] [시드]
#   예: ~/blocktask_headless_scenes.sh full 20 11
#       for s in 11 12 13; do ~/blocktask_headless_scenes.sh full 20 $s; done   # 누적 60ep
#
# 출력: outputs/hl_<조건>_s<시드>/  (epNN_{success,fail}.mp4 + scenes.csv)
#   ※ scenes.csv의 outcome은 termination 기준이다. 2026-08-06에 grasp_history_window를
#     20→1000으로 고쳐 오표기 원인은 제거했지만, **최종 판정은 영상 확인 결과**로 한다.
set -uo pipefail

COND="${1:?조건 필요 (ref|pos_ood|box_rand|box_ood|color_blue|color_green|full|phys_dr|light_dr|box_pos_only|box_yaw_only)}"
NUM="${2:-20}"
SEED="${3:-1984}"
MODEL="${MODEL:-gr00t_blocktask_v3_n16_8bit/checkpoint-40000}"

WORKSHOP="$HOME/blocktask_ws/Sim-to-Real-SO-101-Workshop"
CFG="$WORKSHOP/source/sim_to_real_so101/tasks/vials_to_rack_env_cfg.py"
BASE="$CFG.v3base"
TASK="Lerobot-So101-Teleop-Vials-To-Rack-DR-Eval"
RENAME='{"external_D455": "front", "ego": "wrist"}'
LANG="Pick up the block and place it in the box"
SRV_LOG="$HOME/blocktask_headless_server.log"
OUT_HOST="$WORKSHOP/outputs/hl_${COND}_s${SEED}"
OUT_CT="/workspace/Sim-to-Real-SO-101-Workshop/outputs/hl_${COND}_s${SEED}"

[ -f "$BASE" ] || { echo "❌ 기준본 없음: $BASE (blocktask_gui_cond.sh를 먼저 한 번 실행해 생성)"; exit 1; }

cleanup() {
  cp "$BASE" "$CFG"; chmod 644 "$CFG"
  docker rm -f gr00t-srv teleop-eval >/dev/null 2>&1 || true
  echo "[정리] 씬 복원 + 컨테이너 종료"
}
trap cleanup EXIT
docker rm -f gr00t-srv teleop-eval >/dev/null 2>&1 || true

# 항상 기준본에서 출발 → 이전 실행의 조건이 남아 섞이는 일이 없다
cp "$BASE" "$CFG"; chmod 644 "$CFG"
echo "▶ [1/3] 씬 설정: $COND"
python3 "$HOME/configure_scene.py" "$CFG" "$COND" || exit 1

echo "▶ [2/3] GR00T 서버 기동 ($MODEL)"
docker run -d --name gr00t-srv --rm --network host --privileged --gpus all \
  -e PYTHONUNBUFFERED=1 \
  -v "$HOME/gr00tn16_ws/checkpoints:/workspace/models" \
  -v "$WORKSHOP/docker/real/scripts:/workspace/Isaac-GR00T/gr00t/eval/real_robot/SO100" \
  real-robot \
  bash -c "cd /Isaac-GR00T && python3 gr00t/eval/run_gr00t_server.py --model-path /workspace/models/$MODEL" \
  > /dev/null
docker logs -f gr00t-srv > "$SRV_LOG" 2>&1 &
for i in $(seq 1 120); do
  grep -q "Server is ready" "$SRV_LOG" 2>/dev/null && { echo "   ✅ 서버 준비"; break; }
  docker ps -q --filter name=gr00t-srv | grep -q . || { echo "   ❌ 서버 종료:"; tail -20 "$SRV_LOG"; exit 1; }
  sleep 3
done

docker run --rm -v "$WORKSHOP/outputs:/o" --entrypoint bash real-robot-train8 \
  -c "rm -rf /o/hl_${COND}_s${SEED}" >/dev/null 2>&1 || true

echo "▶ [3/3] 무인 추론 — [$COND] ${NUM}ep, seed $SEED  (약 $((NUM*70/60))분 예상)"
echo "   저장: $OUT_HOST"
docker run --name teleop-eval --rm --privileged --gpus all \
  -e ACCEPT_EULA=Y -e PRIVACY_CONSENT=Y --network host \
  -e CAM_X=0.03 -e CAM_Z=0.02 \
  -v "$WORKSHOP/docker/env:/root/env" \
  -v "$WORKSHOP/source:/workspace/Sim-to-Real-SO-101-Workshop/source" \
  -v "$WORKSHOP/outputs:/workspace/Sim-to-Real-SO-101-Workshop/outputs" \
  teleop-docker:latest \
  bash -c "lerobot_eval --task $TASK --num_envs 1 --num_episodes $NUM --seed $SEED --headless \
    --rename_map '$RENAME' --action_horizon 16 \
    --lang_instruction '$LANG' --save_video_dir $OUT_CT"

echo
echo "▶ 영상 $(ls "$OUT_HOST"/*.mp4 2>/dev/null | wc -l)개 · scenes.csv $( [ -f "$OUT_HOST/scenes.csv" ] && echo 있음 || echo 없음 )"
echo "   로컬로:  rsync -a 5090:'$OUT_HOST' ~/manipulator_ws/inf_video/03_v3_GUI/"
