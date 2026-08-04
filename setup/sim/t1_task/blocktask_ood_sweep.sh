#!/usr/bin/env bash
# blocktask OOD 스윕 — 여러 조건을 한 번에 평가하고 조건별 SR + 시행별 영상을 남긴다.
# **5090에서 실행.** (blocktask_sim_eval.sh를 조건마다 반복 호출 + 씬 cfg 자동 편집/복원)
#
# 사용법(5090):
#   ~/blocktask_ood_sweep.sh <MODEL_SUBPATH> [N] [조건...]
#   예: ~/blocktask_ood_sweep.sh gr00t_blocktask_v3_n16_8bit/checkpoint-40000 10
#       ~/blocktask_ood_sweep.sh gr00t_blocktask_v3_n16_8bit/checkpoint-40000 10 train pos_ood color_blue
#   조건 생략 시 기본 세트 전부 실행.
#
# ⚠️ 조건 정의는 **v3 학습 분포(2026-08-04)** 기준:
#     학습 블록: 반경 0.16~0.34, 각 -0.7~1.25 / 학습 박스: arc 0.28~0.34, 각 ±1.15, yaw ±π
#   → OOD는 그 **바깥**이어야 한다. (v2 시절 "위치 OOD=0.16~0.34"는 v3에선 학습분포이므로 재정의됨)
#
# 조건 목록:
#   train      학습 분포 그대로 (baseline)
#   dr         조명·외형 DR (-DR-Eval 태스크)
#   pos_ood    블록 위치 학습범위 밖 (반경 0.12~0.38, 각 -1.0~1.55)
#   box_ood    박스 위치 학습범위 밖 (arc 0.24~0.38, 각 ±1.45)
#   color_blue / color_green / color_purple   큐브 색만 변경(위치는 학습분포)
#
# 결과: ~/ood_sweep_<타임스탬프>/  (조건별 로그 + SR 요약 summary.txt)
#       영상: $WORKSHOP/outputs/sweep_<조건>/epNN_{success,fail}.mp4
set -uo pipefail

MODEL="${1:?MODEL 서브경로 필요 (예: gr00t_blocktask_v3_n16_8bit/checkpoint-40000)}"
N="${2:-10}"
shift 2 || true
CONDS=("$@")
[ ${#CONDS[@]} -eq 0 ] && CONDS=(train dr pos_ood box_ood color_blue color_green)

WORKSHOP="$HOME/blocktask_ws/Sim-to-Real-SO-101-Workshop"
CFG="$WORKSHOP/source/sim_to_real_so101/tasks/vials_to_rack_env_cfg.py"
OUTDIR="$HOME/ood_sweep_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUTDIR"
SUMMARY="$OUTDIR/summary.txt"

BAK="$CFG.sweep_bak"
cp "$CFG" "$BAK"
restore() { cp "$BAK" "$CFG"; }
cleanup() { restore; rm -f "$BAK"; docker rm -f gr00t-srv teleop-eval >/dev/null 2>&1 || true; }
trap cleanup EXIT

apply_cond() {  # $1 = 조건명. 항상 원본에서 시작.
  restore
  case "$1" in
    train|dr) : ;;  # 씬 편집 없음
    pos_ood)
      sed -i -E 's/^BLOCK_REACH_MIN_DIST = [0-9.]+/BLOCK_REACH_MIN_DIST = 0.12/;
                 s/^BLOCK_REACH_MAX_DIST = [0-9.]+/BLOCK_REACH_MAX_DIST = 0.38/;
                 s/^BLOCK_REACH_ANGLE_RANGE = \([^)]*\)/BLOCK_REACH_ANGLE_RANGE = (-1.0, 1.55)/' "$CFG" ;;
    box_ood)
      # 박스 arc 블록(reset_basket_random) 안의 min/max/angle만 정확히 교체.
      # (주석 정렬 때문에 단순 문자열 치환은 실패 → 블록 범위를 잡아 정규식 적용)
      python3 - "$CFG" <<'PY'
import re, sys
p = sys.argv[1]; s = open(p).read()
m = re.search(r'reset_basket_random\s*=\s*EventTerm\((.*?)\n    \)', s, re.S)
assert m, "reset_basket_random 블록을 찾지 못함"
blk = m.group(0)
new = blk
new = re.sub(r'("min_dist":\s*)[0-9.]+', r'\g<1>0.24', new)
new = re.sub(r'("max_dist":\s*)[0-9.]+', r'\g<1>0.38', new)
new = re.sub(r'("angle_range":\s*)\([^)]*\)', r'\g<1>(-1.45, 1.45)', new)
assert new != blk, "치환이 적용되지 않음"
open(p, "w").write(s.replace(blk, new))
PY
      ;;
    color_blue)   sed -i 's/diffuse_color=(0.9, 0.1, 0.1)/diffuse_color=(0.1, 0.1, 0.9)/' "$CFG" ;;
    color_green)  sed -i 's/diffuse_color=(0.9, 0.1, 0.1)/diffuse_color=(0.15, 0.6, 0.15)/' "$CFG" ;;
    color_purple) sed -i 's/diffuse_color=(0.9, 0.1, 0.1)/diffuse_color=(0.55, 0.15, 0.75)/' "$CFG" ;;
    *) echo "알 수 없는 조건: $1" >&2; return 1 ;;
  esac
}

echo "모델: $MODEL | N=$N | 조건: ${CONDS[*]}" | tee "$SUMMARY"
echo "결과 폴더: $OUTDIR" | tee -a "$SUMMARY"
echo | tee -a "$SUMMARY"

for c in "${CONDS[@]}"; do
  echo "===== [$c] 시작 $(date +%H:%M:%S) ====="
  apply_cond "$c" || continue
  MODE=eval; [ "$c" = "dr" ] && MODE=dr
  rm -rf "$WORKSHOP/outputs/sweep_$c"
  SAVE_VIDEO_DIR=/workspace/Sim-to-Real-SO-101-Workshop/outputs/sweep_$c \
    "$HOME/blocktask_sim_eval.sh" "$MODEL" "$N" "$MODE" > "$OUTDIR/$c.log" 2>&1
  SR=$(grep -oE "success: [0-9.]+%" "$OUTDIR/$c.log" | tail -1)
  printf "%-14s %s\n" "$c" "${SR:-(측정 실패 — 로그 확인)}" | tee -a "$SUMMARY"
done

# 영상 권한(컨테이너 root 소유 → 호스트에서 읽기)
docker run --rm --entrypoint chmod -v "$WORKSHOP/outputs:/o" teleop-docker:latest -R a+rw /o >/dev/null 2>&1 || true

echo | tee -a "$SUMMARY"
echo "=== 완료 ===" | tee -a "$SUMMARY"
cat "$SUMMARY"
