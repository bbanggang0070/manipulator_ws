"""평가 결과(`scenes.csv`)를 **거리·각도 구간별로** 분해한다.

왜 필요한가:
  v3의 병목이 '블록-박스 근접'으로 특정된 뒤로, 전체 SR 하나만으로는 개선 여부를 못 본다.
  근접 구간이 올랐는지, 그 대가로 원거리가 떨어지지 않았는지(catastrophic forgetting)를
  같이 봐야 판정이 된다. 매번 임시 스크립트를 짜던 것을 고정한다.

사용:
  python3 analyze_eval_scenes.py <scenes.csv 폴더> [...]           # 여러 배치 합산
  python3 analyze_eval_scenes.py --exclude 1,15,19 <폴더>          # 겹침 등 무효 ep 제외
  python3 analyze_eval_scenes.py --label v4@86k <폴더>...          # 표에 붙일 이름

`--exclude`는 폴더 순서대로 세미콜론으로 구분해 배치별로 줄 수 있다:
  --exclude "1,15,19;3,7"    # 첫 폴더에서 1·15·19, 두 번째에서 3·7 제외

판정 기준(README §1):
  full 전체 ≥80% · 근접(<0.18m) ≥70% · 원거리(≥0.18m) 유지 ≥80%
"""
import argparse
import csv
import os
import sys
from math import sqrt

# v3@40k 실측 (좌표 보유 57ep). 개선 여부를 바로 볼 수 있게 나란히 찍는다.
BASELINE = {"name": "v3@40k", "overall": (35, 57),
            "bins": {(0, .12): (2, 11), (.12, .18): (7, 14),
                     (.18, .25): (11, 15), (.25, 9): (15, 17)},
            "near": (9, 25), "far": (26, 32)}
BINS = [(0, .12), (.12, .18), (.18, .25), (.25, 9)]
NEAR_CUT = 0.18


def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return 100 * (c - h), 100 * (c + h)


