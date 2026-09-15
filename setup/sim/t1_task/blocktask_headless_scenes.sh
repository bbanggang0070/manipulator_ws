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
# 지시문. 평가 B(언어 일반화)에서 조건마다 바꾼다.
#   LANG_INSTRUCTION="Grab the cube and put it in the container" ~/blocktask_headless_scenes.sh full 45 31
# ⚠️ 컨테이너에는 **-e 로 넘긴다**. bash -c 문자열에 직접 박으면 따옴표가 중첩되는데,
#    이 프로젝트에서 정확히 그 패턴으로 수집 지시문이 "Pick"으로 절단된 사고가 있었다.
#    지시문에 아포스트로피(robot's)가 들어가면 바로 깨진다.
LANG="${LANG_INSTRUCTION:-Pick up the block and place it in the box}"
SRV_LOG="$HOME/blocktask_headless_server.log"
# TAG: 씬 조건(COND)과 시드가 같은데 **지시문만 다른** 실행을 구분한다.
#   평가 B의 언어 축(L0/L3/L5)은 전부 COND=full 이라 태그가 없으면 같은 디렉터리에 쓰고,
#   스크립트가 출력물을 rm -rf 하므로 앞 결과가 지워진다. 시드를 바꿔 피하면 **씬이 달라져
#   언어 비교 자체가 오염된다** — 같은 씬에 문장만 바뀌어야 언어 효과가 분리된다.
#   예: TAG=L3 LANG_INSTRUCTION="Grab the cube ..." ~/blocktask_headless_scenes.sh full 45 31
_TAG="${TAG:+_$TAG}"
OUT_HOST="$WORKSHOP/outputs/hl_${COND}${_TAG}_s${SEED}"
OUT_CT="/workspace/Sim-to-Real-SO-101-Workshop/outputs/hl_${COND}${_TAG}_s${SEED}"

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
  -c "rm -rf /o/hl_${COND}${_TAG}_s${SEED}" >/dev/null 2>&1 || true   # _TAG 누락 시 태그 실행이 안 지워져 이전 판정 파일이 남는다

echo "▶ [3/3] 무인 추론 — [$COND] ${NUM}ep, seed $SEED  (약 $((NUM*70/60))분 예상)"
echo "   지시문: \"$LANG\"   패널: ${EVAL_PANEL:-0}"
echo "   배경: ${EVAL_BG:-<없음>}   작업면: ${EVAL_SURFACE_TEX:-<기본>}"
echo "   저장: $OUT_HOST"
docker run --name teleop-eval --rm --privileged --gpus all \
  -e ACCEPT_EULA=Y -e PRIVACY_CONSENT=Y --network host \
  -e CAM_X=0.03 -e CAM_Z=0.02 \
  -e LANG_INSTRUCTION="$LANG" \
  -e EVAL_PANEL="${EVAL_PANEL:-0}" \
  -e EVAL_BG="${EVAL_BG:-}" -e EVAL_HIDE="${EVAL_HIDE:-}" \
  -e EVAL_SURFACE_TEX="${EVAL_SURFACE_TEX:-}" -e EVAL_SURFACE_UV="${EVAL_SURFACE_UV:-4}" \
  -v "$WORKSHOP/docker/env:/root/env" \
  -v "$WORKSHOP/source:/workspace/Sim-to-Real-SO-101-Workshop/source" \
  -v "$WORKSHOP/outputs:/workspace/Sim-to-Real-SO-101-Workshop/outputs" \
  teleop-docker:latest \
  bash -c "lerobot_eval --task $TASK --num_envs 1 --num_episodes $NUM --seed $SEED --headless \
    --rename_map '$RENAME' --action_horizon 16 \
    --lang_instruction \"\$LANG_INSTRUCTION\" --save_video_dir $OUT_CT"

# 실행 설정을 결과 옆에 남긴다. $OUT_HOST는 컨테이너가 root로 만들어 일반 사용자 쓰기가
# 조용히 실패하므로, 컨테이너를 통해 쓴다.
#   왜 필요한가: 지시문은 어디에도 기록되지 않아, 나중에 "정말 그 문장으로 돌렸나"를
#   확인할 방법이 없었다(2026-08-12 실측). 조건 이름만으로는 증거가 되지 못한다.
META_JSON="{\"cond\":\"$COND\",\"tag\":\"${TAG:-}\",\"seed\":$SEED,\"episodes\":$NUM,\"model\":\"$MODEL\",\"eval_panel\":\"${EVAL_PANEL:-0}\",\"bg\":\"${EVAL_BG:-}\",\"surface_tex\":\"${EVAL_SURFACE_TEX:-}\",\"hide\":\"${EVAL_HIDE:-}\",\"lang\":\"$LANG\",\"finished\":\"$(date -Is)\"}"
docker run --rm -v "$WORKSHOP/outputs:/o" --entrypoint bash real-robot-train8 \
  -c "printf '%s\n' '$META_JSON' > '/o/hl_${COND}${_TAG}_s${SEED}/run.json'" >/dev/null 2>&1 || true

echo
echo "▶ 영상 $(ls "$OUT_HOST"/*.mp4 2>/dev/null | wc -l)개 · scenes.csv $( [ -f "$OUT_HOST/scenes.csv" ] && echo 있음 || echo 없음 )"
echo "   로컬로:  rsync -a 5090:'$OUT_HOST' ~/manipulator_ws/inf_video/08_evalB_sim/"
