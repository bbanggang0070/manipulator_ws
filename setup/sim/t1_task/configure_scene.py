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
               color="red", shape="cube", box_color="black", distractor=None,
               lang=False, box_scale=0.85)

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
    "obj_eraser":   {"shape": "eraser"},
    "obj_tall":     {"shape": "tall"},
    # 씬 외형
    "box_gray":     {"box_color": "gray"},
    "box_brown":    {"box_color": "brown"},
    "box_blue":     {"box_color": "blue"},
    # 시각적 방해물. ⚠ 빨강 계열 금지 — 분석 스크립트가 빨간 픽셀로 타깃을 찾는다.
    "dist_blue_cube": {"distractor": ["blue_cube"]},
    "dist_green_cyl": {"distractor": ["green_cyl"]},
    "dist_two":       {"distractor": ["blue_cube", "green_cyl"]},

    # 박스 축소만 떼어 재는 축(2026-09-14). 언어 씬은 물체·리셋까지 바꾸므로
    # "축소가 성공률을 떨어뜨리는가"를 그것만으로 잴 수 없다 — 한 번에 한 축만.
    #   실측(v4_200@86k · 고정 패널 30ep): 0.85 기준 30/30 → **0.70에서 26/30(−4)**.
    #   실패 4건 전부 900스텝 타임아웃이고 네 배치에 하나씩 흩어졌다 — 특정 기하가 불가능한 게
    #   아니라 배치 여유가 줄어 가끔 못 넣는다는 뜻이다(성공 경계 ±42 → ±35mm).
    #   −2 합격선을 못 넘어 0.80을 다시 잰다.
    "box_small":    {"box_scale": 0.7},
    "box_080":      {"box_scale": 0.8},

    # ── 언어 조건화 (2026-09-14, language_conditioning_sim_plan.md) ──
    # 물체 카탈로그 10종 + 박스 4색을 스폰하고, 배치는 계획표(LANG_PLAN)가 정한다.
    # 배포 체제와 맞추려면 `full+lang`으로 조합한다 — 단독으로 쓰면 물리·조명 DR이 꺼진다.
    "lang":         {"lang": True},
}


def preset(name):
    """프리셋 이름. `a+b`로 조합하면 왼쪽부터 순서대로 덮어쓴다.

    조합이 필요한 이유:
      단일 프리셋은 전부 DEFAULT(박스 고정·물리 DR 없음)에서 출발한다. 그래서
      `color_white` 같은 외형 축을 그대로 돌리면 **박스가 고정된 v2 시절 씬**에서
      일반화를 재게 되고, 배포 조건인 `full`(박스 랜덤 + 물리/조명 DR)과 비교할 수 없다.
      `full+color_white`로 조합하면 씬 체제를 배포와 맞춘 채 색만 바꾼다.
    """
    out = dict(DEFAULT)
    for part in name.split("+"):
        assert part in PRESETS, f"알 수 없는 프리셋: {part} (가능: {sorted(PRESETS)})"
        out.update(PRESETS[part])
    return out


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
BOX_COLOR = {"black": "(0.03, 0.03, 0.03)", "gray": "(0.45, 0.45, 0.45)", "brown": "(0.35, 0.22, 0.12)",
             # 파랑: 빨간 타깃과 분리가 최대이고 계측에도 안전하다.
             # ⚠ 따뜻한 계열(빨강·주황·노랑)은 금지 — 분석 스크립트가 빨간 픽셀로 타깃을
             #   찾으므로 붉은 박스는 모델뿐 아니라 **계측까지** 교란한다.
             "blue": "(0.10, 0.25, 0.65)",
             # 언어 조건화 평가 전용 — 학습에 없던 목적지 색(§7-4)
             "white": "(0.92, 0.92, 0.92)"}
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
    # 굴러가는 형상 — edit_shape에서 각감쇠를 함께 넣는다
    "cylinder": ("CylinderCfg", "radius=0.01, height=0.02"),
    # 지우개 40×20×12mm — 폭 20mm는 학습 범위 안이라 잡히지만 길이 40mm 때문에
    # **접근 방향에 따라 잡히고 안 잡힌다**. 정육면체·구엔 없던 축이다.
    # (연필은 제외: 직경 8mm는 접촉 판정이 안 걸릴 수 있고, 길이 150mm는 박스 내부
    #  단변 84mm를 넘어 성공 판정 자체가 안 뜬다.)
    "eraser":   ("CuboidCfg",   "size=(0.04, 0.02, 0.012)"),
}
ROLLING_SHAPES = {"sphere", "cylinder"}

