"""양팔 전달(오른팔→왼팔) 성공률 지표 — 그리퍼 궤적에서 **전달 시점**을 읽는다.

⚠️ 그리퍼 궤적 기반 지표는 이 세션에서 **이미 네 번 틀렸다**(setup/data/episode_events.py
   머리말 참고 — 전부 "임계값 하나로 사건을 잡으려다" 생긴 실패다). 그래서 여기서도
   **평탄구간 분해**(episode_events.plateaus, 그대로 재사용 — 다시 만들지 않는다)만 쓰고,
   정답 4개(gt_handoff.json, 영상 프레임을 직접 열어 확인)로 고정해 두었다. 지표를 건드리면
       python3 handoff_events.py --selftest
   가 반드시 통과해야 한다.

전달 규칙(record_bi.sh 시연 규칙과 같다): "오른팔은 왼팔 그리퍼가 확실히 물체를 닫은
뒤에 놓는다." 그래서 재는 건 두 시점의 순서다 —
    left_grasp_frame   : 왼팔이 전달받으려 닫히는 평탄구간이 **시작**하는 프레임
    right_release_frame: 오른팔이 쥔 채 버티는 마지막 평탄구간이 **끝나는** 프레임
                          (여는 평탄구간이 따로 잡히면 그게 시작하는 프레임 — 아래 참고)
    gap = right_release_frame - left_grasp_frame
    gap >= 0  → 왼팔이 먼저 닫힌 뒤 오른팔이 놓았다(성공, 규칙대로)
    gap <  0  → 오른팔이 먼저 놓았다(왼팔이 닫히기 전에 놓음 — 떨어뜨렸을 위험)

구조(모든 정상 에피소드가 따르는 모양, bi_manipulator_plan.md §3-2):
    왼팔 그리퍼: rest → **열림(다가감)** → **닫힘(전달받음, grasp)** → 열림(칸에 놓음) → rest
    오른팔 그리퍼: rest → 열림(다가감) → **닫힘(쥐고 옮김)** → **열림(전달, release)** → rest

    왼팔은 "첫 열림 다음 평탄구간"이 곧 전달받는 순간이다 — 그 뒤 운반 중 놓쳤다
    다시 쥐는 일(ep8)이 있어도 **첫** 닫힘만 본다(전달 자체와 운반 품질은 다른 지표다).
    오른팔은 반대로 "마지막에서 두 번째 평탄구간"을 본다 — 집기를 몇 번 실패했어도
    (재시도가 앞에 있어도) 결국 쥐고 옮긴 마지막 구간만 중요하다.

    오른팔이 놓는 동작이 너무 빨라 **열리는 평탄구간 자체가 안 잡히는** 에피소드가
    있다(ep43 — minlen=8프레임 안에 열림이 끝나 쥠→rest 전이에 묻혔다). 그래서 마지막에서
    두 번째 평탄구간 값이 "열림"(OPEN_THRESH 이상)이 아니면, 그 평탄구간을 쥔 구간으로
    보고 **그 구간이 끝나는 지점**을 release_frame으로 쓴다.
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data"))
from episode_events import plateaus  # 평탄구간 분해 자체는 재사용 — 다시 만들지 않는다

GT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gt_handoff.json")

# 쥔 상태(2~10°대)와 연 상태(15°대 이상)가 모든 관측 에피소드에서 뚜렷이 갈린다
# (가장 가까운 쌍이 쥔 값 9.8° · 연 값 15.6° — 그 사이 아무 값이나 된다, 2026-10-14 실측).
# episode_events.py처럼 "이 에피소드의 rest+비율"로 잡지 않는다 — 칸에 놓을 때 쓰는
# 더 큰 열림(바로 다음 평탄구간)이 섞이면 전체 범위가 늘어나 **이 에피소드의** rest+비율
# 임계가 오히려 작은(정상) 첫 열림을 못 넘는 사고가 났었다(ep19·21·31 — 전부 bin에
# 넣을 때 쓰는 더 큰 열림 때문에 비율 임계가 따라 올라간 탓이었다). 그래서 고정값을 쓴다.
OPEN_THRESH = 12.0


def _arm_plateaus(state):
    """state: (T, 6) 배열. 그 팔의 observation.state(pan..gripper) 그대로."""
    g, p = np.asarray(state)[:, 5].astype(float), np.asarray(state)[:, 0].astype(float)
    if len(g) < 30 or g.max() - g.min() < 5:
        return None
    pl = plateaus(g, p)
    return pl if len(pl) >= 3 else None


def analyze_handoff(left_state, right_state, fps=30):
    """left_state·right_state: 각 (T, 6) — observation.state[:, 0:6] / [:, 6:12].

    돌려주는 것: {"left_grasp_frame", "right_release_frame", "gap_frames", "gap_s", "success"}
    판단할 수 없으면 전부 None.
    """
    lpl = _arm_plateaus(left_state)
    rpl = _arm_plateaus(right_state)
    if lpl is None or rpl is None:
        return {"left_grasp_frame": None, "right_release_frame": None,
                "gap_frames": None, "gap_s": None, "success": None}

    left_grasp_frame = lpl[2][0]

    cand = rpl[-2]  # (start, length, median_value, start_pan)
    if cand[2] >= OPEN_THRESH:
        right_release_frame = cand[0]
    else:
        right_release_frame = cand[0] + cand[1]

    gap = right_release_frame - left_grasp_frame
    return {"left_grasp_frame": left_grasp_frame, "right_release_frame": right_release_frame,
            "gap_frames": gap, "gap_s": gap / fps, "success": gap >= 0}


def selftest():
    gt = json.load(open(GT))
    import glob

    import pandas as pd
    D = os.path.expanduser(gt["dataset"])
    tol = gt.get("tol_frames", 5)
    d = pd.concat([pd.read_parquet(f, columns=["episode_index", "frame_index",
                                               "observation.state"])
                   for f in sorted(glob.glob(D + "/data/**/*.parquet", recursive=True))])
    bad = 0
    print(f"{'ep':>4} {'grasp (정답)':>16} {'release (정답)':>18}  결과")
    for k, exp in sorted(gt["episodes"].items(), key=lambda kv: int(kv[0])):
        e = int(k)
        sub = d[d.episode_index == e].sort_values("frame_index")
        if sub.empty:
            print(f"{e:>4} — 데이터셋에 없음(건너뜀)")
            continue
        a = np.stack(sub["observation.state"].values).astype(float)
        got = analyze_handoff(a[:, 0:6], a[:, 6:12])
        ok_g = (got["left_grasp_frame"] is not None and
                abs(got["left_grasp_frame"] - exp["left_grasp_frame"]) <= tol)
        ok_r = (got["right_release_frame"] is not None and
                abs(got["right_release_frame"] - exp["right_release_frame"]) <= tol)
        bad += not (ok_g and ok_r)
        mark = "OK" if ok_g and ok_r else "FAIL"
        gg = "  —  " if got["left_grasp_frame"] is None else str(got["left_grasp_frame"])
        gr = "  —  " if got["right_release_frame"] is None else str(got["right_release_frame"])
        print(f"{e:>4} {gg:>8} ({exp['left_grasp_frame']:>4}) "
              f"{gr:>10} ({exp['right_release_frame']:>4})   {mark}")
    print(f"\n  {'✅ 전부 일치' if not bad else f'❌ {bad}건 불일치 — 지표를 고쳤다면 되돌릴 것'}")
    return 1 if bad else 0


def report(root):
    import glob

    import pandas as pd
    D = os.path.expanduser(root)
    d = pd.concat([pd.read_parquet(f, columns=["episode_index", "frame_index",
                                               "observation.state"])
                   for f in sorted(glob.glob(D + "/data/**/*.parquet", recursive=True))])
    gaps, fails, undetected = [], [], []
    for e, sub in d.groupby("episode_index"):
        a = np.stack(sub.sort_values("frame_index")["observation.state"].values).astype(float)
        ev = analyze_handoff(a[:, 0:6], a[:, 6:12])
        if ev["success"] is None:
            undetected.append(int(e))
            continue
        gaps.append(ev["gap_s"])
        if not ev["success"]:
            fails.append((int(e), ev["gap_s"]))

    n = len(gaps)
    print(f"  전달 시점 검출: {n}/{n + len(undetected)}ep"
          + (f" (미검출 {undetected})" if undetected else ""))
    if not gaps:
        print("  ⏸ 검출된 에피소드가 없어 성공률을 못 잰다")
        return 1
    gaps = np.array(gaps)
    rate = 1 - len(fails) / n
    print(f"  전달 성공률: {rate:.0%} ({n - len(fails)}/{n}ep, gap>=0 기준)")
    print(f"  여유(gap) 분포: 최소 {gaps.min():+.2f}s · 중앙값 {np.median(gaps):+.2f}s · "
          f"최대 {gaps.max():+.2f}s")
    tight = int((gaps < 0.3).sum())
    if tight:
        print(f"  ⚠️  여유 0.3s 미만 {tight}건 — 규칙(먼저 닫은 뒤 놓기)이 아슬아슬했을 수 있다")
    if fails:
        print(f"  ❌ 전달 실패(gap<0) ep: " + ", ".join(f"{e}({g:+.2f}s)" for e, g in fails))
    else:
        print(f"  ✅ 전달 실패(gap<0) 없음")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    if "--report" in sys.argv:
        i = sys.argv.index("--report")
        root = sys.argv[i + 1] if i + 1 < len(sys.argv) else \
            "~/blocktask_ws/Sim-to-Real-SO-101-Workshop/datasets/_train/bi_cleanup"
        sys.exit(report(root))
    print(__doc__)
