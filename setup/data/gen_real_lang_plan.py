"""실기 언어 조건화 수집 계획표 — **사람이 물체를 놓을 수 있게** 에피소드별 지시를 만든다.

sim 계획표(gen_lang_collect_plan.py)와 같은 목적이지만 두 가지가 다르다.

  ① 배치를 코드가 못 한다. 사람이 손으로 놓으므로 **무엇을 놓을지 표로 알려준다.**
     그냥 "아무거나 놓으세요"라고 하면 무의식적으로 같은 자리·같은 조합에 몰린다.
     실기 50ep에서 박스가 사실상 고정이었던 전례가 있다(픽셀 중심 편차 x 7px).
  ② 물체 수가 1~4로 가변이다. sim은 항상 4개였다.

**물체가 1개인 에피소드는 언어 신호가 0이다.** 고를 것이 하나뿐이면 지시문을 안 읽어도
맞는다. 그래서 1개 에피소드 비율을 낮게 두고(기본 10%), 3~4개를 두껍게 깐다.
sim 수집에서 확인된 것과 같은 이유다 — 지시문이 정답을 가르는 **유일한 단서**여야 한다.

사용:
  python3 gen_real_lang_plan.py --episodes 120 --out ~/manipulator_ws/manipulator_md/real/real_lang_plan.csv
"""
import argparse
import csv
import os
import random
from collections import Counter

# 실물 프롭 8종. 이름은 지시문에 그대로 들어간다.
#   ⚠️ sim 카탈로그와 **색이 하나 다르다** — sim은 청록(cyan), 실기는 주황(orange)이다.
#      sim 학습본에 orange 큐브는 0회 등장하므로, co-training 전까지 이 색은
#      "실기에서만 본 색"이다. 반대로 cyan은 실기에 없다.
OBJECTS = {
    "red cube":    "red",
    "blue cube":   "blue",
    "yellow cube": "yellow",
    "green cube":  "green",
    "purple cube": "purple",
    "orange cube": "orange",
    "marker":      "marker",
    "eraser":      "eraser",
}
NAMES = list(OBJECTS)

# 물체 수 분포 — 1개는 언어 신호가 없으므로 얇게 깐다.
COUNT_WEIGHTS = {1: 0.10, 2: 0.20, 3: 0.35, 4: 0.35}

# 목적지 상자 3색 중 **2개**를 매 에피소드 놓는다(sim과 같은 구성).
#   sim에서 목적지 축은 **실패**했다 — 28.3%로 우연(50%)에도 못 미쳤고,
#   같은 배치에서 흑/갈을 각각 지시했을 때 둘 다 성공한 것이 30개 중 3개뿐이었다.
#   cleanup("빨간 건 왼쪽, 파란 건 오른쪽")은 이 축 없이 성립하지 않으므로
#   실기 수집에서 이 구간을 두껍게 채운다.
#   색 이름은 sim 학습본이 이미 배운 것과 맞춘다 — 새 단어를 만들면 실기에서만 본
#   어휘가 또 늘어난다(주황 큐브가 이미 그렇다).
BOXES = ["black", "brown", "gray"]

