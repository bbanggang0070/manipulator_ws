#!/usr/bin/env bash
# v4 타깃 수집 — 블록이 **박스에 가까운(0.08~0.18m)** 배치만 골라 시연을 모은다.
#
# 왜 별도 스크립트인가:
#   v3@40k가 근접 배치에서 SR 39%(원거리 83%)였고, 원인이 수집 필터에 있었다.
#   겹침 ep를 빼면서 **유효 근접 구간까지 함께 걸러져** 학습 근접 비율이 19.2%
#   (씬의 자연 분포는 43.2%)에 그쳤다. 그 구멍만 메운다.
#   태스크가 다르므로(...-Near) blocktask_run.sh를 건드리지 않고 분리했다.
#
# 사용법(5090 데스크톱):
#   ./blocktask_collect_near.sh view      # 배치만 육안 확인(로봇 0액션)
#   ./blocktask_collect_near.sh record    # 리더암 teleop 녹화  ← 본 작업
#   ./blocktask_collect_near.sh clear     # 데이터셋 폴더 삭제(재시작용)
#
#   RESUME=1 ./blocktask_collect_near.sh record   # 기존 폴더에 이어쓰기
#   DSNAME=... 으로 데이터셋 이름 변경 가능
#
# ── 수집 규칙 (중요) ────────────────────────────────────────────────
#   목표 65ep. S=에피소드 저장, R=리셋.
#   · 블록이 박스 **벽에 닿거나 겹친** 씬만 R로 건너뛴다.
#   · **"붙어 있어서 어렵다"는 이유로 건너뛰지 말 것** — 그게 정확히 메우려는 구멍이다.
#     지금 모델이 못 하는 게 그 동작이므로, 박스 벽을 피해 비스듬히 접근해 파지하는
#     시연을 **일부러** 보여줘야 한다.
# ────────────────────────────────────────────────────────────────
set -euo pipefail

MODE="${1:-view}"
WORKSHOP="$HOME/blocktask_ws/Sim-to-Real-SO-101-Workshop"
TASK_ID="Lerobot-So101-Teleop-Vials-To-Rack-Near"
DSNAME="${DSNAME:-sim_so101_blocktask_v4_near}"
TARGET_EP="${TARGET_EP:-65}"

[ -d "$WORKSHOP/source" ] || { echo "❌ $WORKSHOP 없음"; exit 1; }

# Near 태스크가 실제로 등록돼 있는지 확인. 배포 누락으로 무효 수집을 한 전례가 있어
# **씬을 신뢰하지 말고 매번 확인**한다(2026-08-06: 5090이 ref 상태로 굳어 있던 사고).
CFG="$WORKSHOP/source/sim_to_real_so101/tasks/vials_to_rack_env_cfg.py"
grep -q "VialsToRackNearEnvCfg" "$CFG" \
  || { echo "❌ Near 씬 미배포 — vials_to_rack_env_cfg.py에 VialsToRackNearEnvCfg 없음"; exit 2; }
grep -q "$TASK_ID" "$WORKSHOP/source/sim_to_real_so101/tasks/__init__.py" \
  || { echo "❌ Near 태스크 미등록 — tasks/__init__.py 확인"; exit 2; }
grep -q "reset_block_near_box" "$WORKSHOP/source/sim_to_real_so101/mdp/resets.py" \
  || { echo "❌ reset_block_near_box 미배포"; exit 2; }
echo "✅ Near 씬·태스크 확인"

docker_run() { if docker ps >/dev/null 2>&1; then eval "$1"; else sg docker -c "$1"; fi; }

if [ "$MODE" = "clear" ]; then
  echo "삭제: $WORKSHOP/datasets/$DSNAME (기존 에피소드 전부 삭제)"
  docker_run "docker run --rm --entrypoint /bin/bash -v $WORKSHOP/datasets:/d teleop-docker:latest -c 'rm -rf /d/$DSNAME'" 2>&1 | tail -1
  echo "완료"; exit 0
fi

export DISPLAY="${DISPLAY:-:1}"
xhost +local: >/dev/null 2>&1 || true
docker_run "docker rm -f blocktask-near" >/dev/null 2>&1 || true

