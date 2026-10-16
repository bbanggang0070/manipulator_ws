#!/usr/bin/env python
"""배포 실패를 오프라인으로 재현하고, 요인(밝기/구도)을 하나씩 제거해 원인을 좁힌다.

선행 결과(2026-07-20):
  - probe_swap_images.py: 학습 분포 관측에서는 영상 효과 18.9° >> state 효과 1.9°
    → vis2는 시각 그라운딩을 갖고 있음 (모델 문제 아님)
  - 그런데 실기 배포에서는 큐브 위치와 무관하게 pan≈-77 고정
  → 배포 관측이 학습 분포와 다른 것이 원인. 무엇이 다른지 여기서 좁힌다.

배포 dry-run에서 정책이 실제로 본 프레임(video.mp4)을 그대로 서버에 주입한다.
실패가 재현되면(pan이 큐브 방향과 무관한 값) 요인 제거 실험으로 원인을 찾는다.

실행(5090): python ~/probe_deploy_frame.py
"""
import glob
import sys

import numpy as np
import torchvision
from PIL import Image

LANG = "Pick up the red cube and place it in the black box"
DEPLOY_PNG = "/tmp/deploy_frame.png"  # front|wrist 가로 결합 (1280x480)
# dry-run 20260720_165632 chunk 2 시점의 실제 로봇 state
DEPLOY_STATE = np.array([0.88, -101.71, 89.71, 70.46, 0.04, 3.04], dtype=np.float64)

DATASET = "/home/airlab/.cache/huggingface/lerobot/heongyu/so101_t1_pickplace"

sys.path.insert(0, "/home/airlab/gr00t_remote/Isaac-GR00T-n1d5")
from gr00t.eval.service import ExternalRobotInferenceClient  # noqa: E402


def query(client, state, front, wrist):
    obs = {
        "video.front": front[np.newaxis, ...],
        "video.wrist": wrist[np.newaxis, ...],
        "state.single_arm": state[:5][np.newaxis, ...],
        "state.gripper": state[5:6][np.newaxis, ...],
        "annotation.human.task_description": [LANG],
    }
    return client.get_action(obs)["action.single_arm"][:, 0]


def train_frame(ep, frac=0.06):
    out = []
    for key in ("observation.images.top", "observation.images.wrist"):
        p = glob.glob(f"{DATASET}/videos/**/{key}/episode_{ep:06d}.mp4", recursive=True)[0]
        fr, _, _ = torchvision.io.read_video(p, pts_unit="sec", output_format="THWC")
        fr = fr.numpy().astype(np.uint8)
        out.append(fr[min(int(len(fr) * frac), len(fr) - 1)])
    return out


def match_brightness(img, target_mean):
    """이미지 평균 밝기를 target_mean에 맞춰 스케일(간단한 gain 보정)."""
    cur = img.mean()
    if cur < 1:
        return img
    return np.clip(img.astype(np.float32) * (target_mean / cur), 0, 255).astype(np.uint8)


def main():
    client = ExternalRobotInferenceClient(host="localhost", port=5555)

    img = np.array(Image.open(DEPLOY_PNG).convert("RGB"))
    d_front, d_wrist = img[:, :640], img[:, 640:]

    # 학습 프레임 기준(큐브 우측 배치 ep4, 좌측 ep0)
    t4_front, t4_wrist = train_frame(4)
    t0_front, t0_wrist = train_frame(0)

    print("배포 dry-run에서 큐브는 로봇 기준 **왼쪽 앞**에 있었음(실기 관찰).")
    print("아래에서 pan 부호: 음수=왼쪽, 양수=오른쪽\n")
    print(f"{'조건':<44} {'pan[0]':>8} {'pan[7]':>8} {'pan[15]':>8}")
    print("─" * 74)

    cases = [
        ("① 배포 프레임 그대로 (실패 재현 확인)", d_front, d_wrist, DEPLOY_STATE),
        ("② 배포 영상 + 학습 state(ep4 홈)", d_front, d_wrist, None),
        ("③ 배포 밝기를 학습 수준으로 보정", None, None, DEPLOY_STATE),
        ("④ [대조] 학습 ep4(우측 큐브) 원본", t4_front, t4_wrist, None),
        ("⑤ [대조] 학습 ep0(좌측 큐브) 원본", t0_front, t0_wrist, None),
        ("⑥ 배포 front + 학습 wrist(ep4)", d_front, t4_wrist, DEPLOY_STATE),
        ("⑦ 학습 front(ep4) + 배포 wrist", t4_front, d_wrist, DEPLOY_STATE),
    ]

    # ②④⑤용 학습 state (ep4 6% 시점)
    import pandas as pd
    files = sorted(glob.glob(f"{DATASET}/data/**/*.parquet", recursive=True))
    df = pd.concat([pd.read_parquet(f) for f in files])
    g4 = df[df.episode_index == 4].sort_values("frame_index")
    st4 = np.asarray(g4.iloc[int(len(g4) * 0.06)]["observation.state"], dtype=np.float64)
    g0 = df[df.episode_index == 0].sort_values("frame_index")
    st0 = np.asarray(g0.iloc[int(len(g0) * 0.06)]["observation.state"], dtype=np.float64)

    for name, f, w, s in cases:
        if name.startswith("③"):
            f = match_brightness(d_front, t4_front.mean())
            w = match_brightness(d_wrist, t4_wrist.mean())
        if name.startswith("⑤"):
            s = st0
        elif s is None:
            s = st4
        pan = query(client, s, f, w)
        h = len(pan)
        print(f"{name:<44} {pan[0]:>8.1f} {pan[min(7,h-1)]:>8.1f} {pan[h-1]:>8.1f}")

    print("─" * 74)
    print("해석 가이드:")
    print("  ①이 큐브 방향(왼쪽=음수)과 무관한 값이면 배포 실패가 오프라인 재현된 것.")
    print("  ④⑤가 각각 우(+)/좌(-)로 정확히 갈리면 모델·서버는 정상.")
    print("  ③이 ①과 다르면 밝기가 원인. ⑥⑦로 어느 카메라가 문제인지 분리.")


if __name__ == "__main__":
    main()
