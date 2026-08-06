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
# ⚠️ **통제 실험 설계** (2026-08-06 개편)
#   이전 설계는 모든 조건을 전체 랜덤 위에서 측정해, 축을 바꿔도 SR이 45%에서 안 움직였다
#   (베이스 랜덤화가 신호를 덮음). 이제 **기준(ref)을 고정하고 한 번에 한 축만** 켠다.
#   모든 조건은 -DR-Eval에서 실행(씬 에셋 동일) — 바뀌는 것은 이벤트 랜덤화뿐.
#
# 조건(프리셋) — configure_scene.py 참조:
#   ref         기준: 블록만 학습범위 랜덤. 박스 고정·물리 off·조명 off  ← 모든 비교의 기준선
#   pos_ood     ref + 블록 범위 확대 (0.12~0.38 / -1.0~1.55)
#   box_rand    ref + 박스 학습범위 랜덤 (0.28~0.34, ±1.15, yaw±π)
#   box_ood     ref + 박스 범위 확대 (0.24~0.38, ±1.45)
#   phys_dr     ref + 물리 DR (마찰 ±30%, 질량 ±50%)
#   light_dr    ref + 조명 DR
#   color_blue / color_green   ref + 큐브 색만 변경
#   full        전부 랜덤 = **학습 분포** → 'train SR ≥80%' 판정은 이 조건으로
#
#   ※ ref의 박스 고정 위치(r=0.266, ang=-0.97)는 블록 스폰 각도범위 밖이라
#     블록-박스 겹침(전체 랜덤 시 12.4% 발생)이 원천적으로 생기지 않는다.
#
# 결과: ~/ood_sweep_<타임스탬프>/  (조건별 로그 + SR 요약 summary.txt)
#       영상: $WORKSHOP/outputs/sweep_<조건>/epNN_{success,fail}.mp4
set -uo pipefail

