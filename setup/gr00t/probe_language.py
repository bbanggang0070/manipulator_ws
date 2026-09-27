#!/usr/bin/env python
"""언어 민감도 프로브 — **같은 관측에 지시문만 바꿔** 행동이 달라지는지를 °로 잰다.

왜 필요한가 (language_conditioning_sim_plan.md §7-1):
  이 프로젝트의 불변식은 하나다 — *같은 관측 + 다른 지시문 → 다른 행동*.
  그게 성립하는지를 로봇 없이, 사람 없이, 수 분 만에 재는 도구다.

  주의: 이것은 "모델이 언어 능력을 잃었는가"를 재는 게 아니다. GR00T는 언어 인코더를
  동결(`tune_llm=False`)한 채 학습하므로 능력은 애초에 망가지지 않는다. 재는 것은
  **행동 예측부가 지시문을 입력으로 쓰는가**다. 지시문이 상수인 데이터로 학습하면
  언어를 봐도 손실이 안 줄어 무시하게 되고, 그 상태가 0°로 나타난다.

기준선을 먼저 잡아야 하는 이유:
  현 모델(`v4_200@86k`)은 지시문이 상수였으므로 **0°에 가깝게 나와야 정상**이다.
  여기서 7°가 나온다면 모델이 언어를 읽는 게 아니라 **프로브가 잡음을 7° 뿜는 것**이고,
  그러면 학습 후의 8°는 아무것도 주장하지 못한다. 그래서 첫 사용처는 새 모델이 아니라
  **현 모델**이다. `같은 문장 2회` 비교가 그 잡음 하한을 직접 준다
  (행동 헤드가 확산 모델이라 같은 입력도 매번 같지 않다).

눈금:
  영상을 좌↔우로 통째 바꿨을 때 18.9°였다(probe_swap_images.py 실측).
  이것이 "큰 시각 효과"의 크기이고, 판정선 5°는 그 약 1/4이다.

실행 — 서버를 먼저 띄운다(로봇 불필요):
  # 5090에서
  ~/gr00tn16_ws/serve...sh  또는 로컬: setup/gr00t/serve_local.sh <MODEL>
  python probe_language.py --dataset <LeRobot 데이터셋> --label v4_200@86k

  여러 체크포인트에 돌려 --out 으로 모으면 §4-2의 '언어가 언제 살아나는가' 곡선이 된다.
"""
import argparse
import glob
import json
import os
import re
import sys
from collections import defaultdict

import numpy as np
import pandas as pd

# ── 비교군 ────────────────────────────────────────────────────────────────
#   문법은 수집 계획표(§2-5)와 같은 형태로 맞춘다. 학습에서 본 적 없는 문형을 쓰면
#   "언어를 못 읽는다"가 아니라 "그 문형을 모른다"를 재게 된다.
_T = "Pick up the {obj} and place it in the {dst}"
COMPARISONS = [
    # (이름, 문장 A, 문장 B, 합격선°, 해석)
    ("잡음 하한 (같은 문장 2회)",
     _T.format(obj="red cube", dst="black box"),
     _T.format(obj="red cube", dst="black box"), None,
     "확산 헤드의 재현성. 여기가 크면 아래 숫자는 전부 무의미하다"),
    ("색 (red ↔ blue)",
     _T.format(obj="red cube", dst="black box"),
     _T.format(obj="blue cube", dst="black box"), 5.0,
     "색 단어 grounding"),
    ("이름 (eraser ↔ marker)",
     _T.format(obj="eraser", dst="black box"),
     _T.format(obj="marker", dst="black box"), 5.0,
     "색이 아닌 이름 grounding"),
    ("목적지 (black ↔ brown box)",
     _T.format(obj="yellow cube", dst="black box"),
     _T.format(obj="yellow cube", dst="brown box"), 5.0,
     "목적지 grounding"),
    ("패러프레이즈 (동의어)",
     _T.format(obj="red cube", dst="black box"),
     "Grab the red block and put it in the black box", None,
     "같은 뜻이므로 **작을수록 좋다**. 색·이름보다 크면 형식에 반응하는 것"),
]


# ── 데이터셋 읽기 — v3.0(file-NNN)과 v2.1(episode_NNNNNN) 둘 다 ──────────
def _video_path(root, cam_key, ep):
    for pat in (f"{root}/videos/{cam_key}/**/file-{ep:03d}.mp4",
                f"{root}/videos/**/{cam_key}/episode_{ep:06d}.mp4",
                f"{root}/videos/**/{cam_key}/**/*{ep:06d}.mp4"):
        hit = glob.glob(pat, recursive=True)
        if hit:
            return hit[0]
    raise FileNotFoundError(f"{cam_key} ep{ep} 영상을 못 찾음")


def _frame(path, idx):
    """PyAV로 idx번째 프레임을 RGB uint8로 꺼낸다(AV1·h264 모두 가능)."""
    import av
    with av.open(path) as c:
        for i, f in enumerate(c.decode(video=0)):
            if i == idx:
                return f.to_ndarray(format="rgb24")
    raise IndexError(f"{path}: 프레임 {idx} 없음")


