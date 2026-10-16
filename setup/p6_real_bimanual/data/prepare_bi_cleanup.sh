#!/usr/bin/env bash
# 양팔 파일럿 학습셋 준비 — setup/p5_real_cleanup/prepare_cleanup_real.sh 의 bi 판.
#
# 단일팔과 다른 점 셋:
#   · 원본이 datasets/_train/bi_cleanup 에 있다
#   · 카메라 키가 left_top/left_wrist/right_wrist(3대) → modality 는
#     top/wrist_left/wrist_right (setup/p6_real_bimanual/gr00t/modality.json)
#   · 지시문 종류가 32종이다(물체 8 × 칸 4, 문형 1종) — gen_bi_plan.py 기준
#
# **진짜 게이트는 check 의 TASKS 줄 수**다. convert_v3_to_v2.py 가 task_index를
# 한 줄로 접으면(전부 0이 되면) 언어 학습 신호가 0인 데이터가 된다 — 단일팔
# cleanup_real 준비 때 쓰던 게이트를 그대로 가져온다.
#
# 사용: ./prepare_bi_cleanup.sh [단계]
#   all(기본) | send | convert | check
set -euo pipefail
cd "$(dirname "$0")"
STAGE="${1:-all}"

LOCAL_ROOT="${LOCAL_ROOT:-$HOME/blocktask_ws/Sim-to-Real-SO-101-Workshop/datasets/_train}"
DS="${DSNAME:-bi_cleanup}"
REMOTE="~/gr00tn16_ws/sim_data/heongyu"
MODALITY="../gr00t/modality.json"          # top/wrist_left/wrist_right
EXPECT_TASKS="${EXPECT_TASKS:-32}"          # gen_bi_plan.py 실측(물체 8 × 칸 4)
MIN_TASKS="${MIN_TASKS:-24}"

send() {
  echo "▶ [1/3] 로컬 → 5090 전송"
  SRC="$LOCAL_ROOT/$DS"
  [ -d "$SRC/meta" ] || { echo "  ❌ 로컬에 없음: $SRC"; exit 1; }
  n=$(python3 -c "import json;print(json.load(open('$SRC/meta/info.json'))['total_episodes'])")
  f=$(python3 -c "import json;print(json.load(open('$SRC/meta/info.json'))['total_frames'])")
  echo "  · $DS (${n}ep · ${f} frames)"

  ssh 5090 "mkdir -p $REMOTE"
  ssh 5090 "docker run --rm --entrypoint /bin/bash -v \$HOME/gr00tn16_ws/sim_data:/d real-robot-train8 \
    -c 'rm -rf /d/heongyu/$DS /d/heongyu/${DS}_v3.0'" >/dev/null 2>&1 || true

  rsync -a --delete --exclude='images/' "$SRC/" "5090:$REMOTE/$DS/" \
    || { rc=$?; [ "$rc" = 24 ] && echo "    (임시파일 vanished — 무시)" || exit $rc; }
  echo "  전송 완료"
  for f in calibration_snapshot.json collect_progress.txt rest_pose_bi.json; do
    [ -f "$SRC/$f" ] && scp -q "$SRC/$f" "5090:$REMOTE/$DS/" || true
  done
}

convert() {
  echo "▶ [2/3] 5090에서 v3.0 → GR00T v2.1 변환"
  [ -f "$MODALITY" ] || { echo "  ❌ modality 없음: $MODALITY"; exit 1; }
  scp -q "$MODALITY" 5090:/tmp/bi_cleanup_modality.json
  ssh 5090 "docker run --rm --network host \
    -v \$HOME/gr00tn16_ws/sim_data:/data \
    -v \$HOME/gr00t_remote/Isaac-GR00T:/gr00t \
    -v \$HOME/gr00t_remote/scripts:/gscripts \
    -v /tmp/bi_cleanup_modality.json:/tmp/modality.json:ro \
    real-robot-train8 bash -c '
      set -e
      python /gr00t/scripts/lerobot_conversion/convert_v3_to_v2.py --repo-id heongyu/$DS --root /data
      cp /tmp/modality.json /data/heongyu/$DS/meta/modality.json
      python /gscripts/fix_stats_for_gr00t.py /data/heongyu/$DS
    '"
  echo "  변환 완료"
}