MODEL="${1:?MODEL 서브경로 필요 (예: gr00t_blocktask_v3_n16_8bit/checkpoint-40000)}"
N="${2:-10}"
shift 2 || true
CONDS=("$@")
[ ${#CONDS[@]} -eq 0 ] && CONDS=(ref pos_ood box_rand box_ood phys_dr light_dr color_blue color_green full)

WORKSHOP="$HOME/blocktask_ws/Sim-to-Real-SO-101-Workshop"
CFG="$WORKSHOP/source/sim_to_real_so101/tasks/vials_to_rack_env_cfg.py"
CAMCFG="$WORKSHOP/source/sim_to_real_so101/tasks/task_env_cfg.py"
OUTDIR="$HOME/ood_sweep_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUTDIR"
SUMMARY="$OUTDIR/summary.txt"

# ── 씬 버전 검증 (2026-08-06 추가) ────────────────────────────────────────────
# 배경: 로컬 fork에만 v3 씬 개조(물리 DR·박스 arc·위치 확대·카메라 오프셋)를 적용하고
#   5090에 rsync를 빠뜨린 채 sweep을 돌려, v2 씬에서 측정한 무효 데이터를 얻은 사고가 있었다.
#   (box_ood의 assert가 없었다면 조용히 틀린 숫자가 나왔을 것)
# → 매 실행 전에 v3 씬 필수 요소를 확인하고, 하나라도 없으면 즉시 중단한다.
#   씬을 고쳤다면 반드시 배포: rsync -a <로컬>/source/ 5090:~/blocktask_ws/.../source/
verify_scene() {
  local miss=0
  check() {  # $1=설명 $2=파일 $3=패턴
    if grep -q "$3" "$2"; then printf "  ✅ %s\n" "$1"
    else printf "  ❌ %s  (없음: %s)\n" "$1" "$3"; miss=1; fi
  }
  echo "=== 씬 버전 검증 (v3 기준) ==="
  check "물리 DR — 마찰"      "$CFG"    "randomize_block_friction"
  check "물리 DR — 질량"      "$CFG"    "randomize_block_mass"
  check "박스 위치·회전 무작위" "$CFG"    "reset_basket_random"
  check "박스 고정 리셋 비활성" "$CFG"    "reset_props = None"
  check "박스 축소 0.85"       "$CFG"    "scale=(0.85"
  check "카메라 오프셋 고정"    "$CAMCFG" 'CAM_X", "0.03'
  echo "  · 블록 스폰 범위: $(grep -E '^BLOCK_REACH_(MIN|MAX)_DIST' "$CFG" | awk '{printf "%s ", $3}')"
  echo "  · 블록 각도 범위: $(grep -E '^BLOCK_REACH_ANGLE_RANGE' "$CFG" | cut -d= -f2 | cut -d'#' -f1 | xargs)"
  if [ "$miss" != "0" ]; then
    echo
    echo "❌ 씬이 v3 버전이 아닙니다 — 측정이 무효가 되므로 중단합니다."
    echo "   로컬에서 배포하세요:"
    echo "     rsync -a ~/blocktask_ws/Sim-to-Real-SO-101-Workshop/source/ \\"
    echo "       5090:~/blocktask_ws/Sim-to-Real-SO-101-Workshop/source/"
    exit 2
  fi
  echo "  → 검증 통과"; echo
}
verify_scene | tee -a "$SUMMARY"

BAK="$CFG.sweep_bak"
cp "$CFG" "$BAK"
restore() { cp "$BAK" "$CFG"; }
cleanup() { restore; rm -f "$BAK"; docker rm -f gr00t-srv teleop-eval >/dev/null 2>&1 || true; }
trap cleanup EXIT

apply_cond() {  # $1 = 프리셋명. 항상 원본에서 시작.
  restore
  python3 "$HOME/configure_scene.py" "$CFG" "$1" || return 1
}

echo "모델: $MODEL | N=$N | 조건: ${CONDS[*]}" | tee "$SUMMARY"
echo "결과 폴더: $OUTDIR" | tee -a "$SUMMARY"
echo | tee -a "$SUMMARY"
# printf 패딩은 바이트 기준이라 한글(3바이트/2칸)이 섞이면 정렬이 깨진다 → 헤더는 ASCII로 통일.
printf "%-14s %-16s %s\n" "COND" "SR" "TIME(mm:ss)" | tee -a "$SUMMARY"

SWEEP_T0=$(date +%s)
for c in "${CONDS[@]}"; do
  echo "===== [$c] 시작 $(date +%H:%M:%S) ====="
  T0=$(date +%s)
  apply_cond "$c" || continue
  # 전 조건 -DR-Eval 고정(씬 에셋 동일). 조건 차이는 configure_scene.py의 랜덤화 설정뿐.
  MODE=dr
  rm -rf "$WORKSHOP/outputs/sweep_$c"
  SAVE_VIDEO_DIR=/workspace/Sim-to-Real-SO-101-Workshop/outputs/sweep_$c \
    "$HOME/blocktask_sim_eval.sh" "$MODEL" "$N" "$MODE" > "$OUTDIR/$c.log" 2>&1
  SR=$(grep -oE "success: [0-9.]+%" "$OUTDIR/$c.log" | tail -1)
  EL=$(( $(date +%s) - T0 ))   # 조건별 소요(모델 로딩 ~1-2분 + N 에피소드 롤아웃 포함)
  printf "%-14s %-16s %02d:%02d\n" "$c" "${SR:-FAILED(로그 확인)}" $((EL/60)) $((EL%60)) | tee -a "$SUMMARY"
done

# 영상 권한(컨테이너 root 소유 → 호스트에서 읽기)
docker run --rm -v "$WORKSHOP/outputs:/o" --entrypoint chmod teleop-docker:latest -R a+rw /o >/dev/null 2>&1 || true

TOTAL=$(( $(date +%s) - SWEEP_T0 ))
echo | tee -a "$SUMMARY"
printf "총 소요: %02d:%02d:%02d (%d개 조건)\n" $((TOTAL/3600)) $((TOTAL%3600/60)) $((TOTAL%60)) "${#CONDS[@]}" | tee -a "$SUMMARY"
echo "=== 완료 ===" | tee -a "$SUMMARY"
cat "$SUMMARY"
