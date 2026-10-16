#!/usr/bin/env bash
# Phase F: 실기 블록 데이터(로컬 v3.0) → GR00T N1.6용 v2.1 준비 후 5090로 전송(co-training용).
# sim 데이터와 같은 위치(~/gr00tn16_ws/sim_data/heongyu/)에 두어 co-train에서 함께 로드.
# 사용법: (record_blocktask_real*.sh로 수집 후)
#   ./prepare_blocktask_real_gr00t.sh                      # so101_blocktask_real (기존 50ep)
#   DSNAME=so101_blocktask_real_v2 ./prepare_blocktask_real_gr00t.sh   # 박스 다양성 60ep
set -euo pipefail
cd "$(dirname "$0")"

DSNAME="${DSNAME:-so101_blocktask_real}"
LOCAL_DS="$HOME/.cache/huggingface/lerobot/heongyu/$DSNAME"
[ -d "$LOCAL_DS/meta" ] || { echo "❌ 로컬 실기 데이터셋 없음: $LOCAL_DS"; exit 1; }

EP=$(python3 -c "import json;print(json.load(open('$LOCAL_DS/meta/info.json'))['total_episodes'])" 2>/dev/null || echo "?")
echo "로컬 실기 데이터셋: $DSNAME (에피소드 $EP개)"

echo "[1/3] 5090으로 전송 (rsync, 임시 images/ 제외)..."
ssh 5090 'mkdir -p ~/gr00tn16_ws/sim_data/heongyu'
ssh 5090 "docker run --rm --entrypoint /bin/bash -v \$HOME/gr00tn16_ws/sim_data:/d real-robot-train8 -c 'rm -rf /d/heongyu/$DSNAME /d/heongyu/${DSNAME}_v3.0'" 2>/dev/null || true
rsync -a --delete --exclude='images/' "$LOCAL_DS/" \
  "5090:~/gr00tn16_ws/sim_data/heongyu/$DSNAME/" \
  || { rc=$?; [ "$rc" = 24 ] && echo "  (일부 임시파일 vanished — 무시)" || exit $rc; }
scp -q blocktask_real_modality.json _blocktask_real_convert_inner.sh 5090:/tmp/

echo "[2/3] 5090에서 변환 + modality + stats..."
ssh 5090 'docker run --rm --network host \
  -v $HOME/gr00tn16_ws/sim_data:/data \
  -v $HOME/gr00t_remote/Isaac-GR00T:/gr00t \
  -v $HOME/gr00t_remote/scripts:/gscripts \
  -v /tmp/blocktask_real_modality.json:/tmp/blocktask_real_modality.json:ro \
  -v /tmp/_blocktask_real_convert_inner.sh:/tmp/inner.sh:ro \
  -e DSNAME='"$DSNAME"' \
  real-robot-train8 bash /tmp/inner.sh'

echo
echo "[3/3] 완료 ✅  실기 v2.1: 5090:~/gr00tn16_ws/sim_data/heongyu/$DSNAME"
echo "다음(co-training): 5090에서 train_gr00t_blocktask_cotrain_n16_8bit.sh 실행"
