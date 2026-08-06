#!/usr/bin/env bash
# 9개 조건의 씬 검증용 캡처 (추론 없음) — 조건별 10ep 시작 장면만 저장
set -uo pipefail
W="$HOME/blocktask_ws/Sim-to-Real-SO-101-Workshop"
CFG="$W/source/sim_to_real_so101/tasks/vials_to_rack_env_cfg.py"
N="${1:-10}"
CONDS=(ref pos_ood box_rand box_ood phys_dr light_dr color_blue color_green full)
BAK="$CFG.cap_bak"; cp "$CFG" "$BAK"
cleanup(){ cp "$BAK" "$CFG"; rm -f "$BAK"; docker rm -f blk-cap >/dev/null 2>&1 || true; }
trap cleanup EXIT

T0=$(date +%s)
for c in "${CONDS[@]}"; do
  echo "===== [$c] $(date +%H:%M:%S) ====="
  cp "$BAK" "$CFG"
  python3 "$HOME/configure_scene.py" "$CFG" "$c" || continue
  docker run --rm -v "$W/outputs:/o" --entrypoint bash real-robot-train8 -c "rm -rf /o/cap_$c" >/dev/null 2>&1 || true
  t0=$(date +%s)
  docker run --name blk-cap --rm --privileged --gpus all \
    -e ACCEPT_EULA=Y -e PRIVACY_CONSENT=Y --network host \
    -e CAM_X=0.03 -e CAM_Z=0.02 \
    -v "$W/docker/env:/root/env" \
    -v "$W/source:/workspace/Sim-to-Real-SO-101-Workshop/source" \
    -v "$W/outputs:/workspace/Sim-to-Real-SO-101-Workshop/outputs" \
    -v "$HOME/capture_scene_conditions.py:/tmp/cap.py:ro" \
    teleop-docker:latest \
    bash -c "python /tmp/cap.py --out /workspace/Sim-to-Real-SO-101-Workshop/outputs/cap_$c --episodes $N" \
    > "$HOME/cap_$c.log" 2>&1
  n=$(ls "$W/outputs/cap_$c"/*.png 2>/dev/null | wc -l)
  echo "  → ${n}장 ($(( $(date +%s)-t0 ))초)"
done
echo "총 소요: $(( ($(date +%s)-T0)/60 ))분"
docker run --rm -v "$W/outputs:/o" --entrypoint chmod real-robot-train8 -R a+rw /o >/dev/null 2>&1 || true
echo "=== 캡처 완료 ==="
