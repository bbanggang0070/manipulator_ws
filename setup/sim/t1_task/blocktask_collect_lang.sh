#!/usr/bin/env bash
# 언어 조건화 수집 — 물체 8종 중 4개 + 박스 3색 중 2개를 놓고, **계획표가 지시문을 정한다.**
#
# 왜 별도 스크립트인가 (language_conditioning_sim_plan.md §4):
#   씬을 통째로 바꾼다(물체 10 prim·박스 4 prim 스폰, 리셋 term 교체). blocktask_run.sh를
#   건드리면 기존 수집 경로가 함께 흔들린다 — Near 수집을 분리했던 것과 같은 이유다.
#   또 이 수집만 **씬 설정 단계**가 필요하다: configure_scene.py로 cfg를 만들고,
#   끝나면 기준본으로 되돌려야 다음 작업이 오염되지 않는다.
#
# 실행 위치: **로컬 5070 Ti** — 리더암(/dev/ttyLEADER)이 여기 물려 있다.
#
# 사용:
#   ./blocktask_collect_lang.sh view      # 배치만 육안 확인(로봇 0액션)
#   ./blocktask_collect_lang.sh record    # 리더암 teleop 녹화  ← 본 작업
#   ./blocktask_collect_lang.sh clear     # 데이터셋 폴더 삭제(재시작용)
#
#   RESUME=1 ./blocktask_collect_lang.sh record          # 기존 폴더에 이어쓰기
#   PLAN=/path/to/lang_collect_plan.csv ./...            # 계획표 지정(기본: repo의 것)
#
# ── 수집 규칙 (중요) ────────────────────────────────────────────────
#   목표 280ep. S=녹화 시작, →=저장, R=리셋(저장 안 함).
#   · 화면에 뜬 지시문과 **다른 물체를 집었거나 다른 박스에 넣었으면 → 대신 R.**
#     잘못 저장된 한 ep가 "언어를 무시해도 된다"는 반례가 된다.
#   · 타깃이 top 화면에 안 잡히면 R. 보이지 않는 타깃은 어떤 정책도 못 고른다.
#   · 박스가 2개일 때 지시된 박스가 화면 밖이면 R.
#   · `[lang] ⚠ 거부 샘플링 실패` 경고가 뜬 씬은 R.
#   · 옮기는 도중 다른 물체를 크게 건드렸으면 R.
#   · 지우개는 **짧은 변**으로, 마커는 길이 중앙을 잡는다. 같은 물체를 늘 같은 각도로
#     잡지 말 것 — 그러면 물체 자세 일반화가 그대로 남는다.
# ────────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")"

MODE="${1:-view}"
WORKSHOP="$HOME/blocktask_ws/Sim-to-Real-SO-101-Workshop"
TASK_ID="Lerobot-So101-Teleop-Vials-To-Rack-DR"
DSNAME="${DSNAME:-sim_so101_blocktask_lang}"
TARGET_EP="${TARGET_EP:-280}"
PLAN="${PLAN:-$(cd ../../../manipulator_md/sim && pwd)/lang_collect_plan.csv}"
CFG="$WORKSHOP/source/sim_to_real_so101/tasks/vials_to_rack_env_cfg.py"
BASE="$CFG.v3base"
PRESET="${PRESET:-full+lang}"

[ -d "$WORKSHOP/source" ] || { echo "❌ $WORKSHOP 없음"; exit 1; }
[ -f "$BASE" ] || { echo "❌ 기준본 없음: $BASE (blocktask_gui_cond.sh를 한 번 실행해 생성)"; exit 1; }

docker_run() { if docker ps >/dev/null 2>&1; then eval "$1"; else sg docker -c "$1"; fi; }

if [ "$MODE" = "clear" ]; then
  echo "삭제: $WORKSHOP/datasets/$DSNAME"
  docker_run "docker run --rm --entrypoint /bin/bash -v $WORKSHOP/datasets:/d teleop-docker:latest -c 'rm -rf /d/$DSNAME'" 2>&1 | tail -1
  echo "완료"; exit 0
fi

# 계획표·리셋 term이 실제로 배포돼 있는지 **먼저** 확인한다.
# 전례: 씬을 5090에 배포하지 않아 v2 씬에서 측정한 무효 데이터를 만든 적이 있다.
[ -f "$PLAN" ] || { echo "❌ 계획표 없음: $PLAN"; echo "   ./gen_lang_collect_plan.py --out $PLAN 로 생성하세요"; exit 2; }
grep -q "def reset_lang_scene" "$WORKSHOP/source/sim_to_real_so101/mdp/resets.py" \
  || { echo "❌ reset_lang_scene 미배포 — mdp/resets.py 확인"; exit 2; }
grep -q "_sync_lang_instruction" "$WORKSHOP/source/sim_to_real_so101/scripts/lerobot_agent.py" \
  || { echo "❌ lerobot_agent.py에 지시문 동기화 패치 미적용 — 문장이 에피소드마다 안 바뀐다"; exit 2; }
echo "✅ 계획표 $(($(wc -l < "$PLAN") - 1))행 · reset_lang_scene · 지시문 동기화 확인"

# 씬 설정: 항상 기준본에서 출발 → 이전 실행의 조건이 남아 섞이는 일이 없다
cleanup() { cp "$BASE" "$CFG"; chmod 644 "$CFG"; echo "[정리] 씬 기준본 복원"; }
trap cleanup EXIT
cp "$BASE" "$CFG"; chmod 644 "$CFG"
python3 ./configure_scene.py "$CFG" "$PRESET" || exit 1

