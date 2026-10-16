"""양팔(bi-manipulator) 파일럿 수집 계획표.

bi_manipulator_plan.md §3 파일럿(40~60ep)용. 과제는 단일팔 cleanup과 언어
구조가 같다 — "Put the {obj} into the {dst} bin" 한 문장이 오른팔(파지 대상)과
왼팔(목적지 칸)을 동시에 정한다. 바뀐 건 그 사이에 **전달**이 끼어드는 것뿐이다.
그래서 4칸·대응쌍/4연속 구조를 setup/p5_real_cleanup/gen_real_lang_plan.py에서 그대로
가져온다 — 바뀌는 변수(양팔·전달)를 하나만 넣어야 뭐가 문제인지 구분된다.

물체 8종(2026-10-14 변경) — 큐브를 전부 빼고 교체했다. red/blue/black marker·
yellow straw·glue stick·toothbrush·eraser·screwdriver. 에피소드당 2~4개를
무작위 배치한다(1개짜리는 이번엔 쓰지 않는다 — 큐브 축소판 수준의 쉬운 구성을
덜어내고 방해물이 항상 있는 구성으로 간다).

EXCLUSIVE는 비워 둔다 — 이전엔 red/orange cube 혼동(v3 평가 실측, 18° 색상환
차이)이 있었지만 큐브가 전부 빠지면서 그 근거가 사라졌다. 새 물체 조합에서
비슷한 혼동이 나오면(예: marker 색 간) 그때 실측 근거를 들어 추가한다 —
근거 없이 미리 짐작해 배제하지 않는다.

eraser는 **항상 세워서** 배치한다(사용자 지정, 2026-10-14) — POSE_VARIANTS가
단일 옵션 리스트라 pick_least가 항상 그 값을 고른다.

사용:
  python3 gen_bi_plan.py --episodes 50
  python3 gen_bi_plan.py --episodes 50 --out ~/manipulator_ws/manipulator_md/p6_real_bimanual/bi_pilot_plan.csv
"""
import argparse
import csv
import os
import random
from collections import Counter

OBJECTS = ["red marker", "blue marker", "black marker", "yellow straw",
           "glue stick", "toothbrush", "eraser", "screwdriver"]

EXCLUSIVE = []

POSE_VARIANTS = {"eraser": ["세워서"]}

SLOTS = [(1, "black"), (2, "cyan"), (3, "pink"), (4, "white")]
DEST_NOUN = "bin"
COUNT_WEIGHTS = {2: 0.30, 3: 0.35, 4: 0.35}
TEMPLATES_DEST = ["Put the {obj} into the {dst} " + DEST_NOUN]

FIELDS = ["ep", "group", "group_kind", "group_pos", "keep_layout",
          "n_objects", "objects", "target", "slot", "slot_color",
          "pose_hint", "instruction", "layout"]


def layout_str(perm):
    return " · ".join(f"{i}번 {c}" for i, c in enumerate(perm, 1))


def pick_layouts(base, n_blocks, rng, tries=20000):
    """블록마다 칸 색 배치를 바꾼다 — 색↔위치 암기를 끊기 위해.

    조건: 직전 블록과 비교해 **모든 색이 자리를 옮긴다**(완전순열). 그 위에서
    (1) 색×위치 횟수가 고르게, (2) 같은 이웃 쌍이 반복되지 않게, (3) 같은 배치가
    두 번 나오지 않게 고른다. 이웃 쌍까지 보는 이유: 순환 이동(abcd→bcda)만 쓰면
    위치는 바뀌어도 "black 옆엔 white" 같은 상대 순서가 그대로 남아 그걸 외울 수 있다.
    """
    from itertools import permutations
    perms = list(permutations(base))
    best, best_s = None, None
    for _ in range(tries):
        seq = [tuple(base)]
        for _ in range(n_blocks - 1):
            cand = [p for p in perms if all(a != b for a, b in zip(p, seq[-1]))]
            seq.append(rng.choice(cand))
        cp = Counter((c, i) for p in seq for i, c in enumerate(p))
        ideal = n_blocks / len(base)
        s = sum((cp[(c, i)] - ideal) ** 2 for c in base for i in range(len(base)))
        adj = Counter(frozenset(pr) for p in seq for pr in zip(p, p[1:]))
        s += sum(v - 1 for v in adj.values() if v > 1) * 0.5
        s += (len(seq) - len(set(seq))) * 10
        if best_s is None or s < best_s:
            best, best_s = seq, s
    return [list(p) for p in best]


