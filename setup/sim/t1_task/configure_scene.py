"""blocktask 씬을 '조건 프리셋'으로 설정 — OOD 축을 하나씩만 바꾸는 통제 실험용.

배경(2026-08-06): 기존 sweep은 모든 조건을 전체 랜덤(-DR) 위에서 측정해, 축을 바꿔도
SR이 45%에서 움직이지 않았다(베이스 랜덤화가 신호를 덮음). 축별 기여를 분리하려면
**기준 조건(ref)을 고정해두고 한 번에 한 축만** 켜야 한다.

설계 원칙
  · **모든 조건을 -DR-Eval(dr 모드)에서 실행** — 씬 에셋(sky_light 등)을 동일하게 유지하고,
    바뀌는 것은 오직 '이벤트 랜덤화'뿐이게 한다.
  · 끄는 방법은 항목을 삭제하지 않고 **범위를 0폭으로** 만들거나 None 처리 → 씬 구조 불변.
  · 박스 고정 위치는 원래 기본값(r=0.266, angle=-0.97)을 재현 — 블록 각도범위(-0.7~1.25)
    밖이라 **블록-박스 겹침이 발생하지 않는다**(겹침 12.4% 아티팩트 회피).

일반화 평가 축 추가(2026-08-11, generalization_eval_plan.md):
  물체 색상(yellow/white) · 형상·크기(small/large/sphere/cylinder/tall) ·
  박스 색상(gray/brown) · 시각적 방해물(distractor).
  프리셋을 튜플에서 **딕셔너리 병합**으로 바꿨다 — 축이 늘어도 시그니처가 길어지지 않는다.
  기존 11개 프리셋은 리팩터 전후 출력이 md5까지 동일함을 확인했다.

사용: python3 configure_scene.py <cfg경로> <프리셋>
      python3 configure_scene.py --list        # 프리셋 목록
"""
import re
import sys

# 프리셋은 **기본값에서 바뀌는 항목만** 적는다(딕셔너리 병합). 축이 늘어나도 튜플이
# 길어지지 않고, 어떤 조건이 무엇을 바꾸는지가 한눈에 보인다.
DEFAULT = dict(block="train", box="fixed", phys=False, light=False,
               color="red", shape="cube", box_color="black", distractor=None)

PRESETS = {
    # ── 기존 축 (v3 평가) ────────────────────────────────
    "ref":          {},                                   # 전부 기본값 = 비교의 원점
    "pos_ood":      {"block": "ood"},
    "box_rand":     {"box": "train"},
    "box_ood":      {"box": "ood"},
    "phys_dr":      {"phys": True},
    "light_dr":     {"light": True},
    "color_blue":   {"color": "blue"},
    "color_green":  {"color": "green"},
    # 학습 분포 그대로(= 배포 현실). 목표 'train SR ≥80%' 판정은 이 조건으로 한다.
    "full":         {"box": "train", "phys": True, "light": True},
    # 진단용(2026-08-06): box_rand의 −40%p가 '위치' 때문인지 '회전(yaw)' 때문인지 분해
    "box_pos_only": {"box": "pos_only"},
    "box_yaw_only": {"box": "yaw_only"},

    # ── 일반화 평가 축 (2026-08-11 추가, generalization_eval_plan.md) ──
    # 색상 극단. white는 배경과 유사해 검출 난이도가 가장 높다.
    "color_yellow": {"color": "yellow"},
    "color_white":  {"color": "white"},
    # 물체 형상·크기. ⚠ 구·원기둥은 놓은 뒤 굴러 경계를 벗어나면 성공 판정이 오표기될 수
    # 있어 영상 전수 확인이 필요하다(계획서 §3-4).
    "obj_small":    {"shape": "small"},
    "obj_large":    {"shape": "large"},
    "obj_sphere":   {"shape": "sphere"},
    "obj_cylinder": {"shape": "cylinder"},
    "obj_tall":     {"shape": "tall"},
    # 씬 외형
    "box_gray":     {"box_color": "gray"},
    "box_brown":    {"box_color": "brown"},
    # 시각적 방해물. ⚠ 빨강 계열 금지 — 분석 스크립트가 빨간 픽셀로 타깃을 찾는다.
    "dist_blue_cube": {"distractor": ["blue_cube"]},
    "dist_green_cyl": {"distractor": ["green_cyl"]},
    "dist_two":       {"distractor": ["blue_cube", "green_cyl"]},
}


