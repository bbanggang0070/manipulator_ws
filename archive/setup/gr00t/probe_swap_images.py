#!/usr/bin/env python
"""통제 실험: state는 고정하고 **영상만** 좌↔우로 바꿔 예측이 따라가는지 본다.

probe_training_obs.py에서 진행률 6% 지점(state가 좌우 모두 홈 근처로 무정보)에서
예측이 좌우로 20° 갈라지는 것을 관측했다. 다만 그 5° state 차이가 원인일 가능성을
배제하려면 state를 완전히 고정한 채 영상만 교체해야 한다.

  조건1: state(좌) + 영상(좌)   ← 원본
  조건2: state(좌) + 영상(우)   ← 영상만 교체
  조건3: state(우) + 영상(우)   ← 원본
  조건4: state(우) + 영상(좌)   ← 영상만 교체

예측이 영상을 따라가면(1≈4, 2≈3) 시각 그라운딩 확정.
예측이 state를 따라가면(1≈2, 3≈4) 시각 미사용 확정.

실행(5090): cd ~/gr00t_remote/Isaac-GR00T-n1d5 && source .venv/bin/activate
            python ~/probe_swap_images.py
"""
import glob
import sys

import numpy as np
import pandas as pd
import torchvision

DATASET = "/home/airlab/.cache/huggingface/lerobot/heongyu/so101_t1_pickplace"
LANG = "Pick up the red cube and place it in the black box"
FRAC = 0.06  # state가 아직 좌우 미분기인 시점
PAIRS = [(0, 4), (5, 9), (20, 24), (25, 44)]  # (좌 ep, 우 ep)

sys.path.insert(0, "/home/airlab/gr00t_remote/Isaac-GR00T-n1d5")
from gr00t.eval.service import ExternalRobotInferenceClient  # noqa: E402

_CACHE = {}


def obs_of(df_all, ep):
    if ep in _CACHE:
        return _CACHE[ep]
    g = df_all[df_all.episode_index == ep].sort_values("frame_index")
    i = int(len(g) * FRAC)
    state = np.asarray(g.iloc[i]["observation.state"], dtype=np.float64)
    imgs = {}
    for cam, key in (("front", "observation.images.top"), ("wrist", "observation.images.wrist")):
        p = glob.glob(f"{DATASET}/videos/**/{key}/episode_{ep:06d}.mp4", recursive=True)[0]
        fr, _, _ = torchvision.io.read_video(p, pts_unit="sec", output_format="THWC")
        fr = fr.numpy().astype(np.uint8)
        imgs[cam] = fr[min(int(len(fr) * FRAC), len(fr) - 1)]
    _CACHE[ep] = (state, imgs)
    return _CACHE[ep]


def query(client, state, imgs):
    obs = {
        "video.front": imgs["front"][np.newaxis, ...],
        "video.wrist": imgs["wrist"][np.newaxis, ...],
        "state.single_arm": state[:5][np.newaxis, ...],
        "state.gripper": state[5:6][np.newaxis, ...],
        "annotation.human.task_description": [LANG],
    }
    return client.get_action(obs)["action.single_arm"][:, 0][-1]


def main():
    files = sorted(glob.glob(f"{DATASET}/data/**/*.parquet", recursive=True))
    df_all = pd.concat([pd.read_parquet(f) for f in files])
    client = ExternalRobotInferenceClient(host="localhost", port=5555)

    print(f"관측 시점: 진행률 {FRAC:.0%} (state가 좌우 미분기인 구간)\n")
    print(f"{'좌ep':>5} {'우ep':>5} │ {'①S좌+V좌':>9} {'②S좌+V우':>9} │ "
          f"{'③S우+V우':>9} {'④S우+V좌':>9} │ {'영상효과':>8} {'state효과':>9}")
    print("─" * 86)

    vis_eff, st_eff = [], []
    for lep, rep in PAIRS:
        sL, iL = obs_of(df_all, lep)
        sR, iR = obs_of(df_all, rep)
        p1 = query(client, sL, iL)
        p2 = query(client, sL, iR)
        p3 = query(client, sR, iR)
        p4 = query(client, sR, iL)
        # 영상 효과: state 고정하고 영상만 바꿨을 때의 변화량 (평균)
        v = ((p2 - p1) + (p3 - p4)) / 2
        # state 효과: 영상 고정하고 state만 바꿨을 때의 변화량 (평균)
        s = ((p4 - p1) + (p3 - p2)) / 2
        vis_eff.append(v)
        st_eff.append(s)
        print(f"{lep:>5} {rep:>5} │ {p1:>9.1f} {p2:>9.1f} │ {p3:>9.1f} {p4:>9.1f} │ "
              f"{v:>8.1f} {s:>9.1f}")

    V, S = np.mean(vis_eff), np.mean(st_eff)
    print("─" * 86)
    print(f"평균 영상 효과 = {V:>6.1f}°   평균 state 효과 = {S:>6.1f}°")
    if abs(V) > 2 * abs(S):
        print("→ 결론: 예측이 **영상**을 따라감 = 시각 그라운딩 존재 (가설 B: 배포 관측 갭)")
    elif abs(S) > 2 * abs(V):
        print("→ 결론: 예측이 **state**를 따라감 = 시각 미사용 (가설 A: 데이터/모드 문제)")
    else:
        print("→ 결론: 두 요인이 비슷하게 기여 — 추가 분석 필요")


if __name__ == "__main__":
    main()
