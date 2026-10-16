#!/usr/bin/env python
"""학습 데이터 관측을 GR00T 서버에 주입해 "시각 그라운딩 유무"를 판정한다.

배경(2026-07-20): vis2(tune_visual+유효batch32, loss 0.009)에서도 실기 배포 시
큐브 위치와 무관하게 pan≈-77로 고정되는 v2 증상이 재현됨. 남은 두 가설:
  (A) 모델이 시각을 무시하고 학습 데이터의 지배적 모드/자기 자세만 재생 → 데이터 문제
  (B) 모델은 시각을 쓰지만 배포 시 관측이 학습 분포와 달라 실패 → 배포/도메인 갭

⚠️ 교란변수: 접근 중반 관측은 이미 state.pan이 좌우로 갈라져 있어, 모델이 시각을
   안 쓰고 "현재 자세 이어가기"만 해도 좌우 차이가 크게 나온다. 따라서 좌우 예측차만
   보면 안 되고, **같은 시점의 GT 액션과 비교**해야 한다:
     - GT가 이미 갈라진 구간에서 모델이 GT를 따라감  → 시각 사용 근거로 약함(자세 추종으로 설명 가능)
     - GT가 갈라지기 시작하는 구간에서 모델도 함께 갈라짐 → 시각 사용 근거로 강함
     - GT는 갈라지는데 모델은 안 갈라짐 → 시각 미사용(가설 A)

실행(5090에서):
  cd ~/gr00t_remote/Isaac-GR00T-n1d5 && source .venv/bin/activate
  python ~/probe_training_obs.py
전제: gr00t-server.sh t1 로 서버가 5555에서 떠 있어야 함.
"""
import glob
import sys

import numpy as np
import pandas as pd
import torchvision

DATASET = "/home/airlab/.cache/huggingface/lerobot/heongyu/so101_t1_pickplace"
LANG = "Pick up the red cube and place it in the black box"

# grasp 시점 pan 분석 결과: 5지점 그리드 순환이라 ep%5가 위치를 결정
#   ep%5==0 → pan≈-80(최좌) … ep%5==4 → pan≈+25(최우)
LEFT_EPS = [0, 5, 20, 25]
RIGHT_EPS = [4, 9, 24, 44]
FRACS = (0.02, 0.06, 0.10, 0.15, 0.20, 0.35)

sys.path.insert(0, "/home/airlab/gr00t_remote/Isaac-GR00T-n1d5")
from gr00t.eval.service import ExternalRobotInferenceClient  # noqa: E402

_VID_CACHE = {}


def _video(ep, key):
    if (ep, key) not in _VID_CACHE:
        paths = glob.glob(f"{DATASET}/videos/**/{key}/episode_{ep:06d}.mp4", recursive=True)
        frames, _, _ = torchvision.io.read_video(paths[0], pts_unit="sec", output_format="THWC")
        _VID_CACHE[(ep, key)] = frames.numpy().astype(np.uint8)
    return _VID_CACHE[(ep, key)]


def probe(client, df_all, ep, frac, horizon=16):
    """진행률 frac 지점의 관측을 주입하고, 예측 pan과 GT pan을 함께 반환."""
    g = df_all[df_all.episode_index == ep].sort_values("frame_index")
    i = int(len(g) * frac)
    state = np.asarray(g.iloc[i]["observation.state"], dtype=np.float64)

    front = _video(ep, "observation.images.top")
    wrist = _video(ep, "observation.images.wrist")
    fi = min(int(len(front) * frac), len(front) - 1)
    wi = min(int(len(wrist) * frac), len(wrist) - 1)

    obs = {
        "video.front": front[fi][np.newaxis, ...],
        "video.wrist": wrist[wi][np.newaxis, ...],
        "state.single_arm": state[:5][np.newaxis, ...],
        "state.gripper": state[5:6][np.newaxis, ...],
        "annotation.human.task_description": [LANG],
    }
    pred_pan = client.get_action(obs)["action.single_arm"][:, 0]

    # 같은 구간의 GT 액션 pan (관측 시점부터 horizon 스텝)
    gt = np.stack(g["action"].values)[:, 0]
    gt_pan = gt[i : i + horizon]
    return state[0], pred_pan, gt_pan


def main():
    files = sorted(glob.glob(f"{DATASET}/data/**/*.parquet", recursive=True))
    df_all = pd.concat([pd.read_parquet(f) for f in files])
    client = ExternalRobotInferenceClient(host="localhost", port=5555)

    print(f"{'진행률':>6} │ {'관측state(좌/우)':>17} │ {'GT 청크끝(좌/우)':>17} │ "
          f"{'예측 청크끝(좌/우)':>19} │ {'GT차':>7} {'예측차':>7}  판정")
    print("─" * 108)

    for frac in FRACS:
        acc = {}
        for label, eps in (("L", LEFT_EPS), ("R", RIGHT_EPS)):
            st, gtv, pdv = [], [], []
            for ep in eps:
                s0, pred, gt = probe(client, df_all, ep, frac)
                st.append(s0)
                gtv.append(gt[-1] if len(gt) else np.nan)
                pdv.append(pred[-1])
            acc[label] = (np.mean(st), np.nanmean(gtv), np.mean(pdv))

        (sL, gL, pL), (sR, gR, pR) = acc["L"], acc["R"]
        gt_gap, pd_gap = gR - gL, pR - pL
        state_gap = sR - sL

        # 관측 state가 이미 갈라져 있으면 예측차는 자세추종으로 설명 가능 → 판정 보류
        if abs(state_gap) > 15:
            verdict = "판정보류(state 이미 분기)"
        elif abs(gt_gap) < 10:
            verdict = "판정보류(GT도 아직 미분기)"
        elif abs(pd_gap) > 0.5 * abs(gt_gap):
            verdict = "★시각 사용(GT 따라 분기)"
        else:
            verdict = "✗시각 미사용(GT는 분기, 예측 안 함)"

        print(f"{frac:>6.0%} │ {sL:>7.1f} / {sR:>7.1f} │ {gL:>7.1f} / {gR:>7.1f} │ "
              f"{pL:>8.1f} / {pR:>8.1f} │ {gt_gap:>7.1f} {pd_gap:>7.1f}  {verdict}")

    print("─" * 108)
    print("해석: state 분기 전(진행률 낮음) 구간에서 GT는 좌우로 갈라지는데 예측이 안 갈라지면")
    print("      모델이 시각을 안 쓰는 것 = 가설 A(데이터/모드 문제).")


if __name__ == "__main__":
    main()
