"""색지 교체 검증 — **6개 배치 × 5시행 = 30시행**.

목적: 목적지 선택이 "색을 읽는 것"인지 "칸 위치를 궤적으로 외운 것"인지 가른다.
배치 1개만 바꾸면 "그 특정 교체를 외웠다"는 설명을 배제할 수 없고, 배치를
둘만 쓰면(이전 설계) "그 두 패턴을 외웠다"는 설명이 남는다. 6개를 쓰고 그중
5개를 **회전군 전체**(항등 + 90°/180°/270° 회전) + **반사 2종**(전체반전·쌍교환)
으로 짜면, 위치-암기로는 설명되지 않는 체계적인 커버리지가 된다.

배치 1은 **학습 배치 그대로**(1=black 2=cyan 3=pink 4=white) — 대조군이다.
나머지 5개는 전부 **완전 교란**(derangement) — 모든 색이 원래 자리를 반드시 벗어난다.

사용:
  python3 gen_swap6_plan.py --out ~/manipulator_ws/manipulator_md/real/swap6_plan.csv
"""
import argparse
import csv
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cleanup_eval import EXCLUSIVE, OBJECTS, POSE_VARIANTS, SLOTS, partners_of  # noqa: E402

# 왼쪽→오른쪽 물리 순서 1~4에 어떤 색이 오는지. L1 = 학습 배치(대조군).
#   L2 180°회전(전체반전) · L3 270°회전 · L4 90°회전 · L5 반사(인접쌍 교환) · L6 반사(대각 교환)
#   네 가지 회전(0°=L1,90°,180°,270°)과 서로 다른 구조의 반사 2종 — 전부 다른 변환군.
LAYOUTS = {
    "L1": ["black", "cyan", "pink", "white"],   # 학습 배치 그대로 (대조군)
    "L2": ["white", "black", "cyan", "pink"],   # 90°  회전(각 색이 한 칸씩 오른쪽으로)
    "L3": ["pink", "white", "black", "cyan"],   # 180° 회전
    "L4": ["cyan", "pink", "white", "black"],   # 270° 회전
    "L5": ["white", "pink", "cyan", "black"],   # 반사(전체 반전, 1↔4·2↔3)
    "L6": ["cyan", "black", "white", "pink"],   # 반사(인접쌍 교환, 1↔2·3↔4)
}

TRAINED = LAYOUTS["L1"]


def check_derangements():
    for name, cols in LAYOUTS.items():
        if name == "L1":
            continue
        assert all(c != t for c, t in zip(cols, TRAINED)), f"{name} 는 완전 교란이 아니다: {cols}"
        assert set(cols) == set(TRAINED), f"{name} 색 구성이 다르다: {cols}"
    # 서로 다른 배치인지(동일한 게 섞여 있으면 "6개"가 아니라 더 적은 수를 반복한 것)
    seen = set()
    for name, cols in LAYOUTS.items():
        t = tuple(cols)
        assert t not in seen, f"{name} 가 앞선 배치와 동일하다: {cols}"
        seen.add(t)


def hint_text(name):
    cols = LAYOUTS[name]
    pretty = " · ".join(f"{i + 1}번={c}" for i, c in enumerate(cols))
    tag = " (원래 학습 배치)" if name == "L1" else ""
    return f"배치 {name}{tag}: {pretty}"


TEMPLATES = ["Put the {obj} into the {dst} bin"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-layout", type=int, default=5)
    ap.add_argument("--seed", type=int, default=606)
    ap.add_argument("--out", default=os.path.expanduser(
        "~/manipulator_ws/manipulator_md/real/swap6_plan.csv"))
    a = ap.parse_args()
    check_derangements()
    rng = random.Random(a.seed)

    FIELDS = ["trial", "group", "kind", "pos", "keep_layout", "objects", "target",
              "slot", "slot_color", "pose_hint", "layout_hint", "instruction"]
    rows = []
    trial = 0
    tgt_count = {o: 0 for o in OBJECTS}
    order = sorted(LAYOUTS)  # L1..L6, L1(대조군) 먼저
    for li, lname in enumerate(order):
        cols = LAYOUTS[lname]
        # 이 배치의 5시행에 쓸 칸(색) 순서 — 4색을 한 번씩 쓰고 다섯 번째는
        # 배치마다 돌아가며 다른 색이 반복되게 한다(전체적으로 고르게).
        slot_cycle = list(cols)
        extra = cols[li % 4]
        slot_colors = slot_cycle + [extra]
        rng.shuffle(slot_colors)
        for j, scol in enumerate(slot_colors):
            trial += 1
            snum = cols.index(scol) + 1  # 이 배치에서 그 색이 물리적으로 몇 번 자리인지
            tgt = min(OBJECTS, key=lambda o: (tgt_count[o], rng.random()))
            tgt_count[tgt] += 1
            pool = [o for o in OBJECTS if o != tgt and o not in partners_of(tgt)]
            n_obj = rng.choice([2, 3, 3, 4])
            objs = [tgt]
            for _ in range(n_obj - 1):
                if not pool:
                    break
                pick = rng.choice(pool)
                objs.append(pick)
                drop = partners_of(pick) | {pick}
                pool = [o for o in pool if o not in drop]
            rng.shuffle(objs)
            rows.append({
                "trial": trial, "group": trial, "kind": "single", "pos": "1/1",
                "keep_layout": "NEW",
                "objects": ", ".join(objs), "target": tgt,
                "slot": snum, "slot_color": scol,
                "pose_hint": " · ".join(f"{o} {POSE_VARIANTS[o]}"
                                        for o in objs if o in POSE_VARIANTS),
                "layout_hint": hint_text(lname),
                "instruction": rng.choice(TEMPLATES).format(obj=tgt, dst=scol),
            })

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    print(f"\n  {a.out}  —  {len(rows)}시행 · {len(order)}배치 × {a.per_layout}시행")
    for lname in order:
        print(f"    {hint_text(lname)}")
    from collections import Counter
    tc = Counter(r["target"] for r in rows)
    print(f"\n  타깃 분포: {dict(sorted(tc.items(), key=lambda kv: -kv[1]))}")
    bad = [r["trial"] for r in rows
           for x, y in EXCLUSIVE if x in r["objects"] and y in r["objects"]]
    print(f"  상호 배제: {'✅ 위반 0건' if not bad else f'❌ {bad}'}")
    print(f"  예상 시간: 약 {len(rows) * 2.5 / 60:.1f}시간 (시행당 2.5분) "
          f"+ 배치 전환 {len(order) - 1}회")
    return 0


if __name__ == "__main__":
    import sys as _sys
    _sys.exit(main())
