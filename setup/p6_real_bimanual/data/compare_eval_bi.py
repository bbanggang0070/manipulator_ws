"""양팔 cleanup 평가 결과 여러 개를 나란히 비교 — 데이터(300/392ep) × 언어 모델 학습 층(4/8).

cleanup_eval_bi.py report 는 결과 하나만 본다. 모델끼리 비교할 때 필요한 것은 셋이다:
  1) 같은 축 지표를 한 표에 (분모 규칙은 report 와 같다 — 전달률은 집은 시행, 목적지는 전달 성공 시행)
  2) **같은 시행끼리 짝지은 비교** — 36시행이면 정확도 차이 10%p 도 우연일 수 있다.
     A만 맞춤 / B만 맞춤 개수와 정확 McNemar p(양측)를 낸다.
  3) 틀릴 때 무엇을 집었나 — 300ep 8층은 오답 6건이 black marker 로 쏠렸다(Notion 4-4)

사용:
  python3 compare_eval_bi.py                      # 평가 A, 있는 결과만 (bi300 · bi300llm8 · bi392 · bi392llm8)
  python3 compare_eval_bi.py --eval B
  python3 compare_eval_bi.py 300_4층=bi300_eval_A.csv 392_8층=/경로/x.csv   # 직접 지정 (이름=csv)
"""
import argparse
import csv
import os
import sys
import unicodedata
from collections import Counter
from math import comb

R = os.path.expanduser("~/manipulator_ws/manipulator_md/p6_real_bimanual")
DEFAULT = [("300ep·4층", "bi300"), ("300ep·8층", "bi300llm8"), ("392ep·4층", "bi392"), ("392ep·8층", "bi392llm8")]
# 데이터 효과는 층을 고정하고, 층 효과는 데이터를 고정하고 본다
PAIRS = [("300ep·4층", "392ep·4층"), ("300ep·8층", "392ep·8층"),
         ("300ep·4층", "300ep·8층"), ("392ep·4층", "392ep·8층")]
MARKERS = ("red marker", "blue marker", "black marker")


def dw(s):
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in s)


def L(s, w):   # 한글 폭(2칸)을 고려한 왼쪽 정렬
    return s + " " * max(0, w - dw(s))


def Rj(s, w):  # 오른쪽 정렬
    return " " * max(0, w - dw(s)) + s


def mcnemar(b, c):
    n = b + c
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)


def ok_obj(r):
    return r["picked"] == r["target"]


def ok_all(r):
    return ok_obj(r) and r["handoff"] == "성공" and r["landed"] == r["slot_color"]


def frac(k, n):
    return f"{k}/{n} ({k / n * 100:.0f}%)" if n else "-"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="*", help="이름=csv (생략하면 기본 4개 중 있는 것)")
    ap.add_argument("--eval", default="A")
    a = ap.parse_args()

    if a.runs:
        runs = [x.split("=", 1) for x in a.runs]
        runs = [(n, p if os.path.isabs(p) else os.path.join(R, p)) for n, p in runs]
    else:
        runs = [(n, f"{R}/{t}_eval_{a.eval}.csv") for n, t in DEFAULT]
    data = {}
    for n, p in runs:
        if os.path.exists(p):
            data[n] = {r["trial"]: r for r in csv.DictReader(open(p)) if r.get("picked", "") != ""}
        else:
            print(f"  (없음: {n} — {os.path.basename(p)})")
    if not data:
        sys.exit("❌ 비교할 결과가 없다")
    names = list(data)

    # 1) 지표
    W = 18
    print(f"\n{'=' * (22 + W * len(names))}\n평가 {a.eval} 비교\n{'=' * (22 + W * len(names))}")
    print(" " * 22 + "".join(Rj(n, W) for n in names))
    rows = {}
    for n in names:
        rs = list(data[n].values())
        pk = [r for r in rs if r["picked"] != "(없음)"]
        ho = [r for r in pk if r["handoff"] == "성공"]
        pl = [r for r in ho if r["landed"] != "(없음)"]
        mk = [r for r in rs if r["target"] in MARKERS]
        rows[n] = [
            ("시행", f"{len(rs)}"),
            ("무언가 집음", frac(len(pk), len(rs))),
            ("전달 성공 /집음", frac(len(ho), len(pk))),
            ("칸에 넣음 /전달", frac(len(pl), len(ho))),
            ("① 지시 물체 집음", frac(sum(map(ok_obj, rs)), len(rs))),
            ("   마커 지시만", frac(sum(map(ok_obj, mk)), len(mk))),
            ("③ 지시 칸 /넣음", frac(sum(r["landed"] == r["slot_color"] for r in pl), len(pl))),
            ("완전 성공", frac(sum(map(ok_all, rs)), len(rs))),
        ]
    for i, (lab, _) in enumerate(rows[names[0]]):
        print(L(lab, 22) + "".join(Rj(rows[n][i][1], W) for n in names))

    # 2) 짝 비교
    pairs = [p for p in PAIRS if p[0] in data and p[1] in data] if not a.runs else \
        [(names[i], names[j]) for i in range(len(names)) for j in range(i + 1, len(names))]
    if pairs:
        print(f"\n  같은 시행끼리 — 지시 물체를 집었나 (뒤 모델 기준)")
        print("    " + L("비교", 28) + "".join(Rj(h, w) for h, w in (("공통", 6), ("뒤만", 6), ("앞만", 6), ("둘다", 6), ("둘다X", 7), ("McNemar p", 11))))
        for x, y in pairs:
            ts = sorted(set(data[x]) & set(data[y]), key=int)
            b = sum(ok_obj(data[y][t]) and not ok_obj(data[x][t]) for t in ts)
            c = sum(ok_obj(data[x][t]) and not ok_obj(data[y][t]) for t in ts)
            both = sum(ok_obj(data[x][t]) and ok_obj(data[y][t]) for t in ts)
            print("    " + L(x + " → " + y, 28) + f"{len(ts):>6}{b:>6}{c:>6}{both:>6}{len(ts) - b - c - both:>7}"
                  f"{mcnemar(b, c):>11.3f}")
        print(f"    ※ p 는 '뒤만'과 '앞만'이 같은 비율일 때 이 정도 차이가 나올 확률. 0.05 미만이어야 차이라고 본다.")

    # 3) 오답 내용
    print(f"\n  틀릴 때 집은 물체 (지시 ≠ 집음, 못 집음 제외)")
    for n in names:
        w = Counter(r["picked"] for r in data[n].values() if r["picked"] not in ("(없음)", r["target"]))
        print("    " + L(n, 12) + (" · ".join(f"{o} {k}" for o, k in w.most_common()) or "-"))

    # 물체별
    objs = sorted({r["target"] for d in data.values() for r in d.values()})
    print(f"\n  지시 물체별 정답")
    print("    " + " " * 16 + "".join(Rj(n, 12) for n in names))
    for o in objs:
        cells = []
        for n in names:
            rs = [r for r in data[n].values() if r["target"] == o]
            cells.append(f"{sum(map(ok_obj, rs))}/{len(rs)}")
        print(f"    {o:<16}" + "".join(f"{c:>12}" for c in cells))
    return 0


if __name__ == "__main__":
    sys.exit(main())
