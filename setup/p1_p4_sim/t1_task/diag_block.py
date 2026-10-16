import sys, traceback
from isaaclab.app import AppLauncher
app = AppLauncher(headless=True, enable_cameras=True).app
def P(*a):
    print("BDIAG", *a, flush=True)
try:
    import torch, gymnasium as gym
    import isaaclab_tasks  # noqa
    from isaaclab_tasks.utils import parse_env_cfg
    import sim_to_real_so101.tasks  # noqa
    cfg = parse_env_cfg("Lerobot-So101-Teleop-Vials-To-Rack", device="cuda:0", num_envs=1)
    env = gym.make("Lerobot-So101-Teleop-Vials-To-Rack", cfg=cfg)
    env.reset()
    sc = env.unwrapped.scene
    for _ in range(30):
        env.step(torch.zeros(env.action_space.shape, device=env.unwrapped.device))
    for n in ["mat", "block_red", "basket_black", "robot"]:
        try:
            p = sc[n].data.root_pos_w[0].tolist(); P(f"{n}: ({p[0]:.3f},{p[1]:.3f},{p[2]:.3f})")
        except Exception as e: P(n, "ERR", e)
    env.close()
except Exception:
    P("EXCEPTION"); traceback.print_exc()
app.close()
