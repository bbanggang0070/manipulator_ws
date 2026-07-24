#!/usr/bin/env bash
# 블록 학습 데이터(로컬 v3.0) → GR00T N1.6용 v2.1 준비. vials로 검증한 파이프라인(80% 모델) 재현.
#   1) 로컬 → 5090 전송   2) v3→v2.1 변환   3) modality.json   4) stats count 수정
# 사용법: (75ep 녹화 후) ./prepare_blocktask_gr00t.sh
# 결과: 5090:~/gr00tn16_ws/sim_data/heongyu/sim_so101_blocktask (v2.1, 학습 바로 가능)
set -euo pipefail
cd "$(dirname "$0")"

LOCAL_DS="$HOME/blocktask_ws/Sim-to-Real-SO-101-Workshop/datasets/sim_so101_blocktask"
[ -d "$LOCAL_DS/meta" ] || { echo "❌ 로컬 데이터셋 없음: $LOCAL_DS (먼저 녹화하세요)"; exit 1; }

EP=$(python3 -c "import json;print(json.load(open('$LOCAL_DS/meta/info.json'))['total_episodes'])" 2>/dev/null || echo "?")
echo "로컬 데이터셋: $LOCAL_DS (에피소드 $EP개)"
echo

echo "[1/3] 5090으로 전송 (rsync)..."
ssh 5090 'mkdir -p ~/gr00tn16_ws/sim_data/heongyu'
rsync -a --delete "$LOCAL_DS/" "5090:~/gr00tn16_ws/sim_data/heongyu/sim_so101_blocktask/"
scp -q blocktask_modality.json _blocktask_convert_inner.sh 5090:/tmp/

echo "[2/3] 5090에서 변환 + modality + stats (real-robot-train8 컨테이너)..."
ssh 5090 'docker run --rm --network host \
  -v $HOME/gr00tn16_ws/sim_data:/data \
  -v $HOME/gr00t_remote/Isaac-GR00T:/gr00t \
  -v $HOME/gr00t_remote/scripts:/gscripts \
  -v /tmp/blocktask_modality.json:/tmp/blocktask_modality.json:ro \
  -v /tmp/_blocktask_convert_inner.sh:/tmp/inner.sh:ro \
  real-robot-train8 bash /tmp/inner.sh'

echo
echo "[3/3] 완료 ✅"
echo "  GR00T용 v2.1 데이터: 5090:~/gr00tn16_ws/sim_data/heongyu/sim_so101_blocktask"
echo "  v3.0 백업:          5090:~/gr00tn16_ws/sim_data/heongyu/sim_so101_blocktask_v3.0"
echo
echo "다음(학습): 5090에서 train_gr00t_sim_n16_8bit.sh의 --dataset-path를"
echo "  /data/heongyu/sim_so101_blocktask 로 지정해 N1.6 8-bit 학습."
