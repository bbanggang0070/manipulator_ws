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
#   ~/blocktask_gui_cond.sh <조건> [에피소드수]           # 모델 기본값 사용
#   ~/blocktask_gui_cond.sh <조건> [모델] [에피소드수]
#   예: ~/blocktask_gui_cond.sh ref
#       ~/blocktask_gui_cond.sh full 20
#       ~/blocktask_gui_cond.sh box_rand gr00t_blocktask_v3_n16_8bit/checkpoint-40000 10
#
# ⚠ 표본을 늘리려면 **같은 명령을 두 번 돌리지 말 것** — 시드가 고정이라 같은 씬을 재생할 뿐이고,
#   시작 시 출력 폴더를 지우므로 기존 영상까지 사라진다. NUM을 키우거나 SEED를 바꿀 것.
#     SEED=7 ~/blocktask_gui_cond.sh full 10   → outputs/gui_full_s7 에 별도 저장
#
# 조건: ref | pos_ood | box_rand | box_ood | color_blue | color_green | full
#       (full = 학습 분포 전체: 박스 랜덤 + 물리 DR + 조명 DR → **합격 판정 조건**)
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
DEF_MODEL="gr00t_blocktask_v3_n16_8bit/checkpoint-40000"
# 2번째 인자가 숫자면 **에피소드 수**로 해석(모델은 기본값) — `... full 20` 형태를 허용
if [[ "${2:-}" =~ ^[0-9]+$ ]]; then
  MODEL="$DEF_MODEL"; NUM="$2"
else
  MODEL="${2:-$DEF_MODEL}"; NUM="${3:-10}"
fi
# 시드는 조건 간 짝지음(paired)을 위해 1984 고정. 표본을 **늘리려면 NUM을 키울 것**
# (시드는 시작 시 1회만 걸리므로 20ep = 서로 다른 씬 20개, 앞 10개는 10ep 실행과 동일).
# 같은 NUM으로 재실행하는 것은 표본 추가가 아니라 **같은 씬 재생**이고, 아래 rm -rf로
# 기존 영상도 지워진다. 정말 독립 표본이 필요하면 SEED를 바꿔서 실행할 것.
SEED="${SEED:-1984}"
# 시드를 바꾸면 다른 폴더에 저장해 기존 배치를 보존한다.
SUFFIX=""; [ "$SEED" != "1984" ] && SUFFIX="_s$SEED"

WORKSHOP="$HOME/blocktask_ws/Sim-to-Real-SO-101-Workshop"
CFG="$WORKSHOP/source/sim_to_real_so101/tasks/vials_to_rack_env_cfg.py"
TASK="Lerobot-So101-Teleop-Vials-To-Rack-DR-Eval"   # 씬 에셋 동일 유지 (sweep과 같은 조건)
RENAME='{"external_D455": "front", "ego": "wrist"}'
LANG="Pick up the block and place it in the box"
SRV_LOG="$HOME/blocktask_gui_server.log"

# 복원은 **불변 기준본**에서 한다.
# (이전 방식: 실행 시점 파일을 백업 → 비정상 종료로 조건이 적용된 채 남으면 다음 실행이
#  그 오염본을 '기준'으로 백업/복원해 드리프트가 영구화됨. 실제로 5090이 ref 상태로 굳었음.)
BASE="$CFG.v3base"
if [ ! -f "$BASE" ]; then
  echo "⚠ 기준본($BASE)이 없습니다. 현재 파일을 기준본으로 저장합니다 —"
  echo "  현재 파일이 조건이 적용되지 않은 v3 원본인지 먼저 확인하세요:"
  grep -E '^BLOCK_REACH_(MIN|MAX)_DIST' "$CFG"
  sed -n '/reset_basket_random = EventTerm/,/^    )/p' "$CFG" | grep -oE '"(min_dist|max_dist|yaw_range)":[^,#]*'
  echo "  (정상값: min 0.28 / max 0.34 / yaw ±3.14159)"
  read -rp "  기준본으로 저장할까요? [y/N] " _a
  [ "$_a" = "y" ] || exit 1
  cp "$CFG" "$BASE"; chmod 444 "$BASE"
fi
cleanup() {
  cp "$BASE" "$CFG"; chmod 644 "$CFG"
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
OUTDIR_HOST="$WORKSHOP/outputs/gui_$COND$SUFFIX"
OUTDIR_CT="/workspace/Sim-to-Real-SO-101-Workshop/outputs/gui_$COND$SUFFIX"
docker run --rm -v "$WORKSHOP/outputs:/o" --entrypoint bash real-robot-train8 \
  -c "rm -rf /o/gui_$COND$SUFFIX" >/dev/null 2>&1 || true

echo "▶ [3/3] GUI 추론 시작 — 조건 [$COND], ${NUM}ep (seed $SEED)"
echo "   저장 위치: $OUTDIR_HOST"
echo "   ┌────────────────────────────────────────────┐"
echo "   │  R      : 이 씬 건너뛰기(겹침 등) — 미집계 │"
echo "   │  Ctrl+C : 종료                             │"
echo "   └────────────────────────────────────────────┘"
echo "   rerun 뷰어에 cameras/rgb_external_D455(top)·cameras/rgb_ego(wrist) 표시됩니다."
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
  bash -c "lerobot_eval --task $TASK --num_envs 1 --num_episodes $NUM --seed $SEED \
    --rename_map '$RENAME' --action_horizon 16 --rerun \
    --lang_instruction '$LANG' --save_video_dir $OUTDIR_CT"

echo
echo "▶ 저장된 영상: $(ls "$OUTDIR_HOST"/*.mp4 2>/dev/null | wc -l)개  ($OUTDIR_HOST)"
echo "   로컬로 가져오려면(5070Ti에서):"
echo "     scp -r '5090:$OUTDIR_HOST' ~/manipulator_ws/inf_video/02_v3_OOD/"
