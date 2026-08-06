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

사용: python3 configure_scene.py <cfg경로> <프리셋>
"""
import re
import sys

PRESETS = {
    # 이름          블록범위  박스     물리   조명   색
    "ref":         ("train", "fixed", False, False, "red"),
    "pos_ood":     ("ood",   "fixed", False, False, "red"),
    "box_rand":    ("train", "train", False, False, "red"),
    "box_ood":     ("train", "ood",   False, False, "red"),
    "phys_dr":     ("train", "fixed", True,  False, "red"),
    "light_dr":    ("train", "fixed", False, True,  "red"),
    "color_blue":  ("train", "fixed", False, False, "blue"),
    "color_green": ("train", "fixed", False, False, "green"),
    # 학습 분포 그대로(= 배포 현실). 목표 'train SR ≥80%' 판정은 이 조건으로 한다.
    "full":        ("train", "train", True,  True,  "red"),
}

BLOCK = {  # (min, max, angle_range)
    "train": ("0.16", "0.34", "(-0.7, 1.25)"),
    "ood":   ("0.12", "0.38", "(-1.0, 1.55)"),
}
BOX = {  # (min_dist, max_dist, angle_range, yaw_range)
    # 고정: 원래 기본 박스 위치 재현 — 블록 스폰 각도범위 밖이라 겹침 없음
    "fixed": ("0.266", "0.266", "(-0.97, -0.97)", "(0.0, 0.0)"),
    "train": ("0.28",  "0.34",  "(-1.15, 1.15)",  "(-3.14159, 3.14159)"),
    "ood":   ("0.24",  "0.38",  "(-1.45, 1.45)",  "(-3.14159, 3.14159)"),
}
COLOR = {"red": "(0.9, 0.1, 0.1)", "blue": "(0.1, 0.1, 0.9)", "green": "(0.15, 0.6, 0.15)"}


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


def main():
    path, preset = sys.argv[1], sys.argv[2]
    assert preset in PRESETS, f"알 수 없는 프리셋: {preset} (가능: {list(PRESETS)})"
    blk, box, phys, light, color = PRESETS[preset]
    s = open(path).read()
    s = edit_block(s, blk)
    s = edit_box(s, box)
    s = edit_phys(s, phys)
    s = edit_light(s, light)
    if color != "red":
        s = edit_color(s, color)
    open(path, "w").write(s)
    print(f"[scene] {preset}: block={blk} box={box} phys={'on' if phys else 'off'} "
          f"light={'on' if light else 'off'} color={color}")


if __name__ == "__main__":
    main()
