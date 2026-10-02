#!/usr/bin/env bash
# 수집 전 환경 점검 — 선반 배치와 리치 확인. 두 모드다.
#
#   cams    팔을 켜지 않고 **카메라만** 띄운다. 선반을 놓고 색지를 붙이며 화각을 맞춘다.
#           모델이 실제로 보는 256×256 축소본을 나란히 띄우므로, 칸 색이 그 해상도에서
#           구별되는지를 눈이 아니라 **모델 시점으로** 판단할 수 있다.
#
#   teleop  리더암으로 팔로워암을 몰아 **4칸에 전부 닿는지** 확인한다.
#           카메라와 관절 상태가 Rerun에 함께 뜬다.
#
# 왜 리치를 먼저 보나:
#   끝 칸이 작업공간 경계에 걸리면 **그 칸만 성공률이 구조적으로 낮아져** 목적지
#   측정을 오염시킨다. 1단계는 1·4번 칸만 쓰므로 그 두 칸이 특히 중요하다.
#   수집 3시간을 쓰고 나서 알면 늦다.
#
# 사용:
#   ./check_setup.sh              # 카메라만 (기본)
#   ./check_setup.sh teleop       # 리더암 연결, 리치 확인
#   EDGE=448 ./check_setup.sh     # 448 해상도로 보고 싶을 때
set -uo pipefail
cd "$(dirname "$0")"

MODE="${1:-cams}"
EDGE="${EDGE:-256}"
LEROBOT="$(cd ../../envs/lerobot && pwd)"

need_dev() {
  for d in "$@"; do
    [ -e "$d" ] || { echo "❌ $d 없음 — 연결/전원을 확인하세요"; exit 1; }
  done
}

case "$MODE" in
  cams)
    need_dev /dev/cam_top /dev/cam_wrist
    echo "▶ 카메라 전용 모드 (팔 전원 불필요) · 모델 입력 ${EDGE}×${EDGE}"
    cd "$LEROBOT" && exec uv run python ../../setup/data/view_cams.py --edge "$EDGE"
    ;;

  teleop)
    need_dev /dev/ttyLEADER /dev/ttyFOLLOWER /dev/cam_top /dev/cam_wrist
    # 어떤 캘리브레이션으로 도는지 눈에 보이게 한다. 안 보이면 재캘리브레이션을
    # 했는지조차 확인할 수 없고, 리치 판단이 옛 캘리브레이션 기준이 될 수 있다.
    echo
    python3 "$(dirname "$0")/calib_fingerprint.py" --banner || exit 1
    cat <<'INFO'

▶ 텔레오프 모드 — 리더암으로 팔로워암을 몹니다.

  ⚠️ 리더암·팔로워암 **전원을 먼저 켜세요.** 전원이 꺼져 있으면
     "Missing motor IDs: 1..6" 로 죽습니다(전례 있음).

  ┌──────────────────────────────────────────────────────────────┐
  │ 확인할 것 — 4칸을 차례로 돌며                                 │
  │                                                              │
  │  1) 칸 바닥까지 그리퍼가 **여유 있게** 내려가는가             │
  │  2) 가는 길에 관절이 한계에 걸리거나 떨리지 않는가            │
  │  3) 1번과 4번(양 끝) 칸이 특히 무리 없는가 ← 1단계가 쓰는 칸  │
  │  4) wrist 화면에 칸 안쪽이 보이는가                           │
  │  5) 물체를 놓을 작업면 전체에 손이 닿는가                     │
  │                                                              │
  │ 한 칸이라도 빠듯하면 **선반을 당기거나 돌려서** 다시 보세요.  │
  │ 수집을 시작한 뒤에는 선반을 못 옮깁니다.                      │
  └──────────────────────────────────────────────────────────────┘

  Ctrl+C 로 종료

INFO
    CAMS='{ top:   {type: opencv, index_or_path: /dev/cam_top,   width: 640, height: 480, fps: 30, fourcc: MJPG},
            wrist: {type: opencv, index_or_path: /dev/cam_wrist, width: 640, height: 480, fps: 30, fourcc: MJPG}}'
    cd "$LEROBOT" && exec uv run lerobot-teleoperate \
      --robot.type=so101_follower --robot.port=/dev/ttyFOLLOWER --robot.id=follower \
      --robot.cameras="$CAMS" \
      --teleop.type=so101_leader --teleop.port=/dev/ttyLEADER --teleop.id=leader \
      --display_data=true --fps=30
    ;;

  *)
    echo "사용법: ./check_setup.sh [cams|teleop]"
    exit 1
    ;;
esac
