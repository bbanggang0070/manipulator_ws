#!/usr/bin/env bash
# GR00T T1 정식 측정 러너 — 시행 단위 자동화
# 사용법: ./setup/gr00t/eval_gr00t_t1_trials.sh [시행 수]   (기본 10)
#
# 매 시행: ①로봇 홈 복귀(학습 평균 자세, ±2°) → ②큐브 배치 후 ENTER → ③60초 실행(자동 종료)
# 시행별 로그는 logs/gr00t_infer/<타임스탬프>/ (chunks/actions CSV + video.mp4)
# 성공/실패·그리드 지점은 수기 기록 (SmolVLA 측정과 동일하게 5지점 순환, 개입 금지)
#
# 서버 먼저: 5090에서 ~/gr00t_remote/scripts/gr00t-server.sh t1
set -e
N="${1:-10}"
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR/../../envs/lerobot"

for i in $(seq 1 "$N"); do
  echo ""
  echo "===== 시행 $i/$N ====="
  sleep 3  # 직전 클라이언트의 포트/카메라 해제 대기
  # 홈 복귀 — 실패 시(일시적 시리얼 글리치 등) ENTER로 재시도
  echo "-- 홈 복귀 중 --"
  until printf '\n' | uv run python "$DIR/goto_home.py"; do
    read -rp "!! 홈 복귀 실패 — 로봇 전원/케이블 확인 후 ENTER로 재시도: "
  done
  read -rp ">> 큐브를 그리드 지점에 배치 후 ENTER (5지점 순환): "
  echo "-- 60초 실행 (자동 종료) --"
  timeout -s INT 60 "$DIR/infer_gr00t_t1_remote.sh" || true
done
echo ""
echo "===== $N 시행 완료 — 최근 로그: ls -dt ~/manipulator_ws/logs/gr00t_infer/*/ | head -$N ====="
