#!/usr/bin/env python3
"""언어 조건화 수집용 **에피소드 계획표** 생성 — 물체·박스·타깃·목적지·지시문을 미리 확정한다.

왜 계획표를 먼저 만드는가 (language_conditioning_sim_plan.md §2-6):
  사람이 그때그때 정하면 반드시 몰린다. 실기 real50이 그랬고(박스 픽셀 편차 x 7px),
  그래서 v2 재수집 때는 배치표를 띄워놓고 따라 놓게 했다(gen_real_collect_schedule.py).
  언어 수집은 그보다 더하다 — **타깃 색과 위치가 상관되면 정책은 언어 대신 위치를 배운다**
  (R3 위반). 타깃을 계획표가, 위치를 env 난수가 정하면 그 상관이 구조적으로 0이 된다.

  부수적으로 이 파일이 "무엇을 수집했다"는 사후 증거가 된다. 지금까지 지시문은
  어디에도 기록되지 않아 "정말 그 문장으로 돌렸나"를 확인할 수 없었다(2026-08-12).

균형 4종을 동시에 맞춘다:
  ① 물체별 타깃 횟수  ② 박스색별 타깃 횟수  ③ 박스색 쌍 분포  ④ 물체 동반 출현
  ①②는 최소 사용 우선(greedy), ③④는 후보 점수에 페널티로 넣는다.

사용:
  ./gen_lang_collect_plan.py --episodes 330 --seed 20260914 --out ../../manipulator_md/sim/lang_collect_plan.csv
  ./gen_lang_collect_plan.py --episodes 330 --check-only     # 균형만 출력(파일 안 씀)
"""
import argparse
import csv
import random
import sys
from collections import Counter, defaultdict
from itertools import combinations

# ── 카탈로그 (계획서 §2-1, §2-2) ────────────────────────────────────────
# 큐브 6색 + 사물 2종. 색만 다른 6종과 이름이 다른 2종으로 갈라, 평가에서
# "색만 외웠는가 / 이름도 읽는가"를 구분할 수 있게 한다.
# 색상환 6등분. 주황을 뺀 이유는 configure_scene.LANG_COLOR 주석 참고
# (따뜻한 조명에서 주황↔노랑이 붙는다 — 2026-09-14 캡처 확인).
CUBES = ["red", "blue", "yellow", "green", "cyan", "purple"]
OBJECTS = [f"{c}_cube" for c in CUBES] + ["eraser", "marker"]
BOXES = ["black", "brown", "gray"]

# ⚠️ 평가 전용. 수집에 **한 번도** 넣지 않는다 — 하나라도 새면 미학습 색 일반화가 무효다.
HELDOUT_OBJECTS = ["white_cube", "pink_cube"]
HELDOUT_BOXES = ["white"]

N_OBJ = 4          # 에피소드당 배치 물체 수 (거부 표집 실측: 4개는 12cm 간격에서도 99.8%)
MIX = {            # 에피소드 구성 비율 (§2-3)
    "4obj_2box": 0.50,
    "4obj_1box": 0.38,
    "1obj_1box": 0.12,
}
LEGACY_FRAC = 0.5  # 1물체 에피소드 중 기존 문장을 그대로 쓰는 비율

# ── 지시문 (§2-5) ──────────────────────────────────────────────────────
CANONICAL = "Pick up the {obj} and place it in the {dest}"
VARIANTS = [
    "Grab the {obj} and put it in the {dest}",
    "Put the {obj} into the {dest}",
    "Move the {obj} to the {dest}",
]
CANONICAL_FRAC = 0.5   # FineVLA의 역U자(정본:변형 1:1~1:2)에 맞춘 값
LEGACY_SENTENCE = "Pick up the block and place it in the box"

# 단일 박스 씬에서 목적지를 색으로 부르는 비율. 나머지는 그냥 `the box`.
# 둘 다 두는 이유: 색을 말해도 맞다는 것과, 하나뿐이면 색이 없어도 된다는 것을 같이 배운다.
DEST_COLOR_FRAC_1BOX = 0.4


def obj_noun(name, rng):
    """물체 이름 → 지시문 명사. 큐브는 block/cube를 절반씩 섞는다."""
    if name.endswith("_cube"):
        color = name[:-5]
        return f"{color} {'block' if rng.random() < 0.5 else 'cube'}"
    return name


def make_instruction(target, dest, n_boxes, legacy, rng):
    if legacy:
        return LEGACY_SENTENCE
    tmpl = CANONICAL if rng.random() < CANONICAL_FRAC else rng.choice(VARIANTS)
    # ⚠️ 박스가 2개면 색을 반드시 넣는다 — `the box`라고 하면 정답이 정의되지 않는다.
    if n_boxes >= 2 or rng.random() < DEST_COLOR_FRAC_1BOX:
        dest_noun = f"{dest} box"
    else:
        dest_noun = "box"
    return tmpl.format(obj=obj_noun(target, rng), dest=dest_noun)


