#!/usr/bin/env bash
# 프리셋별 씬 캡처 — **로컬 5070 Ti**에서 실행. 추론 없이 리셋만 반복해 시작 장면을 저장한다.
#
# 왜 로컬에서 되나:
#   캡처는 **정책 서버가 필요 없다**(리셋 + 렌더만). GR00T 서버 이미지(real-robot, 61GB)는
#   5090에만 있지만 Isaac Sim 이미지(teleop-docker)는 로컬에도 있으므로,
#   5090이 학습에 묶여 있어도 씬 확인은 로컬에서 계속할 수 있다.
#
# capture_all_conditions.sh(5090판)와의 차이:
#   · 경로를 $HOME 배포본이 아니라 **이 저장소** 기준으로 잡는다
#   · 정리에 real-robot-train8 대신 teleop-docker를 쓴다(로컬에 real-robot* 이미지가 없음)
#   · 프리셋을 인자로 받는다 (기본 = 2026-08-11 추가된 일반화 평가 축 12개)
#
# 사용:
#   ./capture_presets_local.sh                       # 신규 12개, 조건당 6ep
#   ./capture_presets_local.sh 10 obj_sphere dist_two   # ep수 + 프리셋 지정
#
# 출력: ~/blocktask_ws/.../outputs/cap_<프리셋>/*.png  (external_D455 + ego)
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
W="$HOME/blocktask_ws/Sim-to-Real-SO-101-Workshop"
CFG="$W/source/sim_to_real_so101/tasks/vials_to_rack_env_cfg.py"
BASE="$CFG.v3base"
N="${1:-6}"
shift 2>/dev/null || true
CONDS=("$@")
[ ${#CONDS[@]} -eq 0 ] && CONDS=(color_yellow color_white obj_small obj_large obj_sphere \
                                 obj_cylinder obj_tall box_gray box_brown \
                                 dist_blue_cube dist_green_cyl dist_two)

# 불변 기준본에서만 복원한다. 없으면 현재 파일이 깨끗한지 확인 후 만든다.
# (5090에서 조건이 적용된 채 굳어 드리프트가 영구화된 전례가 있다.)
if [ ! -f "$BASE" ]; then
  echo "▶ 기준본이 없어 현재 파일로 만듭니다. 아래 값이 v3 원본인지 확인하세요:"
  grep -E '^BLOCK_REACH_(MIN|MAX)_DIST' "$CFG" | sed 's/^/    /'
  sed -n '/reset_basket_random = EventTerm/,/^    )/p' "$CFG" | grep -oE '"(min_dist|max_dist|yaw_range)":[^,#]*' | sed 's/^/    /'
  echo "    (정상값: min 0.28 / max 0.34 / yaw ±3.14159)"
  read -rp "  기준본으로 저장할까요? [y/N] " a
  [ "$a" = "y" ] || exit 1
  cp "$CFG" "$BASE"; chmod 444 "$BASE"
fi

docker_run() { if docker ps >/dev/null 2>&1; then eval "$1"; else sg docker -c "$1"; fi; }
cleanup() { cp "$BASE" "$CFG"; chmod 644 "$CFG"; docker_run "docker rm -f blk-cap" >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "▶ 프리셋 ${#CONDS[@]}개 × ${N}ep — 로컬 GPU"
T0=$(date +%s)
for c in "${CONDS[@]}"; do
  printf "  %-16s " "$c"
  cp "$BASE" "$CFG"; chmod 644 "$CFG"
  if ! python3 "$HERE/configure_scene.py" "$CFG" "$c" >/dev/null 2>&1; then
    echo "❌ 프리셋 적용 실패"; continue
  fi
  # 생성된 파일이 문법적으로 유효한지 먼저 확인 (Isaac Sim은 실패해도 로그가 길어 찾기 어렵다)
  if ! python3 -c "import ast,sys;ast.parse(open('$CFG').read())" 2>/dev/null; then
    echo "❌ 생성된 cfg 문법 오류"; continue
  fi
  docker_run "docker run --rm -v '$W/outputs:/o' --entrypoint bash teleop-docker:latest -c 'rm -rf /o/cap_$c'" >/dev/null 2>&1 || true
  t0=$(date +%s)
  docker_run "docker run --name blk-cap --rm --privileged --gpus all \
    -e ACCEPT_EULA=Y -e PRIVACY_CONSENT=Y --network host \
    -e CAM_X=0.03 -e CAM_Z=0.02 \
    -v '$W/docker/env:/root/env' \
    -v '$W/source:/workspace/Sim-to-Real-SO-101-Workshop/source' \
    -v '$W/outputs:/workspace/Sim-to-Real-SO-101-Workshop/outputs' \
    -v '$HERE/capture_scene_conditions.py:/tmp/cap.py:ro' \
    teleop-docker:latest \
    bash -c 'python /tmp/cap.py --out /workspace/Sim-to-Real-SO-101-Workshop/outputs/cap_$c --episodes $N'" \
    > "/tmp/cap_$c.log" 2>&1
  n=$(ls "$W/outputs/cap_$c"/*.png 2>/dev/null | wc -l)
  if [ "$n" -gt 0 ]; then echo "✅ ${n}장 ($(( $(date +%s)-t0 ))초)"
  else echo "❌ 캡처 실패 — /tmp/cap_$c.log 확인"; fi
done
echo "▶ 총 $(( ($(date +%s)-T0)/60 ))분 · 출력: $W/outputs/cap_*"
