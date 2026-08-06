"""v4 타깃 수집 씬(`...-Near`) 검증 — 추론 없이 리셋만 반복해 **배치 분포**를 확인.

왜 필요한가:
  `reset_block_near_box`는 블록을 박스 주변 지정 거리대(0.08~0.18m)에 놓는 거부 샘플링이다.
  도달 범위(r 0.16~0.34, θ −0.7~1.25)와 충돌해 폴백으로 빠지면 **의도한 분포가 아닌 채**
  수집이 진행되고, 그 사실을 수집이 끝난 뒤에야 알게 된다.
  → 수집 전에 30회쯤 리셋해 거리·각도 분포를 숫자로 확인한다(약 2분).

  전례: 씬을 5090에 배포하지 않아 v2 씬에서 측정한 무효 데이터를 만든 적이 있다.
  **배포 후 이 스크립트로 값을 확인하고 수집을 시작할 것.**

사용(컨테이너 안):
  python verify_near_scene.py --episodes 30
"""
import argparse

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser()
parser.add_argument("--task", default="Lerobot-So101-Teleop-Vials-To-Rack-Near")
parser.add_argument("--episodes", type=int, default=30)
parser.add_argument("--settle", type=int, default=6, help="리셋 후 계측까지 진행할 스텝")
parser.add_argument("--seed", type=int, default=1984)
parser.add_argument("--csv", default=None, help="설정 시 좌표를 csv로 저장")
AppLauncher.add_app_launcher_args(parser)
args = parser.parse_args()
args.headless = True
# 이미지를 쓰진 않지만 켜야 한다. 끄면 RTX 렌더 설정이 초기화되지 않아
# RenderCfg의 '/rtx/...' 키가 carb 설정에 매핑되지 않는다며 env 생성이 실패한다.
args.enable_cameras = True
app = AppLauncher(args).app

import math
import random

import gymnasium as gym
import numpy as np
import torch
from isaaclab_tasks.utils import parse_env_cfg

import sim_to_real_so101.tasks  # noqa: F401  (태스크 등록)

BASE_XY = (-0.05, 0.0)
TARGET = (0.08, 0.18)      # BLOCK_NEAR_DIST_RANGE와 같아야 한다
REACH_R = (0.16, 0.34)
REACH_TH = (-0.7, 1.25)


def main():
    random.seed(args.seed); np.random.seed(args.seed)
    torch.manual_seed(args.seed); torch.cuda.manual_seed_all(args.seed)

    env_cfg = parse_env_cfg(args.task, device="cuda:0", num_envs=1)
    env_cfg.seed = args.seed
    env = gym.make(args.task, cfg=env_cfg)
    try:
        rows = []
        for _ in range(args.episodes):
            env.reset()
            for _ in range(args.settle):
                env.step(torch.zeros(env.action_space.shape, device=env.unwrapped.device))
            sc = env.unwrapped.scene
            org = sc.env_origins[0].detach().cpu().numpy()
            b = sc["block_red"].data.root_pos_w[0].detach().cpu().numpy() - org
            k = sc["basket_black"].data.root_pos_w[0].detach().cpu().numpy() - org
            rows.append({
                "d": float(np.hypot(b[0] - k[0], b[1] - k[1])),
                "r": float(np.hypot(b[0] - BASE_XY[0], b[1] - BASE_XY[1])),
                "th": float(np.arctan2(b[1] - BASE_XY[1], b[0] - BASE_XY[0])),
                "box_r": float(np.hypot(k[0] - BASE_XY[0], k[1] - BASE_XY[1])),
            })
    finally:
        env.close()

    # ⚠ 요약은 app.close() **전에** 출력해야 한다. AppLauncher의 close()는 프로세스를
    #   즉시 끝내버려 이후 print가 통째로 유실된다(실측: 30회 돌고도 출력이 하나도 안 나옴).
    n = len(rows)
    d = [x["d"] for x in rows]
    inb = sum(1 for x in d if TARGET[0] <= x <= TARGET[1])
    reach = sum(1 for x in rows if REACH_R[0] <= x["r"] <= REACH_R[1]
                and REACH_TH[0] <= x["th"] <= REACH_TH[1])
    neg = sum(1 for x in rows if x["th"] < 0)
    print(f"\n{'='*54}\n리셋 {n}회 — {args.task}\n{'='*54}")
    print(f"  블록-박스 거리  평균 {sum(d)/n:.3f}  범위 {min(d):.3f}~{max(d):.3f}")
    print(f"  목표대({TARGET[0]}~{TARGET[1]}m) 적중   {inb}/{n} = {inb/n*100:.0f}%   ← 95% 이상이어야 정상")
    print(f"  블록이 도달범위 안              {reach}/{n} = {reach/n*100:.0f}%   ← 100%여야 정상")
    print(f"  θ<0(오른쪽) 비율                {neg}/{n} = {neg/n*100:.0f}%   ← 목표 50% 근방")
    bx = [x["box_r"] for x in rows]
    print(f"  박스 반경 {min(bx):.3f}~{max(bx):.3f}  ← 0.28~0.34여야 정상")
    bad = [f"{x['d']:.3f}" for x in rows if not (TARGET[0] <= x["d"] <= TARGET[1])]
    if bad:
        print(f"  ⚠ 목표대 벗어난 거리: {', '.join(bad)}  (폴백 발생 의심 — 로그의 '[near]' 확인)")
    if args.csv:
        with open(args.csv, "w") as f:
            f.write("dist,block_r,block_theta,box_r\n")
            for x in rows:
                f.write(f"{x['d']:.4f},{x['r']:.4f},{x['th']:+.4f},{x['box_r']:.4f}\n")
        print(f"  → {args.csv}")


if __name__ == "__main__":
    main()
    app.close()
