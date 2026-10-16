#!/usr/bin/env bash
# 양팔(bi-manipulator) 파일럿 수집 — setup/p5_real_cleanup/record_real_lang.sh 의 bi 판.
#
# 과제: 오른팔이 지시한 물체를 집어 **그리퍼 대 그리퍼로 왼팔에 직접 전달**하고,
# 왼팔이 지시한 색 칸(4칸)에 넣는다. 문장 하나가 양팔을 동시에 조건화한다
# (bi_manipulator_plan.md §2). 단일팔과 다른 점은 이 전달 구간뿐이므로,
# 시연 규칙도 거기 하나만 추가한다 — 나머지(물체 10종·4칸·대응쌍 유지,
# push_to_hub=false 필수 이유 등)는 setup/p5_real_cleanup/record_real_lang.sh 와 같다.
#
# 시연 규칙(전달 구간, 추가분):
#   · 오른팔은 왼팔 그리퍼가 **확실히 물체를 닫은 뒤에** 놓는다. 서두르면
#     "놓쳤다 다시 집는" 장면이 데이터에 섞인다(기존 재파지 문제와 같은 종류,
#     이번엔 전달 단계에서 — bi_manipulator_plan.md §3-2).
#   · 왼팔이 칸에 넣은 뒤 **양팔 다** rest로 복귀해 1~2초 멈춘 뒤 종료한다.
#     한쪽만 멈추고 한쪽이 계속 움직이면 모델이 "언제 다 끝났는지"를 배우지 못한다.
#
# 사용:
#   ./record_bi.sh              # 처음이면 1행부터, 중단 후 재실행이면 이어서
#   START=11 ./record_bi.sh     # 11행부터
#   EP_TIME=120 ./record_bi.sh  # 에피소드 시간 늘리기(기본 90s — 전달 포함 추정치)
set -uo pipefail
cd "$(dirname "$0")"
HERE="$(pwd)"
DATA="$(cd ../../p5_real_cleanup && pwd)"   # calib_fingerprint.py 는 setup/p5_real_cleanup 에 있다(공용)

PLAN="${PLAN:-$HOME/manipulator_ws/manipulator_md/p6_real_bimanual/bi_cleanup_plan.csv}"
DSNAME="${DSNAME:-bi_cleanup}"
REPO="heongyu/$DSNAME"
ROOT="${ROOT:-$HOME/blocktask_ws/Sim-to-Real-SO-101-Workshop/datasets/_train/$DSNAME}"
START="${START:-}"
END="${END:-0}"
EP_TIME="${EP_TIME:-90}"   # 단일팔 60s + 전달 단계 추정 — 파일럿 실측 후 조정
LEROBOT="$(cd ../../../envs/lerobot && pwd)"

if [ ! -f "$PLAN" ]; then
  echo "❌ 계획표 파일이 없습니다: $PLAN"
  echo "   먼저 생성하세요: python3 gen_bi_plan.py --episodes 50"
  exit 1
fi
for d in /dev/ttyLEADER_L /dev/ttyLEADER_R /dev/ttyFOLLOWER_L /dev/ttyFOLLOWER_R \
         /dev/cam_top /dev/cam_wrist /dev/cam_wrist_right; do
  [ -e "$d" ] || { echo "❌ $d 없음 — 하드웨어 연결을 확인하세요"; exit 1; }
done

CAMS_L='{ top:   {type: opencv, index_or_path: /dev/cam_top,         width: 640, height: 480, fps: 30, fourcc: MJPG},
          wrist: {type: opencv, index_or_path: /dev/cam_wrist,       width: 640, height: 480, fps: 30, fourcc: MJPG}}'
CAMS_R='{ wrist: {type: opencv, index_or_path: /dev/cam_wrist_right, width: 640, height: 480, fps: 30, fourcc: MJPG}}'

TOTAL=$(( $(wc -l < "$PLAN") - 1 ))
[ "$END" = "0" ] && END=$TOTAL
DONE=0
[ -d "$ROOT/meta" ] && DONE=$(python3 -c "import json;print(json.load(open('$ROOT/meta/info.json'))['total_episodes'])" 2>/dev/null || echo 0)

mkdir -p "$(dirname "$ROOT")"

PROGRESS="$ROOT/collect_progress.txt"
if [ -z "$START" ]; then
  if [ -s "$PROGRESS" ]; then
    LAST=$(tail -1 "$PROGRESS" | cut -d, -f1)
    START=$((LAST + 1))
    echo "▶ 진행 기록 발견 — 계획표 ${LAST}행까지 저장됨. **${START}행부터 재개**합니다."
  else
    START=1
  fi
