#!/usr/bin/env bash
# goto_home_sim.py 를 **원본 그대로** 반복 실행하고, 출력의 "최대 오차 X.X°" 값을 읽어
# **오차 <= TOL(기본 1.0°)** 이 될 때까지 홈을 반복한 뒤, 도달 즉시 추론을 자동 시작한다.
# (goto_home_sim.py / infer_gr00t_blocktask_remote.sh 소스는 전혀 수정하지 않음)
#
# 사용법(로컬, 로봇 연결 상태에서):
#   cd ~/manipulator_ws/setup/gr00t
#   STEP_DT=0.033 SERVER_HOST=192.168.0.56 ENSEMBLE=1 ENSEMBLE_W=0.3 ./home_then_infer.sh
#
# 환경변수:
#   TOL        홈 도달 허용 오차(°). 기본 1.0.
#   MAX_TRIES  홈 재시도 최대 횟수. 기본 20. 초과 시 추론 안 하고 중단.
#   그 외 STEP_DT/SERVER_HOST/ENSEMBLE/ENSEMBLE_W/MRT/HORIZON 등은 그대로 추론 스크립트로 전달.
#
# ⚠️ 반복마다 팔이 홈 자세로 이동한다. 첫 실행은 e-stop(Ctrl+C)에 손 두고 지켜볼 것.
set -u

GR00T_DIR="$(cd "$(dirname "$0")" && pwd)"
LEROBOT_DIR="$GR00T_DIR/../../envs/lerobot"
TOL="${TOL:-1.0}"
MAX_TRIES="${MAX_TRIES:-20}"

i=0
while : ; do
  i=$((i + 1))
  echo "[home] 시도 $i/$MAX_TRIES  (목표: 최대 오차 <= ${TOL}°)"

  # 원본 goto_home_sim.py 실행 (출력은 화면에도 보여주고 변수로도 캡처)
  out="$( cd "$LEROBOT_DIR" && uv run python "$GR00T_DIR/goto_home_sim.py" 2>&1 )"
  echo "$out"

  # "최대 오차 X.X°" 에서 숫자만 추출
  worst="$( printf '%s\n' "$out" | grep -oP '최대 오차 \K[0-9]+(\.[0-9]+)?' | tail -1 )"

  if [ -z "$worst" ]; then
    echo "[home] 오차값을 못 읽음(홈 이동 실패로 추정) — 재시도..."
  elif awk "BEGIN{exit !($worst <= $TOL)}"; then
    echo "[home] ✅ 오차 ${worst}° <= ${TOL}° 도달 → 추론 시작"
    break
  else
    echo "[home] 오차 ${worst}° > ${TOL}° — 재시도..."
  fi

  if [ "$i" -ge "$MAX_TRIES" ]; then
    echo "[home] ❌ ${MAX_TRIES}회 시도했지만 <= ${TOL}° 미달 — 추론 실행 안 함." >&2
    echo "       (허용치를 완화하려면 TOL 값을 올려서 재실행: TOL=1.5 ./home_then_infer.sh)" >&2
    exit 1
  fi
  sleep 1
done

# 홈 도달 성공 → 현재 환경변수(SERVER_HOST/STEP_DT/ENSEMBLE/...) 그대로 이어받아 추론 실행
exec "$GR00T_DIR/infer_gr00t_blocktask_remote.sh"
