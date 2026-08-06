"""조건별 씬 검증용 **캡처 전용** 스크립트 — 추론 없이 리셋만 반복해 시작 장면을 저장.

목적: "OOD 조건이 Isaac Sim에 제대로 반영됐는가"만 확인. 정책 추론(롤아웃)이 불필요하므로
      sweep(조건당 ~6분) 대신 조건당 ~1.5분이면 된다.

동작: env를 만들고 N회 reset → 매번 몇 스텝 굴려 이벤트가 적용된 뒤 external_D455 프레임 저장.
      (reset 직후 첫 프레임은 로봇 색·카메라 등 리셋 이벤트가 아직 반영 안 된 상태로 나오므로
       SETTLE 스텝만큼 진행한 뒤 캡처한다 — 실측으로 확인된 현상)

사용(컨테이너 안):
  python capture_scene_conditions.py --out /workspace/.../outputs/cap_<조건> --episodes 10
"""
import argparse

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser()
parser.add_argument("--task", default="Lerobot-So101-Teleop-Vials-To-Rack-DR-Eval")
parser.add_argument("--episodes", type=int, default=10)
parser.add_argument("--settle", type=int, default=6, help="리셋 후 캡처까지 진행할 스텝")
parser.add_argument("--out", required=True)
parser.add_argument("--seed", type=int, default=1984, help="sweep과 동일 seed → 같은 블록 위치")
AppLauncher.add_app_launcher_args(parser)
args = parser.parse_args()
args.headless = True
args.enable_cameras = True
app = AppLauncher(args).app

import os
import random

import gymnasium as gym
import numpy as np
import torch
from isaaclab_tasks.utils import parse_env_cfg

import sim_to_real_so101.tasks  # noqa: F401  (태스크 등록)


def main():
    os.makedirs(args.out, exist_ok=True)
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.cuda.manual_seed_all(args.seed)

    env_cfg = parse_env_cfg(args.task, device="cuda:0", num_envs=1)
    env_cfg.seed = args.seed
    env = gym.make(args.task, cfg=env_cfg)

    import imageio.v2 as imageio

    with torch.inference_mode():
        for ep in range(1, args.episodes + 1):
            obs, _ = env.reset()
            # 리셋 이벤트(로봇 색·카메라·박스 배치)가 렌더에 반영될 때까지 몇 스텝 진행
            for _ in range(args.settle):
                obs, *_ = env.step(torch.zeros(env.action_space.shape, device=env.unwrapped.device))
            vis = obs["visual"] if "visual" in obs else obs
            key = "rgb_external_D455" if "rgb_external_D455" in vis else "rgb_ego"
            img = vis[key][0].detach().cpu().numpy()
            img = np.clip(img, 0, 255).astype(np.uint8)
            path = os.path.join(args.out, f"ep{ep:02d}.png")
            imageio.imwrite(path, img)
            print(f"[cap] {path}", flush=True)
    env.close()


if __name__ == "__main__":
    main()
    app.close()
