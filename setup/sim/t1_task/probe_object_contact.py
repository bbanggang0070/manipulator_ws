"""물체의 물리 속성(질량·관성)을 실측한다 — 파지 이상을 진단할 때 쓴다.

왜 있는가 (2026-09-16):
  수집 중 마커만 그리퍼에 자석처럼 붙었다. 각감쇠 100 → 5로 낮춰도 그대로였고,
  크기대가 비슷한 지우개는 멀쩡했다. 추측을 더 쌓지 않으려고 값을 읽었다.

  측정 결과 — 질량·관성은 정상이었다:
    캡슐/원기둥 Ø13×70  m≈7.2g  I=(3.02e-6, 3.02e-6, 1.53e-7)
      → 이론값 I_transverse=m(3r²+h²)/12, I_axial=mr²/2 과 일치
    지우개 40×20×12     m≈3.8g  I=(1.71e-7, 5.49e-7, 6.30e-7)
    큐브 20             m≈6.4g  I=(4.24e-7, ×3)
  (질량이 5g이 아닌 이유: randomize_*_mass DR이 매 리셋 ±50%로 흔든다)

  남은 차이는 **충돌 형상**뿐이었다. PhysX 기본 도형은 구·캡슐·박스뿐이라
  USD Cylinder만 근사(custom geometry/볼록 껍질) 경로를 탄다 → 마커를 캡슐로 바꿨다.

한계 두 가지:
  · USD/PhysX 충돌 속성 덤프(①)는 스테이지 핸들을 잡는 순간 프로세스가 **조용히 죽는다**.
    contactOffset 같은 값을 직접 읽지 못했다. 고치려면 다른 경로가 필요하다.
  · 정지 높이(②)는 **이번 계획표 행이 실제로 배치한 물체**에만 의미가 있다.
    안 쓰는 물체는 reset_lang_scene이 z≈-20m로 주차하므로 -20001mm로 찍힌다.

사용(컨테이너 안, 또는 ./run_probe_contact.sh):
  python probe_object_contact.py
"""
import argparse

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser()
parser.add_argument("--task", default="Lerobot-So101-Teleop-Vials-To-Rack-DR")
parser.add_argument("--settle", type=int, default=120, help="재우는 데 쓸 스텝")
parser.add_argument("--seed", type=int, default=7)
AppLauncher.add_app_launcher_args(parser)
args = parser.parse_args()
args.headless = True
args.enable_cameras = True          # 끄면 RTX 설정이 초기화되지 않아 env 생성이 실패한다
app = AppLauncher(args).app

import gymnasium as gym                 # noqa: E402
import torch                            # noqa: E402
from isaaclab_tasks.utils import parse_env_cfg   # noqa: E402
from pxr import Usd, UsdGeom, UsdPhysics   # noqa: E402,F401

# 스테이지 핸들 — Isaac 버전에 따라 모듈 경로가 다르다. 셋 다 시도한다.
def _get_stage():
    for mod in ("isaacsim.core.utils.stage", "omni.isaac.core.utils.stage"):
        try:
            import importlib
            return importlib.import_module(mod).get_current_stage()
        except Exception:
            pass
    import omni.usd
    return omni.usd.get_context().get_stage()

import sim_to_real_so101.tasks          # noqa: F401,E402

# (씬 엔티티, prim 이름, 기대 반높이 m) — 기대 반높이는 '바닥에서 중심까지'의 기하값
PROBES = [
    ("obj_marker", "ObjMarker", 0.0065, "원기둥 Ø13×70"),
    ("obj_eraser", "ObjEraser", 0.006,  "직육면체 40×20×12"),
    ("block_red",  "Block",     0.010,  "정육면체 20"),
]


