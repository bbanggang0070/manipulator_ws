"""배경(주변 환경) 교체 실험 — 씬 구조 덤프 + 배경 USD 삽입 + 동일 카메라로 캡처.

목적(2026-08-12):
  학습 씬은 흰 라이트박스가 사방을 감싸고 있어 배경 픽셀이 거의 균일하다. 실제 책상 위처럼
  주변이 복잡해지면 정책이 무너지는지 보려면 **배경만** 바꾸고 나머지는 고정해야 한다.

⚠️ 라이트박스를 통째로 지우면 안 된다:
  top 카메라가 라이트박스에 매달려 있고(`LightStudio/LightBox/camera_mount/...`),
  조명(RectLight)도 그 안에 있다. 지우면 시점과 조명이 함께 바뀌어
  '배경 픽셀의 영향'과 '시점·조명 변화'가 뒤섞인다. **벽 지오메트리만 숨긴다.**

사용(컨테이너 안):
  # 1) 구조 파악 — 무엇을 숨겨야 하는지 이름을 본다
  python capture_background.py --out /o/bg_dump --episodes 1 --dump-prims

  # 2) 배경 교체 + 캡처
  python capture_background.py --out /o/bg_room --episodes 3 \
      --bg https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/5.0/Isaac/Environments/Simple_Room/simple_room.usd \
      --hide Wall,Floor,Ceiling,Backdrop --bg-pos 0,0,0 --bg-scale 1.0
"""
import argparse

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser()
parser.add_argument("--task", default="Lerobot-So101-Teleop-Vials-To-Rack-DR-Eval")
parser.add_argument("--episodes", type=int, default=3)
parser.add_argument("--settle", type=int, default=6)
parser.add_argument("--out", required=True)
parser.add_argument("--seed", type=int, default=100)
parser.add_argument("--dump-prims", action="store_true", help="LightStudio 하위 prim 트리를 출력")
parser.add_argument("--bg", default="", help="배경으로 얹을 USD 경로/URL (빈 값이면 교체 안 함)")
parser.add_argument("--hide", default="", help="LightBox 하위에서 숨길 prim 이름 조각들 (쉼표 구분)")
parser.add_argument("--bg-pos", default="0,0,0")
parser.add_argument("--bg-scale", type=float, default=1.0)
parser.add_argument("--surface-tex", default="", help="작업면(Base)에 입힐 텍스처 파일/URL")
parser.add_argument("--surface-color", default="", help="작업면 단색 r,g,b (0~1). --surface-tex 없을 때만")
parser.add_argument("--surface-uv", type=float, default=1.0, help="텍스처 반복 횟수(클수록 무늬가 촘촘)")
parser.add_argument("--gui", action="store_true", help="Isaac Sim 창을 띄워 직접 둘러본다(캡처 대신)")
AppLauncher.add_app_launcher_args(parser)
args = parser.parse_args()
args.headless = not args.gui
args.enable_cameras = True
app = AppLauncher(args).app

import os
import random

import gymnasium as gym
import numpy as np
import torch
from isaaclab_tasks.utils import parse_env_cfg

import sim_to_real_so101.tasks  # noqa: F401  (태스크 등록)


def dump_prims(stage, root="/World/envs/env_0/LightStudio"):
    from pxr import UsdGeom
    n = 0
    print(f"[bg] --- prim 트리: {root} ---", flush=True)
    for p in stage.Traverse():
        s = str(p.GetPath())
        if not s.startswith(root):
            continue
        t = p.GetTypeName()
        if t in ("Mesh", "RectLight", "Camera", "Xform", "Scope"):
            vis = ""
            im = UsdGeom.Imageable(p)
            if im:
                vis = f"  vis={im.ComputeVisibility()}"
            print(f"[bg]   {s}  [{t}]{vis}", flush=True)
            n += 1
    print(f"[bg] --- 총 {n}개 ---", flush=True)


def hide_prims(stage, needles, root="/World/envs/env_0/LightStudio/LightBox"):
    """이름에 needle이 들어간 prim을 보이지 않게 한다(삭제가 아니라 가시성만 끈다).

    삭제하지 않는 이유: 카메라·조명이 같은 서브트리에 있어 지우면 시점·조명이 함께 바뀐다.
    """
    from pxr import UsdGeom
    hidden = []
    for p in stage.Traverse():
        s = str(p.GetPath())
        if not s.startswith(root):
            continue
        name = p.GetName()
        # 부분 문자열로 맞추면 안 된다: "Back"이 카메라 케이스 메시 "Case_back"까지 걸어
        # D455 모델 일부가 사라진다(실측 2026-08-12). 이름 전체가 같을 때만 숨긴다.
        if any(nd.lower() == name.lower() for nd in needles):
            # 카메라·라이트는 절대 건드리지 않는다
            if p.GetTypeName() in ("Camera", "RectLight") or "camera" in name.lower():
                continue
            im = UsdGeom.Imageable(p)
            if im:
                im.MakeInvisible()
                hidden.append(s)
    print(f"[bg] 숨긴 prim {len(hidden)}개", flush=True)
    for h in hidden[:20]:
        print(f"[bg]   - {h}", flush=True)
    return hidden


