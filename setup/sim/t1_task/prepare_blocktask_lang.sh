#!/usr/bin/env bash
# 언어 조건화 학습셋 준비 — 로컬 v3.0 수집본을 5090으로 보내 v2.1로 변환한다.
#
# v4_200 준비와 다른 점: **선별도 병합도 없다.** 한 세션(280ep)을 통째로 쓰므로
#   send → convert → check 세 단계뿐이다.
#
# 이 준비에서 진짜 게이트는 마지막 check의 **tasks.jsonl 줄 수**다.
#   수집본에는 서로 다른 지시문이 100종 들어 있다. 변환이 태스크를 한 줄로 접으면
#   (`task_index`가 전부 0이 되면) 모든 에피소드가 같은 문장을 갖게 되고,
#   그 데이터로 학습하면 **언어 학습 신호가 0**이다 — 19시간을 통째로 버린다.
#   1줄로 나오면 여기서 멈추고 변환 경로부터 고칠 것.
#
# 사용: ./prepare_blocktask_lang.sh [단계]
#   all(기본) | send | convert | check
set -euo pipefail
cd "$(dirname "$0")"
STAGE="${1:-all}"

LOCAL_DS="$HOME/blocktask_ws/Sim-to-Real-SO-101-Workshop/datasets"
REMOTE="~/gr00tn16_ws/sim_data/heongyu"
DS="${DSNAME:-sim_so101_blocktask_lang}"
EXPECT_TASKS="${EXPECT_TASKS:-100}"     # 수집 실측(2026-09-24). 1이면 변환이 태스크를 접은 것

send() {
  echo "▶ [1/3] 로컬 → 5090 전송"
  [ -d "$LOCAL_DS/$DS/meta" ] || { echo "  ❌ 로컬에 없음: $LOCAL_DS/$DS"; exit 1; }
  n=$(ls "$LOCAL_DS/$DS/videos/observation.images.external_D455/chunk-000/"*.mp4 2>/dev/null | wc -l)
  echo "  · $DS (${n}ep)"
  ssh 5090 "mkdir -p $REMOTE"
  # 이전 변환이 남긴 root 소유 결과 정리(rsync Permission denied 방지)
  ssh 5090 "docker run --rm --entrypoint /bin/bash -v \$HOME/gr00tn16_ws/sim_data:/d real-robot-train8 \
    -c 'rm -rf /d/heongyu/$DS /d/heongyu/${DS}_v3.0'" >/dev/null 2>&1 || true
  # images/ = recorder 임시 PNG(mp4 인코딩 후 삭제) → 제외
  rsync -a --delete --exclude='images/' "$LOCAL_DS/$DS/" "5090:$REMOTE/$DS/" \
    || { rc=$?; [ "$rc" = 24 ] && echo "    (임시파일 vanished — 무시)" || exit $rc; }
  echo "  전송 완료"
}

convert() {
  echo "▶ [2/3] 5090에서 v3.0 → v2.1 변환"
  scp -q blocktask_modality.json 5090:/tmp/
  ssh 5090 "docker run --rm --network host \
    -v \$HOME/gr00tn16_ws/sim_data:/data \
    -v \$HOME/gr00t_remote/Isaac-GR00T:/gr00t \
    -v \$HOME/gr00t_remote/scripts:/gscripts \
    -v /tmp/blocktask_modality.json:/tmp/modality.json:ro \
    real-robot-train8 bash -c '
      set -e
      python /gr00t/scripts/lerobot_conversion/convert_v3_to_v2.py --repo-id heongyu/$DS --root /data
      cp /tmp/modality.json /data/heongyu/$DS/meta/modality.json
      python /gscripts/fix_stats_for_gr00t.py /data/heongyu/$DS
      python -c \"import json;i=json.load(open(\\\"/data/heongyu/$DS/meta/info.json\\\"));print(\\\"    ->\\\",i[\\\"codebase_version\\\"],i[\\\"total_episodes\\\"],\\\"ep\\\")\"
    '"
}

check() {
  echo "▶ [3/3] 검증 — G3 게이트"
  # 컨테이너 안에서 heredoc을 쓰면 ssh→docker 인용 단계를 거치며 스크립트가 유실된다
  # (v4_200 준비에서 실측: 출력이 통째로 비었음). --entrypoint python -c 로 단순화한다.
  ssh 5090 'docker run --rm -v $HOME/gr00tn16_ws/sim_data:/data --entrypoint python real-robot-train8 -c "
import json,os,glob,collections
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
for t in T[:3]: print(\"    -\", t)
if len(T)>3: print(\"    - ... (+%d)\"%(len(T)-3))
" 2>&1 | grep -vE "NVIDIA|license|WARNING|Toolkit|docs.nvidia|CUDA|^=|^$|By pulling|A copy"' | tee /tmp/lang_check.txt

  echo
  T=$(awk '/^  TASKS:/{print $2}' /tmp/lang_check.txt)
  if [ -z "$T" ]; then
    echo "  ❌ tasks.jsonl을 못 읽었다 — 변환이 끝나지 않았을 수 있다"; exit 2
  elif [ "$T" = "1" ]; then
    echo "  ❌❌ 지시문이 1줄로 접혔다 — **이 데이터로 학습하면 언어 신호가 0이다.**"
    echo "       변환 경로(convert_v3_to_v2.py의 task_index 처리)부터 고칠 것. 학습 금지."
    exit 3
  elif [ "$T" -lt 50 ]; then
    echo "  ⚠️  지시문 ${T}종 — 기대(${EXPECT_TASKS})보다 크게 적다. 변환에서 일부가 합쳐졌는지 확인할 것"
    exit 3
  else
    echo "  ✅ G3 통과 — 지시문 ${T}종이 살아남았다 (기대 ${EXPECT_TASKS})"
  fi
  echo
  echo "  다음:"
  echo "    1) 기준선 프로브 — 현 모델로 0°를 확인한다(이게 없으면 학습 후 수치를 주장할 수 없다)"
  echo "       5090에서 서버 기동 후:"
  echo "       python setup/gr00t/probe_language.py --dataset <이 데이터셋> --label v4_200@86k --out probe.json"
  echo "    2) train_gr00t_blocktask_lang_n16_8bit.sh (Run A, 25k step ≈ 19h)"
}

case "$STAGE" in
  send) send ;;
  convert) convert ;;
  check) check ;;
  all) send; convert; check ;;
  *) echo "단계: all|send|convert|check"; exit 1 ;;
esac
