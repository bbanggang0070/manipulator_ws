"""양팔 **물체 대조** 추가 수집 계획표 — 기존 300행 뒤에 이어 붙인다.

왜: 300ep 계획표(gen_bi_plan.py)의 대응쌍·4연속 그룹은 전부 "물체는 그대로, 목적지만
바꿔" 다시 찍었다(목적지 대조 56그룹, 물체 대조 0그룹). 그래서 목적지 정확도는 97%까지
올랐지만 물체는 데이터를 두 배로 늘려도 50% 근처에 머물렀다 — 지시문의 물체 단어가 바뀌면
행동이 바뀌어야 한다는 신호를 받은 적이 없다. 고정 SigLIP2 프로브로는 마커 색·물체를
97~100% 구분하므로 정보는 이미 화면에 있다. 평가 A·B에서 헷갈린 건 거의 전부 마커끼리,
glue stick ↔ 마커였다.

그래서 이 계획표의 그룹은 **같은 배치에서 지시 물체만 바꿔** 2~3번 찍는다.
목적지 칸은 그룹 안에서 고정 — 지시문에서 바뀌는 단어가 물체 하나뿐이도록.

그룹 종류 (마커 비교 비중을 높게):
  mk3   마커 3색(+방해물 0~1) — red·blue·black 를 한 번씩 집는다 (3ep)
  mk2   마커 2색 + 방해물 1~2 — 두 마커를 한 번씩 (2ep)
  glue  glue stick + 마커 1~2 (+방해물 0~1) — glue 와 마커를 한 번씩 (2~3ep)
  other 마커 1 + 나머지 물체 2 — 세 물체를 한 번씩 (3ep, 마커 편향 방지용)

물체 위치: 중앙 물체만 집는 편향(평가 A)을 끊기 위해 물체마다 화면 기준 영역
(왼·가운데·오른)을 정해 준다. 마커별·타깃별로 영역이 고르게 돌아가도록 배정한다.

KEEP 행: 직전 에피소드에서 칸에 넣은 물체를 **원래 자리로 되돌린 뒤** 찍는다
(나머지 물체는 건드리지 않는다).

사용:
  python3 gen_bi_contrast_plan.py            # bi_cleanup_plan_400.csv (앞 300행 그대로 + 301~400행)
  PLAN=~/manipulator_ws/manipulator_md/p6_real_bimanual/bi_cleanup_plan_400.csv ./record_bi.sh
    → collect_progress.txt 가 300행까지라 301행부터 자동 재개
"""
import argparse
import csv
import os
import random
from collections import Counter

from gen_bi_plan import FIELDS, SLOTS, layout_str, pick_layouts