def assign_layouts(rows, every, base, rng):
    """every 행마다 배치를 바꾼다. 그룹(KEEP) 중간에서는 바꾸지 않고 다음 NEW 행까지 미룬다 —
    대응쌍은 '같은 화면, 지시문만 다름'이어야 하므로."""
    n_blocks = -(-len(rows) // every)
    layouts = pick_layouts(base, n_blocks, rng)
    b = 0
    for i, r in enumerate(rows):
        if b + 1 < n_blocks and i >= (b + 1) * every and r["keep_layout"] == "NEW":
            b += 1
        perm = layouts[b]
        r["slot"] = perm.index(r["slot_color"]) + 1
        r["layout"] = layout_str(perm)
    return layouts


def partners_of(x):
    return {b for pr in EXCLUSIVE for a, b in (pr, pr[::-1]) if a == x}


def pick_least(counter, candidates, rng):
    lo = min(counter[c] for c in candidates)
    return rng.choice([c for c in candidates if counter[c] == lo])


def pick_least2(key1, key2, candidates, rng):
    best = min((key1(c), key2(c)) for c in candidates)
    return rng.choice([c for c in candidates if (key1(c), key2(c)) == best])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", type=int, default=50,
                    help="파일럿 규모 — bi_manipulator_plan.md §3-1 권장 40~60")
    ap.add_argument("--seed", type=int, default=20261014)
    ap.add_argument("--out", default=os.path.expanduser(
        "~/manipulator_ws/manipulator_md/p6_real_bimanual/bi_pilot_plan.csv"))
    ap.add_argument("--pair-frac", type=float, default=0.30)
    ap.add_argument("--quad-frac", type=float, default=0.16)
    ap.add_argument("--base", help="이어 짤 기존 계획표 (--keep-head 와 함께)")
    ap.add_argument("--keep-head", type=int, default=0,
                    help="기존 계획표의 앞 N행을 그대로 두고 나머지만 다시 짠다 — "
                         "gen_real_lang_plan.py와 같은 방식(파일럿 뒤에 본 수집을 이어 붙일 때 씀)")
    ap.add_argument("--layout-every", type=int, default=0,
                    help="N행마다 칸 색 배치를 바꾼다(0=고정). 색이 아니라 위치를 외우는 것을 막기 위함")
    ap.add_argument("--base-layout", default="black,white,pink,cyan",
                    help="첫 블록의 칸 배치(1번부터 쉼표로) — 파일럿 50ep 실제 배치")
    a = ap.parse_args()
    rng = random.Random(a.seed)

    slots = SLOTS
    slot_nums = [n for n, _ in slots]
    tgt_count, slot_count, combo_count, pose_count = Counter(), Counter(), Counter(), Counter()
    rows, ep = [], 0

    # ── 0) 이어 짜기 ─ 앞 N행은 그대로 두고 카운터만 채운 뒤 남은 예산만 다시 짠다.
    #   (이미 찍은 행을 건드리면 collect_progress.txt·순서 검사가 깨진다 — v3 때 겪은 그대로)
    head, gi_off = [], 0
    if a.base and a.keep_head:
        base = list(csv.DictReader(open(os.path.expanduser(a.base))))
        n = a.keep_head
        while n < len(base) and base[n]["keep_layout"] == "KEEP":
            n += 1
        head = base[:n]
        # CSV에서 읽으면 전부 문자열이다 — 정수로 안 맞추면 Counter가 "1"과 1을 다르게 센다.
        for r in head:
            for k in ("group", "n_objects", "slot"):
                r[k] = int(r[k])
        for r in head:
            tgt_count[r["target"]] += 1
            slot_count[r["slot"]] += 1
            combo_count[(r["target"], r["slot_color"])] += 1
        rows.extend(head)
        ep, gi_off = n, int(head[-1]["group"])
        print(f"  ▶ 앞 {n}행 유지 (그룹 {gi_off}까지) · {n + 1}행부터 다시 짠다")

    budget = a.episodes - ep
    assert budget > 0, f"--keep-head({ep})가 --episodes({a.episodes}) 이상이다"
    n_quad = int(budget * a.quad_frac) // 4
    n_pair = int(budget * a.pair_frac) // 2
    n_single = budget - n_quad * 4 - n_pair * 2
    assert n_single >= 0, "pair-frac + quad-frac 이 1을 넘었다"

    kinds = ["quad"] * n_quad + ["pair"] * n_pair + ["single"] * n_single
    rng.shuffle(kinds)

    for gi, kind in enumerate(kinds, start=gi_off):
        target = pick_least2(lambda o: tgt_count[o],
                             lambda o: min(combo_count[(o, c)] for _, c in slots),
                             OBJECTS, rng)
        n_obj = rng.choices(list(COUNT_WEIGHTS), list(COUNT_WEIGHTS.values()))[0]
        pool = [o for o in OBJECTS if o != target and o not in partners_of(target)]
        objs = [target]
        for _ in range(n_obj - 1):
            if not pool:
                break
            pick = rng.choice(pool)
            objs.append(pick)
            drop = partners_of(pick) | {pick}
            pool = [o for o in pool if o not in drop]
        n_obj = len(objs)
        rng.shuffle(objs)

        if kind == "quad":
            picks = list(slots)
            rng.shuffle(picks)
        else:
            cmap = {n: c for n, c in slots}
            k1 = lambda n: combo_count[(target, cmap[n])]
            k2 = lambda n: slot_count[n]
            if kind == "pair":
                first = pick_least2(k1, k2, slot_nums, rng)
                second = pick_least2(k1, k2, [n for n in slot_nums if n != first], rng)
                picks = [(n, c) for n, c in slots if n in (first, second)]
                rng.shuffle(picks)
            else:
                n = pick_least2(k1, k2, slot_nums, rng)
                picks = [(sn, sc) for sn, sc in slots if sn == n]

        for pos, (snum, scol) in enumerate(picks, start=1):
            ep += 1
            tgt_count[target] += 1
            slot_count[snum] += 1
            combo_count[(target, scol)] += 1

            if pos == 1:
                hints = []
                for o in objs:
                    if o in POSE_VARIANTS:
                        v = pick_least(pose_count, POSE_VARIANTS[o], rng)
                        pose_count[v] += len(picks)
                        hints.append(f"{o} {v}")
                group_hint = " · ".join(hints)

            rows.append({
                "ep": ep,
                "group": gi + 1,
                "group_kind": kind,
                "group_pos": f"{pos}/{len(picks)}",
                "keep_layout": "NEW" if pos == 1 else "KEEP",
                "n_objects": n_obj,
                "objects": ", ".join(objs),
                "target": target,
                "slot": snum,
                "slot_color": scol,
                "pose_hint": group_hint,
                "instruction": rng.choice(TEMPLATES_DEST).format(obj=target, dst=scol),
            })

    layouts = None
    if a.layout_every:
        base = [c.strip() for c in a.base_layout.split(",")]
        assert sorted(base) == sorted(c for _, c in SLOTS), f"--base-layout 색이 SLOTS와 다르다: {base}"
        # 별도 rng — 위 행 생성 순서(rng)를 건드리면 기존 계획표 내용이 바뀐다.
        layouts = assign_layouts(rows, a.layout_every, base, random.Random(a.seed + 1))
    else:
        for r in rows:
            r["layout"] = layout_str([c for _, c in SLOTS])

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    report(rows, slots, a)
    if layouts:
        report_layouts(rows, layouts)
    return 0


