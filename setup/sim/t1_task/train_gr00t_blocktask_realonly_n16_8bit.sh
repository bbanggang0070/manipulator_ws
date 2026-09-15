#!/usr/bin/env bash
# **실기 데이터만으로** 학습 — sim 혼합의 값어치를 재는 대조군. **5090에서 실행.**
#
# 왜 필요한가(2026-08-13, 보고서 §9-2 ③):
#   sim이 기여했다는 증거가 지금은 '제로샷 실패'뿐인데, 그것은 *sim 단독으로는 전이가
#   안 된다*를 보일 뿐 **sim+real > real 단독**을 보이지 않는다.
#   게다가 현재 sim은 digital twin이 아니라, 혼합으로 얻는 것은 궤적 다양성인데
#   지금 병목은 다양성이 아니라 **언어 조건화**다. 값어치를 직접 재야 한다.
#
# co-training 스크립트와의 차이는 **데이터뿐**이다:
#   · --dataset-path 를 실기로 주고 sim을 뺀다
#   · GR00T_COTRAIN_DATASET 미설정 → 데이터셋 1개
#   · lr·warmup·weight_decay·batch·grad-accum·save-steps 전부 동일하게 유지한다.
#     비교의 유일한 변수를 '데이터 구성'으로 남기기 위해서다.
#
# 스텝 산정: effective batch 64, 실기 38,362 frames
#   co-train 48k  → 실기 40.0 epoch (mix 1.0이라 표본의 절반)
#   real-only 25k → 실기 41.7 epoch  ← **실기 노출량 일치** 비교점 (24k는 저장 지점이 아니다)
#   real-only 48k → 실기 80.1 epoch  ← **총 연산량 일치** 비교점
#   48k로 한 번 돌리고 checkpoint-25000 / 48000 을 각각 평가하면 두 비교를 다 얻는다.
#   ※ save-steps 5000 · save-total-limit 6 이므로 남는 것은 25k~48k 6개다.
#   한쪽만 보면 "베이스라인을 덜 학습시켰다" 또는 "57ep을 80 epoch 돌려 과적합"이라는
#   반론에 각각 막힌다.
#
# 소요: 약 36시간(2.69초/스텝 실측). 24k 지점은 약 18시간.
# ⚠ 학습 중에는 5090이 묶여 실기 추론 서버를 띄울 수 없다.
#
# 사용(5090): ~/train_gr00t_blocktask_realonly_n16_8bit.sh [DATA_ROOT] [STEPS]
set -e
DATA_ROOT="${1:-$HOME/gr00tn16_ws/sim_data}"
[ -z "$DATA_ROOT" ] && DATA_ROOT="$HOME/gr00tn16_ws/sim_data"
STEPS="${2:-48000}"
OUT_NAME="gr00t_blocktask_realonly_n16_8bit"
SIM_DS="sim_so101_blocktask_v4_200"
REAL_DS="so101_blocktask_real_v2_57"   # 재시도 섞인 ep2·33·49 제외본
LAUNCH="$HOME/gr00tn16_ws/launch_cotrain.py"

[ -f "$LAUNCH" ] || { echo "❌ launch_cotrain.py 없음: $LAUNCH"; exit 1; }
for d in "$REAL_DS"; do
  [ -d "$DATA_ROOT/heongyu/$d/meta" ] || { echo "❌ 데이터셋 없음: $d"; exit 1; }
  # 병합·변환 후처리를 빠뜨리면 학습이 한참 뒤에야 실패한다 → 선확인
  [ -f "$DATA_ROOT/heongyu/$d/meta/modality.json" ] || { echo "❌ $d: modality.json 없음"; exit 1; }
  python3 - "$DATA_ROOT/heongyu/$d" <<'PY' || exit 1
import json, sys
d = sys.argv[1]
if "count" in json.load(open(f"{d}/meta/stats.json")).get("observation.state", {}):
    sys.exit(f"❌ {d}: stats.json에 count가 남아 있다 (fix_stats_for_gr00t.py 미적용)")
i = json.load(open(f"{d}/meta/info.json"))
print(f"  ✅ {d.split('/')[-1]}: {i['codebase_version']} · {i['total_episodes']}ep · {i['total_frames']}f")
PY
done

if docker ps --format '{{.Names}}' | grep -q '^gr00t-train8$'; then
  echo "❌ gr00t-train8 이 이미 실행 중입니다 (진행 중인 학습을 덮어쓰지 않도록 중단)."
  echo "   진행 상황: docker logs --tail 5 gr00t-train8"
  exit 1
fi

echo "  스텝 $STEPS · 실기 단독(sim 미사용)"
docker run -d --name gr00t-train8 --rm --gpus all --network host --ipc=host \
  -e PYTHONUNBUFFERED=1 -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
  -e HF_TOKEN="$(cat $HOME/.cache/huggingface/token 2>/dev/null)" \
  -v "$DATA_ROOT:/data" \
  -v "$HOME/gr00tn16_ws/checkpoints:/workspace/models" \
  -v "$HOME/gr00tn16_ws/hf_cache_container:/root/.cache/huggingface" \
  -v "$LAUNCH:/tmp/launch_cotrain.py:ro" \
  real-robot-train8 \
  bash -c "cd /Isaac-GR00T && python3 /tmp/launch_cotrain.py \
    --base-model-path nvidia/GR00T-N1.6-3B \
    --dataset-path /data/heongyu/$REAL_DS \
    --modality-config-path examples/SO100/so100_config.py \
    --embodiment-tag NEW_EMBODIMENT --num-gpus 1 \
    --output-dir /workspace/models/$OUT_NAME \
    --save-steps 5000 --save-total-limit 6 --max-steps $STEPS \
    --warmup-ratio 0.05 --weight-decay 1e-5 --learning-rate 1e-4 \
    --global-batch-size 2 --gradient-accumulation-steps 32 \
    --color-jitter-params brightness 0.3 contrast 0.4 saturation 0.5 hue 0.08 \
    --dataloader-num-workers 8"

echo
echo "real-only 학습 시작 (gr00t-train8). 실기=$REAL_DS 단독"
echo "  로그: docker logs -f gr00t-train8"
echo "  출력: ~/gr00tn16_ws/checkpoints/$OUT_NAME"
echo
echo "완주 후 실기 배포:"
echo "  ~/serve_blocktask_n16_5090.sh $OUT_NAME/checkpoint-$STEPS start"
echo "  ⚠ 배포 전 카메라 정렬 확인: rerun_cam_align.py (기준 sim_v4)"
