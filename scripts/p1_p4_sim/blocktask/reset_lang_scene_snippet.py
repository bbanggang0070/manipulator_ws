

# ── 언어 조건화 씬 리셋 (2026-09-14, language_conditioning_sim_plan.md §3-2) ──────────
_LANG_PLAN_CACHE = {}


def _load_lang_plan(path):
    """에피소드 계획표(CSV)를 읽어 리스트로 돌려준다. 같은 경로는 한 번만 읽는다.

    계획표가 없으면 빈 리스트를 주고, 호출부가 '카탈로그에서 무작위 4개'로 되돌린다.
    평가는 계획표 없이 EVAL_* 환경변수로 도는 경우가 있어 그 경로를 막으면 안 된다.
    """
    if path in _LANG_PLAN_CACHE:
        return _LANG_PLAN_CACHE[path]
    rows = []
    if path and os.path.exists(path):
        import csv
        with open(path) as f:
            for r in csv.DictReader(f):
                rows.append({
                    "objects": [x for x in r["objects"].split(",") if x],
                    "boxes": [x for x in r["boxes"].split(",") if x],
                    "target": r["target"],
                    "dest": r["dest"],
                    "instruction": r.get("instruction", ""),
                })
        print(f"[lang] 계획표 {len(rows)}행 로드: {path}", flush=True)
    else:
        print(f"[lang] ⚠ 계획표 없음({path!r}) — 카탈로그에서 무작위 배치로 진행", flush=True)
    _LANG_PLAN_CACHE[path] = rows
    return rows


def _box_gap(px, py, bx, by, yaw, hx, hy):
    """점과 박스(회전 사각형) 사이의 간격. 박스 안이면 음수.

    왜 중심거리가 아닌가: 박스 반장축이 7cm(0.7배 축소 기준)라 중심거리 8cm로 자르면
    **박스 안에 물체가 들어간다.** reset_box_and_block_clear가 같은 이유로 사각형 판정을 쓴다.
    """
    dx, dy = px - bx, py - by
    c, s = torch.cos(-yaw), torch.sin(-yaw)
    lx = dx * c - dy * s
    ly = dx * s + dy * c
    gx = torch.abs(lx) - hx
    gy = torch.abs(ly) - hy
    outside = torch.sqrt(torch.clamp(gx, min=0.0) ** 2 + torch.clamp(gy, min=0.0) ** 2)
    inside = -torch.minimum(torch.abs(gx), torch.abs(gy))
    return torch.where((gx < 0) & (gy < 0), inside, outside)


