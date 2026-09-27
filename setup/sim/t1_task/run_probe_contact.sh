#!/usr/bin/env bash
# probe_object_contact.py를 언어 씬(full+lang)에 적용해 컨테이너 안에서 돌린다.
#
# blocktask_collect_lang.sh와 같은 씬 설정·복원 절차를 쓴다 — 기준본에서 출발해
# 프리셋을 입히고, 끝나면 되돌린다. 그래야 다음 수집이 오염되지 않는다.
set -uo pipefail
cd "$(dirname "$0")"

WORKSHOP="$HOME/blocktask_ws/Sim-to-Real-SO-101-Workshop"
TASK_ID="Lerobot-So101-Teleop-Vials-To-Rack-DR"
CFG="$WORKSHOP/source/sim_to_real_so101/tasks/vials_to_rack_env_cfg.py"
BASE="$CFG.v3base"
PRESET="${PRESET:-full+lang}"
PLAN="${PLAN:-$(cd ../../../manipulator_md/sim && pwd)/lang_collect_plan.csv}"

[ -f "$BASE" ] || { echo "❌ 기준본 없음: $BASE"; exit 1; }
docker_run() { if docker ps >/dev/null 2>&1; then eval "$1"; else sg docker -c "$1"; fi; }

cleanup() { cp "$BASE" "$CFG"; chmod 644 "$CFG"; echo "[정리] 씬 기준본 복원"; }
trap cleanup EXIT
cp "$BASE" "$CFG"; chmod 644 "$CFG"
python3 ./configure_scene.py "$CFG" "$PRESET" || exit 1

docker_run "docker rm -f blocktask-probe" >/dev/null 2>&1 || true
docker_run "docker run --name blocktask-probe --rm --privileged --gpus all \
  -e ACCEPT_EULA=Y -e PRIVACY_CONSENT=Y --network=host \
  -e LANG_PLAN=/workspace/lang_collect_plan.csv \
  -v $PLAN:/workspace/lang_collect_plan.csv:ro \
  -v $HOME/docker/isaac-sim/cache/kit:/isaac-sim/kit/cache:rw \
  -v $HOME/docker/isaac-sim/cache/ov:/root/.cache/ov:rw \
  -v $HOME/docker/isaac-sim/cache/glcache:/root/.cache/nvidia/GLCache:rw \
  -v $HOME/docker/isaac-sim/cache/computecache:/root/.nv/ComputeCache:rw \
  -v $WORKSHOP/docker/env:/root/env \
  -v $WORKSHOP/source:/workspace/Sim-to-Real-SO-101-Workshop/source \
  -v $PWD/probe_object_contact.py:/workspace/probe_object_contact.py:ro \
  teleop-docker:latest bash -c 'cd /workspace && python probe_object_contact.py --task $TASK_ID'"
