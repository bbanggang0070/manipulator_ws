#!/usr/bin/env bash
# coworker 포크(별도 클론 ~/blocktask_ws)의 Task1 블록 씬을 띄운다. 우리 T1(~/Sim-to-Real-SO-101-Workshop)과
# 완전 분리 — 그 소스만 마운트하고 기존 teleop-docker 이미지를 재사용(이미지·우리 작업 불변).
#
# 사용법: ./blocktask_run.sh view      # zero_agent로 씬 육안 확인 (로봇 0액션)
#         ./blocktask_run.sh record    # 리더암 teleop 녹화 (학습 데이터 수집)
#
# 태스크 ID: Lerobot-So101-Teleop-Vials-To-Rack (coworker가 이 등록을 블록 씬으로 덮어씀)
set -euo pipefail

MODE="${1:-view}"
WORKSHOP="$HOME/blocktask_ws/Sim-to-Real-SO-101-Workshop"
[ -d "$WORKSHOP/source" ] || { echo "❌ $WORKSHOP 없음 — 먼저 클론하세요"; exit 1; }

# 데이터셋 이름(=repo 하위). 기본은 새 수집본 v2 → record/clear가 원본(sim_so101_blocktask)을
# 건드리지 않음(원본은 DSNAME=sim_so101_blocktask 로 명시해야만 접근). 다른 데이터셋은 DSNAME 지정.
DSNAME="${DSNAME:-sim_so101_blocktask_v2}"
DATASET_DIR="$WORKSHOP/datasets/$DSNAME"

# clear: 데이터셋 폴더 삭제(root 소유 → 컨테이너로). 재녹화 전 초기화용.
# ⚠️ 기존 녹화 에피소드가 모두 지워집니다. recorder가 resume을 못 해 재시작 시 필요.
if [ "$MODE" = "clear" ]; then
  echo "삭제: $DATASET_DIR (기존 에피소드 전부 삭제됩니다)"
  sg docker -c "docker run --rm --entrypoint /bin/bash -v $WORKSHOP/datasets:/d teleop-docker:latest -c 'rm -rf /d/$DSNAME'" 2>&1 | tail -1
  echo "완료 — 이제 ./blocktask_run.sh record 로 새로 녹화하세요."
  exit 0
fi

export DISPLAY="${DISPLAY:-:1}"
xhost +local: >/dev/null 2>&1 || true
docker_run() { if docker ps >/dev/null 2>&1; then eval "$1"; else sg docker -c "$1"; fi; }
docker_run "docker rm -f blocktask" >/dev/null 2>&1 || true

CALIB=".cache/huggingface/lerobot/calibration"
mkdir -p "$WORKSHOP/outputs" "$WORKSHOP/datasets"

if [ "$MODE" = "record" ]; then
  # 기본: 대상 폴더가 있으면 새 폴더(_2, _3...)로 분리(세션별 → 나중에 병합).
  # RESUME=1: 기존 폴더에 그대로 이어쓰기(recorder._init_existing_dataset). 단일 데이터셋 유지.
  if [ "${RESUME:-0}" = "1" ]; then
    if [ -d "$WORKSHOP/datasets/$DSNAME" ]; then echo "▶ 이어쓰기(RESUME): 기존 datasets/$DSNAME 에 추가"
    else echo "▶ RESUME=1이나 폴더 없음 → 신규 datasets/$DSNAME 생성"; fi
  else
    N=1; TRY="$DSNAME"
    while [ -d "$WORKSHOP/datasets/$TRY" ]; do N=$((N+1)); TRY="${DSNAME}_${N}"; done
    DSNAME="$TRY"
    echo "▶ 녹화 대상 폴더(신규): datasets/$DSNAME"
  fi
  DATASET_DIR="$WORKSHOP/datasets/$DSNAME"
  # 리더암 teleop 녹화 (S=에피소드 저장/중지, R=리셋).
  INNER="lerobot_agent --task Lerobot-So101-Teleop-Vials-To-Rack-DR --num_envs 1 --rerun \
    --port /dev/ttyLEADER --robot_id leader \
    --repo_id heongyu/$DSNAME \
    --repo_root /workspace/Sim-to-Real-SO-101-Workshop/datasets/$DSNAME \
    --task_name 'Pick up the block and place it in the box'"
else
  INNER="zero_agent --task Lerobot-So101-Teleop-Vials-To-Rack --num_envs 1"
fi

echo "모드: $MODE | 워크숍: $WORKSHOP"
echo "종료: Ctrl+C 또는 다른 터미널에서 docker rm -f blocktask"

RUN="docker run --name blocktask --rm -it --privileged --gpus all \
  -e ACCEPT_EULA=Y -e PRIVACY_CONSENT=Y -e DISPLAY=$DISPLAY --network=host \
  -e CAM_X=${CAM_X:-0} -e CAM_Y=${CAM_Y:-0} -e CAM_Z=${CAM_Z:-0} \
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
