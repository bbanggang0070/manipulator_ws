"""색지 교체 검증 v2 — **목적지 축만** 분리해서 재측정.

v1(30시행, 배치당 5)의 문제: 물체 선택 실패(17%)가 목적지 축 분모를 깎아먹어
배치당 유효 표본이 3~5건까지 줄었다. 신뢰구간이 겹쳐 결론을 못 냈다.

여기서는 **cleanup_eval.py 가 이미 가진 가장 강한 설계**(dest 4연속 — 같은 배치·
같은 물체로 4칸을 전부 순환)를 배치마다 여러 그룹 반복한다. 장점 둘:
  · 물체를 한 번만 놓고 그룹 안에서는 다시 안 놓는다 → 재배치로 인한 변동 없음
  · 타깃을 **큐브로만** 고정한다 — v1에서 못 집은 5건 전부가 marker/screwdriver/
    glue stick/eraser 류였다(얇거나 세워야 하는 물체). 큐브는 실기 평가 전체에서
    재파지율이 가장 낮았던 부류다(설정 data/gen_real_lang_plan.py 수집 로그 참고).
    "목적지를 읽는가"를 재는 게 목적이므로, 파지 실패 잡음은 최대한 뺀다.

배치 1개당 --groups-per-layout(기본 4) 그룹 × 4시행 = 16시행. 6배치 × 16 = 96시행.
--groups-per-layout 5 로 올리면 배치당 20시행(총 120)이 된다.

사용:
  python3 gen_swap6_dest_plan.py --out ~/manipulator_ws/manipulator_md/p5_real_cleanup/swap6_dest_plan.csv
  python3 gen_swap6_dest_plan.py --groups-per-layout 5 --out ...   # 배치당 20시행
"""
import argparse
import csv
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cleanup_eval import EXCLUSIVE, partners_of  # noqa: E402
from gen_swap6_plan import LAYOUTS, check_derangements, hint_text  # noqa: E402

# 큐브 6색만. marker/eraser/glue stick/screwdriver 는 뺀다(파지 신뢰도 낮음 — 위 설명).
CUBE_OBJECTS = ["red cube", "blue cube", "yellow cube",
                "green cube", "purple cube", "orange cube"]
DISTRACTOR_POOL = CUBE_OBJECTS + ["marker", "eraser", "glue stick", "screwdriver"]

TEMPLATES = ["Put the {obj} into the {dst} bin"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--groups-per-layout", type=int, default=4,
                    help="배치당 4연속 그룹 수. 4 → 배치당 16시행(기본), 5 → 20시행")
    ap.add_argument("--seed", type=int, default=909)
    ap.add_argument("--out", default=os.path.expanduser(
        "~/manipulator_ws/manipulator_md/p5_real_cleanup/swap6_dest_plan.csv"))
    a = ap.parse_args()
    check_derangements()
    rng = random.Random(a.seed)

    FIELDS = ["trial", "group", "kind", "pos", "keep_layout", "objects", "target",
              "slot", "slot_color", "pose_hint", "layout_hint", "instruction"]
    rows = []
    trial = group = 0
    order = sorted(LAYOUTS)  # L1(대조군) 먼저, 이어서 L2..L6
    tgt_count = {o: 0 for o in CUBE_OBJECTS}

    for lname in order:
        cols = LAYOUTS[lname]  # 이 배치의 물리 위치별 색
        for _ in range(a.groups_per_layout):
            group += 1
            # 타깃은 **그룹당 1회**가 아니라 뽑히는 순간 기준으로 가장 적게 쓴 것부터.
            #   (cleanup_eval.py 에서 그룹당 1회로 세어 orange 10회 vs red 2회로
            #    벌어졌던 버그를 반복하지 않는다 — 여기서도 4연속이 4시행이므로
            #    그만큼 카운트해야 한다.)
            tgt = min(CUBE_OBJECTS, key=lambda o: (tgt_count[o], rng.random()))
            tgt_count[tgt] += 4
            pool = [o for o in DISTRACTOR_POOL if o != tgt and o not in partners_of(tgt)]
            n_obj = rng.choice([2, 3, 3])  # 큐브 타깃 + 방해물 1~2개. 너무 빽빽하면 안 그래도
                                            # 적은 목적지 표본을 또 깎아먹는다 — 가볍게 유지.
            objs = [tgt]
            for _ in range(n_obj - 1):
                if not pool:
                    break
                pick = rng.choice(pool)
                objs.append(pick)
                drop = partners_of(pick) | {pick}
                pool = [o for o in pool if o not in drop]
            rng.shuffle(objs)

            picks = list(enumerate(cols, start=1))  # (물리번호, 색) 쌍 4개
            rng.shuffle(picks)
            for pos, (snum, scol) in enumerate(picks, start=1):
                trial += 1
                rows.append({
                    "trial": trial, "group": group, "kind": "dest",
                    "pos": f"{pos}/4", "keep_layout": "NEW" if pos == 1 else "KEEP",
                    "objects": ", ".join(objs), "target": tgt,
                    "slot": snum, "slot_color": scol,
                    "pose_hint": "",
                    "layout_hint": hint_text(lname) if pos == 1 else "",
                    "instruction": rng.choice(TEMPLATES).format(obj=tgt, dst=scol),
                })
            # layout_hint 는 cmd_log 의 "이전 행과 다르면 배너" 로직용이다. 그룹
            # 중간(pos>1, KEEP)에 값을 넣으면 **그룹 안에서** 전환 배너가 떠서
            # "물체 건드리지 마세요"와 "배치를 바꾸세요"가 동시에 뜨는 모순이 생긴다.
            # 그래서 각 그룹의 1행(pos=1)에만 쓰고, 배치가 실제로 안 바뀐 그룹(같은
            # 배치의 2번째 이후 그룹)은 cmd_log 쪽에서 "이전과 동일"로 자동 무시된다.

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    from collections import Counter
    print(f"\n  {a.out}  —  {len(rows)}시행 · {len(order)}배치 × "
          f"{a.groups_per_layout}그룹(16연속) = 배치당 {a.groups_per_layout * 4}시행")
    for lname in order:
        print(f"    {hint_text(lname)}")
    tc = Counter(r["target"] for r in rows)
    print(f"\n  타깃(큐브만) 분포: {dict(sorted(tc.items(), key=lambda kv: -kv[1]))}")
    bad = [r["trial"] for r in rows
           for x, y in EXCLUSIVE if x in r["objects"] and y in r["objects"]]
    print(f"  상호 배제: {'✅ 위반 0건' if not bad else f'❌ {bad}'}")
    print(f"  예상 시간: 약 {len(rows) * 2.5 / 60:.1f}시간 (시행당 2.5분, KEEP 구간은 더 빠름) "
          f"+ 배치 전환 {len(order) - 1}회")
    need = 20
    print(f"\n  참고: 우연 25% 기준 정확도 50%를 p<0.05로 잡으려면 배치=분모 {need}건 필요.")
    print(f"  배치당 목표 분모는 {a.groups_per_layout * 4}건(파지 성공 시) — "
          + ("충분" if a.groups_per_layout * 4 >= need else "약간 모자랄 수 있음(파지 실패 감안)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