def preset(name):
    assert name in PRESETS, f"알 수 없는 프리셋: {name} (가능: {sorted(PRESETS)})"
    return {**DEFAULT, **PRESETS[name]}


BLOCK = {  # (min, max, angle_range)
    "train": ("0.16", "0.34", "(-0.7, 1.25)"),
    "ood":   ("0.12", "0.38", "(-1.0, 1.55)"),
}
BOX = {  # (min_dist, max_dist, angle_range, yaw_range)
    # 고정: 원래 기본 박스 위치 재현 — 블록 스폰 각도범위 밖이라 겹침 없음
    "fixed": ("0.266", "0.266", "(-0.97, -0.97)", "(0.0, 0.0)"),
    "train": ("0.28",  "0.34",  "(-1.15, 1.15)",  "(-3.14159, 3.14159)"),
    "ood":   ("0.24",  "0.38",  "(-1.45, 1.45)",  "(-3.14159, 3.14159)"),
    # 진단용: 학습범위 위치 랜덤 + yaw만 고정
    "pos_only": ("0.28", "0.34", "(-1.15, 1.15)", "(0.0, 0.0)"),
    # 진단용: 위치는 ref와 동일 고정 + yaw만 학습범위 랜덤
    "yaw_only": ("0.266", "0.266", "(-0.97, -0.97)", "(-3.14159, 3.14159)"),
}
COLOR = {"red": "(0.9, 0.1, 0.1)", "blue": "(0.1, 0.1, 0.9)", "green": "(0.15, 0.6, 0.15)",
         "yellow": "(0.9, 0.85, 0.1)",
         # 배경(밝은 회색)과 유사 → 검출 난이도 최대. 일반화 평가의 극단 조건.
         "white": "(0.9, 0.9, 0.9)"}
BOX_COLOR = {"black": "(0.03, 0.03, 0.03)", "gray": "(0.45, 0.45, 0.45)", "brown": "(0.35, 0.22, 0.12)"}
# 물체 형상·크기. CuboidCfg를 다른 spawn 타입으로 갈아끼운다.
# 판정 경계(rack_local_*)는 그대로이므로 물체가 커지면 경계를 넘기 쉬워진다는 점에 유의.
# 방해물 정의: (색, 형상). ⚠ 빨강 계열 금지 — 분석 스크립트가 빨간 픽셀로 타깃을 찾는다.
DISTRACTOR = {"blue_cube": ("blue", "cube"), "green_cyl": ("green", "cylinder")}
SHAPE = {
    "cube":     ("CuboidCfg",   "size=(0.02, 0.02, 0.02)"),
    "small":    ("CuboidCfg",   "size=(0.015, 0.015, 0.015)"),
    "large":    ("CuboidCfg",   "size=(0.028, 0.028, 0.028)"),
    "tall":     ("CuboidCfg",   "size=(0.02, 0.02, 0.035)"),
    "sphere":   ("SphereCfg",   "radius=0.01"),
    "cylinder": ("CylinderCfg", "radius=0.01, height=0.02"),
}


def edit_block(s, mode):
    mn, mx, ang = BLOCK[mode]
    s = re.sub(r"^BLOCK_REACH_MIN_DIST = [0-9.]+", f"BLOCK_REACH_MIN_DIST = {mn}", s, flags=re.M)
    s = re.sub(r"^BLOCK_REACH_MAX_DIST = [0-9.]+", f"BLOCK_REACH_MAX_DIST = {mx}", s, flags=re.M)
    s = re.sub(r"^BLOCK_REACH_ANGLE_RANGE = \([^)]*\)", f"BLOCK_REACH_ANGLE_RANGE = {ang}", s, flags=re.M)
    return s


