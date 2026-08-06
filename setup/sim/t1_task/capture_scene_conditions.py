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

    def visual_group(obs):
        """obs에서 카메라 그룹을 꺼낸다. 구조가 예상과 다르면 사용 가능한 키를 보여주고 중단."""
        if isinstance(obs, dict) and "visual" in obs:
            return obs["visual"]
        # wrapper 등으로 구조가 바뀐 경우 — rgb_* 키를 가진 dict를 탐색
        if isinstance(obs, dict):
            for v in obs.values():
                if isinstance(v, dict) and any(str(k).startswith("rgb_") for k in v):
                    return v
            if any(str(k).startswith("rgb_") for k in obs):
                return obs
        raise KeyError(
            "카메라 관측을 찾지 못했습니다. obs 최상위 키: "
            f"{list(obs.keys()) if isinstance(obs, dict) else type(obs)}"
        )

    def to_uint8(t):
        """cfg가 normalize=False라 0~255로 오지만, 0~1(float)로 오는 경우도 안전하게 처리."""
        a = t.detach().cpu().numpy() if hasattr(t, "detach") else np.asarray(t)
        a = a.astype(np.float32)
        if a.size and a.max() <= 1.001:   # 0~1 정규화된 경우
            a = a * 255.0
        return np.clip(a, 0, 255).astype(np.uint8)

    # front(external_D455) + wrist(ego) 둘 다 저장 — 조건별 시점 비교용
    CAMS = {"": "rgb_external_D455", "_wrist": "rgb_ego"}

    with torch.inference_mode():
        for ep in range(1, args.episodes + 1):
            obs, _ = env.reset()
            # 리셋 이벤트(로봇 색·카메라·박스 배치)가 렌더에 반영될 때까지 몇 스텝 진행
            for _ in range(args.settle):
                obs, *_ = env.step(torch.zeros(env.action_space.shape, device=env.unwrapped.device))
            vis = visual_group(obs)
            if ep == 1:
                print(f"[cap] 사용 가능한 카메라 키: {list(vis.keys())}", flush=True)
            for suffix, key in CAMS.items():
                if key not in vis:
                    continue
                path = os.path.join(args.out, f"ep{ep:02d}{suffix}.png")
                imageio.imwrite(path, to_uint8(vis[key][0]))
                print(f"[cap] {path}", flush=True)
    env.close()


if __name__ == "__main__":
    # 예외가 나도 Isaac Sim 앱은 반드시 닫는다(미종료 시 GPU 점유·hang).
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        raise
    finally:
        app.close()