MARKERS = ["red marker", "blue marker", "black marker"]
OTHERS = ["yellow straw", "toothbrush", "eraser", "screwdriver"]
GLUE = "glue stick"
ZONES = ["왼", "가운데", "오른"]
POSE = {"eraser": "세워서"}
PLAN_DIR = os.path.expanduser("~/manipulator_ws/manipulator_md/p6_real_bimanual")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=f"{PLAN_DIR}/bi_cleanup_plan.csv")
    ap.add_argument("--out", default=f"{PLAN_DIR}/bi_cleanup_plan_400.csv")
    ap.add_argument("--mk3", type=int, default=14, help="마커 3색 그룹 수 (×3ep)")
    ap.add_argument("--mk2", type=int, default=6, help="마커 2색 그룹 수 (×2ep)")
    ap.add_argument("--glue", type=int, default=8, help="glue+마커 그룹 수 (×2~3ep)")
    ap.add_argument("--other", type=int, default=6, help="마커1+기타2 그룹 수 (×3ep)")
    ap.add_argument("--layout-every", type=int, default=50)
    ap.add_argument("--seed", type=int, default=20261019)
    ap.add_argument("--relayout-from", type=int, default=0,
                    help="이미 만든 --out 계획표에서 이 행부터 칸 배치만 다시 정한다 (앞 행·물체·목적지 색은 그대로)")
    ap.add_argument("--relayout-groups", type=int, default=3, help="--relayout-from 이후 몇 그룹마다 칸 배치를 바꿀지")
    a = ap.parse_args()
    if a.relayout_from:
        return relayout(a)
    rng = random.Random(a.seed)

    base = list(csv.DictReader(open(a.base)))
    ep0, g0 = int(base[-1]["ep"]), int(base[-1]["group"])
    last_layout = [s.split("번 ")[1] for s in base[-1]["layout"].split(" · ")]

    # ── 그룹(물체 구성과 집는 순서) 만들기 ──
    groups = []
    for _ in range(a.mk3):
        objs = MARKERS[:] + rng.sample(OTHERS + [GLUE], rng.choice([0, 1]))
        groups.append(("mk3", objs, rng.sample(MARKERS, 3)))
    pairs = [(x, y) for i, x in enumerate(MARKERS) for y in MARKERS[i + 1:]]
    for i in range(a.mk2):
        m = list(pairs[i % 3])
        objs = m + rng.sample(OTHERS + [GLUE], rng.choice([1, 2]))
        groups.append(("mk2", objs, rng.sample(m, 2)))
    for i in range(a.glue):
        m = rng.sample(MARKERS, 1 + i % 2)
        objs = [GLUE] + m + rng.sample(OTHERS, rng.choice([0, 1]))
        tg = [GLUE] + m
        groups.append(("glue", objs, rng.sample(tg, len(tg))))
    for i in range(a.other):
        oth = rng.sample(OTHERS, 2)
        objs = [MARKERS[i % 3]] + oth
        groups.append(("other", objs, rng.sample(objs, 3)))
    rng.shuffle(groups)

    # ── 영역 배정: 물체×영역, 타깃×영역 횟수가 고르게 ──
    oz, tz = Counter(), Counter()
    zone_of = []
    for kind, objs, tgts in groups:
        best, best_s = None, None
        for _ in range(200):
            zs = [ZONES[i % 3] for i in range(len(objs))]  # 4개면 한 영역에 2개
            rng.shuffle(zs)
            z = dict(zip(objs, zs))
            s = sum(oz[(o, z[o])] for o in objs) + 2 * sum(tz[z[t]] for t in tgts)
            if best_s is None or s < best_s:
                best, best_s = z, s
        for o in objs:
            oz[(o, best[o])] += 1
        for t in tgts:
            tz[best[t]] += 1
        zone_of.append(best)

    # ── 목적지: 그룹 안 고정, 그룹 간 색 고르게 ──
    cc = Counter()
    rows, ep = [], ep0
    for gi, ((kind, objs, tgts), zmap) in enumerate(zip(groups, zone_of)):
        lo = min(cc[c] for _, c in SLOTS)
        col = rng.choice([c for _, c in SLOTS if cc[c] == lo])
        cc[col] += len(tgts)
        place = " · ".join(f"{o} {zmap[o]}" + (f"({POSE[o]})" if o in POSE else "")
                           for o in sorted(objs, key=lambda o: ZONES.index(zmap[o])))
        for pos, t in enumerate(tgts, 1):
            ep += 1
            hint = f"화면 기준 {place}"
            if pos > 1:
                hint = f"직전 {tgts[pos - 2]} 원래 자리({zmap[tgts[pos - 2]]})로 되돌리기 · " + hint
            rows.append({
                "ep": ep, "group": g0 + gi + 1, "group_kind": f"obj-{kind}",
                "group_pos": f"{pos}/{len(tgts)}", "keep_layout": "NEW" if pos == 1 else "KEEP",
                "n_objects": len(objs), "objects": ", ".join(objs), "target": t,
                "slot": 0, "slot_color": col, "pose_hint": hint,
                "instruction": f"Put the {t} into the {col} bin",
            })

    # ── 칸 배치: 300행 마지막 배치에서 모든 색이 자리를 옮기도록 이어 간다 ──
    n_blocks = -(-len(rows) // a.layout_every)
    lays = pick_layouts(last_layout, n_blocks + 1, random.Random(a.seed + 1))[1:]
    b = 0
    for i, r in enumerate(rows):
        if b + 1 < n_blocks and i >= (b + 1) * a.layout_every and r["keep_layout"] == "NEW":
            b += 1
        r["slot"] = lays[b].index(r["slot_color"]) + 1
        r["layout"] = layout_str(lays[b])

    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(base)
        w.writerows(rows)
    report(rows, lays, a.out, ep0)


def relayout(a):
    """수집 도중 칸 배치를 더 자주 바꾸기 — relayout_from 행부터 N그룹마다 새 배치.

    그룹 경계에서만 바꾼다(그룹 안에서는 같은 장면에서 물체만 바뀌어야 하므로).
    목적지 색은 그대로 두고 칸 번호(slot)만 새 배치에 맞춰 다시 계산한다.
    """
    rows = list(csv.DictReader(open(a.out)))
    keep = [r for r in rows if int(r["ep"]) < a.relayout_from]
    rest = [r for r in rows if int(r["ep"]) >= a.relayout_from]
    assert rest and rest[0]["keep_layout"] == "NEW", "그룹 첫 행(NEW)부터 다시 정해야 한다"
    groups = list(dict.fromkeys(r["group"] for r in rest))
    blocks = [groups[i:i + a.relayout_groups] for i in range(0, len(groups), a.relayout_groups)]
    if len(blocks) > 1 and len(blocks[-1]) < a.relayout_groups:  # 짧은 꼬리는 앞 블록에 붙인다
        tail = blocks.pop()
        blocks[-1] += tail
    prev = [s.split("번 ")[1] for s in keep[-1]["layout"].split(" · ")]
    lays = pick_layouts(prev, len(blocks) + 1, random.Random(a.seed + 2))[1:]
    gi = {g: b for b, gs in enumerate(blocks) for g in gs}
    for r in rest:
        lay = lays[gi[r["group"]]]
        r["slot"] = lay.index(r["slot_color"]) + 1
        r["layout"] = layout_str(lay)
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(keep + rest)
    print(f"\n  {a.out}\n  {a.relayout_from - 1}행까지 그대로, 이후 {a.relayout_groups}그룹마다 칸 배치 변경\n")
    print(f"    ~{a.relayout_from - 1}행        {keep[-1]['layout']}  (현재)")
    for lay in lays:
        e = [int(r["ep"]) for r in rest if r["layout"] == layout_str(lay)]
        cc = Counter(r["slot_color"] for r in rest if r["layout"] == layout_str(lay))
        print(f"    {min(e)}~{max(e)}행 ({len(e)}ep)  {layout_str(lay)}   목적지 "
              + " ".join(f"{c}{cc[c]}" for _, c in SLOTS))


def report(rows, lays, out, ep0):
    N = len(rows)
    kc = Counter(r["group_kind"] for r in rows)
    print(f"\n  {out}\n  앞 {ep0}행 그대로 + 새 {N}행 ({ep0 + 1}~{ep0 + N}행)\n")
    print("  그룹 종류")
    for k in ("obj-mk3", "obj-mk2", "obj-glue", "obj-other"):
        g = len({r["group"] for r in rows if r["group_kind"] == k})
        print(f"    {k:<10} {g:>2}그룹 {kc[k]:>3}ep")
    tc = Counter(r["target"] for r in rows)
    print("\n  타깃 분포")
    for o in MARKERS + [GLUE] + OTHERS:
        print(f"    {o:<13} {tc[o]:>3}")
    mk = sum(tc[m] for m in MARKERS)
    print(f"    → 마커 타깃 {mk}ep ({mk / N * 100:.0f}%)")
    # 마커끼리 대조: 같은 화면에 다른 마커가 하나 이상 있는 마커 타깃
    mm = sum(1 for r in rows if r["target"] in MARKERS
             and sum(m in r["objects"] for m in MARKERS) >= 2)
    print(f"    → 다른 마커가 같이 있는 마커 타깃 {mm}ep")
    tz = Counter(r["pose_hint"].split(f"{r['target']} ")[-1].split(" ")[0].split("(")[0]
                 for r in rows)
    print("\n  타깃 위치(화면 기준) " + " · ".join(f"{z} {tz[z]}" for z in ZONES))
    print("  목적지 색 " + " · ".join(f"{c} {Counter(r['slot_color'] for r in rows)[c]}"
                                     for _, c in SLOTS))
    print("\n  칸 배치 블록")
    for lay in lays:
        e = [int(r["ep"]) for r in rows if r["layout"] == layout_str(lay)]
        print(f"    {min(e)}~{max(e)}행 ({len(e)}ep)  {layout_str(lay)}")
    bad = [g for g in {r["group"] for r in rows}
           if len({(r["objects"], r["slot_color"]) for r in rows if r["group"] == g}) != 1
           or len({r["target"] for r in rows if r["group"] == g})
           != len([r for r in rows if r["group"] == g])]
    print(f"\n  {'✅' if not bad else '❌'} 그룹 무결성(같은 배치·같은 칸·타깃 모두 다름) 위반 {len(bad)}건")
    keep = sum(r["keep_layout"] == "KEEP" for r in rows)
    print(f"  예상 수집 시간 약 {((N - keep) * 200 + keep * 160) / 3600:.1f}시간 "
          f"(NEW 200s · KEEP 160s 추정)")


if __name__ == "__main__":
    raise SystemExit(main())
