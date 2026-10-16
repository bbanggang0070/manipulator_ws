"""언어 조건화 씬 검증 — 추론 없이 리셋만 반복해 **배치·치수·주차**를 숫자로 확인한다.

왜 필요한가 (language_conditioning_sim_plan.md §3-1 검증 5단):
  이 씬은 물체 10종·박스 4색을 스폰해 두고 계획표가 지정한 것만 꺼내 쓴다. 세 가지가
  조용히 틀어질 수 있고, 전부 **수집이 끝난 뒤에야** 드러난다:

    ① YCB 마커의 스케일이 틀려 **어떤 것도 못 잡는 데이터**를 5시간 모은다
       (원본 Ø18×121mm — 스케일 없이 쓰면 그리퍼에 안 들어간다).
    ② 주차한 물체가 화면 구석에 남아, "미학습 색은 본 적 없다"는 전제가 깨진다.
       흰·분홍 큐브가 한 프레임이라도 보이면 §7-4 일반화 평가가 통째로 무효다.
    ③ 거부 표집이 자주 실패해 물체가 겹친 채로 시연이 진행된다.

  전례: 씬을 5090에 배포하지 않아 v2 씬에서 측정한 무효 데이터를 만든 적이 있다.
  **배포 후 이 스크립트로 값을 확인하고 수집을 시작할 것.**

사용(컨테이너 안):
  python verify_lang_scene.py --episodes 30 --aabb
  LANG_PLAN=/workspace/.../lang_collect_plan.csv python verify_lang_scene.py --episodes 30
"""
import argparse

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser()
parser.add_argument("--task", default="Lerobot-So101-Teleop-Vials-To-Rack-DR")
parser.add_argument("--episodes", type=int, default=30)
parser.add_argument("--settle", type=int, default=6, help="리셋 후 계측까지 진행할 스텝")
parser.add_argument("--seed", type=int, default=1984)
parser.add_argument("--aabb", action="store_true", help="물체별 AABB(파지 폭) 출력")
AppLauncher.add_app_launcher_args(parser)
args = parser.parse_args()
args.headless = True
# 이미지를 쓰진 않지만 켜야 한다. 끄면 RTX 렌더 설정이 초기화되지 않아 env 생성이 실패한다.
args.enable_cameras = True
app = AppLauncher(args).app

import numpy as np                      # noqa: E402
import gymnasium as gym                 # noqa: E402
import torch                            # noqa: E402
from isaaclab_tasks.utils import parse_env_cfg   # noqa: E402

import sim_to_real_so101.tasks          # noqa: F401,E402  (태스크 등록)
# 카탈로그를 cfg에서 직접 읽는다. scene.keys()로 훑으면 이름이 안 걸릴 때
# **검사가 0건으로 조용히 통과**한다(2026-09-14 실측 — 주차·AABB가 통째로 헛돌았다).
from sim_to_real_so101.tasks.vials_to_rack_env_cfg import (   # noqa: E402
    LANG_OBJ_PRIM, LANG_BOX_PRIM,
)

BASE_XY = (-0.05, 0.0)
GRASP_MIN, GRASP_MAX = 0.012, 0.025     # 파지 폭 합격 구간 (§2-1)
BOX_LONGEST = 0.100                     # 박스 내부 단변 여유를 감안한 최대 허용 길이
MIN_SEP = 0.10
# 리셋 직후 물리가 몇 스텝 굴러 물체가 1~3mm 움직인다(실측: 98.7mm). 표집은 100mm로 하되
# 판정은 10mm 여유를 둔다 — 재려는 것은 "샘플러가 정확한가"가 아니라 "집을 공간이 있는가"다.
MIN_SEP_TOL = 0.010
BOX_CLEAR = 0.03
# 주차 좌표는 configure_scene.LANG_PARK_XY와 같아야 한다. 여기서는 "충분히 멀리 갔는가"만 본다.
PARK_FAR = 0.30                          # base에서 이만큼 밖이면 주차된 것으로 본다


def aabb(path):
    """스폰된 prim의 월드 AABB 크기(m). USD로 직접 잰다.

    XFormPrim.get_world_bounding_box()는 이 Isaac 버전에 없다(실측 2026-09-14).
    UsdGeom.Imageable.ComputeWorldBound는 stage만 있으면 되고 버전 의존이 적다.
    """
    from pxr import Usd, UsdGeom
    from isaaclab.sim import get_current_stage
    prim = get_current_stage().GetPrimAtPath(path)
    if not prim or not prim.IsValid():
        return f"prim 없음: {path}"
    rng = UsdGeom.Imageable(prim).ComputeWorldBound(
        Usd.TimeCode.Default(), UsdGeom.Tokens.default_).ComputeAlignedRange()
    if rng.IsEmpty():
        return f"AABB 비어 있음: {path}"
    return np.array([abs(v) for v in rng.GetSize()])