def report_layouts(rows, layouts):
    print("\n  칸 배치 블록 (색↔위치 암기 방지)")
    for lay in layouts:
        eps = [int(r["ep"]) for r in rows if r["layout"] == layout_str(lay)]
        print(f"    {min(eps):>3}~{max(eps):>3}행 ({len(eps):>2}ep)  {layout_str(lay)}")
    cols = layouts[0]
    cnt = Counter((r["slot_color"], int(r["slot"])) for r in rows)
    print("\n  색×위치 에피소드 수 (고를수록 위치로 색을 맞힐 수 없다)")
    print("    " + " " * 7 + "".join(f"{i}번".rjust(6) for i in range(1, len(cols) + 1)))
    for c in sorted(cols):
        print(f"    {c:<7}" + "".join(f"{cnt[(c, i)]:>6}" for i in range(1, len(cols) + 1)))


def groups(rows):
    cur, buf = None, []
    for r in rows:
        if r["group"] != cur:
            if buf:
                yield cur, buf
            cur, buf = r["group"], [r]
        else:
            buf.append(r)
    if buf:
        yield cur, buf


def report(rows, slots, a):
    N = len(rows)
    tc = Counter(r["target"] for r in rows)
    sc = Counter(r["slot"] for r in rows)
    kc = Counter(r["group_kind"] for r in rows)
    ok = True

    print(f"\n  {a.out}\n  {N}행(에피소드) · 칸 {len(slots)}개\n")
    print("  그룹 구성")
    for k in ("quad", "pair", "single"):
        if kc[k]:
            print(f"    {k:<7} {kc[k]:>3}ep ({kc[k] / N * 100:.0f}%)")

    exp = N / len(OBJECTS)
    bad = [o for o in OBJECTS if not exp * 0.5 <= tc[o] <= exp * 1.6]
    print(f"\n  타깃 분포 (기대 {exp:.1f})")
    for o in OBJECTS:
        print(f"    {o:<13} {tc[o]:>3}{'  ⚠' if o in bad else ''}")
    ok &= not bad

    exps = N / len(slots)
    badv = [n for n, _ in slots if not exps * 0.5 <= sc[n] <= exps * 1.6]
    print(f"\n  칸(위치) 분포 (기대 {exps:.1f})")
    for n, _ in slots:
        print(f"    {n}번 {sc[n]:>3}{'  ⚠' if n in badv else ''}")
    ok &= not badv

    bad_pairs = []
    for g, items in groups(rows):
        if len(items) == 1:
            continue
        if len({i["objects"] for i in items}) != 1 or len({i["target"] for i in items}) != 1:
            bad_pairs.append((g, "배치가 다름"))
        if len({i["slot"] for i in items}) != len(items):
            bad_pairs.append((g, "칸이 겹침"))
    ok &= not bad_pairs
    print(f"\n  {'✅' if not bad_pairs else '❌'} 쌍 무결성  위반 {len(bad_pairs)}건")

    viol = [(r["ep"], a_, b_) for r in rows
            for a_, b_ in EXCLUSIVE
            if a_ in r["objects"] and b_ in r["objects"]]
    ok &= not viol
    print(f"  {'✅' if not viol else '❌'} 상호 배제 위반 {len(viol)}건")

    reuse = sum(1 for r in rows if r["keep_layout"] == "KEEP")
    # 전달이 끼므로 단일팔(150s/110s)보다 여유를 둔다 — 실측 전 추정치.
    hours = ((N - reuse) * 200 + reuse * 150) / 3600
    print(f"\n  예상 수집 시간 약 {hours:.1f}시간 (전달 단계 포함 추정 — 실측 전)")
    print(f"\n  {'✅ 통과 — 수집 시작 가능' if ok else '❌ 위 항목을 고칠 것'}")


if __name__ == "__main__":
    raise SystemExit(main())
