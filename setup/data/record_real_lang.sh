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

cat <<INFO

  계획표   : $PLAN  (${TOTAL}행)
  데이터셋 : $ROOT
  이미 저장: ${DONE}ep
  진행 구간: ${START} ~ ${END}행

  ┌────────────────────────────────────────────────────────────┐
  │ 매 에피소드: 터미널에 뜬 물체만 놓고 → Enter → 시연         │
  │ 지시문과 다른 물체를 집었으면 **재녹화**(lerobot 안내 참고) │
  │ 물체는 매번 다른 자리에. 같은 자리 반복이 분포 구멍을 만든다│
  └────────────────────────────────────────────────────────────┘

INFO

# 계획표를 읽어 한 행씩 돈다. 행마다 프로세스를 새로 띄워 문장을 박제한다.
python3 - "$PLAN" "$START" "$END" <<'PY' > /tmp/real_lang_rows.txt
import csv, sys
plan, s, e = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
for r in csv.DictReader(open(plan)):
    i = int(r["ep"])
    if s <= i <= e:
        print("\t".join([r["ep"], r["n_objects"], r["objects"], r["target"],
                          r["boxes"], r["dest"], r["instruction"]]))
PY

N=0
while IFS=$'\t' read -r EP NOBJ OBJS TGT BOXES DEST INSTR; do
  N=$((N+1))
  echo
  echo "════════════════════════════════════════════════════════════════"
  printf "  계획표 %s/%s행      (저장된 에피소드 %s개)\n" "$EP" "$TOTAL" "$DONE"
  echo "────────────────────────────────────────────────────────────────"
  printf "  놓을 물체 (%s개):  \033[1m%s\033[0m\n" "$NOBJ" "$OBJS"
  printf "  놓을 상자 (2개):  \033[1m%s\033[0m\n" "$BOXES"
  printf "  집을 것        :  \033[1;33m%s\033[0m\n" "$TGT"
  printf "  넣을 곳        :  \033[1;33m%s box\033[0m\n" "$DEST"
  echo
  printf "  지시문         :  \033[1;36m\"%s\"\033[0m\n" "$INSTR"
  echo "════════════════════════════════════════════════════════════════"
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
  else
    echo "  ⚠ 저장이 안 됐습니다 — 다음 행으로 넘어갑니다"
  fi
done < /tmp/real_lang_rows.txt

echo
echo "▶ 종료. 누적 ${DONE}ep · $ROOT"
echo "   검증: verify_real_lang_dataset.py (에피소드당 지시문 1개 · 타깃 균형)"