def main():
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    env_cfg = parse_env_cfg(args.task, device="cuda:0", num_envs=1)
    env_cfg.seed = args.seed
    env = gym.make(args.task, cfg=env_cfg)

    rows, dims, fail_park, fail_sep, fail_clear = [], {}, [], [], []
    n_checked = 0   # 주차 검사가 실제로 몇 건을 봤는가 (0이면 검사가 헛돈 것)
    min_obs = {"sep": 9.9, "clear": 9.9}   # 실측 최솟값 — 합격/불합격보다 이 숫자가 정보다
    try:
        for _ in range(args.episodes):
            env.reset()
            for _ in range(args.settle):
                env.step(torch.zeros(env.action_space.shape, device=env.unwrapped.device))
            sc = env.unwrapped.scene
            org = sc.env_origins[0].detach().cpu().numpy()
            row = getattr(env.unwrapped, "_lang_row", None)
            if row is None:
                print("❌ env._lang_row 없음 — lang 프리셋이 적용되지 않았다"
                      " (configure_scene.py <cfg> full+lang 을 먼저 실행)")
                break

            used = list(row["objects"])
            pos = {}
            for name in used:
                pos[name] = sc[name].data.root_pos_w[0].detach().cpu().numpy() - org
            box = {}
            for name in row["boxes"]:
                box[name] = sc[name].data.root_pos_w[0].detach().cpu().numpy() - org

            # ── 주차 확인: 쓰지 않은 물체·박스가 전부 화각 밖으로 갔는가 ──
            for name in list(LANG_OBJ_PRIM.values()) + list(LANG_BOX_PRIM.values()):
                if name in used or name in row["boxes"]:
                    continue
                n_checked += 1
                p = sc[name].data.root_pos_w[0].detach().cpu().numpy() - org
                if np.hypot(p[0] - BASE_XY[0], p[1] - BASE_XY[1]) < PARK_FAR or p[2] > -0.05:
                    fail_park.append((name, np.round(p, 3).tolist()))

            # ── 간격 확인 ──
            names = list(pos)
            for i in range(len(names)):
                for j in range(i + 1, len(names)):
                    d = float(np.hypot(*(pos[names[i]][:2] - pos[names[j]][:2])))
                    min_obs["sep"] = min(min_obs["sep"], d)
                    if d < MIN_SEP - MIN_SEP_TOL:
                        fail_sep.append((names[i], names[j], round(d, 4)))
                for bname, bp in box.items():
                    d = float(np.hypot(*(pos[names[i]][:2] - bp[:2])))
                    min_obs["clear"] = min(min_obs["clear"], d)
                    if d < BOX_CLEAR:
                        fail_clear.append((names[i], bname, round(d, 4)))

            rows.append({"n_obj": len(used), "n_box": len(box), "target": row["target"],
                         "dest": row["dest"], "objects": used})

            if args.aabb and not dims:
                for name in LANG_OBJ_PRIM.values():
                    path = (sc[name].cfg.prim_path
                            .replace("{ENV_REGEX_NS}", "/World/envs/env_0")
                            .replace("/World/envs/env_.*", "/World/envs/env_0"))
                    try:
                        dims[name] = aabb(path)
                    except Exception as e:
                        dims[name] = f"측정 실패: {e}"
    finally:
        env.close()

    # ⚠ 요약은 app.close() **전에** 출력한다. AppLauncher의 close()는 프로세스를 즉시 끝내
    #   이후 print가 통째로 유실된다(verify_near_scene.py에서 실측된 현상).
    n = len(rows)
    print(f"\n{'=' * 60}\n언어 씬 검증 — 리셋 {n}회 · {args.task}\n{'=' * 60}")
    if not n:
        return

    from collections import Counter
    print(f"  물체 수 분포: {dict(Counter(r['n_obj'] for r in rows))}"
          f"   박스 수 분포: {dict(Counter(r['n_box'] for r in rows))}")
    print(f"  타깃 물체: {dict(Counter(r['target'] for r in rows))}")
    print(f"  타깃 박스: {dict(Counter(r['dest'] for r in rows))}")

    ok = True
    def check(label, bad, extra=""):
        nonlocal ok
        good = not bad
        ok &= good
        print(f"  {'✅' if good else '❌'} {label:<28} {len(bad)}건 {extra}")
        for b in bad[:5]:
            print(f"       {b}")

    check("주차 누락(화면에 남음)", fail_park,
          f"/ 검사 {n_checked}건 ← 흰·분홍이 있으면 일반화 평가 무효")
    if n_checked == 0:
        ok = False
        print("  ❌ 주차 검사가 0건 — 엔티티 이름이 안 걸린다. 검사가 헛돌았다")
    check(f"물체 간격 < {MIN_SEP - MIN_SEP_TOL:.3f}m", fail_sep,
          f"/ 실측 최소 {min_obs['sep'] * 1000:.0f}mm")
    check(f"물체-박스 간격 < {BOX_CLEAR}m", fail_clear,
          f"/ 실측 최소 {min_obs['clear'] * 1000:.0f}mm")

    if args.aabb:
        print(f"\n  파지 폭(AABB 최소변) — 합격 {GRASP_MIN * 1000:.0f}~{GRASP_MAX * 1000:.0f}mm")
        for name, d in sorted(dims.items()):
            if isinstance(d, str):
                print(f"    ⚠ {name:<14} {d}")
                continue
            mn, mx = float(np.min(d)) * 1000, float(np.max(d)) * 1000
            good = GRASP_MIN * 1000 <= mn <= GRASP_MAX * 1000 and mx < BOX_LONGEST * 1000
            ok &= good
            print(f"    {'✅' if good else '❌'} {name:<14} {d[0]*1000:5.1f} × {d[1]*1000:5.1f} × "
                  f"{d[2]*1000:5.1f} mm   (최소변 {mn:.1f} · 최대변 {mx:.1f})")

    print(f"\n  {'✅ 통과 — 수집 시작 가능' if ok else '❌ 실패 — 위 항목을 고치고 다시 확인할 것'}")


if __name__ == "__main__":
    main()
    app.close()