def edit_box(s, mode):
    mn, mx, ang, yaw = BOX[mode]
    m = re.search(r"reset_basket_random\s*=\s*EventTerm\((.*?)\n    \)", s, re.S)
    assert m, "reset_basket_random 블록 없음 — 씬이 v3 버전이 아님"
    blk = m.group(0)
    new = re.sub(r'("min_dist":\s*)[0-9.]+', r"\g<1>" + mn, blk)
    new = re.sub(r'("max_dist":\s*)[0-9.]+', r"\g<1>" + mx, new)
    new = re.sub(r'("angle_range":\s*)\([^)]*\)', r"\g<1>" + ang, new)
    new = re.sub(r'("yaw_range":\s*)\([^)]*\)', r"\g<1>" + yaw, new)
    return s.replace(blk, new)


def edit_phys(s, on):
    # 끌 때는 항목을 지우지 않고 범위를 0폭(기본값)으로 → 씬 구조 불변
    fr = ("(0.56, 1.04)", "(0.42, 0.78)") if on else ("(0.8, 0.8)", "(0.6, 0.6)")
    ms = "(0.5, 1.5)" if on else "(1.0, 1.0)"
    s = re.sub(r'("static_friction_range":\s*)\([^)]*\)', r"\g<1>" + fr[0], s)
    s = re.sub(r'("dynamic_friction_range":\s*)\([^)]*\)', r"\g<1>" + fr[1], s)
    s = re.sub(r'("mass_distribution_params":\s*)\([^)]*\)', r"\g<1>" + ms, s)
    return s


def edit_light(s, on):
    # sky light 랜덤화는 텍스처까지 바뀌어 범위로 못 끄므로 term 자체를 None 처리(기존 패턴과 동일)
    if on:
        return s.replace("    reset_sky_light = None\n", "")
    if re.search(r"^    reset_sky_light = None$", s, re.M):
        return s
    m = re.search(r"    reset_sky_light\s*=\s*EventTerm\(.*?\n    \)\n", s, re.S)
    assert m, "reset_sky_light 블록 없음"
    return s.replace(m.group(0), "    reset_sky_light = None\n")


def edit_color(s, c):
    return re.sub(r"diffuse_color=\(0\.9, 0\.1, 0\.1\)", f"diffuse_color={COLOR[c]}", s)


def edit_box_color(s, c):
    # 박스 기본색 (0.03, 0.03, 0.03). 블록 색과 값이 겹치지 않아 안전하게 치환된다.
    return re.sub(r"diffuse_color=\(0\.03, 0\.03, 0\.03\)", f"diffuse_color={BOX_COLOR[c]}", s)


def edit_shape(s, sh):
    """블록의 spawn 타입·치수를 바꾼다 (CuboidCfg → SphereCfg/CylinderCfg 등).

    ⚠️ 성공 판정 경계(rack_local_*)는 그대로다. 물체가 커지면 경계를 넘기 쉬워지고,
       구·원기둥은 놓은 뒤 굴러 나가 **오표기**될 수 있다 → 영상 전수 확인이 필요하다.
    ⚠️ 그리퍼 접촉 판정(force_threshold=2)이 작은 물체에서 안 걸릴 수 있다 → obj_small은
       5ep 예비 확인 후 본 측정을 한다.
    """
    if sh == "cube":
        return s
    cfg, dims = SHAPE[sh]
    m = re.search(r"spawn=sim_utils\.CuboidCfg\(\n\s*size=BLOCK_SIZE,", s)
    assert m, "block_base의 CuboidCfg(size=BLOCK_SIZE) 블록 없음 — 씬 구조가 바뀌었다"
    return s.replace(m.group(0), f"spawn=sim_utils.{cfg}(\n        {dims},")


