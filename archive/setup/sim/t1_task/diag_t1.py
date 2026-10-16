"""T1 씬 물체 실제 위치 진단 — reset 후 mat/cube/box world z 출력."""
import sys, traceback
from isaaclab.app import AppLauncher
app = AppLauncher(headless=True, enable_cameras=True).app

def P(*a):
    print("T1_DIAG", *a, flush=True)
    sys.stderr.write("T1_DIAG " + " ".join(str(x) for x in a) + "\n"); sys.stderr.flush()

try:
    import torch
    import gymnasium as gym
    import isaaclab_tasks  # noqa
    from isaaclab_tasks.utils import parse_env_cfg
    import sim_to_real_so101.tasks  # noqa

    P("creating env...")
    cfg = parse_env_cfg("Lerobot-So101-T1-CubeBox", device="cuda:0", num_envs=1)
    env = gym.make("Lerobot-So101-T1-CubeBox", cfg=cfg)
    P("env created, resetting...")
    env.reset()
    sc = env.unwrapped.scene

    def zinfo(name):
        p = sc[name].data.root_pos_w[0].tolist()
        return f"{name}: ({p[0]:.3f}, {p[1]:.3f}, {p[2]:.3f})"

    P("--- after reset ---")
    for n in ["mat", "cube", "box", "robot"]:
        try: P(zinfo(n))
        except Exception as e: P(n, "ERR", e)

    for _ in range(30):
        env.step(torch.zeros(env.action_space.shape, device=env.unwrapped.device))
    P("--- after 30 steps ---")
    for n in ["mat", "cube", "box", "robot"]:
        try: P(zinfo(n))
        except Exception as e: P(n, "ERR", e)
    env.close()
except Exception:
    P("EXCEPTION"); traceback.print_exc()
app.close()
