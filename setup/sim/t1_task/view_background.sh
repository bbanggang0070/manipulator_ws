#!/usr/bin/env bash
# 배경(주변 환경) 후보를 **Isaac Sim 창으로 띄워** 직접 둘러본다. 로컬 5070 Ti에서 실행.
#
# 왜 필요한가(2026-08-12):
#   학습 씬은 흰 라이트박스가 사방을 감싸 배경 픽셀이 거의 균일하다. 실제 책상처럼 주변이
#   복잡해질 때 정책이 무너지는지 보려면 배경만 바꿔야 하는데, **어떤 방(map)이 우리 씬
#   스케일과 맞는지**는 숫자로 고를 수 없다. 눈으로 보고 정하는 단계다.
#
# ⚠️ 라이트박스를 통째로 지우면 안 된다: top 카메라와 RectLight가 그 안에 매달려 있어
#   (`LightStudio/LightBox/camera_mount/...`) 지우면 시점·조명이 함께 바뀐다.
#   `--hide`로 **벽 지오메트리만** 숨긴다.
#
# 최초 1회: xhost +local:root
#
# 사용:
#   ./view_background.sh dump                 # 구조 확인 — 무엇을 숨길지 이름을 본다
#   ./view_background.sh room                 # Simple_Room 얹어서 창 띄우기
#   ./view_background.sh office
#   ./view_background.sh warehouse
#   ./view_background.sh none                 # 배경 교체 없이 현재 씬만
#   HIDE="Wall,Floor" ./view_background.sh room     # 숨길 prim 조각 바꾸기
#   SHOT=1 ./view_background.sh room          # 창 대신 캡처만 (headless)
set -uo pipefail

W="$HOME/blocktask_ws/Sim-to-Real-SO-101-Workshop"
HERE="$(cd "$(dirname "$0")" && pwd)"
CFG="$W/source/sim_to_real_so101/tasks/vials_to_rack_env_cfg.py"
BASE="$CFG.v3base"
A="https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/5.0/Isaac/Environments"
T="https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/5.0/Isaac/Materials/Textures/Patterns"

MAP="${1:-room}"
case "$MAP" in
  room)      BG="$A/Simple_Room/simple_room.usd";        SCALE="${SCALE:-1.0}" ;;
  office)    BG="$A/Office/office.usd";                  SCALE="${SCALE:-1.0}" ;;
  warehouse) BG="$A/Simple_Warehouse/warehouse.usd";     SCALE="${SCALE:-1.0}" ;;
  hospital)  BG="$A/Hospital/hospital.usd";              SCALE="${SCALE:-1.0}" ;;
  none|dump) BG="";                                      SCALE="1.0" ;;
  wood)      BG="";  TEX="$T/nv_wooden_wall.jpg";        SCALE="1.0" ;;
  wood2)     BG="";  TEX="$T/nv_wood_siding_weathered_green.jpg"; SCALE="1.0" ;;
  gray)      BG="";  COLOR="0.35,0.35,0.35";               SCALE="1.0" ;;
  *)         BG="$MAP";                                  SCALE="${SCALE:-1.0}" ;;   # 임의 USD 경로/URL
esac
TEX="${TEX:-${SURFACE_TEX:-}}"
COLOR="${COLOR:-${SURFACE_COLOR:-}}"
# 임의 URL을 MAP으로 받으면 출력 경로에 슬래시가 섞여 디렉터리가 깨진다 — 파일명만 딴다
SAFE="$(basename "$MAP" .usd | tr -cd 'A-Za-z0-9_.-')"

# 라이트박스 벽만 숨긴다. dump로 확인한 실제 메시는 5개: Top / Right / Left / Back / Base.
#   **Base는 기본으로 남긴다** — 블록·박스가 놓이는 작업면(z≈0.026)이라, 숨기면 물체가
#   방 바닥 위에 떠 있는 것처럼 보인다. 실제 책상 느낌은 벽 4면만 걷어내도 충분하다.
#   Base까지 지우려면 방 USD의 책상 높이에 맞춰 --bg-pos 로 내려야 한다.
HIDE="${HIDE:-Top,Right,Left,Back}"
[ "$MAP" = "none" ] && HIDE=""
EXTRA=""
[ "$MAP" = "dump" ] && EXTRA="--dump-prims"

OUT="$W/outputs/bg_${SAFE}"
docker_run() { if docker ps >/dev/null 2>&1; then eval "$1"; else sg docker -c "$1"; fi; }

# Ctrl+C로 확실히 끝나게 한다.
#   `docker run`은 -it 없이 돌면 SIGINT가 컨테이너로 전달되지 않는다. Ctrl+C는 도커
#   클라이언트만 끊고 **Isaac Sim 창은 그대로 남는다**(실측 2026-08-12: 13분·16분짜리
#   컨테이너 2개가 살아 있었다). 이름을 붙이고 트랩에서 직접 지운다.
CNAME="blk-bgview"
cleanup() { docker_run "docker rm -f $CNAME" >/dev/null 2>&1 || true; }
trap 'cleanup; exit 130' INT TERM
trap cleanup EXIT
cleanup   # 이전 실행이 남아 있으면 먼저 치운다

# 항상 기준본에서 출발 — 이전 실행의 프리셋이 남아 섞이지 않게 한다
[ -f "$BASE" ] && { cp "$BASE" "$CFG"; chmod 644 "$CFG"; }

if [ -n "${SHOT:-}" ] || [ "$MAP" = "dump" ]; then
  MODE="--episodes ${EPISODES:-3}"
  GUI=""
  DISP=""
  IT=""
else
  MODE="--episodes 1"
  GUI="--gui"
  DISP="-e DISPLAY=${DISPLAY:-:1} -v /tmp/.X11-unix:/tmp/.X11-unix"
  # -it 를 쓰지 않는다: TTY 없는 환경(백그라운드 실행)에서 "input device is not a TTY"로 죽는다.
  # Isaac Sim GUI는 stdin이 필요 없다 — 창을 닫으면 종료된다.
  IT=""
fi

echo "▶ 배경: ${BG:-<교체 없음>}"
echo "  작업면: ${TEX:-${COLOR:-<변경 없음>}}"
echo "  숨김: ${HIDE:-<없음>}   스케일: $SCALE   ${GUI:+창 모드}${GUI:-캡처 모드 → $OUT}"
echo

docker_run "docker run --rm --name $CNAME $IT --privileged --gpus all \
  -e ACCEPT_EULA=Y -e PRIVACY_CONSENT=Y --network host $DISP \
  -e CAM_X=0.03 -e CAM_Z=0.02 \
  -v '$W/docker/env:/root/env' \
  -v '$W/source:/workspace/Sim-to-Real-SO-101-Workshop/source' \
  -v '$W/outputs:/workspace/Sim-to-Real-SO-101-Workshop/outputs' \
  -v '$HERE/capture_background.py:/tmp/bg.py:ro' \
  teleop-docker:latest \
  bash -c 'python /tmp/bg.py --out /workspace/Sim-to-Real-SO-101-Workshop/outputs/bg_${SAFE} \
     $MODE $GUI $EXTRA --bg-scale $SCALE \
     ${BG:+--bg \"$BG\"} ${HIDE:+--hide \"$HIDE\"} \
     ${TEX:+--surface-tex \"$TEX\"} ${COLOR:+--surface-color \"$COLOR\"} --surface-uv ${UV:-4}'"

echo
[ -d "$OUT" ] && echo "▶ 캡처 $(ls "$OUT"/*.png 2>/dev/null | wc -l)장 · $OUT"