def add_background(stage, usd, pos, scale):
    from pxr import Gf, Sdf, UsdGeom
    path = "/World/Background"
    prim = stage.DefinePrim(path, "Xform")
    prim.GetReferences().AddReference(usd)
    x = UsdGeom.Xformable(prim)
    x.ClearXformOpOrder()
    # ClearXformOpOrder는 '순서'만 지운다 — 속성 자체는 남아 있어, 기존 xformOp:scale이
    # double3인데 float 정밀도로 다시 만들면 Tf.ErrorException이 난다. 명시적으로 double을 쓴다.
    x.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Vec3d(*pos))
    x.AddScaleOp(UsdGeom.XformOp.PrecisionDouble).Set(Gf.Vec3d(scale, scale, scale))
    print(f"[bg] 배경 삽입: {usd}  pos={pos} scale={scale}", flush=True)
    return prim


SURFACE_PRIMS = (
    "/World/envs/env_0/LightStudio/LightBox/Base",   # 라이트박스 바닥
    "/World/envs/env_0/Mat",                         # 그 위에 깔린 매트(실제 작업면)
)


def set_surface(stage, tex="", color="", uv=1.0, targets=SURFACE_PRIMS):
    """작업면(Base 메시)의 재질을 바꾼다.

    왜 여기인가(2026-08-12 실측):
      배경 실험에서 방(Simple_Room/Office/Warehouse)을 갈아끼워도 정책 시점의 픽셀은 거의
      안 변한다 — top 카메라 화각이 좁아 **작업면이 화면의 대부분**을 차지하기 때문이다.
      실제로 '주변 픽셀의 영향'을 재려면 이 면을 바꾸는 게 지렛대가 가장 크다.

    카메라·조명·기하는 그대로 두고 **재질만** 교체하므로, 성능이 떨어지면 원인을
    배경 픽셀로 좁힐 수 있다(시점·조명 변화가 섞이지 않는다).
    """
    from pxr import Gf, Sdf, UsdShade
    prims = []
    for t in targets:
        pr = stage.GetPrimAtPath(t)
        if pr and pr.IsValid():
            prims.append(pr)
        else:
            print(f"[bg] ⚠ 작업면 prim 없음(건너뜀): {t}", flush=True)
    if not prims:
        return None

    mat = UsdShade.Material.Define(stage, "/World/Looks/SurfaceMat")
    sh = UsdShade.Shader.Define(stage, "/World/Looks/SurfaceMat/PBR")
    sh.CreateIdAttr("UsdPreviewSurface")
    sh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.7)
    sh.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)

    if tex:
        reader = UsdShade.Shader.Define(stage, "/World/Looks/SurfaceMat/stReader")
        reader.CreateIdAttr("UsdPrimvarReader_float2")
        reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
        reader.CreateOutput("result", Sdf.ValueTypeNames.Float2)

        t = UsdShade.Shader.Define(stage, "/World/Looks/SurfaceMat/Tex")
        t.CreateIdAttr("UsdUVTexture")
        t.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(tex)
        t.CreateInput("wrapS", Sdf.ValueTypeNames.Token).Set("repeat")
        t.CreateInput("wrapT", Sdf.ValueTypeNames.Token).Set("repeat")
        t.CreateInput("scale", Sdf.ValueTypeNames.Float4).Set(Gf.Vec4f(1, 1, 1, 1))
        t.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(
            reader.ConnectableAPI(), "result")
        t.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
        sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(
            t.ConnectableAPI(), "rgb")
        # UV 반복: st를 곱해 무늬 밀도를 조절한다(작업면이 30cm 남짓이라 기본 1회면 너무 크다)
        if uv != 1.0:
            reader.CreateInput("scale", Sdf.ValueTypeNames.Float2).Set(Gf.Vec2f(uv, uv))
        print(f"[bg] 작업면 텍스처: {tex}  (uv×{uv})", flush=True)
    else:
        rgb = [float(v) for v in (color or "0.5,0.5,0.5").split(",")]
        sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*rgb))
        print(f"[bg] 작업면 단색: {rgb}", flush=True)

    sh.CreateOutput("surface", Sdf.ValueTypeNames.Token)
    mat.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")
    for pr in prims:
        # Xform에 바인딩하면 하위 메시로 상속된다(Mat은 메시를 품은 Xform이다).
        UsdShade.MaterialBindingAPI.Apply(pr)
        UsdShade.MaterialBindingAPI(pr).Bind(mat)
        print(f"[bg]   바인딩: {pr.GetPath()}", flush=True)
    return mat


