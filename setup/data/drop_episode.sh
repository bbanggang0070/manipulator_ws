#!/usr/bin/env bash
# 저장된 에피소드를 **안전하게** 지운다. 기본은 마지막 하나.
#
# 왜 스크립트가 필요한가:
#   LeRobot v3.0 은 메타(info.json · meta/episodes/*.parquet · stats)와
#   데이터(data/*.parquet) · 영상(videos/**/*.mp4)이 서로 묶여 있다.
#   파일만 지우거나 이름을 바꾸면 **데이터셋 전체가 깨진다**
#   (실제로 file-002.mp4 이름을 바꿨다가 수집이 안 됐다, 2026-10-06).
#
#   정식 도구는 lerobot-edit-dataset 인데 두 가지 함정이 있다:
#     ① --new_repo_id 없이 쓰면 제자리 모드가 되는데, 그 경로 계산이 틀려
#        "FileNotFoundError: .../cleanup_real_old/videos/..." 로 실패한다.
#        반드시 **새 이름으로 출력**한 뒤 옮겨야 한다.
#     ② 출력이 <root>/<new_repo_id> 아래 **중첩**되어 생긴다.
#     ③ 우리가 쓰는 calibration_snapshot.json · collect_progress.txt 는
#        lerobot 이 모르는 파일이라 **복사해 주지 않는다.** 잃으면 재개 지점과
#        캘리브레이션 가드가 둘 다 망가진다.
#
#   이 셋을 매번 손으로 하면 틀린다. 묶어 둔다.
#
# 사용:
#   ./drop_episode.sh              # 마지막 에피소드 삭제
#   ./drop_episode.sh 2            # episode_index 2 삭제
#   ./drop_episode.sh 2 --keep-backup
#   ./drop_episode.sh --yes            # 확인 프롬프트 없이
set -euo pipefail
cd "$(dirname "$0")"

ROOT="${ROOT:-$HOME/blocktask_ws/Sim-to-Real-SO-101-Workshop/datasets/_train/cleanup_real}"
REPO="${REPO:-heongyu/cleanup_real}"
LEROBOT="$(cd ../../envs/lerobot && pwd)"
# 위치 인자(에피소드 번호)와 플래그를 분리한다 — 플래그를 번호로 오인하지 않도록.
IDX=""
KEEP_BACKUP=0
ASSUME_YES=0
for a in "$@"; do
  case "$a" in
    --keep-backup) KEEP_BACKUP=1 ;;
    --yes|-y)      ASSUME_YES=1 ;;
    -*)            echo "❌ 모르는 옵션: $a"; exit 1 ;;
    *)             IDX="$a" ;;
  esac
done
if [ -n "$IDX" ] && ! [[ "$IDX" =~ ^[0-9]+$ ]]; then
  echo "❌ 에피소드 번호는 숫자여야 합니다: $IDX"; exit 1
fi

[ -d "$ROOT/meta" ] || { echo "❌ 데이터셋 없음: $ROOT"; exit 1; }

TOTAL=$(python3 -c "import json;print(json.load(open('$ROOT/meta/info.json'))['total_episodes'])")
[ "$TOTAL" -gt 0 ] || { echo "❌ 에피소드가 0개입니다"; exit 1; }
[ -n "$IDX" ] || IDX=$((TOTAL - 1))      # 기본: 마지막
[ "$IDX" -lt "$TOTAL" ] || { echo "❌ episode_index $IDX 는 범위 밖 (0~$((TOTAL-1)))"; exit 1; }

PROG="$ROOT/collect_progress.txt"
ROW=""
[ -f "$PROG" ] && ROW=$(sed -n "$((IDX + 1))p" "$PROG" | cut -d, -f1)

cat <<INFO

  데이터셋   : $ROOT
  현재       : ${TOTAL}ep
  지울 것    : episode_index $IDX${ROW:+  (계획표 ${ROW}행)}
  남을 것    : $((TOTAL - 1))ep

INFO
if [ "$ASSUME_YES" = 1 ]; then
  echo "  (--yes 지정됨 — 확인 생략)"
else
  read -r -p "  진행할까요? (y/N): " YN </dev/tty
  [[ "$YN" =~ ^[yY]$ ]] || { echo "  취소."; exit 0; }
fi

PARENT="$(dirname "$ROOT")"; NAME="$(basename "$ROOT")"
BACKUP="$PARENT/${NAME}_backup_$(date +%H%M%S)"
echo "  백업 → $BACKUP"
cp -r "$ROOT" "$BACKUP"

# ── 정식 도구로 삭제본 생성 (반드시 새 이름으로) ──
echo "  삭제 중..."
( cd "$LEROBOT" && uv run lerobot-edit-dataset \
    --repo_id "$REPO" --root "$ROOT" \
    --new_repo_id "${REPO}_fix" \
    --operation.type delete_episodes \
    --operation.episode_indices "[$IDX]" ) >/tmp/drop_ep.log 2>&1 || {
  echo "❌ 실패 — /tmp/drop_ep.log 확인. 원본은 그대로입니다."; tail -5 /tmp/drop_ep.log; exit 1; }

NEW="$ROOT/${REPO}_fix"
[ -d "$NEW/meta" ] || { echo "❌ 결과물을 못 찾음: $NEW"; tail -5 /tmp/drop_ep.log; exit 1; }

# ── 우리 메타를 챙겨 제자리로 교체 ──
TMP_SNAP=$(mktemp); TMP_PROG=$(mktemp)
[ -f "$ROOT/calibration_snapshot.json" ] && cp "$ROOT/calibration_snapshot.json" "$TMP_SNAP"
# 진행 기록에서 **그 에피소드의 줄만** 뺀다(0-based idx → 1-based 줄번호)
[ -f "$PROG" ] && sed "$((IDX + 1))d" "$PROG" > "$TMP_PROG"

STAGE="$PARENT/.${NAME}_new_$$"
mv "$NEW" "$STAGE"
rm -rf "$ROOT"
mv "$STAGE" "$ROOT"
[ -s "$TMP_SNAP" ] && cp "$TMP_SNAP" "$ROOT/calibration_snapshot.json"
[ -s "$TMP_PROG" ] && cp "$TMP_PROG" "$ROOT/collect_progress.txt"
rm -f "$TMP_SNAP" "$TMP_PROG"

NEWTOT=$(python3 -c "import json;print(json.load(open('$ROOT/meta/info.json'))['total_episodes'])")
echo "  ✅ 완료 — ${TOTAL}ep → ${NEWTOT}ep"
if [ -f "$PROG" ]; then
  LAST=$(tail -1 "$PROG" 2>/dev/null | cut -d, -f1)
  echo "     재개 지점: $([ -n "$LAST" ] && echo "$((LAST + 1))행" || echo "1행")부터"
fi
if [ "$KEEP_BACKUP" = 1 ]; then
  echo "     백업 유지: $BACKUP"
else
  rm -rf "$BACKUP"; echo "     백업 삭제 (남기려면 --keep-backup)"
fi
echo
echo "  검증:"
echo "    cd $LEROBOT && REAL_LANG_PLAN=~/manipulator_ws/manipulator_md/p5_real_cleanup/real_lang_plan_s1.csv \\"
echo "      uv run python ../../setup/data/verify_real_lang_dataset.py"