export DISPLAY="${DISPLAY:-:1}"
xhost +local: >/dev/null 2>&1 || true
docker_run "docker rm -f blocktask-lang" >/dev/null 2>&1 || true

CALIB=".cache/huggingface/lerobot/calibration"
mkdir -p "$WORKSHOP/outputs" "$WORKSHOP/datasets"

if [ "$MODE" = "record" ]; then
  [ -e /dev/ttyLEADER ] || { echo "❌ /dev/ttyLEADER 없음 — 리더암 연결 확인(로컬 5070 Ti에서 실행)"; exit 3; }
  if [ "${RESUME:-0}" = "1" ]; then
    echo "▶ 이어쓰기(RESUME): datasets/$DSNAME"
  else
    N=1; TRY="$DSNAME"
    while [ -d "$WORKSHOP/datasets/$TRY" ]; do N=$((N+1)); TRY="${DSNAME}_${N}"; done
    DSNAME="$TRY"
    echo "▶ 녹화 대상 폴더(신규): datasets/$DSNAME"
  fi
  # --task_name은 **폴백**이다. 실제 문장은 계획표에서 와서 에피소드마다 갱신된다
  # (_sync_lang_instruction). 이 인자가 없으면 recorder 자체가 켜지지 않는다.
  INNER="lerobot_agent --task $TASK_ID --num_envs 1 --rerun \
    --port /dev/ttyLEADER --robot_id leader \
    --repo_id heongyu/$DSNAME \
    --repo_root /workspace/Sim-to-Real-SO-101-Workshop/datasets/$DSNAME \
    --task_name \"\$TASK_NAME\""
else
  INNER="zero_agent --task $TASK_ID --num_envs 1"
fi

# 카메라 오프셋은 평가와 **반드시 같아야 한다**(학습·평가 불일치 방지).
CAM_X_V="${CAM_X:-0.03}"; CAM_Y_V="${CAM_Y:-0}"; CAM_Z_V="${CAM_Z:-0.02}"

cat <<INFO

  태스크   : $TASK_ID  ($PRESET)
  계획표   : $PLAN
  데이터셋 : datasets/$DSNAME     목표 ${TARGET_EP}ep
  카메라   : CAM_X=$CAM_X_V CAM_Y=$CAM_Y_V CAM_Z=$CAM_Z_V  ← 평가와 동일해야 함

  ┌──────────────────────────────────────────────────────────┐
  │ S : 녹화 시작   → : 저장   R : 리셋(저장 안 함)          │
  │                                                          │
  │ 리셋마다 콘솔에 **이번 지시문**이 뜬다. 그대로 수행할 것.│
  │ 다른 물체/다른 박스로 갔으면 →가 아니라 R.               │
  └──────────────────────────────────────────────────────────┘

INFO

RUN="docker run --name blocktask-lang --rm -it --privileged --gpus all \
  -e ACCEPT_EULA=Y -e PRIVACY_CONSENT=Y -e DISPLAY=$DISPLAY --network=host \
  -e CAM_X=$CAM_X_V -e CAM_Y=$CAM_Y_V -e CAM_Z=$CAM_Z_V \
  -e LANG_PLAN=/workspace/lang_collect_plan.csv \
  -e TASK_NAME=\"${TASK_NAME:-Pick up the block and place it in the box}\" \
  -e LEROBOT_RERUN_MEMORY_LIMIT=${LEROBOT_RERUN_MEMORY_LIMIT:-30%} \
  -v /dev:/dev -v /run/udev:/run/udev:ro \
  -v /tmp/.X11-unix:/tmp/.X11-unix -v $HOME/.Xauthority:/root/.Xauthority \
  -v $HOME/docker/isaac-sim/cache/kit:/isaac-sim/kit/cache:rw \
  -v $HOME/docker/isaac-sim/cache/ov:/root/.cache/ov:rw \
  -v $HOME/docker/isaac-sim/cache/glcache:/root/.cache/nvidia/GLCache:rw \
  -v $HOME/docker/isaac-sim/cache/computecache:/root/.nv/ComputeCache:rw \
  -v $HOME/$CALIB:/root/$CALIB \
  -v $PLAN:/workspace/lang_collect_plan.csv:ro \
  -v $WORKSHOP/docker/env:/root/env \
  -v $WORKSHOP/source:/workspace/Sim-to-Real-SO-101-Workshop/source \
  -v $WORKSHOP/outputs:/workspace/Sim-to-Real-SO-101-Workshop/outputs \
  -v $WORKSHOP/datasets:/workspace/Sim-to-Real-SO-101-Workshop/datasets \
  teleop-docker:latest bash -c '$INNER'"

docker_run "$RUN"

if [ "$MODE" = "record" ]; then
  D="$WORKSHOP/datasets/$DSNAME"
  n=$(ls "$D/videos/observation.images.external_D455/chunk-000/"*.mp4 2>/dev/null | wc -l)
  echo
  echo "▶ 수집 완료: ${n}ep  (목표 ${TARGET_EP})  → $D"
  [ "$n" -lt "$TARGET_EP" ] && echo "   부족분은 RESUME=1 DSNAME=$DSNAME 로 이어서 수집하세요."
  echo "   다음: 균형 검증 → verify_lang_dataset.py (물체별 타깃·상관·미학습 색 유출)"
fi