CALIB=".cache/huggingface/lerobot/calibration"
mkdir -p "$WORKSHOP/outputs" "$WORKSHOP/datasets"

if [ "$MODE" = "record" ]; then
  if [ "${RESUME:-0}" = "1" ]; then
    echo "▶ 이어쓰기(RESUME): datasets/$DSNAME"
  else
    N=1; TRY="$DSNAME"
    while [ -d "$WORKSHOP/datasets/$TRY" ]; do N=$((N+1)); TRY="${DSNAME}_${N}"; done
    DSNAME="$TRY"
    echo "▶ 녹화 대상 폴더(신규): datasets/$DSNAME"
  fi
  # ⚠️ task_name은 컨테이너 env로 받는다 — 문자열에 공백이 있어 여기서 작은따옴표로 직접 넣으면
  # 바깥 bash -c '$INNER'의 따옴표와 중첩되어 "Pick"만 남고 유실된다(2026-08-04 발견).
  INNER="lerobot_agent --task $TASK_ID --num_envs 1 --rerun \
    --port /dev/ttyLEADER --robot_id leader \
    --repo_id heongyu/$DSNAME \
    --repo_root /workspace/Sim-to-Real-SO-101-Workshop/datasets/$DSNAME \
    --task_name \"\$TASK_NAME\""
else
  INNER="zero_agent --task $TASK_ID --num_envs 1"
fi

# 카메라 오프셋: **평가와 반드시 같아야 한다**(학습·평가 불일치 방지).
# blocktask_run.sh는 CAM_*를 0으로 강제해 코드 기본값(0.03/0.02)을 덮어쓴다 — 여기선
# 평가 스크립트(blocktask_gui_cond.sh / headless_scenes.sh)와 동일하게 명시 고정한다.
CAM_X_V="${CAM_X:-0.03}"; CAM_Y_V="${CAM_Y:-0}"; CAM_Z_V="${CAM_Z:-0.02}"

cat <<INFO

  태스크   : $TASK_ID   (블록을 박스에서 0.08~0.18m 거리에 배치)
  데이터셋 : datasets/$DSNAME
  목표     : ${TARGET_EP}ep
  카메라   : CAM_X=$CAM_X_V CAM_Y=$CAM_Y_V CAM_Z=$CAM_Z_V  ← 평가와 동일해야 함

  ┌──────────────────────────────────────────────────────────┐
  │ S : 에피소드 저장     R : 리셋(건너뛰기)                 │
  │                                                          │
  │ R은 **벽에 닿거나 겹친 씬**에만 쓸 것.                   │
  │ "붙어 있어 어렵다"고 건너뛰면 메우려는 구멍이 그대로다.  │
  │ 박스 벽을 피해 비스듬히 접근하는 시연을 일부러 보여줄 것.│
  └──────────────────────────────────────────────────────────┘

INFO

RUN="docker run --name blocktask-near --rm -it --privileged --gpus all \
  -e ACCEPT_EULA=Y -e PRIVACY_CONSENT=Y -e DISPLAY=$DISPLAY --network=host \
  -e CAM_X=$CAM_X_V -e CAM_Y=$CAM_Y_V -e CAM_Z=$CAM_Z_V \
  -e TASK_NAME=\"${TASK_NAME:-Pick up the block and place it in the box}\" \
  -e LEROBOT_RERUN_MEMORY_LIMIT=${LEROBOT_RERUN_MEMORY_LIMIT:-30%} \
  -v /dev:/dev -v /run/udev:/run/udev:ro \
  -v /tmp/.X11-unix:/tmp/.X11-unix -v $HOME/.Xauthority:/root/.Xauthority \
  -v $HOME/docker/isaac-sim/cache/kit:/isaac-sim/kit/cache:rw \
  -v $HOME/docker/isaac-sim/cache/ov:/root/.cache/ov:rw \
  -v $HOME/docker/isaac-sim/cache/glcache:/root/.cache/nvidia/GLCache:rw \
  -v $HOME/docker/isaac-sim/cache/computecache:/root/.nv/ComputeCache:rw \
  -v $HOME/$CALIB:/root/$CALIB \
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
  echo "   다음: 분포 확인 → analyze_dataset_geometry.py 로 거리 분포 검증"
fi
