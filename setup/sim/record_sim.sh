#!/usr/bin/env bash
# Isaac Sim 시연 데이터 수집 (리더암 teleop → LeRobot 포맷)
#
# 사용법: ./setup/sim/record_sim.sh              # DR 태스크(본 수집용)
#         ./setup/sim/record_sim.sh nodr         # DR 없음(디버그용)
#         ./setup/sim/record_sim.sh dr zero      # 녹화 없이 동작만 확인(zero_agent)
#
# 조작: S = 녹화 시작/중지(에피소드 1개 저장) / R = 월드 리셋(녹화도 중지)
# 종료: Ctrl+C
#
# ⚠️ 수집 규칙 (model_md/sim2real/05_SimToReal.md §0.1.1):
#   - 성공으로 끝나는 에피소드만 저장, 녹화 시작 즉시 동작 개시(idle 금지)
#   - **정상 ~70% / 교정(recovery) ~30%**: 교정 시연은 **사람이 리더암으로 직접** 만든다 —
#     녹화 중 팔을 일부러 목표에서 어긋나게 움직인 뒤 되돌아와 정렬·파지·배치까지 성공 종결.
#     (⚠️ 시작 자세 자동 무작위화(옵션 B)는 teleop이 절대 위치 추종이라 불가능 — 리셋 오프셋이
#      첫 스텝에 리더암 자세로 덮어써짐. 2026-07-21 확인. 교정은 반드시 사람이 수동 생성)
#     근거: 실기 GR00T 실패의 근본 원인이 교정 시연 부재였음 — report/GR00T_report.md §3.2
#   - 예: 50ep 목표면 정상 35ep + 교정 15ep(같은 명령, 사람이 수동으로 어긋냄→복구)
#
# ⚠️ 함정 기록 (setup/sim/README.md):
#   - docker/env·source 마운트 누락 시 컨테이너가 아무 출력 없이 exit 1
#   - 컨테이너 lerobot은 calibration을 so101_leader/ 에서 찾음(실기는 so_leader/)
set -euo pipefail

cd "$(dirname "$0")/../.."
WS="$(pwd)"
WORKSHOP="$HOME/Sim-to-Real-SO-101-Workshop"
cd "$WORKSHOP"

TASK="Lerobot-So101-Teleop-Vials-To-Rack-DR"
[ "${1:-}" = "nodr" ] && TASK="Lerobot-So101-Teleop-Vials-To-Rack"

# GUI 필수 — teleop은 화면을 보며 조작해야 함
export DISPLAY="${DISPLAY:-:1}"
if ! xhost >/dev/null 2>&1; then
  echo "❌ DISPLAY=$DISPLAY 로 X 서버에 접근할 수 없습니다."
  echo "   GUI 세션 터미널에서 실행하거나 DISPLAY를 올바르게 지정하세요 (예: DISPLAY=:1 $0)"
  exit 1
fi
xhost +local: >/dev/null

# 이전 크래시로 남은 컨테이너 정리 (--rm이어도 비정상 종료 시 잔존)
sg docker -c "docker rm -f teleop" >/dev/null 2>&1 || true

mkdir -p "$WS/logs" "$WORKSHOP/outputs" "$WORKSHOP/datasets"
LOG="$WS/logs/sim_record_$(date +%Y%m%d_%H%M%S).log"
CALIB=".cache/huggingface/lerobot/calibration"

if [ "${2:-}" = "zero" ]; then
  INNER="zero_agent --task $TASK --num_envs 1"
else
  INNER="lerobot_agent --task $TASK --num_envs 1 \
    --port /dev/ttyLEADER --robot_id leader \
    --repo_id heongyu/sim_so101_vials \
    --repo_root /workspace/Sim-to-Real-SO-101-Workshop/datasets/sim_so101_vials \
    --task_name 'Pick up the vial and place it in the yellow rack'"
fi

echo "태스크: $TASK"
echo "로그:   $LOG"
echo

exec sg docker -c "docker run --name teleop --rm -it --privileged --gpus all \
  -e ACCEPT_EULA=Y -e PRIVACY_CONSENT=Y -e DISPLAY=$DISPLAY --network=host \
  -v /dev:/dev -v /run/udev:/run/udev:ro \
  -v $HOME/.Xauthority:/root/.Xauthority \
  -v /tmp/.X11-unix:/tmp/.X11-unix \
  -v $HOME/docker/isaac-sim/cache/kit:/isaac-sim/kit/cache:rw \
  -v $HOME/docker/isaac-sim/cache/ov:/root/.cache/ov:rw \
  -v $HOME/docker/isaac-sim/cache/pip:/root/.cache/pip:rw \
  -v $HOME/docker/isaac-sim/cache/glcache:/root/.cache/nvidia/GLCache:rw \
  -v $HOME/docker/isaac-sim/cache/computecache:/root/.nv/ComputeCache:rw \
  -v $HOME/docker/isaac-sim/logs:/root/.nvidia-omniverse/logs:rw \
  -v $HOME/docker/isaac-sim/data:/root/.local/share/ov/data:rw \
  -v $HOME/docker/isaac-sim/documents:/root/Documents:rw \
  -v $HOME/$CALIB:/root/$CALIB \
  -v $WORKSHOP/docker/env:/root/env \
  -v $WORKSHOP/source:/workspace/Sim-to-Real-SO-101-Workshop/source \
  -v $WORKSHOP/outputs:/workspace/Sim-to-Real-SO-101-Workshop/outputs \
  -v $WORKSHOP/datasets:/workspace/Sim-to-Real-SO-101-Workshop/datasets \
  teleop-docker:latest bash -c \"$INNER\" 2>&1 | tee '$LOG'"