# ── 언어 조건화 수집·평가 씬 (2026-09-14, language_conditioning_sim_plan.md) ──────
# 카탈로그를 **전부 스폰**해 두고, 리셋 때 계획표가 지정한 것만 배치하고 나머지는 주차한다.
# 색을 리셋마다 바꾸지 않는 이유: 색은 PreviewSurfaceCfg로 스폰 시 구워지고, 런타임 변경은
# USD 셰이더 경로를 직접 건드려야 해서 **조용히 아무것도 안 바뀔 위험**이 있다.
# 물체마다 prim을 따로 두면 위치 쓰기만으로 끝나고, 그 경로는 reset_distractors에서 검증됐다.
# 큐브 6색은 **색상환을 6등분**한다(빨강·노랑·초록·청록·파랑·보라).
#   처음엔 주황을 넣었으나, 조명 DR(색온도 2500~9500K)의 따뜻한 쪽에서 **주황↔노랑이 붙었다**
#   (2026-09-14 캡처 확인 — 224px로 줄이면 둘 다 노란 덩어리로 보인다).
#   빨강·주황·노랑은 색상환에서 이웃이라 애초에 세 개를 함께 쓰면 안 되는 조합이었다.
#   빠진 주황은 지우개로 옮겼다 — 지우개가 **흰색이라 흰 작업면과 거의 안 갈렸기** 때문이다.
LANG_COLOR = dict(COLOR, cyan="(0.05, 0.65, 0.70)", purple="(0.5, 0.1, 0.75)",
                  orange="(0.95, 0.45, 0.05)", pink="(0.9, 0.4, 0.6)", gray="(0.5, 0.5, 0.5)",
                  # 마커 몸통: 검정 박스(0.03)와 구분되게 어두운 회청색으로 둔다
                  marker="(0.20, 0.20, 0.26)")

# 계획표 이름 → (씬 엔티티, spawn 종류, 치수, 색, 굴러가는가, 초기 자세 quat|None)
#   red_cube는 기존 block_red를 그대로 쓴다 — 성공 판정·물리 DR·scenes.csv가 이미 그 이름을 참조한다.
#
#   ⚠️ 마커는 **프리미티브 원기둥**이다. 처음엔 YCB `040_large_marker.usd`를 쓰려 했으나
#      Isaac 자산이 실패했다(2026-09-14 실측):
#        RuntimeError: Failed to find a rigid body when resolving '.../ObjMarker'
#      `Axis_Aligned` 세트는 RigidBodyAPI가 없고, 물리가 붙은 `Axis_Aligned_Physics`에는
#      large_marker가 없다(404). 우리가 필요한 성질은 "색이 아닌 이름 + 길쭉한 형상"뿐이라
#      원기둥으로 충분하고, 덕분에 **Isaac 기동 때 네트워크 의존이 사라진다**(로컬·5090 동일 자산).
#   Ø13×70mm — 직경 8mm 이하는 접촉 판정(force_threshold=2)이 안 걸릴 수 있다.
#   처음 Ø11로 뒀다가 파지 폭 합격선(12~25mm) 아래라 13mm로 올렸다(2026-09-14 실측).
#   눕혀 놓는다(y축 90° 회전). 세워 두면 넘어지고, 파지 문제가 '집기'가 아니라 '세우기'가 된다.
_LIE_FLAT = "(0.7071, 0.0, 0.7071, 0.0)"   # (w, x, y, z) — 원기둥 축 z → x
LANG_OBJECTS = {
    "red_cube":    ("block_red",  "Cuboid",   "size=(0.02, 0.02, 0.02)",      "red",    False, None),
    "blue_cube":   ("obj_blue",   "Cuboid",   "size=(0.02, 0.02, 0.02)",      "blue",   False, None),
    "yellow_cube": ("obj_yellow", "Cuboid",   "size=(0.02, 0.02, 0.02)",      "yellow", False, None),
    "green_cube":  ("obj_green",  "Cuboid",   "size=(0.02, 0.02, 0.02)",      "green",  False, None),
    "cyan_cube":   ("obj_cyan",   "Cuboid",   "size=(0.02, 0.02, 0.02)",      "cyan",   False, None),
    "purple_cube": ("obj_purple", "Cuboid",   "size=(0.02, 0.02, 0.02)",      "purple", False, None),
    # 지우개는 주황. 흰색이면 흰 작업면과 대비가 거의 없어 **정책이 볼 수가 없다**(캡처 확인).
    "eraser":      ("obj_eraser", "Cuboid",   "size=(0.04, 0.02, 0.012)",     "orange", False, None),
    "marker":      ("obj_marker", "Cylinder", "radius=0.0065, height=0.07",   "marker", True,  _LIE_FLAT),
    # ⚠️ 아래 둘은 **평가 전용**. 수집 계획표에 들어가면 미학습 색 일반화가 통째로 무효가 된다.
    "white_cube":  ("obj_white",  "Cuboid",   "size=(0.02, 0.02, 0.02)",      "white",  False, None),
    "pink_cube":   ("obj_pink",   "Cuboid",   "size=(0.02, 0.02, 0.02)",      "pink",   False, None),
}
# 박스 색 → 씬 엔티티 이름. black은 기존 basket_black.
LANG_BOXES = {"black": "basket_black", "brown": "box_brown", "gray": "box_gray",
              "white": "box_white"}   # white는 평가 전용