def pick_least(counter, pool, rng, penalty=None):
    """사용 횟수가 가장 적은 것을 고른다(동점은 무작위). penalty(dict)가 있으면 더해서 비교."""
    scored = [(counter[x] + (penalty.get(x, 0) if penalty else 0), rng.random(), x) for x in pool]
    scored.sort()
    return scored[0][2]


def build(n_episodes, seed):
    rng = random.Random(seed)

    counts = {k: int(round(n_episodes * v)) for k, v in MIX.items()}
    counts["4obj_2box"] += n_episodes - sum(counts.values())   # 반올림 오차 흡수
    kinds = [k for k, c in counts.items() for _ in range(c)]
    rng.shuffle(kinds)

    tgt_obj = Counter()          # 물체별 타깃 횟수
    tgt_box = Counter()          # 박스색별 타깃 횟수
    use_obj = Counter()          # 물체별 등장 횟수(비타깃 포함)
    pair_box = Counter()         # 박스색 쌍 분포
    co_occ = Counter()           # 물체 동반 출현
    recent = []                  # 직전 조합(습관화 방지)

    rows = []
    # 레거시 문장을 쓸 에피소드를 **미리 무작위로 골라 둔다.** 그때그때 "아직 할당량이
    # 남았으면 쓴다"로 하면 앞쪽 1물체 에피소드에 몰려, 조작자가 같은 문장을 연달아 보게 된다.
    one_obj_idx = [i for i, k in enumerate(kinds) if k == "1obj_1box"]
    legacy_at = set(rng.sample(one_obj_idx, int(round(len(one_obj_idx) * LEGACY_FRAC))))

    for ep, kind in enumerate(kinds, start=1):
        n_obj = 1 if kind.startswith("1obj") else N_OBJ
        n_box = 2 if kind.endswith("2box") else 1

        # ── 타깃 물체: 가장 덜 쓴 것. 단 레거시 문장은 큐브에만 붙일 수 있다
        #    ("the block"이 지칭할 수 있는 것은 큐브뿐) ──
        legacy = (ep - 1) in legacy_at
        pool = [o for o in OBJECTS if o.endswith("_cube")] if legacy else OBJECTS
        target = pick_least(tgt_obj, pool, rng)

        # ── 함께 놓을 물체: 등장 횟수가 적고, 타깃과 덜 만난 것 ──
        others = []
        for _ in range(n_obj - 1):
            cand = [o for o in OBJECTS if o != target and o not in others]
            pen = {o: 0.5 * co_occ[frozenset((target, o))] for o in cand}
            others.append(pick_least(use_obj, cand, rng, penalty=pen))
        objects = [target] + others
        rng.shuffle(objects)

        # ── 박스: 타깃 색은 가장 덜 쓴 것, 짝은 쌍 분포가 고른 쪽 ──
        dest = pick_least(tgt_box, BOXES, rng)
        if n_box == 2:
            cand = [b for b in BOXES if b != dest]
            pen = {b: 1.0 * pair_box[frozenset((dest, b))] for b in cand}
            other_box = pick_least(Counter(), cand, rng, penalty=pen)
            boxes = [dest, other_box]
            rng.shuffle(boxes)
            pair_box[frozenset(boxes)] += 1
        else:
            boxes = [dest]

        # ── 습관화 방지: 같은 (타깃, 목적지)가 3연속이면 타깃을 다음 후보로 민다 ──
        combo = (target, dest)
        if len(recent) >= 2 and all(r == combo for r in recent[-2:]):
            alt = [o for o in objects if o != target]
            if alt:
                target = rng.choice(alt)
                combo = (target, dest)
        recent.append(combo)

        tgt_obj[target] += 1
        tgt_box[dest] += 1
        for o in objects:
            use_obj[o] += 1
        for a, b in combinations(sorted(objects), 2):
            co_occ[frozenset((a, b))] += 1

        rows.append({
            "ep": ep,
            "objects": ",".join(objects),
            "boxes": ",".join(boxes),
            "target": target,
            "dest": dest,
            "instruction": make_instruction(target, dest, n_box, legacy, rng),
        })

    return rows


