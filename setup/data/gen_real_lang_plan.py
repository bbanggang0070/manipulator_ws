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
      --out ~/manipulator_ws/manipulator_md/p5_real_cleanup/real_lang_plan_s1.csv
"""
import argparse
import csv
import os
import random
from collections import Counter

# ── 물체 10종. 이름이 지시문에 그대로 들어간다 ───────────────────────────
#   큐브 6색 + 사물 5종. 사물 쪽은 형상이 다양해 **파지 난이도 편차가 크다** —
#   sim 분해에서 병목이 언어가 아니라 조작(물체+배치 45.0%)이었으므로,
#   어려운 물체를 넣을수록 전체 성공률은 더 내려간다. 평가 때 축을 분리해 본다.
#   · screwdriver, glue stick, marker 는 **가늘고 길다** — 256²에서 서로 닮는다.
#     색이 확실히 다른 것으로 고르고, 수집 전 view_cams.py의 모델 시점에서 확인할 것.
#   · glue stick 은 **구른다.** 눕혀 놓되 굴러가지 않는 자세로 둘 것.
#   ⚠️ **red cube 와 orange cube 는 같이 쓰면 안 된다.** v2 수집본 실측:
#      색상환에서 red 4° · orange 22° 로 **18° 차이**뿐이고 둘 다 채도가 낮다
#      (33%, 42% — 초록 큐브는 75%). 사람이 봐도 구별이 어렵고, 평가에서
#      "orange" 지시의 40%가 red 로 샜다(10회 중 4회). 이건 학습량으로 풀 문제가
#      아니라 **물체를 바꿔야** 하는 문제다. 색상환에서 60° 이상 떨어뜨릴 것.
#      (참고: 학습에 쓴 hue 증강 ±5.4° 조차 이 18° 간격의 30% 를 먹는다)
OBJECTS = ["red cube", "blue cube", "yellow cube", "green cube",
           "purple cube", "orange cube",
           "marker", "eraser", "glue stick", "screwdriver"]

# ── 같은 에피소드에 **함께 놓지 않을** 쌍 ────────────────────────────────
#   지금은 비어 있다 — board eraser를 빼면서 유일한 충돌 쌍이 사라졌다.
#   이름이 서로 포함 관계인 물체를 추가하면(예: "eraser"와 "board eraser")
#   여기 넣어야 한다. "the eraser"가 어느 쪽인지 사람도 헷갈리고, 시연자가
#   잘못 집으면 그 에피소드가 "언어를 무시해도 된다"는 반례가 되기 때문이다.
EXCLUSIVE = []

# ── 같은 물체를 **여러 자세로** 놓게 한다 ───────────────────────────────
#   v2 수집본 실측: eraser 는 재파지율 20% 로 1위였고(큐브는 4~8%), 파지 시
#   shoulder_lift 가 +4.0° 로 다른 물체(-3.6 ~ -11.3°)보다 훨씬 깊이 내려가는
#   유일한 outlier 였다. 납작해서 책상에 바싹 붙기 때문이다.
#   그 결과 평가에서 "eraser" 지시의 절반이 marker 로 샜다 — 생김새가 아니라
#   **파지가 불안정해 행동이 안 정해진 것**이다.
#   눕힘/세움을 번갈아 시연하면 (a) 세운 자세는 파지 높이가 올라가 책상에 안 닿고
#   (b) 두 자세를 모두 덮어 자세 일반화가 생긴다.
#   값은 시연자에게 주는 **배치 지시**다. 지시문에는 들어가지 않는다.
#   ⚠️ v3 는 **세움으로 통일**한다. v2 250ep 에서 eraser 가 88회 등장했고 전부
#      눕힌 자세였으므로 눕힘은 이미 충분하다. 여기에 세움만 더해 두 자세를 덮는다.
#      (궤적으로는 자세를 가릴 수 없다 — 파지 시 lift 의 편차 14.0° 가 큐브 13.6° 와
#       같아서, 그 편차는 자세가 아니라 **물체를 놓은 위치** 때문이다.
#       자세 균형은 사람이 지키는 수밖에 없고, 그래서 계획표가 행마다 지시한다.)
POSE_VARIANTS = {"eraser": ["세워서"]}

# ── 목적지 4칸. 색↔칸은 **고정**이다(선반이 고정이므로) ──────────────────
#   번호는 **물리적 왼쪽→오른쪽** 순서다. 색지를 이 순서로 붙일 것.
#   1단계는 1·4번만 쓰므로 **양 끝이 black·white** — 휘도 양극단이 공간적으로도
#   가장 멀리 놓인다. 대비와 행동차가 동시에 최대가 되는 배치다.
#
#   색 선택 기준 셋:
#     · 저해상도·조명 변화에서 서로 멀 것 → 휘도 양극단(white/black) + 포화 색상 2개
#     · 큐브 6색과 **겹치지 않을 것** → 색↔명사 결합 부담을 250ep에 얹지 않는다
#     · 흔한 영어 색 이름일 것
#   ⚠️ 물리 색지는 하늘색이어도 **지시문 단어는 `cyan`**을 쓴다.
#      "blue bin"이라고 하면 **blue cube와 같은 단어**가 되어 충돌한다.
#   brown·gray는 쓰지 않는다 — sim에서 black과 구별되지 않은 바로 그 색들이다.
SLOTS = [(1, "black"), (2, "cyan"), (3, "pink"), (4, "white")]

# 목적지를 부르는 명사. 선반 칸이므로 box가 아니라 bin으로 통일한다.
DEST_NOUN = "bin"

# ── 물체 수 분포 ─────────────────────────────────────────────────────────
#   이전 버전에서는 "1물체 = 언어 신호 0"이라 얇게 깔았다. 이제는 **아니다** —
#   칸이 4개라 물체가 하나여도 목적지 신호는 온전하다(오히려 곱이 풀려 측정이 깨끗하다).
#   다만 **물체 축** 신호는 여전히 0이므로 계속 얇게 유지한다.
COUNT_WEIGHTS = {1: 0.12, 2: 0.20, 3: 0.34, 4: 0.34}

# ── 지시문 문형 ──────────────────────────────────────────────────────────
#   ⚠️ **문형은 1종이다** (2026-10-07 변경). 전에는 3종이었는데, 그러면 지시문
#      가짓수가 3배로 불어난다. 1차 수집 실측: 80ep 에 지시문 49종 =
#      **지시문당 1.6 에피소드**. sim(280ep/100종 = 2.8)보다도 얇았고
#      그 데이터로 학습한 모델은 물체를 집지 못했다.
#      문형을 하나로 고정하면 지시문이 **물체 × 칸**으로만 결정된다:
#        4칸 × 물체 10종 = 40종 → 250ep 이면 지시문당 5.3 에피소드.
#      문형 일반화(같은 뜻의 다른 문장)는 **포기한다.** 지금 재야 하는 것은
#      "색 단어를 읽는가"이지 "문장을 바꿔도 되는가"가 아니다.
#   ⚠️ **목적지 미명시(the bin)는 쓰지 않는다** (2026-10-07, dest-frac 기본 1.0).
#      전에는 "색 단어의 유무가 의미를 갖는다"를 가르치려고 10~15% 남겼다.
#      그런데 칸이 4개면 "the bin" 의 **정답이 정의되지 않는다.** 시연자는
#      임의로 지정된 칸에 넣고, 모델은 같은 문장에서 서로 다른 칸을 본다 —
#      결국 "목적지 단어를 무시해도 된다"를 배운다. 지금 재야 하는 건
#      "색 단어를 읽는가"이므로 그 반대를 가르칠 여유가 없다.
#      최종형("그냥 치워")은 색을 다 읽게 된 뒤에 별도로 붙인다.
TEMPLATES_DEST = [
    "Put the {obj} into the {dst} " + DEST_NOUN,
]
TEMPLATES_PLAIN = [
    "Put the {obj} into the " + DEST_NOUN,
]

FIELDS = ["ep", "group", "group_kind", "group_pos", "keep_layout",
          "n_objects", "objects", "target", "slot", "slot_color",
          "dest_named", "pose_hint", "instruction"]


def pick_least(counter, candidates, rng):
    """가장 적게 쓴 후보를 고른다(동률이면 무작위). 매번 무작위로 뽑으면 고르게 안 나온다."""
    lo = min(counter[c] for c in candidates)
    return rng.choice([c for c in candidates if counter[c] == lo])


def pick_least2(key1, key2, candidates, rng):
    """1차 기준으로 고르고 동률이면 2차 기준, 그래도 동률이면 무작위.

    물체와 칸을 **따로** 균등하게 맞추면 그 **조합**은 고르지 않다.
    v2 계획표 실측: 물체당 24~27ep · 칸당 62~63ep 으로 주변 분포는 완벽한데
    (물체×칸) 40종은 2~12회로 6배나 벌어졌다. 주변 분포가 중요하긴 해도
    조합을 맞추는 데 드는 추가 비용이 **0**이므로 맞춰 둔다.
    """
    best = min((key1(c), key2(c)) for c in candidates)
    return rng.choice([c for c in candidates if (key1(c), key2(c)) == best])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", type=int, default=250)
    ap.add_argument("--seed", type=int, default=20260930)
    ap.add_argument("--out", default=os.path.expanduser(
        "~/manipulator_ws/manipulator_md/p5_real_cleanup/real_lang_plan.csv"))
    ap.add_argument("--slots", default="1,2,3,4",
                    help="쓸 칸 번호. 1단계는 '1,4'(양 끝)로 좁혀 우연 50%%·행동차 최대로 본다")
    ap.add_argument("--pair-frac", type=float, default=0.30,
                    help="대응쌍(같은 배치, 목적지만 다름)이 차지할 에피소드 비율")
    ap.add_argument("--quad-frac", type=float, default=0.16,
                    help="4연속(같은 배치, 4칸 전부)이 차지할 비율. 칸이 4개일 때만")
    ap.add_argument("--dest-frac", type=float, default=1.0,
                    help="목적지 색을 명시하는 비율. 기본 1.0 = **전부 명시**. "
                         "4칸에서 'the bin' 은 정답이 없어 언어 신호를 거꾸로 가르친다")
    ap.add_argument("--base", help="이어 짤 기존 계획표 (--keep-head 와 함께)")
    ap.add_argument("--keep-head", type=int, default=0,
                    help="기존 계획표의 앞 N행을 그대로 두고 나머지만 다시 짠다. "
                         "수집 중에 고칠 때 쓴다 — 이미 찍은 행을 건드리면 진행 기록이 깨진다")
    a = ap.parse_args()
    rng = random.Random(a.seed)

    want = [int(x) for x in a.slots.split(",") if x.strip()]
    slots = [(n, c) for n, c in SLOTS if n in want]
    assert len(slots) >= 2, "칸이 2개 이상이어야 목적지 축이 성립한다"
    slot_nums = [n for n, _ in slots]

    tgt_count, slot_count, combo_count = Counter(), Counter(), Counter()
    pose_count = Counter()
    rows, single_i, ep = [], 0, 0

    # ── 0) 이어 짜기 ────────────────────────────────────────────────────
    #   수집 중에 계획표를 고쳐야 할 때가 있다(실제로 겪음). 이미 찍은 행을
    #   건드리면 진행 기록·순서 검사가 깨지므로 **앞 N행은 그대로 두고**
    #   카운터만 그 행들로 채운 뒤 **남은 예산만큼** 다시 짠다.
    #   ⚠️ 그룹 예산은 반드시 **남은 에피소드 수**로 계산해야 한다. 전체 예산으로
    #      만든 뒤 잘라내면 그룹 수가 어긋나 총 행 수가 모자란다(실제로 겪음).
    head, gi_off = [], 0
    if a.base and a.keep_head:
        base = list(csv.DictReader(open(os.path.expanduser(a.base))))
        n = a.keep_head
        # 그룹 중간에서 자르면 대응쌍이 반토막 난다 — 그룹 끝까지 민다.
        while n < len(base) and base[n]["keep_layout"] == "KEEP":
            n += 1
        head = base[:n]
        # ⚠️ CSV 에서 읽으면 전부 문자열이다. 새로 만드는 행은 slot/group/n_objects 가
        #    정수라, 그대로 합치면 Counter 가 "1" 과 1 을 **다른 키로** 센다
        #    (칸 분포가 새 행만 세어 멀쩡한 계획표가 불균형으로 찍혔다).
        for r in head:
            for k in ("group", "n_objects", "slot"):
                r[k] = int(r[k])
        for r in head:
            tgt_count[r["target"]] += 1
            slot_count[int(r["slot"])] += 1
            combo_count[(r["target"], r["slot_color"])] += 1
        ep, gi_off = n, int(head[-1]["group"])
        print(f"  ▶ 앞 {n}행 유지 (그룹 {gi_off}까지) · {n + 1}행부터 다시 짠다")

    budget = a.episodes - ep
    assert budget > 0, f"--keep-head({ep})가 --episodes({a.episodes}) 이상이다"

    # ── 1) 그룹 구조를 정한다 ───────────────────────────────────────────
    #   에피소드를 낱개로 뽑으면 쌍이 안 생긴다. 그룹 단위로 예산을 나눈 뒤 펼친다.
    n_quad = int(budget * a.quad_frac) // 4 if len(slots) >= 4 else 0
    n_pair = int(budget * a.pair_frac) // 2
    n_single = budget - n_quad * 4 - n_pair * 2
    assert n_single >= 0, "pair-frac + quad-frac 이 1을 넘었다"

    kinds = ["quad"] * n_quad + ["pair"] * n_pair + ["single"] * n_single
    rng.shuffle(kinds)

    # 목적지 미명시는 **단독 에피소드에서만** 나온다.
    #   쌍/4연속에서 목적지를 안 부르면 같은 지시문에 서로 다른 목적지를 시연하는 것이 되어
    #   "목적지 단어를 무시하라"를 정면으로 가르친다. 대응쌍의 취지를 정확히 뒤집는다.
    n_unnamed = min(int(budget * (1 - a.dest_frac)), n_single)
    unnamed = set(rng.sample(range(n_single), n_unnamed)) if n_single else set()

    for gi, kind in enumerate(kinds, start=gi_off):
        # 그룹 하나는 배치(물체 구성·타깃)를 공유한다. 사람은 물체를 한 번만 놓는다.
        # 타깃은 총량 기준으로 고르되, 동률이면 **덜 채워진 조합을 더 많이 가진** 쪽.
        target = pick_least2(lambda o: tgt_count[o],
                             lambda o: min(combo_count[(o, c)] for _, c in slots),
                             OBJECTS, rng)
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
        else:
            # 이 타깃과의 **조합**이 가장 적게 쓰인 칸을 고르고, 동률이면 칸 총량으로.
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

            named = True
            if kind == "single":
                named = single_i not in unnamed
                single_i += 1

            instr = (rng.choice(TEMPLATES_DEST).format(obj=target, dst=scol) if named
                     else rng.choice(TEMPLATES_PLAIN).format(obj=target))

            # 자세 지시 — 화면에 있는 물체 중 POSE_VARIANTS 에 든 것만.
            # 그룹 안에서는 배치를 바꾸지 않으므로 1회차(NEW)에 정하고 그대로 쓴다.
            if pos == 1:
                hints = []
                for o in objs:
                    if o in POSE_VARIANTS:
                        v = pick_least(pose_count, POSE_VARIANTS[o], rng)
                        # 그룹 크기만큼 센다 — 4연속에서 고른 자세는 4에피소드에
                        # 쓰인다. 그룹당 1로 세면 22 vs 14 로 벌어진다(실측).
                        pose_count[v] += len(picks)
                        hints.append(f"{o} {v}")
                group_hint = " · ".join(hints)

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
                "pose_hint": group_hint,
                "instruction": instr,
            })

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(head + rows)

    report(head + rows, slots, a)
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
   · **한 번에 못 잡았으면 다시 찍는다.** 1차 수집 실측은 재파지 11%(9/80)로
     나쁘지 않았지만, 모델은 시연을 그대로 모사하므로 이 비율이 낮을수록 좋다.
     검증기가 '파지 시도 2회 이상'을 에피소드 번호까지 찍어 준다(15% 초과면 실패).
   · **시작 자세를 매번 같게.** 1차 수집 실측: wrist_flex ±14.3° · gripper ±11.0°.
     rest 가 느슨하게 정의되면 배포 때 어느 자세로 출발해야 할지 정할 수 없다
     (goto_home 목표가 흔들린다). 리더를 거치대에 놓고 시작할 것.
   · **놓은 뒤에는 곧장 rest 로 — 확인하러 머물지 말 것. 그리고 rest 에서
     1~2초 멈춘 뒤 녹화를 끝낸다.**
     v2 실측: 에피소드 끝 자세가 시작 자세에서 중앙 7.7° 벗어나 있었고
     5° 이내로 복귀한 것은 27% 뿐이었다. 즉 **복귀 도중에 녹화가 끝났다.**
     모델에는 종료 신호가 없어 "이제 멈춰라"를 오직 궤적으로만 배우는데,
     그 궤적이 끝나다 말았으니 배울 것이 없었다. 평가에서 **42%가 칸 위에
     머문 채 타임아웃**했고, 그중 18건은 올바른 칸에 넣기까지 성공한 뒤였다.
   · **파지는 책상에 닿지 않는 높이에서.** v2 실측: eraser 는 파지 시
     shoulder_lift 가 +4.0° 로 다른 물체(-3.6 ~ -11.3°)보다 훨씬 깊이 내려갔고,
     재파지율도 20% 로 1위였다(큐브는 4~8%). 평가에서 "eraser" 지시의 절반이
     marker 로 샜다 — 생김새가 아니라 **파지가 불안정해서 행동이 안 정해진 것**이다.
     납작한 물체는 받침을 두거나 세워 놓아 파지 높이를 맞출 것.
""")


if __name__ == "__main__":
    raise SystemExit(main())
