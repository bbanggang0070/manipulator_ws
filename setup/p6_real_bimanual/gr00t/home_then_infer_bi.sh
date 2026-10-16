#!/usr/bin/env bash
# goto_home_bi.py 를 **원본(단일팔 home_then_infer.sh)과 같은 방식**으로 반복 실행하고,
# 오차 <= TOL 에 도달하면 바로 infer_gr00t_bi_local.sh 로 추론을 시작한다.
#
# 사용법(로컬, 양팔 로봇 연결 상태에서):
#   cd ~/manipulator_ws/setup/p6_real_bimanual/gr00t
#   SERVER_HOST=127.0.0.1 ./home_then_infer_bi.sh   (ENSEMBLE_W 기본 0.8)
#
# ⚠️ 반복마다 양팔이 홈 자세로 이동한다. 첫 실행은 e-stop(Ctrl+C)에 손 두고 지켜볼 것.
set -u

GR00T_DIR="$(cd "$(dirname "$0")" && pwd)"
LEROBOT_DIR="$GR00T_DIR/../../../envs/lerobot"
# 양팔(12관절)은 단일팔(6관절)보다 모든 관절이 동시에 TOL 안에 들기 어려워 기본값을 3.0으로 올렸다
# (단일팔 home_then_infer.sh 의 "완화 시 TOL=3.0" 권장치와 동일한 값을 기본으로 채택).
TOL="${TOL:-3.0}"
MAX_TRIES="${MAX_TRIES:-20}"

i=0
while : ; do
  i=$((i + 1))
  echo "[home] 시도 $i/$MAX_TRIES  (목표: 최대 오차 <= ${TOL}°)"

  # out="$( ... 2>&1 )" 는 프로세스가 끝나야 출력이 보인다 — calibrate() 의 input() 프롬프트가
  # 안 보이는 채로 멈춰 있어도 "로그 없음"처럼 보이는 문제가 있었다. tee 로 실시간으로 뿌리면서
  # 동시에 파싱용으로도 캡처한다. PYTHONUNBUFFERED=1 로 파이프를 통과해도 즉시 flush 되게 한다.
  tmp_out="$(mktemp)"
  ( cd "$LEROBOT_DIR" && PYTHONUNBUFFERED=1 uv run python "$GR00T_DIR/goto_home_bi.py" ) 2>&1 | tee "$tmp_out"
  out="$(cat "$tmp_out")"
  rm -f "$tmp_out"

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
    exit 1
  fi
  sleep 1
done

exec "$GR00T_DIR/infer_gr00t_bi_local.sh"