def reset_lang_scene(
        env,
        env_ids: torch.Tensor,
        plan_csv: str,
        objects: dict,
        boxes: dict,
        park_xy: tuple[float, float],
        base_xy: tuple[float, float],
        obj_min_dist: float,
        obj_max_dist: float,
        obj_angle_range: tuple[float, float],
        obj_z: float,
        box_min_dist: float,
        box_max_dist: float,
        box_angle_range: tuple[float, float],
        box_yaw_range: tuple[float, float],
        box_z: float,
        box_min_ang_sep: float,
        box_half_extent: tuple[float, float],
        box_clear: float,
        min_sep: float,
        max_tries: int = 200,
):
    """계획표의 현재 행대로 **박스를 먼저, 물체를 그 다음에** 놓고 나머지는 전부 주차한다.

    왜 이 순서인가:
      물체가 박스를 피하려면 박스 위치가 먼저 확정돼야 한다. reset_distractors가 `avoid`의
      **현재 좌표**를 읽는 것과 같은 이유이고, 분리된 term으로는 성립하지 않는다는 것이
      이미 실측으로 확인됐다(reset_box_and_block_clear 주석: seed 31에서 3/10이 겹침권).

    왜 주차가 필요한가:
      색은 스폰 시점에 구워지므로 카탈로그를 전부 스폰해 두고 쓸 것만 꺼내는 구조다.
      쓰지 않는 물체는 **화각 밖 + 매트 아래**로 보낸다. 한 프레임이라도 화면에 남으면
      "미학습 색은 본 적 없다"는 전제가 깨져 일반화 평가가 통째로 무효가 된다.

    이 term 하나가 reset_block_position·reset_basket_random을 대신한다(둘은 None 처리).
    """
    all_objs = list(objects.values())
    all_boxes = list(boxes.values())
    dev = env.scene[all_objs[0]].device
    n = len(env_ids)
    org = env.scene.env_origins[env_ids]

    # ── 에피소드 인덱스 — 리셋 이벤트는 **에피소드당 두 번** 불린다 ──
    #   reset_fixed_panel에서 실측된 현상(사용된 인덱스가 0,2,4,… 로 절반이 건너뛰어졌다).
    #   같은 step에서 다시 불리면 직전 인덱스를 재사용해 중복 호출을 흡수한다.
    plan = _load_lang_plan(plan_csv)
    if not hasattr(env, "_lang_idx"):
        env._lang_idx = torch.zeros(env.num_envs, dtype=torch.long, device=dev)
        env._lang_last = torch.full((env.num_envs,), -1, dtype=torch.long, device=dev)
    step = int(getattr(env, "common_step_counter", 0))
    same = env._lang_last[env_ids] == step
    cur = env._lang_idx[env_ids]
    idx = torch.where(same, cur - 1, cur)
    env._lang_idx[env_ids] = torch.where(same, cur, cur + 1)
    env._lang_last[env_ids] = step

    # 단일 env 전제(수집·평가 모두 --num_envs 1). 여러 env면 첫 번째 행을 공유한다.
    row_i = int(idx[0].item())
    if plan:
        row = plan[row_i % len(plan)]
        use_objs = [objects[o] for o in row["objects"] if o in objects]
        use_boxes = [boxes[b] for b in row["boxes"] if b in boxes]
        tgt, dst = row["target"], row["dest"]
        instr = row["instruction"]
    else:
        # 계획표가 없으면 카탈로그에서 무작위 4개 + 박스 2개(평가·검증용 폴백)
        import random as _rnd
        keys = [k for k in objects if not k.startswith(("white", "pink"))]
        pick = _rnd.sample(keys, min(4, len(keys)))
        bkeys = [b for b in boxes if b != "white"]
        bpick = _rnd.sample(bkeys, min(2, len(bkeys)))
        use_objs = [objects[o] for o in pick]
        use_boxes = [boxes[b] for b in bpick]
        tgt, dst, instr = pick[0], bpick[0], ""

    # 다음 단계(recorder·scenes.csv)가 읽을 수 있게 이번 행을 env에 남긴다.
    env._lang_row = {"index": row_i, "objects": use_objs, "boxes": use_boxes,
                     "target": tgt, "dest": dst, "instruction": instr}

    # ── 1) 박스 — 각분리 ≥ box_min_ang_sep ──
    #   r=0.31에서 0.8rad이면 중심거리 241mm로, 장축이 마주 보는 최악(필요 ~190mm)에도 겹치지 않는다.
    box_pose = []
    for bi, bname in enumerate(use_boxes):
        asset: RigidObject = env.scene[bname]
        for _ in range(max_tries):
            ang = math_utils.sample_uniform(box_angle_range[0], box_angle_range[1], (n,), device=dev)
            if not box_pose:
                break
            gap = torch.stack([torch.abs(ang - a) for a, _, _ in box_pose], dim=0).min(dim=0).values
            if bool((gap >= box_min_ang_sep).all()):
                break
        else:
            print(f"[lang] ⚠ 박스 각분리 확보 실패({bname}) — 이 ep는 건너뛸 것", flush=True)
        r = math_utils.sample_uniform(box_min_dist, box_max_dist, (n,), device=dev)
        yaw = math_utils.sample_uniform(box_yaw_range[0], box_yaw_range[1], (n,), device=dev)
        bx = base_xy[0] + r * torch.cos(ang)
        by = base_xy[1] + r * torch.sin(ang)
        default = asset.data.default_root_state[env_ids].clone()
        zeros = torch.zeros_like(yaw)
        dq = math_utils.quat_from_euler_xyz(zeros, zeros, yaw)
        quat = math_utils.quat_mul(default[:, 3:7], dq)
        pos = torch.stack([bx, by, torch.full((n,), box_z, device=dev)], dim=-1)
        asset.write_root_pose_to_sim(torch.cat([pos + org, quat], dim=-1), env_ids=env_ids)
        asset.write_root_velocity_to_sim(torch.zeros((n, 6), device=dev), env_ids=env_ids)
        box_pose.append((ang, (bx, by), yaw))

    # ── 2) 물체 — 박스(사각형 간격)와 서로(중심거리)를 피해 거부 표집 ──
    hx, hy = box_half_extent
    placed = []
    for oname in use_objs:
        asset: RigidObject = env.scene[oname]
        px = torch.zeros((n,), device=dev)
        py = torch.zeros((n,), device=dev)
        done = torch.zeros((n,), dtype=torch.bool, device=dev)
        for _ in range(max_tries):
            ang = math_utils.sample_uniform(obj_angle_range[0], obj_angle_range[1], (n,), device=dev)
            r = torch.sqrt(math_utils.sample_uniform(obj_min_dist ** 2, obj_max_dist ** 2, (n,), device=dev))
            cx = base_xy[0] + r * torch.cos(ang)
            cy = base_xy[1] + r * torch.sin(ang)
            ok = torch.ones((n,), dtype=torch.bool, device=dev)
            for _a, (bx, by), yaw in box_pose:
                ok &= _box_gap(cx, cy, bx, by, yaw, hx, hy) >= box_clear
            for qx, qy in placed:
                ok &= torch.sqrt((cx - qx) ** 2 + (cy - qy) ** 2) >= min_sep
            take = ok & (~done)
            px = torch.where(take, cx, px)
            py = torch.where(take, cy, py)
            done |= take
            if bool(done.all()):
                break
            # 전량 실패해도 좌표가 비지 않게 마지막 후보를 보관한다
            px = torch.where(done, px, cx)
            py = torch.where(done, py, cy)
        if not bool(done.all()):
            # 조용히 넘기지 않는다 — 조작자가 R로 건너뛸 수 있게 로그를 남긴다
            print(f"[lang] ⚠ 거부 샘플링 실패 {oname} — 겹칠 수 있으니 이 ep는 건너뛸 것", flush=True)
        default = asset.data.default_root_state[env_ids].clone()
        pos = torch.stack([px, py, torch.full((n,), obj_z, device=dev)], dim=-1)
        asset.write_root_pose_to_sim(torch.cat([pos + org, default[:, 3:7]], dim=-1), env_ids=env_ids)
        asset.write_root_velocity_to_sim(torch.zeros((n, 6), device=dev), env_ids=env_ids)
        placed.append((px, py))

    # ── 3) 주차 — 쓰지 않는 물체·박스는 화각 밖 + 매트 아래로 ──
    #   간격을 두고 늘어놓는다(한 점에 겹쳐 쌓으면 물리 해석기가 폭발한다).
    park = [o for o in all_objs if o not in use_objs] + [b for b in all_boxes if b not in use_boxes]
    for i, name in enumerate(park):
        asset: RigidObject = env.scene[name]
        default = asset.data.default_root_state[env_ids].clone()
        pos = torch.tensor([park_xy[0] - 0.06 * i, park_xy[1], -0.30], device=dev).repeat(n, 1)
        asset.write_root_pose_to_sim(torch.cat([pos + org, default[:, 3:7]], dim=-1), env_ids=env_ids)
        asset.write_root_velocity_to_sim(torch.zeros((n, 6), device=dev), env_ids=env_ids)
