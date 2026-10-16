#!/usr/bin/env bash
# 학습 중 사라질 초반 체크포인트를 따로 보관한다 — **언어가 언제 살아나는가** 곡선용.
#
# 왜 필요한가:
#   Run A는 `--save-steps 2000 --save-total-limit 10`으로 돈다. 20k를 넘어가는 순간
#   가장 오래된 2k가 지워지고, 25k에 닿을 때쯤엔 초반 구간이 통째로 사라진다.
#   그런데 우리가 보고 싶은 것은 **초반**이다 — 언어 민감도가 2k에서 오르기 시작하는지
#   16k까지 잠잠한지가 복원 계획 §4-2의 핵심 그림이고, 다시 학습하지 않으면 못 얻는다.
#
# 용량 (실측 2026-09-24, checkpoint-86000 기준):
#   체크포인트 1개 = **13GB**  (가중치 9.8GB + optimizer.pt 3.3GB)
#   ※ 계획서의 "9.2GB, optimizer 없음"은 틀렸다. optimizer.pt가 들어 있다.
#   보관본은 **추론(프로브)에만 쓰므로 optimizer.pt를 뺀다** → 개당 9.8GB.
#   6개 보관 = 약 59GB. 학습 중 유지분(10개 × 13GB = 130GB)과 합쳐 약 190GB.
#
# 사용 (5090에서):
#   ./ckpt_keep.sh once     # 지금 존재하는 대상만 복사하고 끝
#   ./ckpt_keep.sh watch    # 10분마다 훑으며 대상이 생기는 대로 복사 (학습과 함께 띄워둔다)
#   KEEP="2000 6000 25000" ./ckpt_keep.sh once
set -uo pipefail

SRC="${SRC:-$HOME/gr00tn16_ws/checkpoints/gr00t_blocktask_lang_n16_8bit}"
DST="${DST:-${SRC}_keep}"
KEEP="${KEEP:-2000 4000 6000 10000 16000 25000}"
MODE="${1:-once}"
INTERVAL="${INTERVAL:-600}"
# ⚠️ 복사는 **컨테이너 안에서 root로** 한다(2026-09-25 실측).
#   학습 컨테이너가 만든 가중치는 `-rw------- root root`라 호스트 사용자가 읽지 못한다.
#   rsync를 호스트에서 돌리면 메타데이터만 넘어가고 safetensors는 조용히 빠진다 —
#   처음 5개 보관본이 전부 700~900KB짜리 껍데기였다. `ls`는 되므로 완료 검사도 통과했다.
#   docker 그룹만 있으면 sudo 없이 root 권한으로 복사할 수 있다.
# 재개용 파일은 뺀다. 프로브는 가중치만 있으면 된다.
DROP="optimizer.pt rng_state.pth scheduler.pt"
CKROOT="$(dirname "$SRC")"
SRC_NAME="$(basename "$SRC")"
DST_NAME="$(basename "$DST")"
IMAGE="${IMAGE:-real-robot-train8}"

mkdir -p "$DST"

# 체크포인트가 **다 쓰였는지** 본다. 쓰는 중에 복사하면 조용히 깨진 사본이 생긴다.
complete() {
  local c="$1"
  [ -f "$c/config.json" ] || return 1
  [ -d "$c/experiment_cfg" ] || return 1
  [ -f "$c/model.safetensors.index.json" ] || return 1
  # 가중치 샤드가 다 있고 크기가 10초간 변하지 않으면 완료로 본다
  local n; n=$(ls "$c"/model-*.safetensors 2>/dev/null | wc -l)
  [ "$n" -ge 1 ] || return 1
  local a b
  a=$(du -sb "$c" 2>/dev/null | cut -f1); sleep 10
  b=$(du -sb "$c" 2>/dev/null | cut -f1)
  [ "$a" = "$b" ]
}

sweep() {
  local copied=0
  for s in $KEEP; do
    local src="$SRC/checkpoint-$s" dst="$DST/checkpoint-$s"
    [ -d "$src" ] || continue
    [ -d "$dst" ] && [ -f "$dst/.done" ] && continue
    if ! complete "$src"; then
      echo "  · checkpoint-$s 아직 쓰는 중 — 다음 회차에"
      continue
    fi
    local avail; avail=$(df -BG --output=avail "$DST" | tail -1 | tr -dc '0-9')
    if [ "${avail:-0}" -lt 20 ]; then
      echo "  ❌ 여유 ${avail}G — 보관 중단 (개당 약 10G 필요)"
      return 1
    fi
    echo "  · checkpoint-$s 보관 중..."
    docker run --rm --entrypoint /bin/bash -v "$CKROOT:/m" "$IMAGE" -c "
      set -e
      mkdir -p /m/$DST_NAME/checkpoint-$s
      cp -a /m/$SRC_NAME/checkpoint-$s/. /m/$DST_NAME/checkpoint-$s/
      cd /m/$DST_NAME/checkpoint-$s && rm -f $DROP
      # 가중치가 실제로 넘어왔을 때만 완료 표시를 남긴다. 표시가 없으면 다음 회차에 다시 받는다.
      n=\$(ls model-*.safetensors 2>/dev/null | wc -l)
      [ \"\$n\" -ge 1 ] || { echo '    가중치 없음'; exit 1; }
      date -Is > .done
      chmod -R a+rX /m/$DST_NAME/checkpoint-$s
    " || { echo "    ❌ 복사 실패"; continue; }
    local w; w=$(ls "$dst"/model-*.safetensors 2>/dev/null | wc -l)
    echo "    ✅ $(du -sh "$dst" | cut -f1)  (가중치 ${w}개)"
    copied=$((copied + 1))
  done
  # 남은 대상 보고
  local left=""
  for s in $KEEP; do [ -f "$DST/checkpoint-$s/.done" ] || left="$left $s"; done
  echo "  보관 완료: $(ls -d "$DST"/checkpoint-*/ 2>/dev/null | wc -l)/$(echo $KEEP | wc -w)   남은 대상:${left:- 없음}"
  [ -z "$left" ] && return 2   # 전부 끝남
  return 0
}

echo "▶ 체크포인트 보관"
echo "  원본: $SRC"
echo "  보관: $DST   (optimizer.pt 제외 — 프로브는 가중치만 쓴다)"
echo "  대상: $KEEP"
echo

if [ "$MODE" = "once" ]; then
  sweep; rc=$?
  [ "$rc" = 2 ] && echo "  전부 보관됐다."
  exit 0
fi

while true; do
  echo "── $(date +%H:%M:%S) ──"
  sweep; rc=$?
  if [ "$rc" = 2 ]; then echo "  전부 보관됐다. 종료."; exit 0; fi
  # 학습이 끝났고 더 나올 게 없으면 멈춘다
  if ! docker ps --format '{{.Names}}' | grep -q '^gr00t-train8$'; then
    echo "  학습 컨테이너가 없다 — 마지막 훑기 후 종료."
    sleep 30; sweep; exit 0
  fi
  sleep "$INTERVAL"
done