# 박스 배율 — **기존 0.85 그대로 둔다**(2026-09-14 측정으로 확정).
#   축소를 검토한 이유는 물체를 8개 놓으려던 설계 때문이었다. 4개로 줄인 뒤 전제를 다시 재보니
#   **0.85에서도 물체 4개 + 박스 2개가 10cm 간격으로 100% 배치된다**(거부 표집 2,000회).
#   줄일 이유가 없었고, 줄이면 성공률만 깎였다 — 기존 모델·고정 패널 30ep 실측:
#       0.85 → 30/30   ·   0.80 → 28/30   ·   0.70 → 26/30 (실패 전부 900스텝 타임아웃)
#   0.70의 실패 4건은 네 배치에 흩어졌고(여유 부족), 0.80의 2건은 근접 배치 #2에 몰렸다.
#   **성공 경계(rack_local_*)도 기존 값(±42/±85/68mm)을 그대로 쓴다.**
LANG_BOX_SCALE = 0.85
# 배치 규칙 (거부 표집 실측: 물체 4개는 12cm 간격에서도 99.8%, 여유를 두고 10cm)
LANG_MIN_SEP = 0.10
# 박스 각도 범위를 기존 (-1.15, 1.15)에서 **오른쪽만 잘라** 좁힌다.
#   측정(probe_box_visibility.py, 80회): 박스가 top 카메라에 안 잡히거나 크게 잘리는 구간이
#   θ < -0.8에 몰려 있다 — 비가시 2/80, "크게 잘림(<1500px)" 19/80(24%)이 전부 그 대역이다.
#   θ ≥ -0.8로 자르면 **비가시 0, 크게 잘림 8%**로 떨어지고 호는 15%만 잃는다.
#   목적지를 색으로 지정하는 설계에서 **박스가 안 보이면 어떤 정책도 고를 수 없다** —
#   평가 B에서 타깃이 안 잡히는 배치를 분모에서 뺐던 것과 같은 이유이고, 이번엔 매 에피소드
#   등장하므로 범위 자체를 좁히는 편이 맞다.
LANG_BOX_ANGLE = (-0.8, 1.15)
LANG_BOX_ANG_SEP = 0.8
LANG_BOX_CLEAR = 0.03      # 물체-박스는 중심거리가 아니라 **사각형 간격**으로 잰다
LANG_PARK_XY = (-0.40, 0.45)   # 카메라 화각 밖. 검증 3에서 눈으로 확인한다


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
    s = s.replace(m.group(0), f"spawn=sim_utils.{cfg}(\n        {dims},")

    # 구·원기둥은 그리퍼가 스치기만 해도 굴러 달아난다(2026-08-12 실측). 그러면 측정 대상이
    # '형상 일반화'가 아니라 '굴러가는 물체 추격'이 돼 버린다 — 축을 분리하려면 구름을 막아야 한다.
    # 이 저장소에 이미 같은 처방이 있다: vial(원기둥)도 angular_damping=100.0으로 세운다.
    # 마찰을 올리지 않고 각감쇠를 쓰는 이유: phys DR의 randomize_block_friction이 매 reset마다
    # 마찰을 덮어써서, 마찰로 막으면 물리 DR을 켠 조건(full+obj_sphere)에서 무효가 된다.
    if sh in ROLLING_SHAPES:
        i = s.index("block_base = RigidObjectCfg(")
        pat = ("rigid_props=sim_utils.RigidBodyPropertiesCfg(\n"
               "            solver_position_iteration_count=8,\n"
               "            solver_velocity_iteration_count=4,\n"
               "        ),")
        j = s.index(pat, i)          # block_base의 것만 (같은 패턴이 paper_box_base에도 있다)
        s = s[:j] + pat.replace(
            "solver_velocity_iteration_count=4,",
            "solver_velocity_iteration_count=4,\n            angular_damping=100.0,",
        ) + s[j + len(pat):]
    return s


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


