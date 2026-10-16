#!/usr/bin/env bash
# v4 학습셋(200ep) 준비 — 로컬 v3.0 세션들을 5090으로 보내 v2.1로 변환하고, 선별 병합한다.
#
# 구성 (근접 비율 54.5%, 자연 분포 43.2% 대비 1.26배 오버샘플):
#   · sim_so101_blocktask_v3        100ep  (5090에 이미 v2.1로 존재, 근접 19)
#   · 잔여(v3_3+v3_4) 중 근접 우선   35ep  (근접 35)   ← selected_35_near.txt
#   · sim_so101_blocktask_v4_near_3  65ep  (근접 55)
#
# 왜 231ep 전부를 안 쓰나: 오래된 '원거리' 데이터가 분모만 키워 근접 비율을 희석시킨다
#   (295ep면 39%, 200ep면 54.5%). 원거리는 이미 SR 83~88%라 데이터 양이 병목이 아니다.
#
# 사용: ./prepare_blocktask_v4_200.sh [단계]
#   all(기본) | send | convert | merge | check
set -euo pipefail
cd "$(dirname "$0")"
STAGE="${1:-all}"

LOCAL_DS="$HOME/blocktask_ws/Sim-to-Real-SO-101-Workshop/datasets"
REMOTE="~/gr00tn16_ws/sim_data/heongyu"
OUT="sim_so101_blocktask_v4_200"
SESSIONS=(sim_so101_blocktask_v3_3 sim_so101_blocktask_v3_4 sim_so101_blocktask_v4_near_3)
SEL="selected_35_near.txt"

[ -f "$SEL" ] || { echo "❌ $SEL 없음 — analyze_dataset_geometry.py 를 먼저 실행"; exit 1; }

send() {
  echo "▶ [1/4] 로컬 → 5090 전송"
  ssh 5090 "mkdir -p $REMOTE"
  for s in "${SESSIONS[@]}"; do
    [ -d "$LOCAL_DS/$s/meta" ] || { echo "  ❌ 없음: $s"; exit 1; }
    n=$(ls "$LOCAL_DS/$s/videos/observation.images.external_D455/chunk-000/"*.mp4 2>/dev/null | wc -l)
    echo "  · $s (${n}ep)"
    # 이전 변환이 남긴 root 소유 결과 정리(rsync Permission denied 방지)
    ssh 5090 "docker run --rm --entrypoint /bin/bash -v \$HOME/gr00tn16_ws/sim_data:/d real-robot-train8 \
      -c 'rm -rf /d/heongyu/$s /d/heongyu/${s}_v3.0'" >/dev/null 2>&1 || true
    # images/ = recorder 임시 PNG(mp4 인코딩 후 삭제) → 제외
    rsync -a --delete --exclude='images/' "$LOCAL_DS/$s/" "5090:$REMOTE/$s/" \
      || { rc=$?; [ "$rc" = 24 ] && echo "    (임시파일 vanished — 무시)" || exit $rc; }
  done
}

convert() {
  echo "▶ [2/4] 5090에서 v3.0 → v2.1 변환"
  scp -q blocktask_modality.json 5090:/tmp/
  for s in "${SESSIONS[@]}"; do
    echo "  · $s"
    ssh 5090 "docker run --rm --network host \
      -v \$HOME/gr00tn16_ws/sim_data:/data \
      -v \$HOME/gr00t_remote/Isaac-GR00T:/gr00t \
      -v \$HOME/gr00t_remote/scripts:/gscripts \
      -v /tmp/blocktask_modality.json:/tmp/modality.json:ro \
      real-robot-train8 bash -c '
        set -e
        python /gr00t/scripts/lerobot_conversion/convert_v3_to_v2.py --repo-id heongyu/$s --root /data
        cp /tmp/modality.json /data/heongyu/$s/meta/modality.json
        python /gscripts/fix_stats_for_gr00t.py /data/heongyu/$s
        python -c \"import json;i=json.load(open(\\\"/data/heongyu/$s/meta/info.json\\\"));print(\\\"    ->\\\",i[\\\"codebase_version\\\"],i[\\\"total_episodes\\\"],\\\"ep\\\")\"
      '"
  done
}