check() {
  echo "▶ [3/3] 검증 — 학습 전 게이트"
  ssh 5090 'docker run --rm -v $HOME/gr00tn16_ws/sim_data:/data --entrypoint python real-robot-train8 -c "
import json,os,glob,collections,re
D=\"/data/heongyu/'"$DS"'\"
i=json.load(open(D+\"/meta/info.json\"))
print(\"  codebase:\",i[\"codebase_version\"],\"| ep:\",i[\"total_episodes\"],\"| frames:\",i[\"total_frames\"])
print(\"  modality.json:\", os.path.exists(D+\"/meta/modality.json\"))
st=json.load(open(D+\"/meta/stats.json\"))
print(\"  stats count 제거:\", \"count\" not in st.get(\"observation.state\",{}), \"(True면 정상)\")
for vk in sorted(os.listdir(D+\"/videos/chunk-000\")):
    print(\"  \",vk, len(glob.glob(D+\"/videos/chunk-000/\"+vk+\"/*.mp4\")))
print(\"  data parquet:\", len(glob.glob(D+\"/data/chunk-000/*.parquet\")))
T=[json.loads(l)[\"task\"] for l in open(D+\"/meta/tasks.jsonl\")]
print(\"  TASKS:\", len(T))
c=collections.Counter()
for t in T:
    m=re.search(r\"\\b(black|white|cyan|pink) bin\\b\", t)
    c[m.group(1) if m else \"(미지정)\"]+=1
print(\"  BINS:\", dict(c))
for t in T[:3]: print(\"    -\", t)
if len(T)>3: print(\"    - ... (+%d)\"%(len(T)-3))
" 2>&1 | grep -vE "NVIDIA|license|WARNING|Toolkit|docs.nvidia|CUDA|^=|^$|By pulling|A copy"' | tee /tmp/bi_cleanup_check.txt

  echo
  T=$(awk '/^  TASKS:/{print $2}' /tmp/bi_cleanup_check.txt)
  if [ -z "$T" ]; then
    echo "  ❌ tasks.jsonl을 못 읽었다 — 변환이 끝나지 않았을 수 있다"; exit 2
  elif [ "$T" = "1" ]; then
    echo "  ❌❌ 지시문이 1줄로 접혔다 — **이 데이터로 학습하면 언어 신호가 0이다.**"
    echo "       변환 경로(convert_v3_to_v2.py의 task_index 처리)부터 고칠 것. 학습 금지."
    exit 3
  elif [ "$T" -lt "$MIN_TASKS" ]; then
    echo "  ⚠️  지시문 ${T}종 — 기대(${EXPECT_TASKS})보다 크게 적다. 변환에서 합쳐졌는지 확인할 것"
    exit 3
  else
    echo "  ✅ 지시문 ${T}종이 살아남았다 (기대 ${EXPECT_TASKS})"
  fi

  _MISS=""
  for _c in black cyan pink white; do
    grep -q "'$_c'" /tmp/bi_cleanup_check.txt || _MISS="$_MISS $_c"
  done
  if [ -z "$_MISS" ]; then
    echo "  ✅ 목적지 단어 4색(black·cyan·pink·white) 전부 살아 있다"
  else
    echo "  ❌ 목적지 단어가 빠졌다:$_MISS — BINS 줄 확인 (그 칸은 목적지 축을 못 잰다)"
    exit 3
  fi

  _VMISS=""
  for _v in observation.images.left_top observation.images.left_wrist observation.images.right_wrist; do
    grep -q "^   $_v " /tmp/bi_cleanup_check.txt || _VMISS="$_VMISS $_v"
  done
  if [ -z "$_VMISS" ]; then
    echo "  ✅ 카메라 3대(left_top·left_wrist·right_wrist) 전부 변환됐다"
  else
    echo "  ❌ 카메라 변환 누락:$_VMISS"
    exit 3
  fi

  echo
  echo "  다음: 스모크 학습(SMOKE=1 ./train_bi_cleanup.sh)으로 modality config·변환 파이프라인이"
  echo "  안 깨지는지부터 확인할 것(bi_manipulator_plan.md §5 step 6)."
}

case "$STAGE" in
  send) send ;;
  convert) convert ;;
  check) check ;;
  all) send; convert; check ;;
  *) echo "단계: all|send|convert|check"; exit 1 ;;
esac
