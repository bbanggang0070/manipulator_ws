#!/usr/bin/env bash
# GR00T N1.6 8-bit sim 학습 — blocktask **v4_200** (근접 보강 200ep). **5090에서 실행.**
#
# v3(100ep, 40k)가 학습 분포에서 61~67%에 그친 원인을 좌표 기록으로 규명한 결과:
#   블록이 박스에 **가까울수록** SR이 단조 하락 (<0.12m 18% / 0.12~0.18 50% / ≥0.25 88%).
#   그런데 수집 때 겹침 ep를 빼면서 **유효 근접 구간까지 걸러져** 학습 근접 비율이
#   19.2%(씬의 자연 분포는 43.2%)뿐이었다. → 그 구멍만 메운 데이터셋이 v4_200이다.
#
#   데이터: ~/gr00tn16_ws/sim_data/heongyu/sim_so101_blocktask_v4_200  (200ep, 82,951 frames)
#     · v3 기존 100ep            (근접 19)
#     · 잔여 131ep에서 근접 우선 35ep (근접 35)  ← selected_35_near.txt
#     · v4 신규 타깃 수집 65ep    (근접 55)
#     = 근접 109/200 = **54.5%** (v3의 19.2% → 2.8배, 자연 분포 대비 1.26배 오버샘플)
#     원거리는 91ep로 v3의 80ep보다 많아 **원거리 퇴행 위험도 통제**된다.
#
#   증강·하이퍼파라미터: v3와 **완전 동일** (color jitter b0.3 c0.4 s0.5 h0.08, lr 1e-4 cosine,
#     warmup 5%, effective batch 64 = 2 × grad_accum 32) → 변수를 데이터 하나로 둔다.
#   워커: dataloader 8 (v3는 4. v3 학습 중 GPU util 19%로 로딩 병목 관찰 → 상향)
#
# ⚠️ 스텝은 **86k**가 기본이다 (40k 아님).
#   effective batch 64 → 40k steps = 2.56M 샘플.
#     v3 (100ep,  38,906 frames) @40k → 65.8 epoch
#     v4 (200ep,  82,951 frames) @40k → **30.8 epoch**  ← 절반. 그대로 두면 더 언더핏된다
#     v4 (200ep)                 @86k → **66.3 epoch**  ← v3와 정합 ✅
#   "데이터를 늘렸는데 성능이 떨어졌다"는 결과의 흔한 원인이 이 epoch 부족이다.
#
#   소요: v3 실측 1,333 step/h 기준 약 **65시간**.
#
# ※ resume 대신 신규 학습인 이유: cosine LR이 40k에서 0으로 완주해 resume은 warm restart가
#   되고, GR00T는 ShardedMixtureDataset(IterableDataset)이라 trainer 주석대로
#   "stateful samplers rely on global_step" — **데이터셋이 바뀌면 샘플러 상태가 어긋난다.**
#   상세: manipulator_md/sim/training_plan.md §2
#
# 사용법(5090): ~/train_gr00t_blocktask_v4_200_n16_8bit.sh [DATA_ROOT] [STEPS]
set -e
DATA_ROOT="${1:-$HOME/gr00tn16_ws/sim_data}"
STEPS="${2:-86000}"
OUT_NAME="gr00t_blocktask_v4_200_n16_8bit"
DS="$DATA_ROOT/heongyu/sim_so101_blocktask_v4_200"

[ -d "$DS/meta" ] || { echo "❌ v4_200 데이터셋 없음: $DS (prepare_blocktask_v4_200.sh 먼저)"; exit 1; }
# 병합 후처리를 빠뜨리면 학습이 한참 뒤에야 실패한다(merge 스크립트는 이걸 안 한다) → 선확인
[ -f "$DS/meta/modality.json" ] || { echo "❌ modality.json 없음 — prepare 스크립트의 merge 단계 후처리 누락"; exit 1; }
python3 - "$DS" <<'PY' || exit 1
import json, sys
d = sys.argv[1]
st = json.load(open(f"{d}/meta/stats.json"))
if "count" in st.get("observation.state", {}):
    sys.exit("❌ stats.json에 count가 남아 있다 — fix_stats_for_gr00t.py 미적용")
i = json.load(open(f"{d}/meta/info.json"))
print(f"  데이터셋 확인: {i['codebase_version']} · {i['total_episodes']}ep · {i['total_frames']} frames")
PY

# ⚠️ 학습 컨테이너가 이미 돌고 있으면 중단시키지 않고 알림만 (진행 중 학습 덮어쓰기 방지)
if docker ps --format '{{.Names}}' | grep -q '^gr00t-train8$'; then
  echo "❌ gr00t-train8 이 이미 실행 중입니다 (진행 중인 학습을 덮어쓰지 않도록 중단)."
  echo "   진행 상황: docker logs --tail 5 gr00t-train8"
  echo "   정말 교체하려면: docker rm -f gr00t-train8  후 다시 실행하세요."
  exit 1
fi

FRAMES=$(python3 -c "import json;print(json.load(open('$DS/meta/info.json'))['total_frames'])")
echo "  스텝 $STEPS × batch 64 = $((STEPS*64)) 샘플 → 약 $((STEPS*64/FRAMES)) epoch"

docker run -d --name gr00t-train8 --rm --gpus all --network host --ipc=host \
  -e PYTHONUNBUFFERED=1 -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
  -e HF_TOKEN="$(cat $HOME/.cache/huggingface/token 2>/dev/null)" \
  -v "$DATA_ROOT:/data" \
  -v "$HOME/gr00tn16_ws/checkpoints:/workspace/models" \
  -v "$HOME/gr00tn16_ws/hf_cache_container:/root/.cache/huggingface" \
  real-robot-train8 \
  bash -c "cd /Isaac-GR00T && python3 gr00t/experiment/launch_finetune.py \
    --base-model-path nvidia/GR00T-N1.6-3B \
    --dataset-path /data/heongyu/sim_so101_blocktask_v4_200 \
    --modality-config-path examples/SO100/so100_config.py \
    --embodiment-tag NEW_EMBODIMENT --num-gpus 1 \
    --output-dir /workspace/models/$OUT_NAME \
    --save-steps 5000 --save-total-limit 8 --max-steps $STEPS \
    --warmup-ratio 0.05 --weight-decay 1e-5 --learning-rate 1e-4 \
    --global-batch-size 2 --gradient-accumulation-steps 32 \
    --color-jitter-params brightness 0.3 contrast 0.4 saturation 0.5 hue 0.08 \
    --dataloader-num-workers 8"

echo
echo "v4_200 N1.6 8-bit 학습 시작 (gr00t-train8, ${STEPS} steps ≈ 65h)"
echo "  로그: docker logs -f gr00t-train8"
echo "  출력: ~/gr00tn16_ws/checkpoints/$OUT_NAME"
echo
echo "평가(무인, 사람 불필요):"
echo "  for s in 21 22; do ~/blocktask_headless_scenes.sh full 45 \$s; done"
echo "  ※ MODEL 환경변수로 체크포인트 지정: MODEL=$OUT_NAME/checkpoint-$STEPS"
echo "  판정: full ≥80% · 근접(<0.18m) ≥70% · 원거리 유지 ≥80% · OOD ≥70%"
