#!/usr/bin/env bash
# 실기 cleanup 학습셋 준비 — 로컬 v3.0 수집본을 5090으로 보내 GR00T v2.1로 변환한다.
#
# sim 준비(prepare_blocktask_lang.sh)와 같은 구조지만 세 가지가 다르다:
#   · 원본이 datasets/_train/cleanup_real 에 있다(sim 은 datasets/ 바로 아래)
#   · 카메라 키가 top/wrist 다 → modality 는 top→front, wrist→wrist
#   · 칸 4개(black·cyan·pink·white)를 모두 쓴다 → 네 단어가 다 살아남았는지 본다
#
# **진짜 게이트는 check 의 TASKS 줄 수**다.
#   250ep 에 서로 다른 지시문이 40종 들어 있다(물체 10 × 칸 4, 문형은 1종). 변환이 태스크를 한 줄로 접으면
#   (task_index 가 전부 0이 되면) 모든 에피소드가 같은 문장을 갖게 되고,
#   그 데이터로 학습하면 **언어 학습 신호가 0**이다 — 학습 시간을 통째로 버린다.
#   sim 에서 실제로 이 사고를 대비해 만든 게이트이고, 여기서도 같다.
#
# 사용: ./prepare_cleanup_real.sh [단계]
#   all(기본) | send | convert | check
set -euo pipefail
cd "$(dirname "$0")"
STAGE="${1:-all}"

LOCAL_ROOT="${LOCAL_ROOT:-$HOME/blocktask_ws/Sim-to-Real-SO-101-Workshop/datasets/_train}"
DS="${DSNAME:-cleanup_real}"
REMOTE="~/gr00tn16_ws/sim_data/heongyu"
MODALITY="../p1_p4_sim/t1_task/blocktask_real_modality.json"   # top→front, wrist→wrist
EXPECT_TASKS="${EXPECT_TASKS:-40}"   # v2 250ep 실측(물체 10 × 칸 4). 1이면 변환이 태스크를 접은 것
MIN_TASKS="${MIN_TASKS:-30}"

send() {
  echo "▶ [1/3] 로컬 → 5090 전송"
  SRC="$LOCAL_ROOT/$DS"
  [ -d "$SRC/meta" ] || { echo "  ❌ 로컬에 없음: $SRC"; exit 1; }
  n=$(python3 -c "import json;print(json.load(open('$SRC/meta/info.json'))['total_episodes'])")
  f=$(python3 -c "import json;print(json.load(open('$SRC/meta/info.json'))['total_frames'])")
  echo "  · $DS (${n}ep · ${f} frames)"

  ssh 5090 "mkdir -p $REMOTE"
  # 이전 변환이 남긴 root 소유 결과 정리 — 안 하면 rsync 가 Permission denied 로 막힌다
  # (컨테이너가 root 로 돌며 만든 파일이다. 로컬 캐시에서도 같은 일을 겪었다.)
  ssh 5090 "docker run --rm --entrypoint /bin/bash -v \$HOME/gr00tn16_ws/sim_data:/d real-robot-train8 \
    -c 'rm -rf /d/heongyu/$DS /d/heongyu/${DS}_v3.0'" >/dev/null 2>&1 || true

  # images/ = recorder 임시 PNG(mp4 인코딩 후 삭제) → 제외
  rsync -a --delete --exclude='images/' "$SRC/" "5090:$REMOTE/$DS/" \
    || { rc=$?; [ "$rc" = 24 ] && echo "    (임시파일 vanished — 무시)" || exit $rc; }
  echo "  전송 완료"
  # 출처 정보(캘리브레이션 지문·수집 진행 기록)도 같이 보낸다. 나중에 "이 체크포인트가
  # 어떤 캘리브레이션으로 모은 데이터인가"를 되짚을 수 있어야 한다.
  for f in calibration_snapshot.json collect_progress.txt; do
    [ -f "$SRC/$f" ] && scp -q "$SRC/$f" "5090:$REMOTE/$DS/" || true
  done
}

convert() {
  echo "▶ [2/3] 5090에서 v3.0 → GR00T v2.1 변환"
  [ -f "$MODALITY" ] || { echo "  ❌ modality 없음: $MODALITY"; exit 1; }
  scp -q "$MODALITY" 5090:/tmp/cleanup_modality.json
  ssh 5090 "docker run --rm --network host \
    -v \$HOME/gr00tn16_ws/sim_data:/data \
    -v \$HOME/gr00t_remote/Isaac-GR00T:/gr00t \
    -v \$HOME/gr00t_remote/scripts:/gscripts \
    -v /tmp/cleanup_modality.json:/tmp/modality.json:ro \
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
" 2>&1 | grep -vE "NVIDIA|license|WARNING|Toolkit|docs.nvidia|CUDA|^=|^$|By pulling|A copy"' | tee /tmp/cleanup_check.txt

  echo
  T=$(awk '/^  TASKS:/{print $2}' /tmp/cleanup_check.txt)
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

  # 1단계는 칸 2개만 쓴다. 목적지 단어가 둘 다 살아 있어야 목적지 축을 잴 수 있다.
  _MISS=""
  for _c in black cyan pink white; do
    grep -q "'$_c'" /tmp/cleanup_check.txt || _MISS="$_MISS $_c"
  done
  if [ -z "$_MISS" ]; then
    echo "  ✅ 목적지 단어 4색(black·cyan·pink·white) 전부 살아 있다"
  else
    echo "  ❌ 목적지 단어가 빠졌다:$_MISS — BINS 줄 확인 (그 칸은 목적지 축을 못 잰다)"
    exit 3
  fi

  echo
  echo "  다음: 학습 (파운데이션에서 새로). train_cleanup_real.sh 가 EPOCHS 로 step 을 계산한다"
  echo "    ⚠️ **파운데이션 모델에서 출발**할 것. sim 학습본에서 이어가면 안 된다 —"
  echo "       sim 1단계에서 이어학습은 우연 수준(22.5%)이었고 기존 성능까지 27%p 잃었다."
}

case "$STAGE" in
  send) send ;;
  convert) convert ;;
  check) check ;;
  all) send; convert; check ;;
  *) echo "단계: all|send|convert|check"; exit 1 ;;
esac
