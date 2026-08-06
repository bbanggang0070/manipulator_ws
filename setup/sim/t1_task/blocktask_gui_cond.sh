#!/usr/bin/env bash
# 조건(프리셋)별 GUI 추론 — **5090 물리 모니터 앞 터미널에서 실행**.
# 눈으로 보며 SR을 직접 기록하고, 잘못된 씬(블록-박스 겹침 등)은 R 키로 건너뛴다.
#
# 배경:
#  · 자동 sweep의 success/fail 표기는 termination 기준이라, 눈으로 성공해도 성공 판정이
#    안 걸린 채 timeout되면 'fail'로 기록된다(실제 오표기 확인됨) → 육안 확인이 필요.
#  · 박스·블록이 모두 랜덤이라 둘이 겹쳐 스폰되는 경우가 있고(전체 랜덤 시 약 12%),
#    이런 씬은 파지 자체가 불가능하므로 지표에서 빼야 한다 → R 키로 스킵.
#
# 사용법(5090 데스크톱 터미널):
#   xhost +local:root                      # 최초 1회
#   ~/blocktask_gui_cond.sh <조건> [모델] [에피소드수]
#   예: ~/blocktask_gui_cond.sh ref
#       ~/blocktask_gui_cond.sh box_rand gr00t_blocktask_v3_n16_8bit/checkpoint-40000 10
#
# 조건: ref | pos_ood | box_rand | box_ood | color_blue | color_green
#      (phys_dr·light_dr는 제외 — light_dr은 라이트박스가 씬을 감싸 sky_light 효과가
#       거의 없음이 실측 확인됐고, 실기 환경도 조명이 안정적이라 불필요)
#
# ── 조작 ──────────────────────────────────────────────
#   R      현재 에피소드 **취소하고 다음 씬으로** (카운트·영상 저장 안 됨)
#          → 블록·박스가 겹쳐 스폰된 씬을 뺄 때 사용
#   Ctrl+C 종료
# ─────────────────────────────────────────────────────
set -uo pipefail

COND="${1:?조건 필요: ref|pos_ood|box_rand|box_ood|color_blue|color_green}"
MODEL="${2:-gr00t_blocktask_v3_n16_8bit/checkpoint-40000}"
NUM="${3:-10}"

WORKSHOP="$HOME/blocktask_ws/Sim-to-Real-SO-101-Workshop"
CFG="$WORKSHOP/source/sim_to_real_so101/tasks/vials_to_rack_env_cfg.py"
TASK="Lerobot-So101-Teleop-Vials-To-Rack-DR-Eval"   # 씬 에셋 동일 유지 (sweep과 같은 조건)
RENAME='{"external_D455": "front", "ego": "wrist"}'
LANG="Pick up the block and place it in the box"
SRV_LOG="$HOME/blocktask_gui_server.log"

BAK="$CFG.gui_bak"
cp "$CFG" "$BAK"
cleanup() {
  cp "$BAK" "$CFG"; rm -f "$BAK"
  docker rm -f gr00t-srv teleop-eval >/dev/null 2>&1 || true
  echo; echo "[정리] 씬 복원 + 컨테이너 종료 완료"
}
trap cleanup EXIT
docker rm -f gr00t-srv teleop-eval >/dev/null 2>&1 || true

echo "▶ [1/3] 씬 설정: $COND"
python3 "$HOME/configure_scene.py" "$CFG" "$COND" || exit 1

echo "▶ [2/3] GR00T 서버 기동 (모델: $MODEL)"
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
  docker ps -q --filter name=gr00t-srv | grep -q . || { echo "   ❌ 서버 종료됨:"; tail -20 "$SRV_LOG"; exit 1; }
  sleep 3
done

# 영상은 5090 로컬에 조건별로 저장 → 나중에 검토·로컬(5070Ti) 전송 가능.
# R로 건너뛴 씬은 프레임 버퍼가 비워지므로 **저장되지 않는다**(집계에서도 빠짐).
OUTDIR_HOST="$WORKSHOP/outputs/gui_$COND"
OUTDIR_CT="/workspace/Sim-to-Real-SO-101-Workshop/outputs/gui_$COND"
docker run --rm -v "$WORKSHOP/outputs:/o" --entrypoint bash real-robot-train8 \
  -c "rm -rf /o/gui_$COND" >/dev/null 2>&1 || true

echo "▶ [3/3] GUI 추론 시작 — 조건 [$COND], ${NUM}ep"
echo "   저장 위치: $OUTDIR_HOST"
echo "   ┌────────────────────────────────────────────┐"
echo "   │  R      : 이 씬 건너뛰기(겹침 등) — 미집계 │"
echo "   │  Ctrl+C : 종료                             │"
echo "   └────────────────────────────────────────────┘"
echo "   ※ 파일명의 success/fail은 termination 기준이라 오표기 가능 —"
echo "      최종 판정은 **직접 보신 결과**를 기록하세요."
docker run --name teleop-eval --rm -it --privileged --gpus all \
  -e ACCEPT_EULA=Y -e PRIVACY_CONSENT=Y -e DISPLAY="${DISPLAY:-:1}" --network host \
  -e CAM_X=0.03 -e CAM_Z=0.02 \
  -v /tmp/.X11-unix:/tmp/.X11-unix \
  -v "$WORKSHOP/docker/env:/root/env" \
  -v "$WORKSHOP/source:/workspace/Sim-to-Real-SO-101-Workshop/source" \
  -v "$WORKSHOP/outputs:/workspace/Sim-to-Real-SO-101-Workshop/outputs" \
  teleop-docker:latest \
  bash -c "lerobot_eval --task $TASK --num_envs 1 --num_episodes $NUM \
    --rename_map '$RENAME' --action_horizon 16 \
    --lang_instruction '$LANG' --save_video_dir $OUTDIR_CT"

echo
echo "▶ 저장된 영상: $(ls "$OUTDIR_HOST"/*.mp4 2>/dev/null | wc -l)개  ($OUTDIR_HOST)"
echo "   로컬로 가져오려면(5070Ti에서):"
echo "     scp -r '5090:$OUTDIR_HOST' ~/manipulator_ws/inf_video/02_v3_OOD/"