merge() {
  echo "▶ [3/4] 선별 병합 → $OUT"
  # 선별 목록을 '세션:파일번호' 로 전달. 변환 후 에피소드 인덱스 = 원본 file-NNN 번호와 1:1
  # (v3.0에서 파일당 에피소드 1개임을 확인: meta/episodes/*.parquet 개수 == total_episodes).
  awk '!/^#/ && NF {print $1}' "$SEL" | sed 's#^#sim_so101_blocktask_#' > /tmp/v4_select.txt
  echo "  선별 $(wc -l < /tmp/v4_select.txt)개 (잔여에서 근접 우선)"
  scp -q /tmp/v4_select.txt merge_blocktask_select.py 5090:/tmp/
  ssh 5090 "docker run --rm \
    -v \$HOME/gr00tn16_ws/sim_data:/data \
    -v /tmp/merge_blocktask_select.py:/tmp/merge.py:ro \
    -v /tmp/v4_select.txt:/tmp/select.txt:ro \
    real-robot-train8 python /tmp/merge.py $OUT /tmp/select.txt \
      sim_so101_blocktask_v3:ALL \
      sim_so101_blocktask_v3_3:SELECT \
      sim_so101_blocktask_v3_4:SELECT \
      sim_so101_blocktask_v4_near_3:ALL"

  # merge 스크립트는 modality/stats 후처리를 하지 않는다(세션 변환 때 한 것은 세션별 파일).
  # 병합본에 다시 적용하지 않으면 GR00T가 modality.json을 못 찾고, stats의 count 때문에 실패한다.
  echo "  · 병합본 후처리 (modality.json + stats count 제거)"
  ssh 5090 "docker run --rm \
    -v \$HOME/gr00tn16_ws/sim_data:/data \
    -v \$HOME/gr00t_remote/scripts:/gscripts \
    -v /tmp/blocktask_modality.json:/tmp/modality.json:ro \
    --entrypoint bash real-robot-train8 -c '
      cp /tmp/modality.json /data/heongyu/$OUT/meta/modality.json
      python /gscripts/fix_stats_for_gr00t.py /data/heongyu/$OUT
    '"
}

check() {
  echo "▶ [4/4] 검증"
  # 컨테이너 안에서 heredoc을 쓰면 ssh→docker 인용 단계를 거치며 스크립트가 유실된다
  # (실측: 출력이 통째로 비었음). --entrypoint python -c 로 단순화한다.
  ssh 5090 'docker run --rm -v $HOME/gr00tn16_ws/sim_data:/data --entrypoint python real-robot-train8 -c "
import json,os,glob
D=\"/data/heongyu/'"$OUT"'\"
i=json.load(open(D+\"/meta/info.json\"))
print(\"  codebase:\",i[\"codebase_version\"],\"| ep:\",i[\"total_episodes\"],\"| frames:\",i[\"total_frames\"])
print(\"  modality.json:\", os.path.exists(D+\"/meta/modality.json\"))
st=json.load(open(D+\"/meta/stats.json\"))
print(\"  stats count 제거:\", \"count\" not in st.get(\"observation.state\",{}), \"(True면 정상)\")
for vk in sorted(os.listdir(D+\"/videos/chunk-000\")):
    print(\"  \",vk, len(glob.glob(D+\"/videos/chunk-000/\"+vk+\"/*.mp4\")))
print(\"  data parquet:\", len(glob.glob(D+\"/data/chunk-000/*.parquet\")))
print(\"  tasks:\", [json.loads(l)[\"task\"] for l in open(D+\"/meta/tasks.jsonl\")])
" 2>&1 | grep -vE "NVIDIA|license|WARNING|Toolkit|docs.nvidia|CUDA|^=|^$|By pulling|A copy"'
  echo
  echo "  epoch 정합 스텝: 200ep 기준 86k (v3 100ep 40k = 65.8 epoch과 동일)"
  echo "  다음: 5090에서 train_gr00t_blocktask_v4_200_n16_8bit.sh"
}

case "$STAGE" in
  send) send ;;
  convert) convert ;;
  merge) merge ;;
  check) check ;;
  all) send; convert; merge; check ;;
  *) echo "단계: all|send|convert|merge|check"; exit 1 ;;
esac
