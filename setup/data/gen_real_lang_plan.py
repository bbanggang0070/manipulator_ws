"""실기 언어 조건화 수집 계획표 — **4칸 선반 · 색상 단독 · 대응쌍**.

2026-09-30 재설계. 이전 버전(상자 3색 중 2개)에서 바뀐 이유는 sim 1단계에서
목적지 축만 실패했고, 그 원인을 둘로 좁혔기 때문이다.

  ① **저대비.** sim 상자색이 black(0.03,0.03,0.03) / brown(0.35,0.22,0.12) /
     gray(0.45,0.45,0.45)였다. 256²로 줄이면 사실상 한 덩어리다.
     ⚠️ 이건 **저해상도에서 실제로 뭉갠다**는 근거이지, sim에서 편향이 관측됐다는
        근거가 아니다. P8의 갈색 쏠림(10 vs 26)은 P2에서 재현되지 않았다(14 vs 13,
        두 분포 차이 p=0.069). 편향의 실재 여부는 아직 모른다.
  ② **구조적 신호 결핍.** 에피소드 절반이 상자 1개였고(목적지 단어가 장식),
     상자가 2개여도 목적지는 **transport 구간(~30%)만** 지배한다. 물체 축은
     reach 전체(~60%)를 지배한다. 같은 에피소드 수가 같은 기울기를 주지 않는다.

  실측 (langB60@60k, 교차 셀로 분해):
     물체 축   52.5% (우연 25%)
     목적지    66.7% (우연 50%, p=0.0097) — 우연이 아니다
     ⚠️ 조건 5·6의 28.3%는 곱이다: 물체+배치 45.0% × 목적지 63.0%.
        **병목은 언어가 아니라 조작**이다. 물체가 하나뿐일 때도 배치가 60%에 그친다.
        목적지 정확도는 방해물 유무에 거의 영향받지 않는다(1물체 69.4% → 4물체 63.0%)
        → 물체 1~4개 구성을 유지해도 목적지 축은 버틴다.

이 계획표가 ①②를 어떻게 고치나:

  · 칸 4개가 **매 에피소드 전부 존재**하고 목적지를 85% 명시한다 → 신호 희석 제거
  · 색을 **서로 먼 4색**으로 잡는다(black·white·cyan·pink) → 저대비 제거
  · **대응쌍/4연속**을 넣는다 → 관측이 동일하고 행동만 다른 구간을 데이터에 직접 심는다
  · 우연이 50% → **25%**로 내려가 같은 에피소드 수로 훨씬 잘 검출된다

물리 구성 (중요):
  책꽂이를 **등을 바닥에 대고 눕힌다.** 세워 두면 좁은 칸에 수평 삽입이 되어
  P(삽입)이라는 항이 새로 생기고, 그게 작아서 목적지 신호를 다시 가린다.
  눕히면 위가 열린 강체 통 4개라 배치 난이도가 지금과 같다.
  칸 안쪽 너비 ≥ 80mm (마커가 가로로 누워도 여유가 있어야 한다).
  색지는 **자석/벨크로**로 붙인다 — 평가 때 바꿔 끼워야 한다(아래).
  수집 전에 4칸 전부 텔레오프로 넣어 보고 리치를 확인할 것. 끝 칸이 작업공간
  경계에 있으면 그 칸만 성공률이 낮아 목적지 측정을 오염시킨다.

숫자는 선반에 **작게** 붙이되 지시문에는 넣지 않는다. 시연자가 칸을 헷갈리지
않게 하고 발표 자료에서 가리키기 위한 것이다. 색 패치가 면적을 먹어야 한다.
(256²에서 작은 글리프는 패치 14px 기준 1~2패치라 읽히지 않는다. 해상도를 448로
 올리는 버튼은 setup/gr00t/edge_patch.py 에 있지만 1단계에서는 쓰지 않는다.)

평가 때 할 것 — 학습 데이터를 안 쓰는 공짜 실험:
  색↔칸이 **고정**이라 모델은 라벨을 안 보고 "단어 → 횡위치" 룩업만 외워도 만점이다.
  태스크상 그걸로 충분하지만, 어느 쪽인지는 **평가에서 색지 두 장을 바꿔 끼워** 가른다.
  정확도가 유지되면 라벨을 읽는 것이고, 원래 자리로 가면 위치를 외운 것이다.
  보고서에서 주장의 범위를 이 결과에 맞춰 쓴다.

사용:
  python3 gen_real_lang_plan.py --episodes 250
  python3 gen_real_lang_plan.py --episodes 80 --slots 1,4 \\
      --out ~/manipulator_ws/manipulator_md/real/real_lang_plan_s1.csv
"""
import argparse
import csv
import os
import random
from collections import Counter

