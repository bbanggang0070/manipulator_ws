#!/usr/bin/env bash
# 5090 학습이 끝나면 최종 체크포인트를 로컬로 받아 **자동으로 로컬 서빙**한다.
#
# 순서: 학습 컨테이너 종료 대기 → 체크포인트 저장 완료 확인 → 권한 열기 → 추론용 파일만 rsync
#       → 크기 대조 → 기존 로컬 서버 내리고 새 체크포인트로 serve_local.sh → 준비 완료 확인
#
# 세션과 분리해서 띄운다(수십 시간 기다리므로):
#   setsid nohup ./auto_serve_after_train.sh gr00t_bi_cleanup300_n16_8bit checkpoint-52000 \
#       > ~/manipulator_ws/logs/auto_serve.log 2>&1 &
# 진행 확인: tail -f ~/manipulator_ws/logs/auto_serve.log
# 중단:     pkill -f auto_serve_after_train.sh
set -u
M="${1:?모델 폴더 이름 (예: gr00t_bi_cleanup300_n16_8bit)}"
C="${2:?체크포인트 (예: checkpoint-52000)}"
TRAIN_CONTAINER="${TRAIN_CONTAINER:-gr00t-train-bi}"
REMOTE="${REMOTE:-5090}"
RC="gr00tn16_ws/checkpoints"            # 5090 기준 (~ 아래)
LC="$HOME/gr00tn16_ws/checkpoints"      # 로컬
HERE="$(cd "$(dirname "$0")" && pwd)"
S="ssh -o ConnectTimeout=20 -o ServerAliveInterval=15 $REMOTE"
log() { echo "[$(date '+%m/%d %H:%M')] $*"; }

log "시작 — $M/$C, 학습 컨테이너 $TRAIN_CONTAINER 종료를 기다린다"

# 1) 학습 컨테이너 종료 대기 (ssh 실패는 '종료'로 보지 않고 다시 확인)
while :; do
  # grep -c 는 0건일 때 종료코드 1 을 내므로 원격에서 '; true' 로 덮고, 빈 출력(ssh 실패)만 재시도
  n=$($S "docker ps --format '{{.Names}}' | grep -cx $TRAIN_CONTAINER; true" 2>/dev/null)
  [ -z "$n" ] && { sleep 120; continue; }
  [ "$n" = "0" ] && break
  sleep 600
done
log "학습 컨테이너 종료 확인"

# 2) 체크포인트 저장 완료 확인 — index 파일 존재 + 가중치 크기가 1분 동안 그대로
ok=""
for i in $(seq 1 30); do
  a=$($S "test -f ~/$RC/$M/$C/model.safetensors.index.json && du -sb ~/$RC/$M/$C | cut -f1" 2>/dev/null)
  sleep 60
  b=$($S "du -sb ~/$RC/$M/$C | cut -f1" 2>/dev/null)
  if [ -n "$a" ] && [ "$a" = "$b" ]; then ok=1; break; fi
done
[ -n "$ok" ] || { log "❌ $C 가 5090에 없거나 저장이 끝나지 않음 — 중단 (학습이 비정상 종료됐는지 확인)"; exit 1; }
log "5090 $C 저장 완료 ($(( a / 1024 / 1024 / 1024 ))GB, optimizer 포함)"

# 3) 권한 열기 — 컨테이너가 root 로 만든 파일
$S "docker run --rm --entrypoint /bin/bash -v \$HOME/$RC:/c real-robot-train8 \
    -c 'chmod -R a+rX /c/$M/$C /c/$M/experiment_cfg /c/$M/processor'" \
  || { log "❌ 권한 변경 실패"; exit 1; }

# 4) 추론용 파일만 받기 (optimizer·scheduler·rng 제외), 끊기면 재시도
mkdir -p "$LC/$M"
done_rsync=""
for i in $(seq 1 10); do
  log "전송 시도 $i"
  if rsync -a --partial --exclude=optimizer.pt --exclude=scheduler.pt --exclude=rng_state.pth \
       --rsync-path="nice -n 19 ionice -c3 rsync" \
       "$REMOTE:$RC/$M/$C" "$REMOTE:$RC/$M/experiment_cfg" "$REMOTE:$RC/$M/processor" "$LC/$M/"; then
    done_rsync=1; break
  fi
  sleep 120
done
[ -n "$done_rsync" ] || { log "❌ 전송 10회 실패 — 중단"; exit 1; }

# 5) 가중치 파일 크기 대조
for f in $(ls "$LC/$M/$C" | grep -E '^model.*\.safetensors$'); do
  r=$($S "stat -c %s ~/$RC/$M/$C/$f" 2>/dev/null); l=$(stat -c %s "$LC/$M/$C/$f")
  [ "$r" = "$l" ] || { log "❌ 크기 불일치 $f (5090 $r / 로컬 $l) — 중단"; exit 1; }
done
log "✅ 전송 완료 ($(du -sh "$LC/$M/$C" | cut -f1)) · 가중치 크기 일치"

# 6) 로컬 서버 교체
cd "$HERE"
./serve_local.sh '' stop >/dev/null 2>&1 || true
sleep 5
if ./serve_local.sh "$M/$C"; then
  log "✅ 로컬 서빙 시작 — $M/$C (tcp://127.0.0.1:5555)"
else
  log "❌ 로컬 서빙 실패 — ./serve_local.sh '' logs 로 확인"; exit 1
fi
log "끝"
