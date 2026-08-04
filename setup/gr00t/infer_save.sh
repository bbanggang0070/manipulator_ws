#!/usr/bin/env bash
# 조건 라벨을 받아 co-train 모델 추론을 실행하고, 종료(Ctrl+C) 시 정책 시점 영상
# (eval_lerobot.py의 video.mp4 = front|wrist 합성, ~4fps)을 **웹 재생 가능한 H.264**로 변환해
# 리포트 assets(generalization/<라벨>_NN.mp4)에 저장한다.
# (home_then_infer.sh / infer_gr00t_blocktask_remote.sh / eval_lerobot.py 소스는 수정하지 않음 —
#  LOGDIR 환경변수로 영상 저장 위치만 지정하고, 종료 후 변환한다.)
#
# **시행당 1개 파일** 방식: 이 스크립트를 1번 실행 = 1 시행.
#   - 실행 → 홈 정렬 → 추론 시작 → pick&place **1회** → Ctrl+C
#   - 종료 시 <라벨>_NN.mp4 로 저장(NN은 기존 파일을 보고 자동 증가: 01, 02, ...)
#   - 같은 라벨로 다시 실행하면 자동으로 다음 번호에 저장됨 → 10번 반복하면 _01~_10
#
# 사용법(로컬, 로봇 연결 상태에서):
#   cd ~/manipulator_ws/setup/gr00t
#   STEP_DT=0.033 SERVER_HOST=192.168.0.56 ENSEMBLE=1 ENSEMBLE_W=0.3 \
#   LANG_INSTRUCTION="Pick up the red block and place it in the box" ./infer_save.sh color_red
#   → 위 명령을 (큐브 위치 바꿔가며) 10번 반복 = color_red_01.mp4 ... color_red_10.mp4
#
# 인자:  <LABEL>  저장 파일명 접두(확장자·번호 제외). 예: color_red, box_45, obj_toy
# 환경변수: LANG_INSTRUCTION / STEP_DT / SERVER_HOST / ENSEMBLE / ENSEMBLE_W / TOL 등은
#           그대로 home_then_infer.sh → 추론으로 전달.
set -u

GR00T_DIR="$(cd "$(dirname "$0")" && pwd)"
LABEL="${1:?사용법: LANG_INSTRUCTION=\"...\" ./infer_save.sh <LABEL>  (예: color_red)}"
ASSETS="$GR00T_DIR/../../model_markdown/sim2real/08_T1_sim2real/assets/generalization"
mkdir -p "$ASSETS"

# 다음 시행 번호 자동 계산 (<LABEL>_01.mp4, _02.mp4 ... 중 비어있는 첫 번호)
n=1
while [ -f "$(printf '%s/%s_%02d.mp4' "$ASSETS" "$LABEL" "$n")" ]; do n=$((n + 1)); done
IDX="$(printf '%02d' "$n")"
DST="$ASSETS/${LABEL}_${IDX}.mp4"
RUNDIR="$ASSETS/_raw/${LABEL}_${IDX}_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RUNDIR"

echo "=============================================================="
echo "[save] 라벨=$LABEL   ▶ 이번 시행 번호: #$IDX"
echo "[save] 지시문=${LANG_INSTRUCTION:-<기본: Pick up the block...>}"
echo "[save] ⚠️ pick&place **1회**만 하고 Ctrl+C 를 누르세요."
echo "[save] 저장 위치 → $DST (H.264)"
echo "=============================================================="
echo

# Ctrl+C 는 추론(자식)까지 종료시키고, 그 뒤 아래 변환 단계로 넘어가게 한다.
trap 'echo; echo "[save] 종료 감지 — 영상 변환 중..."' INT

# LOGDIR 만 지정해 원본 video.mp4 위치를 고정. 나머지 env 는 그대로 전달.
LOGDIR="$RUNDIR" "$GR00T_DIR/home_then_infer.sh" || true

SRC="$RUNDIR/video.mp4"
if [ -f "$SRC" ]; then
  if ffmpeg -y -loglevel error -i "$SRC" -c:v libx264 -pix_fmt yuv420p -movflags +faststart "$DST"; then
    echo "[save] ✅ 저장 완료: $DST"
  else
    echo "[save] ⚠️ H.264 변환 실패 — 원본(mp4v) 복사로 대체"
    cp "$SRC" "$DST"
  fi
  echo "[save]    (원본 mp4v·csv 로그는 $RUNDIR 에 보존)"
  next=$((n + 1))
  echo "[save] ▶ 다음 시행: 같은 명령을 그대로 다시 실행하면 #$(printf '%02d' "$next") 로 저장됩니다."
else
  echo "[save] ⚠️ video.mp4 가 없음 ($SRC) — 저장할 영상 없음(추론이 프레임을 못 남겼을 수 있음)."
  rmdir "$RUNDIR" 2>/dev/null || true
  exit 1
fi