# ── 물체 11종. 이름이 지시문에 그대로 들어간다 ───────────────────────────
#   큐브 6색 + 사물 5종. 사물 쪽은 형상이 다양해 **파지 난이도 편차가 크다** —
#   sim 분해에서 병목이 언어가 아니라 조작(물체+배치 45.0%)이었으므로,
#   어려운 물체를 넣을수록 전체 성공률은 더 내려간다. 평가 때 축을 분리해 본다.
#   · screwdriver, glue stick, marker 는 **가늘고 길다** — 256²에서 서로 닮는다.
#     색이 확실히 다른 것으로 고르고, 수집 전 view_cams.py의 모델 시점에서 확인할 것.
#   · glue stick 은 **구른다.** 눕혀 놓되 굴러가지 않는 자세로 둘 것.
OBJECTS = ["red cube", "blue cube", "yellow cube", "green cube",
           "purple cube", "orange cube",
           "marker", "eraser", "board eraser", "glue stick", "screwdriver"]

# ── 같은 에피소드에 **함께 놓지 않을** 쌍 ────────────────────────────────
#   "the eraser"가 둘 중 어느 것인지 사람도 헷갈린다. 시연자가 잘못 집으면
#   그 에피소드가 "언어를 무시해도 된다"는 반례가 되어 데이터를 오염시킨다.
#   세밀한 구별은 가치 있는 능력이지만, 250ep에 얹을 부담은 아니다.
EXCLUSIVE = [("eraser", "board eraser")]

# ── 목적지 4칸. 색↔칸은 **고정**이다(선반이 고정이므로) ──────────────────
#   번호는 **물리적 왼쪽→오른쪽** 순서다. 색지를 이 순서로 붙일 것.
#   1단계는 1·4번만 쓰므로 **양 끝이 white·black** — 휘도 양극단이 공간적으로도
#   가장 멀리 놓인다. 대비와 행동차가 동시에 최대가 되는 배치다.
#
#   색 선택 기준 셋:
#     · 저해상도·조명 변화에서 서로 멀 것 → 휘도 양극단(white/black) + 포화 색상 2개
#     · 큐브 6색과 **겹치지 않을 것** → 색↔명사 결합 부담을 250ep에 얹지 않는다
#     · 흔한 영어 색 이름일 것
#   ⚠️ 물리 색지는 하늘색이어도 **지시문 단어는 `cyan`**을 쓴다.
#      "blue bin"이라고 하면 **blue cube와 같은 단어**가 되어 충돌한다.
#   brown·gray는 쓰지 않는다 — sim에서 black과 구별되지 않은 바로 그 색들이다.
SLOTS = [(1, "white"), (2, "cyan"), (3, "pink"), (4, "black")]

# 목적지를 부르는 명사. 선반 칸이므로 box가 아니라 bin으로 통일한다.
DEST_NOUN = "bin"

# ── 물체 수 분포 ─────────────────────────────────────────────────────────
#   이전 버전에서는 "1물체 = 언어 신호 0"이라 얇게 깔았다. 이제는 **아니다** —
#   칸이 4개라 물체가 하나여도 목적지 신호는 온전하다(오히려 곱이 풀려 측정이 깨끗하다).
#   다만 **물체 축** 신호는 여전히 0이므로 계속 얇게 유지한다.
COUNT_WEIGHTS = {1: 0.12, 2: 0.20, 3: 0.34, 4: 0.34}

