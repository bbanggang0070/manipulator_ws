#!/usr/bin/env bash
# GR00T N1.6 블록 sim→real 전이 측정 러너 (Phase E) — 시행 단위 자동화.
# 사용법: ./setup/gr00t/eval_gr00t_blocktask_trials.sh [시행 수]   (기본 10)
#
# 매 시행: ①sim-홈 복귀(goto_home_sim.py = sim 학습 rest 자세) → ②블록 배치 후 ENTER
#          → ③60초 실행(자동 종료) → 성공/실패·그리드 지점 수기 기록(개입 금지, 5지점 순환)
#
# 서버 먼저(5090): ~/serve_blocktask_n16_5090.sh  → 'Server is ready'
# ⚠️ goto_home_sim.py 사용(실기 goto_home 아님) — sim 정책이 학습한 시작 분포에서 출발.
set -e
N="${1:-10}"
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR/../../envs/lerobot"

for i in $(seq 1 "$N"); do
  echo ""
  echo "===== 시행 $i/$N ====="
  sleep 3  # 직전 클라이언트의 포트/카메라 해제 대기
  echo "-- sim-홈 복귀 중 (goto_home_sim.py) --"
  until printf '\n' | uv run python "$DIR/goto_home_sim.py"; do
    read -rp "!! 홈 복귀 실패 — 로봇 전원/케이블 확인 후 ENTER로 재시도: "
  done
  read -rp ">> 빨간 블록을 그리드 지점에 배치 후 ENTER (5지점 순환): "
  echo "-- 60초 실행 (자동 종료) --"
  timeout -s INT 60 "$DIR/infer_gr00t_blocktask_remote.sh" || true
done
echo ""
echo "===== $N 시행 완료 — 성공/실패는 수기 기록. 결과표: manipulator_md/sim2real/03_custom_T1_sim2real.md §10 ====="
