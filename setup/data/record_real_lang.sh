#!/usr/bin/env bash
# 실기 언어 조건화 수집 — 계획표가 에피소드마다 **놓을 물체와 지시문**을 정한다.
#
# 왜 에피소드당 프로세스를 새로 띄우나:
#   lerobot-record는 `--dataset.single_task`로 **런 전체에 문장 하나**를 박는다
#   (lerobot_record.py:547에서 루프 안에 그 값을 그대로 넘긴다).
#   에피소드마다 문장을 바꾸려면 프로세스를 나누거나 site-packages를 패치해야 하는데,
#   실기는 어차피 **사람이 매 에피소드 물체를 손으로 놓아야** 하므로 그 시간에 기동이 묻힌다.
#   그리고 문장이 프로세스 시작 시점에 박제되므로 sim에서 겪은 경쟁 상태가 구조적으로 불가능하다
#   (sim 예행에서 6ep 중 4ep이 지시문을 2~3개씩 갖고 저장된 적이 있다).
#
# 수집 규칙:
#   · 화면(터미널)에 뜬 물체만 놓는다. 다른 것이 섞이면 그 에피소드의 라벨이 틀어진다.
#   · 물체는 **매번 다른 자리**에 놓는다. 무의식적으로 같은 자리에 놓기 쉽다 —
#     실기 50ep에서 박스가 사실상 고정이었던 전례가 있다(픽셀 중심 편차 x 7px).
#   · 지시문과 **다른 물체를 집었으면 해당 에피소드를 다시 찍는다**(lerobot의 재녹화 키).
#     잘못 저장된 한 ep가 "언어를 무시해도 된다"는 반례가 된다.
#   · 지우개는 짧은 변으로, 마커는 길이 중앙을 잡는다. 같은 물체를 늘 같은 각도로 잡지 말 것.
#   · **keep_layout=KEEP 행은 물체를 그대로 둔다.** 같은 배치에 지시문만 바꿔 다시 찍는
#     대응쌍이고, 여기가 언어 신호가 가장 진한 구간이다. 다시 놓으면 그 가치가 사라진다.
#   · **파지 직후 목표 칸 위로 먼저 횡이동**하고 그다음 하강한다. 공통 경로로 올라갔다가
#     마지막에 갈라지지 말 것 — 목적지가 지배하는 프레임이 2~3배로 늘어난다.
#     sim에서 목적지 축이 물체 축보다 약했던 주된 이유가 이 구간 길이 차이다.
#
# 사용:
#   ./record_real_lang.sh              # 계획표 처음부터
#   START=41 ./record_real_lang.sh     # 41번 행부터 (이어서)
#   END=60 ./record_real_lang.sh       # 60번 행까지만
set -uo pipefail
cd "$(dirname "$0")"

PLAN="${PLAN:-$HOME/manipulator_ws/manipulator_md/real/real_lang_plan.csv}"
DSNAME="${DSNAME:-so101_real_lang}"
REPO="heongyu/$DSNAME"
ROOT="${ROOT:-$HOME/.cache/huggingface/lerobot/$REPO}"
START="${START:-1}"
END="${END:-0}"
EP_TIME="${EP_TIME:-60}"
LEROBOT="$(cd ../../envs/lerobot && pwd)"

[ -f "$PLAN" ] || { echo "❌ 계획표 없음: $PLAN"; echo "   python3 gen_real_lang_plan.py 로 먼저 생성하세요"; exit 1; }
for d in /dev/ttyLEADER /dev/ttyFOLLOWER /dev/cam_top /dev/cam_wrist; do
  [ -e "$d" ] || { echo "❌ $d 없음 — 하드웨어 연결을 확인하세요"; exit 1; }
done

CAMS='{ top:   {type: opencv, index_or_path: /dev/cam_top,   width: 640, height: 480, fps: 30, fourcc: MJPG},
        wrist: {type: opencv, index_or_path: /dev/cam_wrist, width: 640, height: 480, fps: 30, fourcc: MJPG}}'

TOTAL=$(( $(wc -l < "$PLAN") - 1 ))
[ "$END" = "0" ] && END=$TOTAL
DONE=0
[ -d "$ROOT/meta" ] && DONE=$(python3 -c "import json;print(json.load(open('$ROOT/meta/info.json'))['total_episodes'])" 2>/dev/null || echo 0)

# ── 캘리브레이션 지문 대조 ──────────────────────────────────────────────
#   수집 도중 캘리브레이션이 바뀌면 관절 공간이 달라져 데이터셋이 **서로 안 맞는
#   두 덩어리**가 된다. 그런데 그 변화는 아무 데도 기록되지 않아 조용히 지나간다.
#   단계를 나눠 모으므로(80 → +80 → +90) 단계 사이가 특히 위험하다.
if ! python3 "$(dirname "$0")/calib_fingerprint.py" --check "$ROOT"; then
  echo "❌ 캘리브레이션이 바뀌었습니다. 위 안내를 보고 정리한 뒤 다시 실행하세요."
  exit 1
fi