def dump_usd(stage, prim_path, label):
    prim = stage.GetPrimAtPath(prim_path)
    if not prim or not prim.IsValid():
        print(f"  ❌ prim 없음: {prim_path}")
        return
    print(f"\n  ── {label}  ({prim_path})")
    print(f"     타입: {prim.GetTypeName()}")
    # 충돌 속성은 prim 자신 또는 자식에 붙는다
    targets = [prim] + list(prim.GetChildren())
    seen = False
    for p in targets:
        attrs = {a.GetName(): a.Get() for a in p.GetAttributes()
                 if any(k in a.GetName() for k in
                        ("physxCollision", "physics:approximation", "CustomGeometry",
                         "physxConvexHull", "physics:collisionEnabled"))}
        if not attrs:
            continue
        seen = True
        if p != prim:
            print(f"     [{p.GetName()}]")
        for k, v in sorted(attrs.items()):
            print(f"       {k:48s} = {v}", flush=True)
    if not seen:
        print("       (충돌 속성 없음 — 기본값 사용, PhysX 씬 기본이 적용된다)")


def main():
    print(">>> probe 시작", flush=True)
    torch.manual_seed(args.seed)
    env_cfg = parse_env_cfg(args.task, device="cuda:0", num_envs=1)
    env_cfg.seed = args.seed
    env = gym.make(args.task, cfg=env_cfg)

    try:
        env.reset()
        print('>>> reset 완료', flush=True)
        dev = env.unwrapped.device
        zero = torch.zeros(env.action_space.shape, device=dev)
        for i in range(args.settle):
            env.step(zero)
        print(f'>>> {args.settle} 스텝 재움 완료', flush=True)

        sc = env.unwrapped.scene
        org = sc.env_origins[0].detach().cpu().numpy()

        print("\n" + "=" * 74)
        print(" ② 정지 높이 — 기대값보다 뜨면 충돌 형상이 부풀려져 있다")
        print("=" * 74)
        print(f"  {'물체':26s} {'중심 z':>9s} {'기대':>9s} {'차이':>9s}")
        for entity, _, half, label in PROBES:
            if entity not in sc.keys():
                print(f"  {label:26s}  (씬에 없음)")
                continue
            z = float(sc[entity].data.root_pos_w[0, 2].item() - org[2])
            # 작업면(mat) 윗면은 0.026 — vials_to_rack_env_cfg의 mat pos+두께에서 온다
            exp = 0.026 + half
            print(f"  {label:26s} {z*1000:8.2f}mm {exp*1000:8.2f}mm {(z-exp)*1000:+8.2f}mm")

        print("\n" + "=" * 74)
        print(" ③ 질량·관성·감쇠")
        print("=" * 74)
        for entity, _, _, label in PROBES:
            if entity not in sc.keys():
                continue
            obj = sc[entity]
            try:
                m = float(obj.root_physx_view.get_masses()[0].item())
                inert = obj.root_physx_view.get_inertias()[0].cpu().numpy()
                diag = (inert[0], inert[4], inert[8]) if inert.size == 9 else tuple(inert[:3])
                print(f"  {label:26s} m={m*1000:6.2f}g  I_diag={tuple(f'{v:.3e}' for v in diag)}")
            except Exception as e:
                print(f"  {label:26s} 읽기 실패: {e}")

        # ① USD 덤프는 **마지막**에 — 스테이지 핸들 획득이 프로세스를 끊는 일이 있다.
        print("\n" + "=" * 74, flush=True)
        print(" ① USD / PhysX 충돌 속성", flush=True)
        print("=" * 74, flush=True)
        try:
            stage = _get_stage()
            for entity, prim_name, _, label in PROBES:
                dump_usd(stage, f"/World/envs/env_0/{prim_name}", f"{label}  [{entity}]")
        except BaseException as e:
            print(f"  USD 덤프 실패: {type(e).__name__}: {e}", flush=True)
    finally:
        env.close()


if __name__ == "__main__":
    import traceback
    try:
        main()
    except Exception:
        traceback.print_exc()
        import sys; sys.stdout.flush(); sys.stderr.flush()
    app.close()