def pct(k, n):
    return f"{k}/{n} = {k/n*100:.1f}%" if n else f"0/0 = —"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="+", help="scenes.csv 가 있는 폴더")
    ap.add_argument("--exclude", default="", help="제외할 ep. 폴더별로 ';' 구분, 폴더 내는 ','")
    ap.add_argument("--label", default="현재", help="표에 붙일 이름")
    ap.add_argument("--fix", default="",
                    help="자동 라벨이 틀린 ep를 성공으로 교정. 폴더별 ';' 구분 "
                         "(예: '6;' = 첫 폴더의 ep6). grasp_history 결함 수정(2026-08-06) "
                         "이전 데이터에만 필요하다 — 이후 45ep 측정에서 오표기 0건.")
    args = ap.parse_args()

    def parse(spec):
        return [set(int(x) for x in part.split(",") if x.strip())
                for part in (spec.split(";") if spec else [])]
    excl, fix = parse(args.exclude), parse(args.fix)
    rows = []
    for i, d in enumerate(args.dirs):
        p = os.path.join(d, "scenes.csv")
        if not os.path.exists(p):
            sys.exit(f"❌ 없음: {p}")
        skip = excl[i] if i < len(excl) else set()
        corr = fix[i] if i < len(fix) else set()
        got = 0
        for r in csv.DictReader(open(p)):
            if int(r["ep"]) in skip:
                continue
            rows.append({"src": os.path.basename(d), "ep": int(r["ep"]),
                         "ok": r["outcome"] == "success" or int(r["ep"]) in corr,
                         "d": float(r["block_box_dist"]),
                         "th": float(r["block_theta"]), "r": float(r["block_r"])})
            got += 1
        print(f"  {os.path.basename(d):<18} {got}ep"
              + (f"  제외 {sorted(skip)}" if skip else "")
              + (f"  성공교정 {sorted(corr)}" if corr else ""))

    n = len(rows)
    k = sum(1 for x in rows if x["ok"])
    lo, hi = wilson(k, n)
    bk, bn = BASELINE["overall"]
    print(f"\n{'='*66}\n{args.label} — 전체 {pct(k,n)}   95% CI [{lo:.0f}, {hi:.0f}]")
    print(f"{'':>{len(args.label)}}   {BASELINE['name']}: {pct(bk,bn)}   (목표 ≥80%)")
    print("=" * 66)

    print(f"\n── 블록-박스 거리 구간별 ── ({args.label} vs {BASELINE['name']})")
    print(f"{'구간':<16}{args.label:>16}{BASELINE['name']:>16}   변화")
    for a, b in BINS:
        sub = [x for x in rows if a <= x["d"] < b]
        kk = sum(1 for x in sub if x["ok"])
        b_k, b_n = BASELINE["bins"][(a, b)]
        cur = kk / len(sub) * 100 if sub else 0
        base = b_k / b_n * 100
        nm = f"{a:.2f}~{b:.2f}m" if b < 9 else f"{a:.2f}m 이상"
        print(f"  {nm:<14}{pct(kk,len(sub)):>16}{pct(b_k,b_n):>16}   {cur-base:+5.1f}%p")

    print(f"\n── 판정 지표 ──")
    for nm, sel, tgt, base in (
        ("근접(<0.18m)", lambda x: x["d"] < NEAR_CUT, 70, BASELINE["near"]),
        ("원거리(≥0.18m)", lambda x: x["d"] >= NEAR_CUT, 80, BASELINE["far"]),
    ):
        sub = [x for x in rows if sel(x)]
        kk = sum(1 for x in sub if x["ok"])
        cur = kk / len(sub) * 100 if sub else 0
        blo, bhi = wilson(kk, len(sub))
        mark = "✅" if cur >= tgt else "❌"
        print(f"  {nm:<14}{pct(kk,len(sub)):>16}  CI [{blo:.0f},{bhi:.0f}]  "
              f"목표 ≥{tgt}% {mark}   ({BASELINE['name']} {base[0]/base[1]*100:.0f}%)")
    ov = "✅" if k / n * 100 >= 80 else "❌"
    print(f"  {'full 전체':<14}{pct(k,n):>16}  CI [{lo:.0f},{hi:.0f}]  목표 ≥80% {ov}")

    print(f"\n── 블록 각도 θ 구간별 (2차 요인) ──")
    for a, b in [(-1.0, -0.35), (-0.35, 0.0), (0.0, 0.45), (0.45, 0.9), (0.9, 1.4)]:
        sub = [x for x in rows if a <= x["th"] < b]
        if sub:
            kk = sum(1 for x in sub if x["ok"])
            print(f"  θ {a:+.2f}~{b:+.2f}   {pct(kk,len(sub)):>14}")

    print(f"\n── 교차: 거리 × 각도 ──")
    med = sorted(x["d"] for x in rows)[n // 2]
    print(f"   (거리 중앙값 {med:.3f}m)\n{'':<16}{'가까움':>13}{'멂':>13}")
    for lab, f in (("θ<0 (오른쪽)", lambda t: t < 0), ("θ≥0 (정면·왼쪽)", lambda t: t >= 0)):
        line = f"  {lab:<14}"
        for near in (True, False):
            sub = [x for x in rows if f(x["th"]) and (x["d"] < med) == near]
            kk = sum(1 for x in sub if x["ok"])
            line += (f"{kk}/{len(sub)}={kk/len(sub)*100:.0f}%" if sub else "—").rjust(13)
        print(line)

    fails = sorted((x["d"], x["src"], x["ep"]) for x in rows if not x["ok"])
    print(f"\n실패 {len(fails)}개 (거리 오름차순): "
          + ", ".join(f"{s}/ep{e}({d:.2f})" for d, s, e in fails[:15])
          + (" …" if len(fails) > 15 else ""))


if __name__ == "__main__":
    main()
