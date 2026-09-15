#!/usr/bin/env python3
"""실기 추론 시행의 객관 지표 — 영상을 보기 전에 먼저 돌린다.

왜 필요한가:
  평가 A(2026-08-12)에서 성공/실패 이항 지표는 n=5에서 세로/가로 차이를 못 잡았지만
  (Fisher 단측 p=0.083), **정지 시간·소요 시간**은 5/5 일관되게 잡았다(부호검정 p=0.031).
  같은 시행 수로 검정력이 다르므로 연속량을 주 지표로 쓴다.

무엇을 보나:
  정지        그리퍼를 뺀 5축이 1초 동안 2° 미만으로만 움직인 구간.
              교시 데이터(so101_blocktask_real_v2, 60ep)의 **최장 정지는 3.5초**이고
              5초를 넘는 ep가 하나도 없다. 그보다 긴 정지는 학습 데이터에 대응물이 없는
              배포측 이상이다 → ⚠ 표시.
  경계 점프    청크 경계(8스텝)의 |Δ| ÷ 비경계 |Δ|. 앙상블을 끄면 3.6~5.3, 켜면 ~1.0.
              ENSEMBLE 설정이 의도대로 걸렸는지 로그만으로 확인하는 용도.
  튐(99%)     스텝간 |Δ|의 99%tile. 교시 데이터는 2.99°. 크게 넘으면 서보에 실리는
              불연속이 교시에 없던 수준이라는 뜻 → ⚠ 표시.
  infer_ms    정지 중 / 이동 중을 나눠 본다. 둘이 비슷하면 네트워크는 원인이 아니다
              (평가 A에서 115ms vs 116ms로 WiFi 교란은 배제됐다).

사용:
  ./analyze_real_run.py ~/manipulator_ws/inf_video/07_real_eval/A/*_t01
  ./analyze_real_run.py <디렉터리...>            # run.json이 있으면 설정도 함께 표시
"""
import csv
import json
import os
import statistics as st
import sys

ARM = ["shoulder_pan.pos", "shoulder_lift.pos", "elbow_flex.pos",
       "wrist_flex.pos", "wrist_roll.pos"]

# 교시 데이터(so101_blocktask_real_v2, 60ep) 실측 기준선
DEMO_MAX_STALL = 3.5    # 초 — ep별 최장 정지의 최대값
DEMO_JERK_P99 = 2.99    # 도 — 스텝간 |Δ|의 99%tile
STALL_DEG, STALL_SEC = 2.0, 1.0


def _stalls(rows):
    """정지 구간 [(시작s, 끝s)] — 5축이 STALL_SEC 동안 STALL_DEG 미만으로만 움직인 구간."""
    A = [([float(r[f"sent_{k}"]) for k in ARM], float(r["t_ms"]) / 1000) for r in rows]
    if len(A) < 2:
        return [], A
    hz = (len(A) - 1) / max(A[-1][1] - A[0][1], 1e-9)
    w = max(2, int(hz * STALL_SEC))
    out, i = [], 0
    while i < len(A) - w:
        seg = [a for a, _ in A[i:i + w]]
        if max(max(x[k] for x in seg) - min(x[k] for x in seg) for k in range(5)) < STALL_DEG:
            j = i
            while j < len(A) - w:
                s2 = [a for a, _ in A[j:j + w]]
                if max(max(x[k] for x in s2) - min(x[k] for x in s2) for k in range(5)) >= STALL_DEG:
                    break
                j += 1
            out.append((A[i][1], A[min(j + w, len(A) - 1)][1]))
            i = j + w
        else:
            i += 1
    return out, A


def analyze(d):
    rows = list(csv.DictReader(open(os.path.join(d, "actions.csv"))))
    iv, A = _stalls(rows)
    dur = A[-1][1] if A else 0.0
    tot = sum(b - a for a, b in iv)
    lng = max((b - a for a, b in iv), default=0.0)

    # 경계 점프 및 튐
    bnd, non, allд = [], [], []
    for t in range(1, len(A)):
        dv = max(abs(A[t][0][k] - A[t - 1][0][k]) for k in range(5))
        allд.append(dv)
        (bnd if t % 8 == 0 else non).append(dv)
    ratio = st.mean(bnd) / max(st.mean(non), 1e-9) if bnd and non else float("nan")
    allд.sort()
    p99 = allд[int(len(allд) * 0.99)] if allд else 0.0

    # infer_ms를 정지/이동으로 가른다 (chunks.csv에는 시각이 없어 청크당 소비 스텝으로 대응)
    si, ni = [], []
    cp = os.path.join(d, "chunks.csv")
    if os.path.exists(cp):
        C = [float(r["infer_ms"]) for r in csv.DictReader(open(cp))]
        per = max(1, round(len(A) / max(len(C), 1)))
        for ci, ms in enumerate(C):
            s = ci * per
            if s < len(A):
                t = A[s][1]
                (si if any(a <= t <= b for a, b in iv) else ni).append(ms)

    cfg = {}
    rp = os.path.join(d, "run.json")
    if os.path.exists(rp):
        try:
            cfg = json.load(open(rp))
        except Exception:
            pass
    return dict(name=os.path.basename(d.rstrip("/")), dur=dur, stall=tot, longest=lng,
                n=len(iv), ratio=ratio, p99=p99,
                inf_s=st.median(si) if si else float("nan"),
                inf_n=st.median(ni) if ni else float("nan"),
                ens=cfg.get("ensemble", "?"), w=cfg.get("ensemble_w", "?"))


def main(dirs):
    dirs = [d for d in dirs if os.path.exists(os.path.join(d, "actions.csv"))]
    if not dirs:
        sys.exit("actions.csv 를 가진 디렉터리가 없습니다.")
    res = [analyze(d) for d in sorted(dirs)]
    print(f"{'시행':<26}{'ENS':>5}{'W':>5}{'소요':>8}{'정지':>8}{'최장':>8}{'구간':>5}"
          f"{'경계비':>8}{'튐99%':>8}{'ms정지':>8}{'ms이동':>8}")
    for r in res:
        warn = ""
        if r["longest"] > DEMO_MAX_STALL * 1.5:
            warn += " ⚠정지"
        if r["p99"] > DEMO_JERK_P99 * 1.5:
            warn += " ⚠튐"
        print(f"{r['name']:<26}{str(r['ens']):>5}{str(r['w']):>5}{r['dur']:>8.1f}{r['stall']:>8.1f}"
              f"{r['longest']:>8.1f}{r['n']:>5}{r['ratio']:>8.2f}{r['p99']:>8.2f}"
              f"{r['inf_s']:>8.0f}{r['inf_n']:>8.0f}{warn}")
    n = len(res)
    print(f"\n  평균  소요 {sum(r['dur'] for r in res)/n:.1f}s · 정지 {sum(r['stall'] for r in res)/n:.1f}s"
          f" · 최장 {sum(r['longest'] for r in res)/n:.1f}s · 튐99% {sum(r['p99'] for r in res)/n:.2f}°")
    print(f"  기준  교시 데이터 최장 정지 {DEMO_MAX_STALL}s · 튐99% {DEMO_JERK_P99}°  "
          f"(60ep 실측; ⚠는 이 값의 1.5배 초과)")
    bad = [r["name"] for r in res if r["longest"] > DEMO_MAX_STALL * 1.5]
    if bad:
        print(f"\n  ⚠ 교시에 없는 긴 정지: {', '.join(bad)}  → ENSEMBLE_W를 올리거나 0으로")


if __name__ == "__main__":
    main(sys.argv[1:] or sys.exit(__doc__))