def main():
    os.makedirs(args.out, exist_ok=True)
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.cuda.manual_seed_all(args.seed)

    env_cfg = parse_env_cfg(args.task, device="cuda:0", num_envs=1)
    env_cfg.seed = args.seed

    if args.gui:
        # GUI 렌더러는 일부 RTX carb 설정을 모른다 — 그대로 두면 env 생성에서
        #   ValueError: '/rtx/translucency/reflectAtAllBounce' ... does not map to a carb setting
        # 로 죽는다(실측 2026-08-12, Isaac 5.1). 뷰어에서만 해당 키를 뺀다.
        # ※ 공용 태스크 설정(task_env_cfg.py)은 건드리지 않는다. 학습·평가 렌더를 바꾸면
        #   지금까지의 결과와 화면이 달라진다.
        cs = getattr(env_cfg.sim.render, "carb_settings", None)
        if isinstance(cs, dict) and cs:
            # 하나씩 빼면 다음 키에서 또 죽는다(reflectAtAllBounce → sampleRoughness → …).
            # 뷰어의 용도는 배경의 구도·스케일 판단이므로 투명도 튜닝을 통째로 비운다.
            # ⚠ 그래서 **창에서 보이는 그림은 평가 렌더와 완전히 같지 않다**.
            #   픽셀 수준 비교는 headless 캡처(SHOT=1)로 해야 한다 — 거기선 원래 설정이 유지된다.
            print(f"[bg] GUI 모드 — 미지원 RTX 설정 {len(cs)}개 제외: {sorted(cs)}", flush=True)
            env_cfg.sim.render.carb_settings = {}
    print("[bg] env 생성 시작", flush=True)
    env = gym.make(args.task, cfg=env_cfg)
    print("[bg] env 생성 완료", flush=True)

    import imageio.v2 as imageio
    import omni.usd
    stage = omni.usd.get_context().get_stage()

    if args.dump_prims:
        dump_prims(stage)
    if args.hide:
        hide_prims(stage, [s.strip() for s in args.hide.split(",") if s.strip()])
    if args.surface_tex or args.surface_color:
        set_surface(stage, args.surface_tex, args.surface_color, args.surface_uv)
    if args.bg:
        add_background(stage, args.bg,
                       [float(v) for v in args.bg_pos.split(",")], args.bg_scale)

    def visual_group(obs):
        if isinstance(obs, dict) and "visual" in obs:
            return obs["visual"]
        if isinstance(obs, dict):
            for v in obs.values():
                if isinstance(v, dict) and any(str(k).startswith("rgb_") for k in v):
                    return v
            if any(str(k).startswith("rgb_") for k in obs):
                return obs
        raise KeyError(f"카메라 관측 없음. 키: {list(obs.keys())}")

    def to_uint8(t):
        a = t.detach().cpu().numpy() if hasattr(t, "detach") else np.asarray(t)
        a = a.astype(np.float32)
        if a.size and a.max() <= 1.001:
            a = a * 255.0
        return np.clip(a, 0, 255).astype(np.uint8)

    if args.gui:
        # 창을 띄워 사람이 직접 둘러본다. 카메라 시점·배경 정합을 눈으로 확인하는 용도라
        # 정책은 돌리지 않고 0 액션으로 유지한다(로봇이 초기 자세에 머문다).
        print(f"[bg] GUI 모드 — app.is_running()={app.is_running()}", flush=True)
        zero = torch.zeros(env.action_space.shape, device=env.unwrapped.device)
        with torch.inference_mode():
            env.reset()          # step 전에 반드시 reset — 없으면 gymnasium이 ResetNeeded로 죽는다
            n = 0
            while app.is_running():
                env.step(zero)
                n += 1
                if n % 600 == 0:
                    env.reset()   # 주기적으로 리셋해 여러 배치를 볼 수 있게 한다
        env.close()
        return

    CAMS = {"": "rgb_external_D455", "_wrist": "rgb_ego"}
    with torch.inference_mode():
        for ep in range(1, args.episodes + 1):
            obs, _ = env.reset()
            for _ in range(args.settle):
                obs, *_ = env.step(torch.zeros(env.action_space.shape, device=env.unwrapped.device))
            vis = visual_group(obs)
            for suffix, key in CAMS.items():
                if key in vis:
                    p = os.path.join(args.out, f"ep{ep:02d}{suffix}.png")
                    imageio.imwrite(p, to_uint8(vis[key][0]))
                    print(f"[bg] {p}", flush=True)
    env.close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        raise
    finally:
        app.close()