fi

if [ -d "$ROOT" ] && [ "$DONE" -eq 0 ]; then
  NFILE=$(find "$ROOT" -type f ! -name "info.json" ! -name "calibration_snapshot.json" 2>/dev/null | wc -l)
  echo
  echo "⚠️  데이터셋 폴더가 이미 있는데 에피소드가 0개입니다: $ROOT"
  if [ "$NFILE" -gt 0 ]; then
    echo "❌ 데이터 파일이 있습니다. 자동으로 지우지 않습니다 — 직접 확인하세요."
    exit 1
  fi
  read -r -p "    지우고 새로 시작할까요? (y/N): " YN </dev/tty
  case "$YN" in
    y|Y) rm -rf "$ROOT" && echo "    지웠습니다." ;;
    *)   echo "    그대로 둡니다."; exit 1 ;;
  esac
fi

if ! python3 "$DATA/calib_fingerprint.py" --check "$ROOT"; then
  echo "❌ 캘리브레이션이 바뀌었습니다. 위 안내를 보고 정리한 뒤 다시 실행하세요."
  exit 1
fi
echo
python3 "$DATA/calib_fingerprint.py" --banner-bi || exit 1

cat <<INFO

  계획표   : $PLAN  (${TOTAL}행)
  데이터셋 : $ROOT
  이미 저장: ${DONE}ep
  진행 구간: ${START} ~ ${END}행

  ┌────────────────────────────────────────────────────────────┐
  │ 매 에피소드: 터미널에 뜬 물체만 놓고 → Enter → 시연         │
  │ 오른팔이 집어 왼팔에 직접 전달(그리퍼 대 그리퍼) → 왼팔이  │
  │ 지시한 칸에 배치                                             │
  │ 빨간 띠(KEEP)가 뜨면 물체를 건드리지 마세요 — 대응쌍입니다  │
  │ 왼팔 그리퍼가 확실히 닫힌 뒤에 오른팔이 놓을 것             │
  │ 배치 후 **양팔 다** rest 복귀 — 한쪽만 멈추면 안 됨         │
  └────────────────────────────────────────────────────────────┘

INFO

python3 - "$PLAN" "$START" "$END" <<'PY' > /tmp/bi_rows.txt
import csv, sys
plan, s, e = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
need = ["ep", "group_kind", "group_pos", "keep_layout", "n_objects",
        "objects", "target", "slot", "slot_color", "pose_hint", "instruction"]
rows = list(csv.DictReader(open(plan)))
missing = [c for c in need if rows and c not in rows[0]]
if missing:
    sys.exit("계획표에 없는 열: %s — gen_bi_plan.py 로 다시 생성하세요" % missing)
for r in rows:
    if s <= int(r["ep"]) <= e:
        print("\t".join([(r[c] or "-") for c in need] + [r.get("layout") or "-"]))
PY