def edit_distractor(s, names):
    """작업과 무관한 물체를 씬에 추가한다 (시각 grounding 평가).

    성공 판정은 `vials=["block_red"]`만 추적하므로, 모델이 방해물을 집어 박스에 넣어도
    성공으로 잡히지 않는다(의도된 동작).

    ⚠️ 빨강 계열은 넣지 않는다 — 분석 스크립트가 빨간 픽셀로 타깃을 찾기 때문에
       모델뿐 아니라 **계측까지** 교란된다.

    배치는 `reset_distractors`(거부 샘플링)로 한다. 처음엔 `reset_prop_random_reach`로
    독립 추첨했는데 실제 캡처에서 **방해물끼리 붙거나 타깃을 가리는 배치**가 잦아
    (3ep 중 2ep) 조건이 무의미해졌다. 이 term은 타깃·박스의 현재 위치를 읽으므로
    **DR cfg의 `reset_basket_random` 다음**에 삽입해야 한다.
    """
    if not names:
        return s
    assert "block_red = block_base.replace()" in s, "block_red 정의 없음"
    objs = []
    for i, n in enumerate(names):
        color, shape = DISTRACTOR[n]
        cfg, dims = SHAPE[shape]
        objs.append(f'''
    {n} = block_base.replace()
    {n}.prim_path = "{{ENV_REGEX_NS}}/Distractor_{i}"
    {n}.spawn = sim_utils.{cfg}(
        {dims},
        mass_props=sim_utils.MassPropertiesCfg(mass=BLOCK_MASS),
        rigid_props=sim_utils.RigidBodyPropertiesCfg(
            solver_position_iteration_count=8, solver_velocity_iteration_count=4),
        collision_props=sim_utils.CollisionPropertiesCfg(),
        visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color={COLOR[color]}),
    )''')
    # (1) 씬 정의 — block_red 선언 뒤
    anchor = re.search(r"(    block_red\.spawn\.visual_material = sim_utils\.PreviewSurfaceCfg\(\n"
                       r"        diffuse_color=[^\n]*\n    \)\n)", s)
    assert anchor, "block_red visual_material 블록 없음"
    s = s.replace(anchor.group(1), anchor.group(1) + "".join(objs) + "\n")

    # (2) import — reset_distractors 추가
    s = s.replace("    reset_prop_random_reach,\n",
                  "    reset_prop_random_reach,\n    reset_distractors,\n", 1)

    # (3) 리셋 이벤트 — **reset_basket_random 다음**(박스 위치가 정해진 뒤)
    m = re.search(r"(    reset_basket_random = EventTerm\(.*?\n    \)\n)", s, re.S)
    assert m, "reset_basket_random 블록 없음 — 씬이 v3 버전이 아님"
    evt = f'''
    reset_distractor_objs = EventTerm(
        func=reset_distractors,
        mode="reset",
        params={{
            "names": {names!r},
            "avoid": ["block_red", "basket_black"],
            "base_xy": BLOCK_REACH_BASE_XY,
            "min_dist": BLOCK_REACH_MIN_DIST,
            "max_dist": BLOCK_REACH_MAX_DIST,
            "angle_range": BLOCK_REACH_ANGLE_RANGE,
            "z": BLOCK_SPAWN_Z,
            "min_sep": 0.08,
        }},
    )
'''
    return s.replace(m.group(1), m.group(1) + evt)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--list":
        for n in PRESETS:
            chg = {k: v for k, v in preset(n).items() if v != DEFAULT[k]}
            print(f"  {n:<16} " + (", ".join(f"{k}={v}" for k, v in chg.items()) or "기본값(ref)"))
        return
    path, name = sys.argv[1], sys.argv[2]
    c = preset(name)
    s = open(path).read()
    s = edit_block(s, c["block"])
    s = edit_box(s, c["box"])
    s = edit_phys(s, c["phys"])
    s = edit_light(s, c["light"])
    if c["shape"] != "cube":
        s = edit_shape(s, c["shape"])
    if c["color"] != "red":
        s = edit_color(s, c["color"])
    if c["box_color"] != "black":
        s = edit_box_color(s, c["box_color"])
    if c["distractor"]:
        s = edit_distractor(s, c["distractor"])
    open(path, "w").write(s)
    chg = {k: v for k, v in c.items() if v != DEFAULT[k]}
    print(f"[scene] {name}: " + (", ".join(f"{k}={v}" for k, v in chg.items()) or "기본값(ref)"))


if __name__ == "__main__":
    main()