cat <<INFO

  계획표   : $PLAN  (${TOTAL}행)
  데이터셋 : $ROOT
  이미 저장: ${DONE}ep
  진행 구간: ${START} ~ ${END}행

  ┌────────────────────────────────────────────────────────────┐
  │ 매 에피소드: 터미널에 뜬 물체만 놓고 → Enter → 시연         │
  │ 빨간 띠(KEEP)가 뜨면 물체를 건드리지 마세요 — 대응쌍입니다  │
  │ 파지 후 목표 칸 위로 먼저 횡이동하고 그다음 하강            │
  │ 지시문과 다른 물체·다른 칸이면 재녹화(lerobot 안내 참고)    │
  │ 물체는 매번 다른 자리에. 같은 자리 반복이 분포 구멍을 만든다│
  └────────────────────────────────────────────────────────────┘

INFO

# 계획표를 읽어 한 행씩 돈다. 행마다 프로세스를 새로 띄워 문장을 박제한다.
python3 - "$PLAN" "$START" "$END" <<'PY' > /tmp/real_lang_rows.txt
import csv, sys
plan, s, e = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
need = ["ep", "group_kind", "group_pos", "keep_layout", "n_objects",
        "objects", "target", "slot", "slot_color", "dest_named", "instruction"]
rows = list(csv.DictReader(open(plan)))
missing = [c for c in need if rows and c not in rows[0]]
if missing:
    sys.exit("계획표에 없는 열: %s\n   gen_real_lang_plan.py 로 다시 생성하세요"
             " (4칸 선반 구성)." % missing)
for r in rows:
    if s <= int(r["ep"]) <= e:
        # ⚠️ 빈 필드를 그대로 흘리면 안 된다. bash의 `read`는 IFS가 탭이어도
        #    **탭은 IFS 공백**이라 연속된 구분자를 하나로 접는다. dest_named가 비면
        #    뒤 필드가 한 칸씩 당겨져 **instruction이 통째로 사라지고**
        #    `--dataset.single_task=""` 로 저장된다(목적지 미명시 ~15%가 전부 해당).
        #    비는 열은 "-"로 채워 자리를 지킨다.
        print("\t".join((r[c] or "-") for c in need))
PY

N=0
while IFS=$'\t' read -r EP KIND POS KEEP NOBJ OBJS TGT SLOT SCOL DNAMED INSTR; do
  N=$((N+1))
  echo
  if [ "$KEEP" = "KEEP" ]; then
    # 대응쌍의 2회차 이상. 물체를 다시 놓으면 이 그룹의 가치가 통째로 사라진다 —
    # 관측이 같고 행동만 다른 구간이 이 데이터셋에서 언어 신호가 가장 진한 곳이다.
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
  printf "  집을 것          :  \033[1;33m%s\033[0m\n" "$TGT"
  if [ "$DNAMED" != "-" ]; then
    printf "  넣을 칸          :  \033[1;33m%s번 (%s)\033[0m\n" "$SLOT" "$SCOL"
  else
    # 지시문이 "the bin"이라 정답이 정의되지 않는 에피소드(계획상 15%).
    # 칸은 분포 균형을 위해 지정해 두지만, **문장은 그 칸을 부르지 않는다.**
    # 시연자가 "표시와 지시문이 다르다"고 혼란스러워하지 않도록 명시한다.
    printf "  넣을 칸          :  \033[1;33m%s번 (%s)\033[0m  \033[2m← 지시문엔 색이 없다(임의 지정)\033[0m\n" "$SLOT" "$SCOL"
  fi
  echo
  printf "  지시문           :  \033[1;36m\"%s\"\033[0m\n" "$INSTR"
  echo "════════════════════════════════════════════════════════════════"
  printf "  \033[2m파지 직후 목표 칸 위로 먼저 횡이동 → 그다음 하강. 마지막에 갈라지지 말 것.\033[0m\n"
  echo
  read -r -p "  물체를 놓았으면 Enter (s=이 행 건너뛰기, q=종료): " KEY </dev/tty
  case "$KEY" in
    q|Q) echo "  종료합니다."; break ;;
    s|S) echo "  건너뜀."; continue ;;
  esac

  RESUME=""
  [ "$DONE" -gt 0 ] && RESUME="--resume=true"
  ( cd "$LEROBOT" && uv run lerobot-record \
      --robot.type=so101_follower --robot.port=/dev/ttyFOLLOWER --robot.id=follower \
      --robot.cameras="$CAMS" \
      --teleop.type=so101_leader --teleop.port=/dev/ttyLEADER --teleop.id=leader \
      --display_data=true \
      --dataset.repo_id="$REPO" \
      --dataset.num_episodes=1 \
      --dataset.single_task="$INSTR" \
      --dataset.episode_time_s="$EP_TIME" \
      --dataset.reset_time_s=5 \
      --dataset.private=true \
      $RESUME )

  NEW=$(python3 -c "import json;print(json.load(open('$ROOT/meta/info.json'))['total_episodes'])" 2>/dev/null || echo "$DONE")
  if [ "$NEW" -gt "$DONE" ]; then
    DONE=$NEW
    echo "  ✅ 저장됨 (누적 ${DONE}ep)"
    # 데이터셋 폴더는 첫 저장 때 생긴다. 그 시점에 지문을 남긴다(이미 있으면 대조만).
    python3 "$(dirname "$0")/calib_fingerprint.py" --write "$ROOT" >/dev/null 2>&1 || true
  else
    echo "  ⚠ 저장이 안 됐습니다 — 다음 행으로 넘어갑니다"
  fi
done < /tmp/real_lang_rows.txt

echo
echo "▶ 종료. 누적 ${DONE}ep · $ROOT"
echo "   검증: verify_real_lang_dataset.py (에피소드당 지시문 1개 · 타깃 균형)"