def load_obs(root, ep, frac):
    """에피소드 ep의 진행률 frac 지점 관측 (state + 카메라 2장)."""
    pq = glob.glob(f"{root}/data/**/*.parquet", recursive=True)
    pq = [p for p in pq if int(re.search(r"(\d+)", os.path.basename(p)).group(1)) == ep]
    if not pq:
        raise FileNotFoundError(f"ep{ep} parquet 없음")
    g = pd.read_parquet(pq[0]).sort_values("frame_index")
    i = min(int(len(g) * frac), len(g) - 1)
    state = np.asarray(g.iloc[i]["observation.state"], dtype=np.float64)
    imgs = {
        "front": _frame(_video_path(root, "observation.images.external_D455", ep), i),
        "wrist": _frame(_video_path(root, "observation.images.ego", ep), i),
    }
    return state, imgs


def query(client, state, imgs, lang):
    obs = {
        "video.front": imgs["front"][np.newaxis, ...],
        "video.wrist": imgs["wrist"][np.newaxis, ...],
        "state.single_arm": state[:5][np.newaxis, ...],
        "state.gripper": state[5:6][np.newaxis, ...],
        "annotation.human.task_description": [lang],
    }
    a = client.get_action(obs)
    return np.asarray(a["action.single_arm"], dtype=np.float64)   # (16, 5) 도 단위


def divergence(a, b):
    """두 행동 청크의 차이. 평균과 최대를 ° 로 돌려준다."""
    d = np.abs(np.asarray(a) - np.asarray(b))
    return float(d.mean()), float(d.max())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True, help="LeRobot 데이터셋 루트 (v3.0 또는 v2.1)")
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=5555)
    ap.add_argument("--episodes", type=int, default=6, help="관측을 뽑을 에피소드 수")
    ap.add_argument("--fracs", default="0.05,0.15,0.30",
                    help="에피소드 내 시점(진행률). 팔이 아직 목표를 정하기 전이 좋다")
    ap.add_argument("--repeats", type=int, default=2, help="같은 조건 반복 질의(확산 잡음 평균)")
    ap.add_argument("--label", default="unknown", help="체크포인트 이름 — 결과에 기록된다")
    ap.add_argument("--out", default=None, help="결과 JSON 누적 파일")
    ap.add_argument("--gr00t-path", default=None, help="Isaac-GR00T 경로(클라이언트 import용)")
    a = ap.parse_args()

    if a.gr00t_path:
        sys.path.insert(0, a.gr00t_path)
    try:
        from gr00t.eval.service import ExternalRobotInferenceClient
    except ImportError:
        here = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, os.path.join(here, "client"))
        from service import ExternalRobotInferenceClient   # noqa: F401

    root = os.path.expanduser(a.dataset)
    fracs = [float(x) for x in a.fracs.split(",")]
    n_ep = int(json.load(open(f"{root}/meta/info.json"))["total_episodes"])
    eps = list(np.linspace(0, n_ep - 1, a.episodes, dtype=int))

    client = ExternalRobotInferenceClient(host=a.host, port=a.port)
    print(f"\n모델: {a.label}   데이터셋: {os.path.basename(root)} ({n_ep}ep)")
    print(f"관측 {len(eps)}ep × {len(fracs)}시점 × 반복 {a.repeats} = "
          f"조건당 {len(eps) * len(fracs) * a.repeats}회 질의\n")

    acc = defaultdict(list)
    for ep in eps:
        for fr in fracs:
            try:
                state, imgs = load_obs(root, int(ep), fr)
            except Exception as e:
                print(f"  ⚠ ep{ep} @{fr}: {type(e).__name__} {e}")
                continue
            for name, la, lb, _thr, _why in COMPARISONS:
                for _ in range(a.repeats):
                    ca = query(client, state, imgs, la)
                    cb = query(client, state, imgs, lb)
                    m, mx = divergence(ca, cb)
                    acc[name].append((m, mx))
            print(f"  ep{ep:>3} @{fr:.2f}  ✓", flush=True)

    print(f"\n{'=' * 78}\n 결과 — 같은 관측, 문장만 다름 (단위 °)\n{'=' * 78}")
    print(f"  {'비교':28s} {'평균Δ':>8s} {'최대Δ':>8s} {'n':>4s}  판정")
    print("  " + "─" * 74)
    summary, noise = {}, None
    for name, _la, _lb, thr, _why in COMPARISONS:
        v = acc.get(name, [])
        if not v:
            continue
        mean = float(np.mean([x[0] for x in v]))
        mx = float(np.mean([x[1] for x in v]))
        summary[name] = {"mean_deg": mean, "max_deg": mx, "n": len(v), "threshold": thr}
        if noise is None:
            noise = mean
        verdict = "—" if thr is None else ("✅ 통과" if mean >= thr else "❌ 미달")
        print(f"  {name:28s} {mean:8.2f} {mx:8.2f} {len(v):4d}  {verdict}")

    print("\n  해석")
    for name, _la, _lb, thr, why in COMPARISONS:
        if name in summary:
            t = f"(합격선 {thr}°)" if thr else ""
            print(f"    · {name} {t} — {why}")
    if noise is not None:
        print(f"\n  잡음 하한은 {noise:.2f}° 다. 나머지 수치는 이 값보다 "
              f"충분히 커야 의미가 있다.")
        print(f"  참고 눈금: 영상 좌↔우 교체 = 18.9° (probe_swap_images 실측)")

    if a.out:
        rec = {"label": a.label, "dataset": os.path.basename(root),
               "episodes": [int(e) for e in eps], "fracs": fracs,
               "repeats": a.repeats, "results": summary}
        hist = []
        if os.path.exists(a.out):
            hist = json.load(open(a.out))
        hist.append(rec)
        with open(a.out, "w") as f:
            json.dump(hist, f, indent=2, ensure_ascii=False)
        print(f"\n  기록: {a.out} ({len(hist)}개 누적)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
