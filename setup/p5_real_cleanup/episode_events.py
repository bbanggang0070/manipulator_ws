"""에피소드 궤적에서 **파지 시도 횟수**와 **놓은 위치**를 뽑는다.

⚠️ 이 파일이 따로 있는 이유: 이 측정을 **네 번 틀렸다**(2026-10-07).
   전부 그리퍼 값에 임계를 걸고 '넘었나'로 사건을 잡으려다 생긴 실패다.

   ① 중점 임계로 개폐 전이를 세어 "재파지 99%" — rest 에서 닫힌 채 시작해
      접근하려 열고→집고→놓고→복귀하며 닫는 **4회 전이가 정상**인데 그걸 셌다.
   ② 첫 1초를 안 빼서 "재파지 56%" — 그리퍼 열린 채 시작한 에피소드가 잡혔다.
   ③ 릴리스를 '마지막 닫힘→열림'으로 잡았더니, 물체가 멀리 있으면
      **집으러 갈 때의 벌림**이 릴리스로 잡혔다(ep114: 실제 +32°를 -47°로).
   ④ '쥐는 구간의 끝'으로 바꿨더니 복귀 중까지 쥐는 걸로 세었다(ep111: +30°를 +13°로).

   해법은 임계가 아니라 **평탄구간 분해**다. 그리퍼 궤적은 항상
       rest → (벌림 → 닫힘)×N → 운반 → 놓기 → rest
   꼴의 평탄구간 열이고, 이 구조에서 읽으면 임계 위치에 둔감하다.
       파지 시도 = **운반 구간보다 앞에 있는** 크게벌림 평탄구간의 수
       놓은 위치 = 운반 구간 **바로 다음** 평탄구간이 시작하는 프레임의 pan

   정답 14개(gt_events.json)로 고정해 두었다. 지표를 건드리면
       python3 episode_events.py --selftest
   가 반드시 통과해야 한다. 정답은 궤적을 손으로 읽고 **영상으로도** 확인했다.
"""
import json
import os
import sys

import numpy as np

GT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gt_events.json")


def plateaus(g, p, tol=3.0, minlen=8):
    """(시작프레임, 길이, 그리퍼 중앙값, 시작 pan) 의 열."""
    out, i = [], 0
    while i < len(g):
        j = i
        while j + 1 < len(g) and abs(g[j + 1] - g[i]) <= tol:
            j += 1
        if j - i + 1 >= minlen:
            out.append((i, j - i + 1, float(np.median(g[i:j + 1])), float(p[i])))
        i = j + 1
    return out


def analyze(state, fps=30):
    """state: (T, 6) 배열. observation.state 그대로.

    돌려주는 것: {"attempts": 파지 시도 수, "release_pan": 놓은 위치(°), "carry": 운반 길이}
    판단할 수 없으면 해당 값이 None.
    """
    g, p = np.asarray(state)[:, 5], np.asarray(state)[:, 0]
    if len(g) < fps or g.max() - g.min() < 5:
        return {"attempts": None, "release_pan": None, "carry": None}
    pl = plateaus(g, p)
    if not pl:
        return {"attempts": None, "release_pan": None, "carry": None}

    rest = min(v for _, _, v, _ in pl)                  # 가장 낮은 평탄값 = 완전히 닫힘
    wide = rest + 0.55 * (g.max() - rest)               # 크게 벌림
    # 운반 = rest 도 크게벌림도 아닌 평탄구간 중 **가장 긴 것**.
    #   '마지막 것'이 아니라 '가장 긴 것'이어야 한다 — 실패한 파지 시도에도
    #   짧은 중간 평탄구간이 생긴다(ep33 은 그런 게 5개였다).
    mids = [k for k, (_, n, v, _) in enumerate(pl) if rest + 3 < v < wide]
    if not mids:
        return {"attempts": None, "release_pan": None, "carry": None}
    c = max(mids, key=lambda k: pl[k][1])
    # 시도 수 = 운반 앞에서 '크게 벌림'에 **들어간 횟수**. 평탄구간을 그냥 세면
    # 열리고 닫히는 경사 위의 중간값(34 다음의 22 같은 것)이 별도 구간으로 잡혀
    # 한 번의 벌림이 두 번으로 세어진다(ep111 이 3 대신 5로 나왔다).
    attempts, prev = 0, False
    for k in range(c):
        now = pl[k][2] >= wide
        if now and not prev:
            attempts += 1
        prev = now
    release = pl[c + 1][3] if c + 1 < len(pl) else None
    return {"attempts": attempts, "release_pan": release, "carry": pl[c][1]}


def selftest():
    gt = json.load(open(GT))
    import glob

    import pandas as pd
    D = os.path.expanduser(gt["dataset"])
    d = pd.concat([pd.read_parquet(f, columns=["episode_index", "frame_index",
                                               "observation.state"])
                   for f in sorted(glob.glob(D + "/data/**/*.parquet", recursive=True))])
    bad = 0
    print(f"{'ep':>4} {'칸':<7}{'시도 (정답)':>14}{'놓은위치 (정답)':>22}")
    for k, exp in sorted(gt["episodes"].items(), key=lambda kv: int(kv[0])):
        e = int(k)
        sub = d[d.episode_index == e].sort_values("frame_index")
        if sub.empty:
            print(f"{e:>4} — 데이터셋에 없음(건너뜀)")
            continue
        a = np.stack(sub["observation.state"].values).astype(float)
        got = analyze(a)
        ok_a = got["attempts"] == exp["attempts"]
        ok_r = got["release_pan"] is not None and abs(got["release_pan"] - exp["release_pan"]) <= 4
        bad += not (ok_a and ok_r)
        got_r = "  —  " if got["release_pan"] is None else f"{got['release_pan']:+.0f}deg"
        mark = "OK" if ok_a and ok_r else "FAIL"
        print(f"{e:>4} {exp['slot']:<7}"
              f"{got['attempts']:>5} ({exp['attempts']})"
              f"{got_r:>12} ({exp['release_pan']:+.0f})   {mark}")
    print(f"\n  {'✅ 전부 일치' if not bad else f'❌ {bad}건 불일치 — 지표를 고쳤다면 되돌릴 것'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else 0)