def edit_box_scale(s, scale):
    """박스를 축소하고 **성공 경계를 같은 배율로 환산**한다.

    경계를 함께 바꾸지 않으면 박스 밖에 놓인 것도 성공으로 잡힌다 — 축소의 가장 큰 함정이다.
    기준값(±0.042/±0.085/0.068)은 0.85배 박스에 맞춰 잡힌 값이다.
    """
    assert "scale=(0.85, 0.85, 0.85)," in s, "paper_box_base scale 줄 없음"
    s = s.replace("scale=(0.85, 0.85, 0.85),", f"scale=({scale}, {scale}, {scale}),", 1)
    k = scale / 0.85
    for key, base in (("rack_local_x_min", -0.042), ("rack_local_x_max", 0.042),
                      ("rack_local_y_min", -0.085), ("rack_local_y_max", 0.085),
                      ("rack_local_z_max", 0.068)):
        pat = key + r"=-?[0-9.]+"
        assert re.search(pat, s), f"{key} 없음"
        s = re.sub(pat, f"{key}={round(base * k, 4)}", s)
    return s


def _obj_spawn_block(name):
    """카탈로그 한 항목의 RigidObjectCfg 코드를 만든다."""
    entity, kind, dims, color, rolling, rot = LANG_OBJECTS[name]
    roll = ("\n            angular_damping=100.0," if rolling else "")
    spawn = (f"sim_utils.{kind}Cfg(\n"
             f"        {dims},\n"
             "        mass_props=sim_utils.MassPropertiesCfg(mass=BLOCK_MASS),\n"
             "        rigid_props=sim_utils.RigidBodyPropertiesCfg(\n"
             "            solver_position_iteration_count=8,\n"
             f"            solver_velocity_iteration_count=4,{roll}\n"
             "        ),\n"
             "        collision_props=sim_utils.CollisionPropertiesCfg(),\n"
             f"        visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color={LANG_COLOR[color]}),\n"
             "    )")
    prim = "".join(w.capitalize() for w in entity.split("_"))
    out = (f"\n    {entity} = block_base.replace()\n"
           f'    {entity}.prim_path = "{{ENV_REGEX_NS}}/{prim}"\n'
           f"    {entity}.spawn = {spawn}\n")
    if rot:
        # 눕혀 놓는다. reset_lang_scene이 default_root_state의 쿼터니언을 그대로 쓰므로
        # 여기서 정한 자세가 매 리셋 재현된다.
        out += f"    {entity}.init_state.rot = {rot}\n"
    return out