N=0
PREV_LAYOUT=""
while IFS=$'\t' read -r EP KIND POS KEEP NOBJ OBJS TGT SLOT SCOL PHINT INSTR LAYOUT; do
  N=$((N+1))
  echo
  # 칸 배치(색↔위치)가 바뀌는 행 — 세션 첫 행에서도 띄워 현재 배치를 확인시킨다.
  # 색이 아니라 위치를 외우는 것을 막으려고 50ep마다 바꾼다(gen_bi_plan.py --layout-every).
  if [ "$LAYOUT" != "-" ] && [ "$LAYOUT" != "$PREV_LAYOUT" ]; then
    echo "################################################################"
    if [ -z "$PREV_LAYOUT" ]; then
      printf "  \033[1;33m▶ 현재 칸 배치를 확인하세요\033[0m\n"
    else
      printf "  \033[1;41m  ▶▶▶ 칸(bin) 배치를 바꾸세요 ◀◀◀  \033[0m\n"
    fi
    printf "  \033[1m%s\033[0m\n" "$LAYOUT"
    echo "################################################################"
    read -r -p "  칸 배치가 위와 같으면 Enter (q=종료): " _L </dev/tty
    case "$_L" in q|Q) echo "  종료합니다."; break ;; esac
    PREV_LAYOUT="$LAYOUT"
  fi
  if [ "$KEEP" = "KEEP" ]; then
    printf "\033[1;41m%s\033[0m\n" "  ████ 물체를 건드리지 마세요 — 배치 그대로, 지시문만 바뀝니다 ████  "
  fi
  echo "════════════════════════════════════════════════════════════════"
  printf "  계획표 %s/%s행   [%s %s]   (저장된 에피소드 %s개)\n" "$EP" "$TOTAL" "$KIND" "$POS" "$DONE"
  echo "────────────────────────────────────────────────────────────────"
  if [ "$KEEP" = "KEEP" ]; then
    printf "  놓을 물체        :  \033[2m%s  (그대로 두세요)\033[0m\n" "$OBJS"
  else
    printf "  놓을 물체 (%s개) :  \033[1m%s\033[0m\n" "$NOBJ" "$OBJS"
  fi
  printf "  오른팔이 집을 것 :  \033[1;33m%s\033[0m\n" "$TGT"
  if [ "$PHINT" != "-" ] && [ -n "$PHINT" ]; then
    printf "  놓는 자세        :  \033[1;35m%s\033[0m\n" "$PHINT"
  fi
  printf "  왼팔이 넣을 칸   :  \033[1;33m%s번 (%s)\033[0m\n" "$SLOT" "$SCOL"
  [ "$LAYOUT" != "-" ] && printf "  \033[2m칸 배치         :  %s\033[0m\n" "$LAYOUT"
  echo
  printf "  지시문           :  \033[1;36m\"%s\"\033[0m\n" "$INSTR"
  echo "════════════════════════════════════════════════════════════════"
  printf "  \033[2m오른팔 → 전달(왼팔 그리퍼 닫힘 확인 후 놓기) → 왼팔 → 목표 칸\033[0m\n"
  printf "  \033[2m넣은 뒤에는 양팔 다 곧장 rest 로 (한쪽만 멈추지 말 것)\033[0m\n"
  echo
  read -r -p "  물체를 놓았으면 Enter (s=건너뛰기, q=종료): " KEY </dev/tty
  case "$KEY" in
    q|Q) echo "  종료합니다."; break ;;
    s|S) echo "  건너뜀."; continue ;;
  esac

  if [ "${REST_GATE:-1}" = "1" ] && [ -f "$HERE/rest_gate_bi.py" ]; then
    if ! ( cd "$LEROBOT" && uv run python "$HERE/rest_gate_bi.py" --check "$ROOT" ) </dev/tty; then
      echo "  ⚠️  시작 자세 게이트 실패"
      read -r -p "  그래도 진행할까요? (y/N): " _G </dev/tty
      [[ "$_G" =~ ^[yY]$ ]] || { echo "  중단합니다."; break; }
    fi
  fi

  RESUME=""
  [ "$DONE" -gt 0 ] && RESUME="--resume=true"
  ( cd "$LEROBOT" && uv run lerobot-record \
      --robot.type=bi_so_follower \
      --robot.left_arm_config.port=/dev/ttyFOLLOWER_L \
      --robot.right_arm_config.port=/dev/ttyFOLLOWER_R \
      --robot.left_arm_config.cameras="$CAMS_L" \
      --robot.right_arm_config.cameras="$CAMS_R" \
      --robot.id=bi_follower \
      --teleop.type=bi_so_leader \
      --teleop.left_arm_config.port=/dev/ttyLEADER_L \
      --teleop.right_arm_config.port=/dev/ttyLEADER_R \
      --teleop.id=bi_leader \
      --display_data=true \
      --dataset.repo_id="$REPO" \
      --dataset.root="$ROOT" \
      --dataset.num_episodes=1 \
      --dataset.single_task="$INSTR" \
      --dataset.episode_time_s="$EP_TIME" \
      --dataset.reset_time_s=5 \
      --dataset.private=true \
      --dataset.push_to_hub=false \
      $RESUME )

  NEW=$(python3 -c "import json;print(json.load(open('$ROOT/meta/info.json'))['total_episodes'])" 2>/dev/null || echo "$DONE")
  if [ "$NEW" -gt "$DONE" ]; then
    DONE=$NEW
    echo "  ✅ 저장됨 (누적 ${DONE}ep)"
    python3 "$DATA/calib_fingerprint.py" --write "$ROOT" >/dev/null 2>&1 || true
    _STAGED="$(dirname "$ROOT")/.$(basename "$ROOT")_rest_pose_bi.json"
    [ -f "$_STAGED" ] && mv "$_STAGED" "$ROOT/rest_pose_bi.json" 2>/dev/null || true
    echo "$EP,$DONE,$(date -Is)" >> "$PROGRESS"
  else
    echo "  ⚠ 저장이 안 됐습니다 — 다음 행으로 넘어갑니다"
  fi
done < /tmp/bi_rows.txt

echo
echo "▶ 종료. 누적 ${DONE}ep · $ROOT"
