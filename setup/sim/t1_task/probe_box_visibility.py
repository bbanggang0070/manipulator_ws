"""박스가 top 카메라에 **실제로 잡히는 (r, θ) 구간**을 측정한다.

왜 필요한가 (2026-09-14):
  언어 씬 캡처 14장을 보니 박스가 화면 밖으로 밀린 장면이 절반 가까이 됐다. 목적지를
  박스 색으로 지정하는 설계에서 **박스가 안 보이면 어떤 정책도 고를 수 없고**, 조작자는
  그 에피소드를 버려야 한다. 스킵률이 높으면 수집 시간이 그만큼 늘어난다.

  평가 B에서 같은 성격의 문제를 이미 겪었다 — 도달 영역 우측 끝(θ≈−0.49, r≈0.31)에서
  **블록이 top 카메라에 전혀 안 잡혀** 패널 #6을 교체해야 했다. 그때는 한 배치를 바꾸고 넘어갔지만,
  이번엔 박스가 매 에피소드 등장하므로 **범위 자체를 좁혀야** 한다.

방법:
  박스를 갈색 하나로 고정하고(색 검출이 쉽다) 리셋을 반복하며 (r, θ)와 갈색 픽셀 수를 기록한다.
  물체는 1개만 둬 화면을 깨끗하게 유지한다. θ 구간별 가시율을 내면 안전 범위가 정해진다.

사용(컨테이너 안):
  LANG_PLAN=/workspace/vis_plan.csv python probe_box_visibility.py --episodes 60
"""
import argparse

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser()
parser.add_argument("--task", default="Lerobot-So101-Teleop-Vials-To-Rack-DR")
parser.add_argument("--episodes", type=int, default=60)
parser.add_argument("--settle", type=int, default=6)
parser.add_argument("--seed", type=int, default=7)
parser.add_argument("--min-pixels", type=int, default=400,
                    help="이만큼 이상 잡히면 '보인다'로 센다 (박스는 크다 — 수천 픽셀이 정상)")
parser.add_argument("--what", choices=("box", "object"), default="box",
                    help="box=갈색 박스 가시성 · object=청록 큐브(타깃) 가시성")
parser.add_argument("--csv", default=None)
AppLauncher.add_app_launcher_args(parser)
args = parser.parse_args()
args.headless = True
args.enable_cameras = True
app = AppLauncher(args).app

import numpy as np                      # noqa: E402
import gymnasium as gym                 # noqa: E402
import torch                            # noqa: E402
from isaaclab_tasks.utils import parse_env_cfg   # noqa: E402

import sim_to_real_so101.tasks          # noqa: F401,E402

BASE_XY = (-0.05, 0.0)


def cyan_mask(img):
    """청록 큐브(0.05, 0.65, 0.70) 픽셀. 20mm라 보여도 수십~수백 픽셀뿐이다."""
    a = img.astype(np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    return (g - r > 25) & (b - r > 25) & (g > 60) & (b > 60)


def brown_mask(img):
    """갈색 박스(0.35, 0.22, 0.12) 픽셀. 나무 작업면이 없는 흰 라이트박스라 오검출이 적다."""
    a = img.astype(np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    return ((r > 60) & (r < 190) & (g > 25) & (g < 130) & (b < 95)
            & (r - g > 20) & (g - b > 8))


def main():
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    env_cfg = parse_env_cfg(args.task, device="cuda:0", num_envs=1)
    env_cfg.seed = args.seed
    env = gym.make(args.task, cfg=env_cfg)

    rows = []
    try:
        for _ in range(args.episodes):
            obs, _ = env.reset()
            for _ in range(args.settle):
                obs, *_ = env.step(torch.zeros(env.action_space.shape, device=env.unwrapped.device))
            row = getattr(env.unwrapped, "_lang_row", None)
            if row is None:
                print("❌ env._lang_row 없음 — full+lang 프리셋을 먼저 적용하라")
                break
            sc = env.unwrapped.scene
            org = sc.env_origins[0].detach().cpu().numpy()
            bname = row["boxes"][0] if args.what == "box" else row["objects"][0]
            p = sc[bname].data.root_pos_w[0].detach().cpu().numpy() - org
            r = float(np.hypot(p[0] - BASE_XY[0], p[1] - BASE_XY[1]))
            th = float(np.arctan2(p[1] - BASE_XY[1], p[0] - BASE_XY[0]))

            vis = obs["visual"] if "visual" in obs else obs
            img = None
            for k in ("rgb_external_D455", "rgb_ego"):
                if k in vis:
                    a = vis[k][0].detach().cpu().numpy()
                    img = (a * 255 if a.max() <= 1.001 else a).clip(0, 255).astype(np.uint8)
                    break
            mask = brown_mask if args.what == "box" else cyan_mask
            npix = int(mask(img).sum()) if img is not None else -1
            rows.append((r, th, npix, bname))
    finally:
        env.close()

    # ⚠ 요약은 app.close() 전에 출력한다(AppLauncher가 프로세스를 즉시 끝낸다).
    n = len(rows)
    print(f"\n{'=' * 62}\n가시성 — 리셋 {n}회 (갈색 픽셀 ≥{args.min_pixels} 이면 '보임')\n{'=' * 62}")
    if not n:
        return
    seen = [x for x in rows if x[2] >= args.min_pixels]
    print(f"  전체 가시율: {len(seen)}/{n} = {len(seen) / n * 100:.0f}%")
    print(f"  갈색 픽셀 중앙값: {int(np.median([x[2] for x in rows]))}\n")

    lo_e, hi_e = (-1.15, 1.15) if args.what == "box" else (-0.7, 1.25)
    edges = np.linspace(lo_e, hi_e, 9)
    print(f"  θ 구간별 가시율 ({'박스' if args.what == 'box' else '물체'} 각도, rad)")
    for i in range(len(edges) - 1):
        lo, hi = edges[i], edges[i + 1]
        sub = [x for x in rows if lo <= x[1] < hi]
        if not sub:
            continue
        s = sum(1 for x in sub if x[2] >= args.min_pixels)
        bar = "█" * int(s / len(sub) * 20)
        print(f"    {lo:+.2f}~{hi:+.2f}  {s:2d}/{len(sub):2d} = {s / len(sub) * 100:3.0f}%  {bar}")

    print(f"\n  r 구간별 가시율 ({'박스' if args.what == 'box' else '물체'} 반경, m)")
    rbins = (((0.28, 0.30), (0.30, 0.32), (0.32, 0.34)) if args.what == "box"
             else ((0.16, 0.22), (0.22, 0.28), (0.28, 0.34)))
    for lo, hi in rbins:
        sub = [x for x in rows if lo <= x[0] < hi]
        if not sub:
            continue
        s = sum(1 for x in sub if x[2] >= args.min_pixels)
        print(f"    {lo:.2f}~{hi:.2f}  {s:2d}/{len(sub):2d} = {s / len(sub) * 100:3.0f}%")

    if args.csv:
        with open(args.csv, "w") as f:
            f.write("r,theta,brown_px,box\n")
            for r, th, npx, b in rows:
                f.write(f"{r:.4f},{th:.4f},{npx},{b}\n")
        print(f"\n  좌표 저장: {args.csv}")


if __name__ == "__main__":
    main()
    app.close()