def edit_lang_scene(s):
    """언어 조건화 씬 — 물체 카탈로그와 박스 3~4색을 스폰하고, 배치를 계획표에 맡긴다.

    바꾸는 것 여섯 가지:
      ① 물체 prim 9개 추가 (block_red를 red_cube로 재사용)
      ② 박스 prim 3개 추가 + 박스 축소(0.85 → 0.7)
      ③ 성공 경계를 축소 배율에 맞춰 갱신  ← 빠뜨리면 박스 밖도 성공으로 잡힌다
      ④ 판정 대상(물체·박스)을 EVAL_TARGET/EVAL_DEST로 전환
      ⑤ 리셋을 reset_lang_scene 하나로 교체(기존 물체·박스 리셋은 해제)
      ⑥ 물리 DR을 카탈로그 전체에 적용  ← 빨강만 흔들리면 물체 정체가 물리 단서와 상관된다
    """
    # ── ① 물체: block_red 선언 뒤에 나머지를 얹는다 ──
    anchor = re.search(r"(    block_red\.init_state\.pos = \([^\n]*\)\n)", s)
    assert anchor, "block_red init_state 블록 없음 — 씬 구조가 바뀌었다"
    objs = "".join(_obj_spawn_block(n) for n in LANG_OBJECTS if n != "red_cube")
    s = s.replace(anchor.group(1), anchor.group(1) + objs)

    # ── ② 박스: basket_black 뒤에 색별 복제 ──
    banchor = re.search(r"(    basket_black\.init_state\.pos = \([^\n]*\)\n)", s)
    assert banchor, "basket_black init_state 블록 없음"
    boxes = ""
    for color, entity in LANG_BOXES.items():
        if color == "black":
            continue
        prim = "".join(w.capitalize() for w in entity.split("_"))
        boxes += (f"\n    {entity} = paper_box_base.replace()\n"
                  f'    {entity}.prim_path = "{{ENV_REGEX_NS}}/{prim}"\n'
                  f"    {entity}.spawn = paper_box_base.spawn.replace(\n"
                  f"        visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color={BOX_COLOR[color]}),\n"
                  f"    )\n"
                  f"    {entity}.init_state.pos = (0.10, -0.22, BASKET_SPAWN_Z)\n")
    s = s.replace(banchor.group(1), banchor.group(1) + boxes)

    if LANG_BOX_SCALE != 0.85:
        s = edit_box_scale(s, LANG_BOX_SCALE)

    # ── ④ 판정 대상 전환. 이름은 계획표와 같은 것을 쓰고(red_cube), 내부에서 prim으로 옮긴다 ──
    lookup = ("LANG_OBJ_PRIM = " + repr({k: v[0] for k, v in LANG_OBJECTS.items()}) + "\n"
              "LANG_BOX_PRIM = " + repr(dict(LANG_BOXES)) + "\n"
              '_EVAL_TARGET = LANG_OBJ_PRIM.get(os.environ.get("EVAL_TARGET", ""), "block_red")\n'
              '_EVAL_DEST = LANG_BOX_PRIM.get(os.environ.get("EVAL_DEST", ""), "basket_black")\n\n\n')
    marker = "def _block_place_params():"
    assert s.count(marker) == 1
    s = s.replace(marker, lookup + marker, 1)
    s = s.replace('vials=["block_red"],', "vials=[_EVAL_TARGET],")
    s = s.replace('rack_name="basket_black",', "rack_name=_EVAL_DEST,")
    s = s.replace('"vials": ["block_red"],', '"vials": [_EVAL_TARGET],')

    # ── ⑤ 리셋 교체 ──
    s = s.replace("    reset_prop_random_reach,\n",
                  "    reset_prop_random_reach,\n    reset_lang_scene,\n", 1)
    m = re.search(r"    reset_basket_random = EventTerm\(.*?\n    \)\n", s, re.S)
    assert m, "reset_basket_random 블록 없음 — 씬이 v3 버전이 아님"
    hx = round(0.10 * LANG_BOX_SCALE / 2, 4)
    hy = round(0.20 * LANG_BOX_SCALE / 2, 4)
    term = (
        "    # 물체·박스를 계획표대로 배치하고 나머지는 주차한다 (언어 조건화 수집·평가).\n"
        "    #   기존 reset_block_position·reset_basket_random을 이 term이 대신하므로 해제한다.\n"
        "    #   ⚠ 이 term은 박스를 먼저 놓고 물체가 그것을 피하게 한다 — 순서가 곧 정확성이다.\n"
        "    reset_block_position = None\n"
        "    reset_basket_random = EventTerm(\n"
        "        func=reset_lang_scene,\n"
        '        mode="reset",\n'
        "        params={\n"
        '            "plan_csv": os.environ.get("LANG_PLAN", ""),\n'
        '            "objects": LANG_OBJ_PRIM,\n'
        '            "boxes": LANG_BOX_PRIM,\n'
        f'            "park_xy": {LANG_PARK_XY},\n'
        '            "base_xy": BLOCK_REACH_BASE_XY,\n'
        '            "obj_min_dist": BLOCK_REACH_MIN_DIST,\n'
        '            "obj_max_dist": BLOCK_REACH_MAX_DIST,\n'
        '            "obj_angle_range": BLOCK_REACH_ANGLE_RANGE,\n'
        '            "obj_z": BLOCK_SPAWN_Z,\n'
        '            "box_min_dist": 0.28,\n'
        '            "box_max_dist": 0.34,\n'
        f'            "box_angle_range": {LANG_BOX_ANGLE},\n'
        '            "box_yaw_range": (-3.14159, 3.14159),\n'
        '            "box_z": BASKET_SPAWN_Z,\n'
        f'            "box_min_ang_sep": {LANG_BOX_ANG_SEP},\n'
        f'            "box_half_extent": ({hx}, {hy}),\n'
        f'            "box_clear": {LANG_BOX_CLEAR},\n'
        f'            "min_sep": {LANG_MIN_SEP},\n'
        "        },\n"
        "    )\n")
    s = s.replace(m.group(0), term)

    # ── ⑥ 물리 DR을 카탈로그 전체로 ──
    mm = re.search(r"    randomize_block_mass = EventTerm\(.*?\n    \)\n", s, re.S)
    assert mm, "randomize_block_mass 블록 없음"
    extra = ""
    for name, spec in LANG_OBJECTS.items():
        entity = spec[0]
        if entity == "block_red":
            continue
        extra += (
            f"\n    randomize_{entity}_friction = EventTerm(\n"
            "        func=randomize_rigid_body_material,\n"
            '        mode="reset",\n'
            "        params={\n"
            f'            "asset_cfg": SceneEntityCfg("{entity}"),\n'
            '            "static_friction_range": (0.56, 1.04),\n'
            '            "dynamic_friction_range": (0.42, 0.78),\n'
            '            "restitution_range": (0.0, 0.0),\n'
            '            "num_buckets": 64,\n'
            "        },\n"
            "    )\n"
            f"    randomize_{entity}_mass = EventTerm(\n"
            "        func=randomize_rigid_body_mass,\n"
            '        mode="reset",\n'
            "        params={\n"
            f'            "asset_cfg": SceneEntityCfg("{entity}"),\n'
            '            "mass_distribution_params": (0.5, 1.5),\n'
            '            "operation": "scale",\n'
            '            "distribution": "uniform",\n'
            "        },\n"
            "    )\n")
    s = s.replace(mm.group(0), mm.group(0) + extra)

    # ── ⑦ 평가용 __post_init__의 리셋 덮어쓰기를 막는다 ──
    #   VialsToRackEvalDREnvCfg가 reset_basket_random.func를 reset_box_and_block_clear(또는
    #   EVAL_PANEL=1이면 reset_fixed_panel)로 **다시 지정**한다. 그대로 두면 언어 씬의
    #   reset_lang_scene이 조용히 날아가고, 평가가 물체 하나짜리 옛 씬에서 돌아간다.
    #   ⚠ 이 덮어쓰기는 파일 뒤쪽에 있어 앞에서 무엇을 심든 이긴다 — 반드시 막아야 한다.
    s = "LANG_SCENE = True\n" + s
    blk = re.search(r"(        self\.events\.reset_block_position = None\n"
                    r"        self\.events\.reset_basket_random\.func = reset_box_and_block_clear\n"
                    r"        self\.events\.reset_basket_random\.params = \{.*?\n        \}\n)", s, re.S)
    assert blk, "Eval post_init의 리셋 덮어쓰기 블록을 못 찾았다"
    guarded = "        if not LANG_SCENE:\n" + "".join(
        ("    " + ln if ln.strip() else ln) + "\n" for ln in blk.group(1).rstrip("\n").split("\n"))
    s = s.replace(blk.group(1), guarded)
    # 고정 패널도 같은 이유로 끈다. 언어 평가의 배치 고정은 **같은 계획표 + 같은 seed**로 한다
    # (조합이 같으면 난수 소비 순서가 같아 배치가 재현된다).
    s = s.replace('if os.environ.get("EVAL_PANEL") == "1":',
                  'if os.environ.get("EVAL_PANEL") == "1" and not LANG_SCENE:')
    return s


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
    if c["box_scale"] != 0.85:
        s = edit_box_scale(s, c["box_scale"])
    if c["distractor"]:
        s = edit_distractor(s, c["distractor"])
    # 언어 씬은 물체·박스·리셋을 통째로 갈아끼우므로 **가장 마지막**에 적용한다
    # (앞 단계가 만든 박스 scale·성공 경계를 이 함수가 다시 쓴다).
    if c["lang"]:
        s = edit_lang_scene(s)
    open(path, "w").write(s)
    chg = {k: v for k, v in c.items() if v != DEFAULT[k]}
    print(f"[scene] {name}: " + (", ".join(f"{k}={v}" for k, v in chg.items()) or "기본값(ref)"))


if __name__ == "__main__":
    main()
