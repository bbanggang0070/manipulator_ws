#!/usr/bin/env bash
# 로컬(5070Ti) 오케스트레이터 — sweep 1개 끝날 때마다 영상을 로컬로 내려받고 다음으로 진행.
#  [1] (진행 중) v3@40k sweep 대기 → 영상 → inf_video/02_v3_OOD/
#  [2] v2@20k 재측정            → 영상 → inf_video/03_v2_OOD/
#  [3] v3@25k (epoch 정합)      → 영상 → inf_video/04_v3_25k_OOD/
#  [4] v3_200 학습 시작
set -u
IV=$HOME/manipulator_ws/inf_video
RW='~/blocktask_ws/Sim-to-Real-SO-101-Workshop/outputs'
LOG=$HOME/manipulator_ws/.orchestrate.log
exec >>"$LOG" 2>&1
echo "=== 오케스트레이터 시작 $(date +%F\ %T) ==="

wait_done() { for i in $(seq 1 400); do ssh -o ConnectTimeout=10 5090 "grep -q '=== 완료 ===' $1" 2>/dev/null && return 0; sleep 30; done; return 1; }

pull_videos() {  # $1 = 로컬 디렉터리명
  local dst="$IV/$1"
  echo "[pull] → $dst"
  mkdir -p "$dst"
  # 컨테이너가 root로 쓴 파일 → 읽기 권한 부여 후 내려받기
  ssh 5090 "docker run --rm -v $RW:/o --entrypoint chmod real-robot-train8 -R a+rw /o >/dev/null 2>&1 || true"
  for c in $(ssh 5090 "ls -d $RW/sweep_* 2>/dev/null | xargs -n1 basename" 2>/dev/null); do
    local cond=${c#sweep_}
    mkdir -p "$dst/$cond"
    scp -q "5090:$RW/$c/*.mp4" "$dst/$cond/" 2>/dev/null
    echo "   $cond: $(ls "$dst/$cond"/*.mp4 2>/dev/null | wc -l)개"
  done
  # 요약도 함께 보관
  ssh 5090 "cat \$(ls -td ~/ood_sweep_*/ | head -1)summary.txt" > "$dst/summary.txt" 2>/dev/null
  # 다음 sweep이 덮어쓰지 않도록 원격 정리
  ssh 5090 "docker run --rm -v $RW:/o --entrypoint bash real-robot-train8 -c 'rm -rf /o/sweep_*' >/dev/null 2>&1 || true"
}

run_sweep() {  # $1=모델 $2=로그파일
  echo "[sweep] $1 시작 $(date +%T)"
  ssh 5090 "nohup ~/blocktask_ood_sweep.sh $1 20 > ~/$2 2>&1 & echo started"
  sleep 5
  wait_done "~/$2" || { echo "❌ $2 타임아웃"; return 1; }
  echo "[sweep] $1 완료 $(date +%T)"
  ssh 5090 "sed -n '/^COND/,/=== 완료/p' ~/$2"
}

echo "[1] v3@40k sweep 완료 대기(진행 중)..."
wait_done "~/sweep_v3.log" || { echo "❌ v3 타임아웃"; exit 1; }
ssh 5090 "sed -n '/^COND/,/=== 완료/p' ~/sweep_v3.log"
pull_videos 02_v3_OOD

echo "[1.5] 갱신된 sweep 스크립트 배포(씬 검증 포함)"
scp -q "$HOME/manipulator_ws/setup/sim/t1_task/blocktask_ood_sweep.sh" 5090:~/blocktask_ood_sweep.sh
ssh 5090 'chmod +x ~/blocktask_ood_sweep.sh'

run_sweep gr00t_blocktask_v2_n16_8bit/checkpoint-20000 sweep_v2.log && pull_videos 03_v2_OOD
run_sweep gr00t_blocktask_v3_n16_8bit/checkpoint-25000 sweep_v3_25k.log && pull_videos 04_v3_25k_OOD

echo "[4] v3_200 학습 시작 $(date +%T)"
ssh 5090 '~/train_gr00t_blocktask_v3_200_n16_8bit.sh'
echo "=== 오케스트레이터 완료 $(date +%F\ %T) ==="