# 지시문 문형. sim 계획표와 같은 형태로 맞춘다 — 학습에서 본 적 없는 문형을 쓰면
# "언어를 못 읽는다"가 아니라 "그 문형을 모른다"를 재게 된다.
#   목적지를 **명시하는 문장이 약 70%**다(sim 실측 분포와 맞춤). 나머지는 "the box"로
#   두어 상자가 하나뿐이던 기존 배포와도 호환된다.
TEMPLATES_DEST = [
    "Pick up the {obj} and place it in the {dst} box",
    "Put the {obj} into the {dst} box",
    "Grab the {obj} and put it in the {dst} box",
]
TEMPLATES = [
    "Pick up the {obj} and place it in the box",
    "Put the {obj} into the box",
    "Grab the {obj} and put it in the box",
]
DEST_FRAC = 0.70          # 목적지 색을 명시하는 비율
# 물체가 1개일 때만 쓰는 문장. sim의 레거시 문장과 같다(기존 배포 호환).
LEGACY = "Pick up the block and place it in the box"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", type=int, default=120)
    ap.add_argument("--seed", type=int, default=20260930)
    ap.add_argument("--out", default=os.path.expanduser(
        "~/manipulator_ws/manipulator_md/real/real_lang_plan.csv"))
    ap.add_argument("--legacy-frac", type=float, default=0.06,
                    help="1물체 에피소드에서 레거시 문장을 쓸 비율")
    a = ap.parse_args()
    rng = random.Random(a.seed)

    counts = list(COUNT_WEIGHTS)
    weights = [COUNT_WEIGHTS[c] for c in counts]

    # 목적지도 균등하게 — 무작위로 뽑으면 3색이 고르게 안 나온다.
    dper = a.episodes // len(BOXES) + 1
    dests = (BOXES * dper)[:a.episodes]
    rng.shuffle(dests)
    dest_rows = set(rng.sample(range(a.episodes), int(a.episodes * DEST_FRAC)))

    # 타깃을 균등하게 깔기 위해 먼저 타깃 열을 만들고 섞는다.
    # 무작위로 매 행 뽑으면 8종이 고르게 안 나온다(실측: 얇은 표본에서 최대 2배 차).
    per = a.episodes // len(NAMES) + 1
    targets = (NAMES * per)[:a.episodes]
    rng.shuffle(targets)

    # 레거시 문장은 미리 자리를 잡아 둔다 — 그때그때 뽑으면 몰린다.
    n_legacy = max(1, int(a.episodes * a.legacy_frac))
    legacy_rows = set(rng.sample(range(a.episodes), n_legacy))

    rows = []
    for i in range(a.episodes):
        tgt = targets[i]
        # 상자 2개를 놓는다. 목적지로 지정된 것이 반드시 그중 하나여야 한다.
        dst = dests[i]
        other_box = rng.choice([b for b in BOXES if b != dst])
        boxes = [dst, other_box]
        rng.shuffle(boxes)

        if i in legacy_rows:
            n, objs, instr = 1, [tgt], LEGACY
            named_dst = ""          # 레거시 문장은 목적지를 지정하지 않는다
        else:
            n = rng.choices(counts, weights)[0]
            if n == 1:
                objs = [tgt]
            else:
                others = [o for o in NAMES if o != tgt]
                objs = [tgt] + rng.sample(others, n - 1)
                rng.shuffle(objs)
            if i in dest_rows:
                instr = rng.choice(TEMPLATES_DEST).format(obj=tgt, dst=dst)
                named_dst = dst
            else:
                instr = rng.choice(TEMPLATES).format(obj=tgt)
                named_dst = ""
        rows.append({"ep": i + 1, "n_objects": n, "objects": ", ".join(objs),
                     "target": tgt, "boxes": ", ".join(boxes),
                     "dest": dst, "dest_named": named_dst, "instruction": instr})

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ep", "n_objects", "objects", "target", "boxes", "dest", "dest_named", "instruction"])
        w.writeheader()
        w.writerows(rows)

    # ── 균형 점검 — 수집 전에 여기서 걸러야 한다 ──
    tc = Counter(r["target"] for r in rows)
    nc = Counter(r["n_objects"] for r in rows)
    ac = Counter(o for r in rows for o in r["objects"].split(", "))
    exp = a.episodes / len(NAMES)
    print(f"\n  {a.out}  —  {len(rows)}행\n")
    print(f"  물체 수 분포:  " + "  ".join(f"{k}개 {nc[k]}({nc[k]/len(rows)*100:.0f}%)"
                                        for k in sorted(nc)))
    print(f"  1물체 에피소드 {nc[1]}개 ({nc[1]/len(rows)*100:.0f}%) — 이 구간은 언어 신호가 없다")
    print(f"\n  타깃 분포 (기대 {exp:.0f} ±30%)")
    bad = []
    for o in NAMES:
        mark = "" if exp * 0.7 <= tc[o] <= exp * 1.3 else "  ⚠"
        if mark:
            bad.append(o)
        print(f"    {o:<13} 타깃 {tc[o]:>3}   등장 {ac[o]:>3}{mark}")
    print(f"\n  {'❌ 타깃 불균형: ' + ', '.join(bad) if bad else '✅ 타깃 균형 통과'}")
    dc = Counter(r["dest"] for r in rows)
    named = sum(1 for r in rows if r["dest_named"])
    print(f"\n  목적지 분포 (기대 {a.episodes/len(BOXES):.0f})")
    for b in BOXES:
        print(f"    {b:<13} {dc[b]:>3}")
    print(f"  목적지 명시 문장 {named}개 ({named/len(rows)*100:.0f}%) — 나머지는 \"the box\"")
    print(f"  레거시 문장 {sum(1 for r in rows if r['instruction'] == LEGACY)}개")
    print("\n  수집 시:  ./record_real_lang.sh")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