def report(rows):
    """균형 검증 — 합격선은 계획서 §5의 표와 같다. 하나라도 어긋나면 False."""
    n = len(rows)
    tgt_obj = Counter(r["target"] for r in rows)
    tgt_box = Counter(r["dest"] for r in rows)
    use_obj = Counter(o for r in rows for o in r["objects"].split(","))
    pairs = Counter(frozenset(r["boxes"].split(",")) for r in rows if "," in r["boxes"])
    co = Counter(frozenset(p) for r in rows
                 for p in combinations(sorted(r["objects"].split(",")), 2))
    tasks = Counter(r["instruction"] for r in rows)
    cross = Counter((r["target"], r["dest"]) for r in rows)

    ok = True

    def line(label, values, lo, hi, unit=""):
        nonlocal ok
        mn, mx = min(values), max(values)
        good = lo <= mn and mx <= hi
        ok &= good
        print(f"  {'✅' if good else '❌'} {label:<26} {mn}~{mx}{unit}  (기준 {lo}~{hi})")

    print(f"\n에피소드 {n}개")
    print(f"  구성: " + " · ".join(
        f"{k} {sum(1 for r in rows if len(r['objects'].split(','))==(1 if k.startswith('1obj') else N_OBJ) and len(r['boxes'].split(','))==(2 if k.endswith('2box') else 1))}"
        for k in MIX))

    exp_o = n / len(OBJECTS)
    line("물체별 타깃", [tgt_obj[o] for o in OBJECTS], int(exp_o * 0.8), int(exp_o * 1.2))
    exp_u = sum(use_obj.values()) / len(OBJECTS)
    line("물체별 등장", [use_obj[o] for o in OBJECTS], int(exp_u * 0.85), int(exp_u * 1.15))
    exp_b = n / len(BOXES)
    line("박스색별 타깃", [tgt_box[b] for b in BOXES], int(exp_b * 0.8), int(exp_b * 1.2))
    n2 = sum(pairs.values())
    line("박스색 쌍", [pairs[frozenset(p)] for p in combinations(BOXES, 2)],
         int(n2 / 3 * 0.75), int(n2 / 3 * 1.25))
    exp_c = sum(co.values()) / len(list(combinations(OBJECTS, 2)))
    line("물체 동반 출현", [co[frozenset(p)] for p in combinations(OBJECTS, 2)],
         int(exp_c * 0.6), int(exp_c * 1.6))
    exp_x = n / (len(OBJECTS) * len(BOXES))
    line("타깃×목적지 교차", [cross[(o, b)] for o in OBJECTS for b in BOXES],
         int(exp_x * 0.5), int(exp_x * 2.0))

    # 지시문 — 문장 수가 아니라 **단어 반복 횟수**가 목표다
    nouns = Counter()
    for r in rows:
        t = r["target"]
        nouns[t] += 1
    dest_words = Counter(r["dest"] for r in rows if f"{r['dest']} box" in r["instruction"])
    print(f"  ℹ️  지시문 종류 {len(tasks)}종 (기대 60~80) · 최다 {tasks.most_common(1)[0][1]}회")
    print(f"  ℹ️  레거시 문장 {tasks.get(LEGACY_SENTENCE, 0)}회 (1물체 씬 한정)")
    print(f"  ℹ️  목적지 색 명시 {sum(dest_words.values())}회 / {n}")

    # ⚠️ 미학습 색이 한 번이라도 들어가면 일반화 평가가 통째로 무효다
    leaked = [x for r in rows for x in r["objects"].split(",") if x in HELDOUT_OBJECTS]
    leaked += [x for r in rows for x in r["boxes"].split(",") if x in HELDOUT_BOXES]
    print(f"  {'✅' if not leaked else '❌'} 미학습 색 유출{'':<18} {len(leaked)}회  (기준 0)")
    ok &= not leaked

    # 물체가 2개 이상인데 `the block`/`the cube`로 지칭하면 정답이 정의되지 않는다
    ambiguous = [r["ep"] for r in rows
                 if len(r["objects"].split(",")) > 1
                 and (" the block " in r["instruction"] or " the cube " in r["instruction"])]
    print(f"  {'✅' if not ambiguous else '❌'} 모호한 지칭{'':<20} {len(ambiguous)}건  (기준 0)")
    ok &= not ambiguous

    # 박스가 2개인데 목적지 색이 없으면 역시 정답이 정의되지 않는다
    no_color = [r["ep"] for r in rows
                if len(r["boxes"].split(",")) == 2 and f"{r['dest']} box" not in r["instruction"]]
    print(f"  {'✅' if not no_color else '❌'} 2박스·색 미지정{'':<16} {len(no_color)}건  (기준 0)")
    ok &= not no_color
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", type=int, default=330,
                    help="생성할 행 수. 목표 280 + 스킵 여유 50")
    ap.add_argument("--seed", type=int, default=20260914)
    ap.add_argument("--out", default=None)
    ap.add_argument("--check-only", action="store_true")
    args = ap.parse_args()

    rows = build(args.episodes, args.seed)
    ok = report(rows)

    if args.out and not args.check_only:
        with open(args.out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["ep", "objects", "boxes", "target", "dest", "instruction"])
            w.writeheader()
            w.writerows(rows)
        print(f"\n저장: {args.out}")
    if not ok:
        print("\n❌ 균형 검증 실패 — seed를 바꿔 다시 생성하거나 비율을 조정하라")
        sys.exit(1)
    print("\n✅ 균형 검증 통과")


if __name__ == "__main__":
    main()
