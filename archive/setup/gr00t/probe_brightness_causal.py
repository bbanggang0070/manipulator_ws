#!/usr/bin/env python
"""밝기 갭이 배포 실패의 원인인지 인과적으로 검증한다.

선행 결과(2026-07-20, vis2):
  - 학습 관측: 영상 효과 18.9° >> state 효과 1.9° → 시각 그라운딩 존재
  - 배포: 시작 자세는 학습 분포 정중앙(|z|<0.4), 초기 예측도 정확(pan≈0.6,
    큐브 x=366 → 정답 pan -6.5~+19)인데 청크당 -1~-3°씩 왼쪽으로 누적 드리프트
  - 배포 영상이 학습보다 어두움: front 135.8 vs 149.3, wrist 138.8 vs 163.7

여기서는 **학습 프레임을 배포 밝기로 어둡게** 만들어 예측이 왼쪽으로 무너지는지 본다.
  - 어둡게 했을 때 예측이 좌측으로 이탈 → 밝기가 원인 (조명 맞추면 해결)
  - 변화 없음 → 밝기는 무관, 구도/도메인 차이 등 다른 요인

대상: 배포 장면과 큐브 위치가 가장 비슷한 학습 에피소드(ep3: x=381, ep8: x=379).

실행(5090): python ~/probe_brightness_causal.py
"""
import glob
import sys

import numpy as np
import pandas as pd
import torchvision

DATASET = "/home/airlab/.cache/huggingface/lerobot/heongyu/so101_t1_pickplace"
LANG = "Pick up the red cube and place it in the black box"
EPS = [3, 8, 13, 18]          # 큐브가 중앙 부근(x≈380)인 에피소드들
FRACS = (0.06, 0.12, 0.20, 0.30)
# 배포 관측의 실측 평균 밝기
DEPLOY_MEAN = {"front": 135.8, "wrist": 138.8}

sys.path.insert(0, "/home/airlab/gr00t_remote/Isaac-GR00T-n1d5")
from gr00t.eval.service import ExternalRobotInferenceClient  # noqa: E402

_CACHE = {}


def frames(ep, key):
    if (ep, key) not in _CACHE:
        p = glob.glob(f"{DATASET}/videos/**/{key}/episode_{ep:06d}.mp4", recursive=True)[0]
        fr, _, _ = torchvision.io.read_video(p, pts_unit="sec", output_format="THWC")
        _CACHE[(ep, key)] = fr.numpy().astype(np.uint8)
    return _CACHE[(ep, key)]


def dim_to(img, target):
    cur = img.mean()
    return np.clip(img.astype(np.float32) * (target / cur), 0, 255).astype(np.uint8)


def query(client, state, front, wrist):
    obs = {
        "video.front": front[np.newaxis, ...],
        "video.wrist": wrist[np.newaxis, ...],
        "state.single_arm": state[:5][np.newaxis, ...],
        "state.gripper": state[5:6][np.newaxis, ...],
        "annotation.human.task_description": [LANG],
    }
    return client.get_action(obs)["action.single_arm"][:, 0]


def main():
    files = sorted(glob.glob(f"{DATASET}/data/**/*.parquet", recursive=True))
    df = pd.concat([pd.read_parquet(f) for f in files])
    client = ExternalRobotInferenceClient(host="localhost", port=5555)

    print("대상: 큐브가 배포 장면과 비슷한 중앙 위치인 학습 에피소드")
    print(f"{'ep':>3} {'진행률':>6} {'state_pan':>10} {'GT끝':>8} │ "
          f"{'원본예측':>9} {'어둡게':>9} │ {'밝기효과':>9}")
    print("─" * 72)

    effects = []
    for ep in EPS:
        g = df[df.episode_index == ep].sort_values("frame_index")
        gt_all = np.stack(g["action"].values)[:, 0]
        top, wri = frames(ep, "observation.images.top"), frames(ep, "observation.images.wrist")
        for frac in FRACS:
            i = int(len(g) * frac)
            state = np.asarray(g.iloc[i]["observation.state"], dtype=np.float64)
            fi = min(int(len(top) * frac), len(top) - 1)
            wi = min(int(len(wri) * frac), len(wri) - 1)
            f0, w0 = top[fi], wri[wi]
            gt = gt_all[i:i + 16]

            p_orig = query(client, state, f0, w0)[-1]
            p_dim = query(client, state,
                          dim_to(f0, DEPLOY_MEAN["front"]),
                          dim_to(w0, DEPLOY_MEAN["wrist"]))[-1]
            eff = p_dim - p_orig
            effects.append(eff)
            print(f"{ep:>3} {frac:>6.0%} {state[0]:>10.1f} {gt[-1]:>8.1f} │ "
                  f"{p_orig:>9.1f} {p_dim:>9.1f} │ {eff:>9.1f}")

    E = np.mean(effects)
    print("─" * 72)
    print(f"평균 밝기 효과 = {E:+.1f}°  (음수 = 어둡게 하면 왼쪽으로 쏠림)")
    if E < -5:
        print("→ 결론: 밝기 저하가 좌측 편향을 유발 = **조명이 원인**")
    elif abs(E) <= 5:
        print("→ 결론: 밝기는 예측을 거의 바꾸지 않음 = 밝기는 원인 아님 (구도/도메인 차이 의심)")
    else:
        print("→ 결론: 어둡게 하면 오히려 우측 — 예상과 반대, 추가 분석 필요")


if __name__ == "__main__":
    main()