# ── 지시문 문형 ──────────────────────────────────────────────────────────
#   목적지 미명시(the bin)를 일부 남기는 이유: **색 단어의 유무가 의미를 갖는다**는
#   것도 배워야 하고, 최종형("그냥 치워")과 이어진다. 다만 칸이 4개라 정답이
#   정의되지 않으므로 비율을 낮게 두고, **쌍/4연속에는 절대 넣지 않는다**(아래).
TEMPLATES_DEST = [
    "Pick up the {obj} and put it in the {dst} " + DEST_NOUN,
    "Put the {obj} into the {dst} " + DEST_NOUN,
    "Grab the {obj} and place it in the {dst} " + DEST_NOUN,
]
TEMPLATES_PLAIN = [
    "Pick up the {obj} and put it in the " + DEST_NOUN,
    "Put the {obj} into the " + DEST_NOUN,
    "Grab the {obj} and place it in the " + DEST_NOUN,
]

FIELDS = ["ep", "group", "group_kind", "group_pos", "keep_layout",
          "n_objects", "objects", "target", "slot", "slot_color",
          "dest_named", "instruction"]


def pick_least(counter, candidates, rng):
    """가장 적게 쓴 후보를 고른다(동률이면 무작위). 매번 무작위로 뽑으면 고르게 안 나온다."""
    lo = min(counter[c] for c in candidates)
    return rng.choice([c for c in candidates if counter[c] == lo])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", type=int, default=250)
    ap.add_argument("--seed", type=int, default=20260930)
    ap.add_argument("--out", default=os.path.expanduser(
        "~/manipulator_ws/manipulator_md/real/real_lang_plan.csv"))
    ap.add_argument("--slots", default="1,2,3,4",
                    help="쓸 칸 번호. 1단계는 '1,4'(양 끝)로 좁혀 우연 50%%·행동차 최대로 본다")
    ap.add_argument("--pair-frac", type=float, default=0.30,
                    help="대응쌍(같은 배치, 목적지만 다름)이 차지할 에피소드 비율")
    ap.add_argument("--quad-frac", type=float, default=0.16,
                    help="4연속(같은 배치, 4칸 전부)이 차지할 비율. 칸이 4개일 때만")
    ap.add_argument("--dest-frac", type=float, default=0.85,
                    help="목적지 색을 명시하는 비율. 나머지는 'the bin'(단독에서만)")
    a = ap.parse_args()
    rng = random.Random(a.seed)

    want = [int(x) for x in a.slots.split(",") if x.strip()]
    slots = [(n, c) for n, c in SLOTS if n in want]
    assert len(slots) >= 2, "칸이 2개 이상이어야 목적지 축이 성립한다"
    slot_nums = [n for n, _ in slots]

    # ── 1) 그룹 구조를 먼저 정한다 ──────────────────────────────────────
    #   에피소드를 낱개로 뽑으면 쌍이 안 생긴다. 그룹 단위로 예산을 나눈 뒤 펼친다.
    n_quad = int(a.episodes * a.quad_frac) // 4 if len(slots) >= 4 else 0
    n_pair = int(a.episodes * a.pair_frac) // 2
    n_single = a.episodes - n_quad * 4 - n_pair * 2
    assert n_single >= 0, "pair-frac + quad-frac 이 1을 넘었다"

    kinds = ["quad"] * n_quad + ["pair"] * n_pair + ["single"] * n_single
    rng.shuffle(kinds)

    # 목적지 미명시는 **단독 에피소드에서만** 나온다.
    #   쌍/4연속에서 목적지를 안 부르면 같은 지시문에 서로 다른 목적지를 시연하는 것이 되어
    #   "목적지 단어를 무시하라"를 정면으로 가르친다. 대응쌍의 취지를 정확히 뒤집는다.
    n_unnamed = min(int(a.episodes * (1 - a.dest_frac)), n_single)
    unnamed = set(rng.sample(range(n_single), n_unnamed)) if n_single else set()

    tgt_count, slot_count = Counter(), Counter()
    rows, single_i, ep = [], 0, 0

    for gi, kind in enumerate(kinds):
        # 그룹 하나는 배치(물체 구성·타깃)를 공유한다. 사람은 물체를 한 번만 놓는다.
        target = pick_least(tgt_count, OBJECTS, rng)
        n_obj = rng.choices(list(COUNT_WEIGHTS), list(COUNT_WEIGHTS.values()))[0]
        # 상호 배제 — 헷갈리는 짝이 **한 화면에 같이 서지 않도록** 한다.
        #   타깃 기준으로만 막으면 부족하다. 타깃이 'red cube'여도 방해물로
        #   eraser와 board eraser가 **둘 다** 뽑힐 수 있다(자체 검사로 13건 적발).
        #   그래서 하나를 고를 때마다 그 짝을 풀에서 즉시 뺀다.
        def partners_of(x):
            return {b for pr in EXCLUSIVE for a, b in (pr, pr[::-1]) if a == x}

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
        elif kind == "pair":
            first = pick_least(slot_count, slot_nums, rng)
            second = pick_least(slot_count, [n for n in slot_nums if n != first], rng)
            picks = [(n, c) for n, c in slots if n in (first, second)]
            rng.shuffle(picks)
        else:
            n = pick_least(slot_count, slot_nums, rng)
            picks = [(sn, sc) for sn, sc in slots if sn == n]

        for pos, (snum, scol) in enumerate(picks, start=1):
            ep += 1
            tgt_count[target] += 1
            slot_count[snum] += 1

            named = True
            if kind == "single":
                named = single_i not in unnamed
                single_i += 1

            instr = (rng.choice(TEMPLATES_DEST).format(obj=target, dst=scol) if named
                     else rng.choice(TEMPLATES_PLAIN).format(obj=target))

            rows.append({
                "ep": ep,
                "group": gi + 1,
                "group_kind": kind,
                "group_pos": f"{pos}/{len(picks)}",
                # 시연자에게 주는 유일한 조작 지시다. 2회차부터는 물체를 건드리면 안 된다.
                "keep_layout": "NEW" if pos == 1 else "KEEP",
                "n_objects": n_obj,
                "objects": ", ".join(objs),
                "target": target,
                "slot": snum,
                "slot_color": scol,
                "dest_named": scol if named else "",
                "instruction": instr,
            })

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    report(rows, slots, a)
    return 0


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
    """수집 **전에** 걸러야 하는 것들. 9시간 쓰고 나서 알면 늦다."""
    N = len(rows)
    tc = Counter(r["target"] for r in rows)
    sc = Counter(r["slot"] for r in rows)
    nc = Counter(r["n_objects"] for r in rows)
    kc = Counter(r["group_kind"] for r in rows)
    ac = Counter(o for r in rows for o in r["objects"].split(", "))
    named = sum(1 for r in rows if r["dest_named"])
    ok = True

    print(f"\n  {a.out}\n  {N}행 · 칸 {len(slots)}개 " +
          " ".join(f"{n}={c}" for n, c in slots) + "\n")

    print("  그룹 구성")
    for k in ("quad", "pair", "single"):
        if kc[k]:
            print(f"    {k:<7} {kc[k]:>3}ep ({kc[k] / N * 100:.0f}%)")
    print("    ↑ quad·pair는 **같은 배치**를 재사용한다 — 관측 동일, 행동만 다름.")
    print("      물체를 다시 놓지 않으므로 에피소드당 ~40초 절약된다.")

    exp = N / len(OBJECTS)
    print(f"\n  타깃 분포 (기대 {exp:.0f} ±30%)")
    bad = [o for o in OBJECTS if not exp * 0.7 <= tc[o] <= exp * 1.3]
    for o in OBJECTS:
        print(f"    {o:<13} 타깃 {tc[o]:>3}   등장 {ac[o]:>3}{'  ⚠' if o in bad else ''}")
    ok &= not bad
    print(f"  {'✅ 타깃 균형' if not bad else '❌ 타깃 불균형: ' + ', '.join(bad)}")

    exps = N / len(slots)
    print(f"\n  칸 분포 (기대 {exps:.0f} ±30%)")
    badv = [n for n, _ in slots if not exps * 0.7 <= sc[n] <= exps * 1.3]
    for n, c in slots:
        print(f"    {n}번 {c:<7} {sc[n]:>3}{'  ⚠' if n in badv else ''}")
    ok &= not badv
    print(f"  {'✅ 칸 균형' if not badv else '❌ 칸 불균형: ' + str(badv)}")

    print("\n  물체 수: " + "  ".join(
        f"{k}개 {nc[k]}({nc[k] / N * 100:.0f}%)" for k in sorted(nc)))
    print(f"  목적지 명시 {named}/{N} ({named / N * 100:.0f}%) — 계획 {a.dest_frac * 100:.0f}%")
    print(f"  서로 다른 지시문 {len(set(r['instruction'] for r in rows))}종")

    # 쌍 무결성 — 여기가 깨지면 대응쌍이 역효과를 낸다
    bad_pairs = []
    for g, items in groups(rows):
        if len(items) == 1:
            continue
        if len({i["objects"] for i in items}) != 1 or len({i["target"] for i in items}) != 1:
            bad_pairs.append((g, "배치가 다름"))
        if len({i["slot"] for i in items}) != len(items):
            bad_pairs.append((g, "칸이 겹침"))
        if any(not i["dest_named"] for i in items):
            bad_pairs.append((g, "목적지 미명시가 섞임"))
    ok &= not bad_pairs
    print(f"  {'✅' if not bad_pairs else '❌'} 쌍 무결성 "
          f"(같은 배치 · 서로 다른 칸 · 목적지 전부 명시)  위반 {len(bad_pairs)}건")
    for g, why in bad_pairs[:5]:
        print(f"       그룹 {g}: {why}")

    # 상호 배제가 지켜졌는가 — 깨지면 지시문이 모호해진다
    viol = []
    for r in rows:
        on = set(x.strip() for x in r["objects"].split(","))
        for a, b in EXCLUSIVE:
            if a in on and b in on:
                viol.append((r["ep"], a, b))
    ok &= not viol
    print(f"  {'✅' if not viol else '❌'} 상호 배제 (같은 화면에 두지 않을 쌍)  위반 {len(viol)}건")
    for ep, a, b in viol[:3]:
        print(f"       ep{ep}: '{a}' 와 '{b}' 가 함께 있다")

    reuse = sum(1 for r in rows if r["keep_layout"] == "KEEP")
    hours = ((N - reuse) * 150 + reuse * 110) / 3600
    print(f"\n  예상 수집 시간 약 {hours:.1f}시간 "
          f"(신규 {N - reuse}ep×150s + 배치재사용 {reuse}ep×110s)")
    print(f"\n  {'✅ 통과 — 수집 시작 가능' if ok else '❌ 위 항목을 고칠 것'}")

    print("""
  ── 시연 규칙 (수집 내내 지킬 것) ─────────────────────────────────────
   · keep_layout=KEEP 행은 **물체를 건드리지 않는다.** 지시문만 바뀐다.
     이 데이터셋에서 언어 신호가 가장 진한 구간이다.
   · 파지 직후 **목표 칸 위로 먼저 횡이동**하고 그다음 하강한다.
     공통 경로로 올라갔다가 마지막에 갈라지지 말 것 — 목적지가 지배하는
     프레임이 2~3배로 늘어난다(sim에서 목적지 축이 죽은 주된 이유가 이것이다).
   · 물체는 매번 다른 자리에. 무의식적으로 같은 자리에 놓기 쉽다
     (실기 50ep에서 박스가 사실상 고정이었던 전례: 픽셀 중심 편차 x 7px).
   · 지시와 다른 물체를 집었거나 다른 칸에 넣었으면 **그 에피소드를 다시 찍는다.**
     잘못 저장된 1개가 "언어를 무시해도 된다"는 반례가 된다.
""")


if __name__ == "__main__":
    raise SystemExit(main())
