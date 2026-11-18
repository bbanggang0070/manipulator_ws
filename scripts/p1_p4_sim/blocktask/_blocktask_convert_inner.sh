#!/bin/bash
# real-robot-train8 컨테이너 내부에서 실행 (prepare_blocktask_gr00t.sh가 호출).
# v3.0 블록 데이터셋 → GR00T N1.6용 v2.1 (변환 + modality.json + stats count 수정).
set -e
DS=/data/heongyu/sim_so101_blocktask

echo "== [1] v3.0 → v2.1 변환 (원본 경로에 v2.1, _v3.0 백업 생성) =="
python /gr00t/scripts/lerobot_conversion/convert_v3_to_v2.py \
  --repo-id heongyu/sim_so101_blocktask --root /data

echo "== [2] modality.json 배치 (external_D455→front, ego→wrist) =="
cp /tmp/blocktask_modality.json "$DS/meta/modality.json"

echo "== [3] stats.json count 제거 (GR00T 호환) =="
python /gscripts/fix_stats_for_gr00t.py "$DS"

echo "== [4] 결과 확인 =="
python - <<PY
import json, os
info = json.load(open("$DS/meta/info.json"))
print("codebase_version:", info.get("codebase_version"), "| episodes:", info.get("total_episodes"))
print("features:", [k for k in info.get("features", {})])
print("modality.json:", os.path.exists("$DS/meta/modality.json"))
st = json.load(open("$DS/meta/stats.json"))
print("stats state has count:", "count" in st.get("observation.state", {}), "(False면 정상)")
PY
echo "== 완료: $DS (GR00T v2.1 준비됨) =="
