#!/usr/bin/env bash
# 임의의 등록된 Isaac Lab 태스크를 zero_agent로 띄워 육안 확인 (GUI 머신에서 실행).
# 사용법: ./zero_view.sh <TASK_ID>
#   예) ./zero_view.sh Lerobot-So101-Teleop-Vials-To-Rack        # 바이알→랙 (sreetz 데이터셋 환경)
#       ./zero_view.sh Lerobot-So101-Teleop-Vials-To-Rack-DR
#       ./zero_view.sh Lerobot-So101-T1-CubeBox                   # 우리 커스텀 T1
set -euo pipefail

TASK="${1:?사용법: ./zero_view.sh <TASK_ID>  (예: Lerobot-So101-Teleop-Vials-To-Rack)}"
WORKSHOP="$HOME/Sim-to-Real-SO-101-Workshop"
export DISPLAY="${DISPLAY:-:1}"
xhost +local: >/dev/null 2>&1 || true

# docker 그룹이 세션에 없을 수 있어 sg docker 폴백
docker_run() { if docker ps >/dev/null 2>&1; then eval "$1"; else sg docker -c "$1"; fi; }
docker_run "docker rm -f zeroview" >/dev/null 2>&1 || true

echo "태스크: $TASK  (DISPLAY=$DISPLAY) — 종료: Ctrl+C 또는 다른 터미널에서 docker rm -f zeroview"

INNER="zero_agent --task $TASK --num_envs 1"
RUN="docker run --name zeroview --rm -it --privileged --gpus all \
  -e ACCEPT_EULA=Y -e PRIVACY_CONSENT=Y -e DISPLAY=$DISPLAY --network=host \
  -v /tmp/.X11-unix:/tmp/.X11-unix \
  -v $HOME/.Xauthority:/root/.Xauthority \
  -v $HOME/docker/isaac-sim/cache/kit:/isaac-sim/kit/cache:rw \
  -v $HOME/docker/isaac-sim/cache/ov:/root/.cache/ov:rw \
  -v $HOME/docker/isaac-sim/cache/glcache:/root/.cache/nvidia/GLCache:rw \
  -v $HOME/docker/isaac-sim/cache/computecache:/root/.nv/ComputeCache:rw \
  -v $WORKSHOP/docker/env:/root/env \
  -v $WORKSHOP/source:/workspace/Sim-to-Real-SO-101-Workshop/source \
  teleop-docker:latest bash -c '$INNER'"

docker_run "$RUN"
