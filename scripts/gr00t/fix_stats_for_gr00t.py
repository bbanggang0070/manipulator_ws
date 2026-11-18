"""v3→v2 변환된 stats.json을 GR00T n1d5 호환으로 수정.

GR00T dataset.py _get_metadata는 state/action의 모든 stat 항목에 차원 슬라이싱
(stat[start:end])을 적용하는데, 변환본 stats.json의 `count`는 [1]이라
IndexError 발생(2026-07-15 실측). GR00T 스키마(max/min/mean/std/q01/q99)에
없는 스칼라 `count`를 state/action 항목에서 제거한다.

사용: python3 fix_stats_for_gr00t.py <dataset_root>
"""
import json, sys
p = sys.argv[1] + "/meta/stats.json"
s = json.load(open(p))
removed = []
for key in ("observation.state", "action"):
    if key in s and "count" in s[key]:
        del s[key]["count"]
        removed.append(key)
json.dump(s, open(p, "w"), indent=4)
print(f"count 제거: {removed} -> {p}")
