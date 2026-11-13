#!/usr/bin/env python3
"""학습 / 추론 흐름 애니메이션 — groot_n16_architecture 구조도 위에서 데이터가 흐르는 모습.

python3 make_flow_n16.py  →  train_flow_n16.svg, infer_flow_n16.svg, flow_n16.html (같은 폴더)
블록 배치·이름은 make_groot_n16_arch.py 와 같고, 그 위에 SMIL 애니메이션(흐르는 점, 블록 강조)을 얹는다.
모든 애니메이션이 같은 주기(dur=T)를 공유하므로 svg.setCurrentTime(t) 로 어느 순간이든 정확히 재현된다
(flow_n16.html#frame=train@3.5 → 그 순간에 멈춘 화면, GIF 렌더용).
"""
import base64, math, os, random

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 1800, 960
DY = 40                      # 구조도를 아래로 내려 위쪽에 역전파 화살표 길을 만든다
# 캔버스 · DY 는 make_groot_n16_arch.py 와 같다 → 구조도 · 학습 · 추론을 겹쳐 넘겨도 기존 블록 크기 · 위치가 그대로
SANS = "Helvetica, Arial, 'IBM Plex Sans KR', 'Noto Sans CJK KR', sans-serif"
MONO = "Menlo, Consolas, 'Courier New', monospace"
INK, LINE, BOX = "#111", "#555", "#f2f2f2"
GREEN, TRAIN = "#dde9d3", "#f97316"
CYAN, VIOLET, BLUE, GT, RED = "#0ea5e9", "#7c3aed", "#2563eb", "#059669", "#dc2626"

out = []
add = out.append
T = 12.0
HOLES = None                 # MP4 합성용: 리스트이면 영상 칸을 비워 두고 (x, y, w, h, crop) 를 모은다


def img(name):
    with open(os.path.join(HERE, name), "rb") as f:
        return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()


# 학습 그림에서 사이클마다 바뀌는 시연 장면 (학습 데이터셋 에피소드 0 · 6 · 7 · 120 · 250)
SETS = [(0, "Put the yellow straw into the black bin"), (6, "Put the red marker into the white bin"),
        (7, "Put the blue marker into the pink bin"), (120, "Put the toothbrush into the cyan bin"),
        (250, "Put the screwdriver into the white bin")]
CYCLE_LABEL = ["1", "2", "3", "…", "69,000"]


def cyc(k, n=len(SETS)):
    """n 사이클(n×T 초) 중 k 번째 사이클에만 보이는 opacity 애니메이션"""
    if k == 0:
        kt, vs = f"0;{1 / n:.4f}", "1;0"
    elif k == n - 1:
        kt, vs = f"0;{k / n:.4f}", "0;1"
    else:
        kt, vs = f"0;{k / n:.4f};{(k + 1) / n:.4f}", "0;1;0"
    return f'<animate attributeName="opacity" dur="{n * T}s" repeatCount="indefinite" calcMode="discrete" keyTimes="{kt}" values="{vs}"/>'


def instruction(s):
    a, b = s.split(" into ")
    add(f'<text text-anchor="start" dominant-baseline="middle" font-family="{MONO}" font-size="16" fill="{INK}">'
        f'<tspan x="16" y="256">“{a}</tspan><tspan x="16" y="278">into {b}”</tspan></text>')


# ---------------------------------------------------------------- 키프레임
def kf(attr, pts, extra=""):
    pts = sorted(pts)
    if pts[0][0] > 0:
        pts = [(0, pts[0][1])] + pts
    if pts[-1][0] < T:
        pts = pts + [(T, pts[-1][1])]
    kt = ";".join(f"{t / T:.4f}" for t, _ in pts)
    vs = ";".join(str(v) for _, v in pts)
    return f'<animate attributeName="{attr}" dur="{T}s" repeatCount="indefinite" keyTimes="{kt}" values="{vs}" {extra}/>'


def show(t0, t1=None, fade=0.2, hi=1):
    t1 = T - 0.3 if t1 is None else t1
    return kf("opacity", [(0, 0), (max(t0 - 0.001, 0), 0), (t0 + fade, hi), (t1, hi), (min(t1 + fade, T), 0)])


def pulses(times, width=0.5, hi=1):
    pts = [(0, 0)]
    for t in times:
        pts += [(t - 0.001, 0), (t + width * 0.3, hi), (t + width, 0)]
    return kf("opacity", pts)


def dots(path, t0, t1, color, n=3, gap=0.1, r=7):
    for i in range(n):
        a, b = t0 + i * gap, t1 + i * gap
        add(f'<circle r="{r}" fill="{color}" stroke="#fff" stroke-width="1.5" opacity="0">'
            f'<animateMotion dur="{T}s" repeatCount="indefinite" path="{path}" keyPoints="0;0;1;1" '
            f'keyTimes="0;{a / T:.4f};{b / T:.4f};1" calcMode="linear"/>'
            + kf("opacity", [(a - 0.001, 0), (a + 0.04, 1), (b - 0.04, 1), (b, 0)]) + "</circle>")


def glow(x, y, w, h, color, inner, rx=16, sw=5):
    """블록 위에 겹치는 강조 테두리 — inner 는 opacity 애니메이션"""
    add(f'<rect x="{x - 3}" y="{y - 3}" width="{w + 6}" height="{h + 6}" rx="{rx + 3}" fill="{color}" fill-opacity="0.05" '
        f'stroke="{color}" stroke-width="{sw}" opacity="0">{inner}</rect>')


# ---------------------------------------------------------------- 도형 (make_groot_n16_arch.py 와 같은 모양)
def rect(x, y, w, h, fill=BOX, rx=16, stroke=LINE, sw=2.2, extra="", inner=""):
    add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" {extra}>{inner}</rect>')


def text(x, y, lines, size=22, color=INK, anchor="middle", font=SANS, weight="normal", lh=None, extra="", inner=""):
    if isinstance(lines, str):
        lines = [lines]
    lh = lh or size * 1.25
    y0 = y - lh * (len(lines) - 1) / 2
    spans = "".join(f'<tspan x="{x}" y="{y0 + i * lh:.1f}">{s}</tspan>' for i, s in enumerate(lines))
    add(f'<text text-anchor="{anchor}" dominant-baseline="middle" font-family="{font}" font-size="{size}" '
        f'font-weight="{weight}" fill="{color}" {extra}>{spans}{inner}</text>')


def line(x1, y1, x2, y2, arrow=False, color=LINE, dash=None, sw=2):
    da = f' stroke-dasharray="{dash}"' if dash else ""
    me = ' marker-end="url(#ah)"' if arrow else ""
    add(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{sw}"{da}{me}/>')


def path(d, color=LINE, sw=2, dash=None, marker="ah", extra="", inner=""):
    da = f' stroke-dasharray="{dash}"' if dash else ""
    me = f' marker-end="url(#{marker})"' if marker else ""
    add(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{sw}"{da}{me} {extra}>{inner}</path>')


def token(x, y, fill, stroke, s=19):
    add(f'<rect x="{x}" y="{y:.1f}" width="{s}" height="{s}" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>')


def snowflake(cx, cy, r=12, sw=2.0):
    arms = []
    for k in range(6):
        b = r * 0.45
        arms.append(f'<g transform="rotate({k * 60} {cx} {cy})"><line x1="{cx}" y1="{cy}" x2="{cx}" y2="{cy - r}"/>'
                    f'<line x1="{cx}" y1="{cy - b}" x2="{cx - r * 0.3:.1f}" y2="{cy - r * 0.7:.1f}"/>'
                    f'<line x1="{cx}" y1="{cy - b}" x2="{cx + r * 0.3:.1f}" y2="{cy - r * 0.7:.1f}"/></g>')
    add(f'<g stroke="#4d8ff0" stroke-width="{sw}" stroke-linecap="round">' + "".join(arms) + "</g>")


def photo(name, x, y, w, h, label=None, crop=None):
    """crop 이 있으면 정지 사진 위에 영상 칸(canvas)을 얹는다 — HTML 의 한 영상에서 crop 번째 카메라를 잘라 그린다."""
    if crop is not None and HOLES is not None:
        HOLES.append((x, y + DY, w, h, crop))    # 비워 둔 칸 — 뒤에서 ffmpeg 가 영상을 깐다
    else:
        add(f'<image href="{img(name)}" x="{x}" y="{y}" width="{w}" height="{h}" preserveAspectRatio="xMidYMid slice"/>')
    if crop is not None and HOLES is None:
        add(f'<foreignObject x="{x}" y="{y}" width="{w}" height="{h}"><canvas xmlns="http://www.w3.org/1999/xhtml" '
            f'class="vcam" data-crop="{crop}" width="{w * 3}" height="{h * 3}" style="width:100%;height:100%;display:block"></canvas></foreignObject>')
    add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="none" stroke="{LINE}" stroke-width="1.5"/>')
    if label:
        lw = sum(13.5 if ord(ch) > 0x1100 else 7.5 for ch in label) + 10
        add(f'<rect x="{x + 3}" y="{y + h - 21}" width="{lw}" height="18" rx="3" fill="#000" fill-opacity="0.6"/>')
        add(f'<text x="{x + 8}" y="{y + h - 11.5}" dominant-baseline="middle" font-family="{SANS}" font-size="13" fill="#fff">{label}</text>')


def wave(x, y, w, h, noise, seed, n=24):
    random.seed(seed)
    pts = []
    for i in range(n + 1):
        u = i / n
        base = math.sin(u * math.pi * 1.6) * 0.38 + u * 0.25
        pts.append((x + u * w, y + h / 2 - (base + random.uniform(-noise, noise)) * h / 1.4))
    return "M" + " L".join(f"{px:.1f},{py:.1f}" for px, py in pts)


# ---------------------------------------------------------------- 공통 구조도
def vis_tokens(x):
    for g in range(3):
        for k in range(3):
            token(x, 27 + g * 60 + k * 18, "#c8a3ea", "#6e5a8e", 16)
    for k in range(4):
        token(x, 218 + k * 23.7, "#2f6fca", "#1e3f78")


def arch(mode):
    """mode = 'train' | 'infer'. 구조도 좌표는 make_groot_n16_arch.py 와 같다."""
    # 입력
    if mode == "train":
        for k, (_, instr) in enumerate(SETS):           # 학습 사이클마다 다른 시연 장면
            add(f'<g opacity="{1 if k == 0 else 0}">{cyc(k)}')
            photo(f"train_sets/set{k}_top.jpg", 14, 24, 164, 123, "위")
            photo(f"train_sets/set{k}_right.jpg", 184, 24, 80, 60, "오른손목")
            photo(f"train_sets/set{k}_left.jpg", 184, 88, 80, 60, "왼손목")
            instruction(instr)
            add("</g>")
    else:
        live = mode == "infer_video"
        photo("n16_cam_top.jpg", 14, 24, 164, 123, "위", crop=0 if live else None)
        photo("n16_cam_right.jpg", 184, 24, 80, 60, "오른손목", crop=2 if live else None)
        photo("n16_cam_left.jpg", 184, 88, 80, 60, "왼손목", crop=1 if live else None)
        instruction("Put the screwdriver into the black bin")
    text(139, 168, "카메라 3대", 17, weight="bold")
    text(139, 228, "지시 문장", 17, weight="bold")
    line(266, 110, 281, 110)
    line(266, 263, 281, 263)
    rect(281, 25, 142, 175)
    text(352, 108, ["Vision", "Encoder"], 22)
    snowflake(402, 46, 11)
    rect(281, 228, 142, 78)
    text(352, 267, ["Text", "Tokenizer"], 22)
    line(423, 110, 451, 110, True)
    line(423, 263, 451, 263, True)
    vis_tokens(456)
    rect(493, 17, 156, 305, rx=22)
    text(571, 46, "VLM", 22, weight="bold")
    text(571, 68, "언어 모델 16층", 14, "#444")
    add(f'<rect x="507" y="84" width="128" height="104" rx="8" fill="{TRAIN}" stroke="#c2410c" stroke-width="1.5"/>')
    text(571, 136, ["위 8층", "학습"], 16, "#fff", weight="bold", lh=21)
    add('<rect x="507" y="194" width="128" height="116" rx="8" fill="#e5e5e5" stroke="#999" stroke-width="1.5"/>')
    snowflake(571, 232, 13)
    text(571, 274, ["아래 8층", "고정"], 15, "#444", weight="bold", lh=20)
    vis_tokens(665)
    line(695, 167, 1003, 167)
    add('<rect x="798" y="135" width="110" height="24" rx="12" fill="#f8fafc" stroke="#cbd5e1" stroke-width="1"/>')
    text(853, 148, "VLM 출력", 14, "#444", weight="bold")

    # 범례
    rect(1091, 82, 40, 40, TRAIN, rx=8, stroke="#c2410c")
    text(1151, 102, "우리 데이터로 학습", 21, anchor="start")
    snowflake(1111, 152, 16, 3.0)
    text(1151, 152, "사전학습 그대로 고정", 21, anchor="start")
    rect(1091, 184, 40, 40, GREEN, rx=8)
    text(1151, 204, "로봇 전용 모듈 (양팔 12관절)", 21, anchor="start")

    # Action head 묶음
    add(f'<rect x="404" y="330" width="968" height="452" rx="30" fill="none" stroke="{TRAIN}" stroke-width="2.5" stroke-dasharray="10 7"/>')
    add(f'<rect x="1188" y="316" width="168" height="28" rx="14" fill="#fff7ed" stroke="{TRAIN}" stroke-width="1.5"/>')
    text(1272, 330, "Action head · 학습", 15, "#c2410c", weight="bold")

    text(132, 382, "Robot State", 22)
    text(132, 408, "(현재 관절 각도)", 16, "#666")
    line(356, 391, 420, 391)
    rect(420, 341, 163, 103, GREEN)
    text(501, 392, ["State", "Encoder"], 22)
    line(583, 391, 630, 391, True)
    token(665, 367, "#d9646b", "#8a3a3e")
    token(665, 392, "#d9646b", "#8a3a3e")

    text(132, 568, "Noised Action", 22)
    text(132, 596, "(정답 + 노이즈)" if mode == "train" else "(무작위 동작에서 출발)", 16, "#666")
    add(f'<rect x="250" y="450" width="93" height="260" rx="12" fill="#fff" stroke="{LINE}" stroke-width="2.2" stroke-dasharray="8 6"/>')
    for yy, s in ((487, "동작 1"), (539, "동작 2"), (676, "동작 16")):
        text(296, yy, s, 19)
    text(296, 612, "⋮", 24)
    line(356, 579, 420, 579)
    rect(420, 464, 163, 235, GREEN)
    text(501, 582, ["Action", "Encoder"], 22)
    line(583, 579, 630, 579, True)
    for k in range(9):
        token(665, 474 + k * 23.8, "#fdf0dd", "#9a8a72")

    line(695, 525, 720, 525, True)
    rect(721, 341, 415, 369, rx=28)
    for x, lb in ((747, "Cross-Attention"), (825, "Self-Attention"), (974, "Cross-Attention"), (1053, "Self-Attention")):
        rect(x, 357, 58, 336, "#d9d9d9", rx=10)
        add(f'<text x="{x + 29}" y="525" text-anchor="middle" dominant-baseline="middle" font-family="{SANS}" font-size="22" '
            f'fill="{INK}" transform="rotate(90 {x + 29} 525)">{lb}</text>')
    line(776, 167, 776, 356, True)
    line(1003, 167, 1003, 356, True)
    line(805, 525, 825, 525)
    line(883, 525, 974, 525, dash="8 7")
    line(1032, 525, 1053, 525)
    text(928, 728, "× 32층", 19, "#444")
    text(928, 758, "DiT Blocks", 22, weight="bold")
    line(1136, 525, 1164, 525, True)
    token(1171, 367, "#d9646b", "#8a3a3e")
    token(1171, 392, "#d9646b", "#8a3a3e")
    for k in range(9):
        token(1171, 474 + k * 23.8, "#f6a136", "#9a5f12")
    rect(1206, 357, 151, 342, GREEN, rx=22)
    text(1281, 524, ["Action", "Decoder"], 22)
    line(1357, 522, 1383, 522, True)
    text(1433, 376, "예측 16스텝" if mode == "train" else "앞으로 16스텝", 17, weight="bold")
    add(f'<rect x="1386" y="393" width="93" height="259" rx="12" fill="#fff" stroke="{LINE}" stroke-width="2.2" stroke-dasharray="8 6"/>')
    for yy, s in ((430, "동작 1"), (484, "동작 2"), (618, "동작 16")):
        text(1433, yy, s, 19)
    text(1431, 555, "⋮", 24)


# 블록 좌표 (강조 테두리용)
B = dict(ve=(281, 25, 142, 175), tok=(281, 228, 142, 78), vlm=(493, 17, 156, 305), top8=(507, 84, 128, 104),
         se=(420, 341, 163, 103), ae=(420, 464, 163, 235), dit=(721, 341, 415, 369), dec=(1206, 357, 151, 342),
         nz=(250, 450, 93, 260), outb=(1386, 393, 93, 259), head=(404, 330, 968, 452))


def forward(t0, col_in=CYAN):
    """입력 → VLM → DiT → 예측까지 한 번 흐르는 모습. 끝나는 시각을 돌려준다."""
    dots("M200,110 L493,110", t0, t0 + 0.8, col_in)
    dots("M200,263 L493,263", t0 + 0.1, t0 + 0.9, col_in)
    glow(*B["ve"], CYAN, pulses([t0 + 0.3], 0.9))
    glow(*B["tok"], CYAN, pulses([t0 + 0.4], 0.9))
    glow(*B["vlm"], CYAN, pulses([t0 + 1.0], 1.2), rx=22)
    dots("M695,167 L776,167 L776,356", t0 + 1.8, t0 + 2.4, CYAN)
    dots("M695,167 L1003,167 L1003,356", t0 + 1.8, t0 + 2.6, CYAN)
    dots("M356,391 L420,391 M583,391 L650,391", t0 + 0.6, t0 + 1.8, BLUE, 2, 0.2)
    dots("M356,579 L420,579 M583,579 L650,579", t0 + 0.8, t0 + 2.0, VIOLET, 2, 0.2)
    glow(*B["se"], BLUE, pulses([t0 + 1.0], 0.9))
    glow(*B["ae"], VIOLET, pulses([t0 + 1.2], 0.9))
    return t0 + 2.6


def dit_pass(t):
    dots("M695,525 L720,525", t, t + 0.25, VIOLET, 2, 0.08)
    dots("M1136,525 L1164,525 M1357,522 L1386,522", t + 0.55, t + 0.95, VIOLET, 2, 0.1)


def background(h):
    """흰 배경. HOLES 가 있으면 영상 칸 자리를 뚫어 투명하게 둔다."""
    if not HOLES:
        return f'<rect width="{W}" height="{h}" fill="#fff"/>'
    d = f"M0,0 H{W} V{h} H0 Z " + " ".join(f"M{x},{y} v{hh} h{w} v{-hh} Z" for x, y, w, hh, _ in HOLES)
    return f'<path d="{d}" fill="#fff" fill-rule="evenodd"/>'


def svg_wrap(title, h, body):
    defs = (f'<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M0,0 L10,5 L0,10 z" fill="{LINE}"/></marker>'
            f'<marker id="ahO" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
            f'<path d="M0,0 L10,5 L0,10 z" fill="{TRAIN}"/></marker>'
            f'<marker id="ahG" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
            f'<path d="M0,0 L10,5 L0,10 z" fill="{GT}"/></marker></defs>')
    return (f'<svg viewBox="0 0 {W} {h}" width="{W}" height="{h}" xmlns="http://www.w3.org/2000/svg" role="img">'
            f'<title>{title}</title>{defs}{background(h)}'
            f'<g transform="translate(0,{DY})">\n' + "\n".join(body) + "\n</g></svg>")


def uniq(svg, pfx):
    """한 HTML 에 SVG 두 장을 넣으면 화살촉 id 가 겹쳐 숨은 쪽을 가리키므로 id 를 구분한다"""
    return svg.replace('id="ah', f'id="{pfx}ah').replace("url(#ah", f"url(#{pfx}ah")


# ================================================================ 학습
def train_svg():
    global T
    T = 12.0
    out.clear()
    arch("train")

    # 정답 동작(사람 시연) + 노이즈 → Noised Action
    rect(20, 726, 216, 80, "#ecfdf5", rx=12, stroke=GT, sw=2)
    text(128, 748, "정답 동작", 17, GT, weight="bold")
    text(128, 770, "(사람이 조종한 16스텝)", 13, "#444")
    for k in range(len(SETS)):
        add(f'<g opacity="{1 if k == 0 else 0}">{cyc(k)}')
        path(wave(40, 778, 176, 24, 0, 1 + k, 16), GT, 2.5, marker=None)
        add("</g>")
    path("M236,766 L296,766 L296,714", GT, 2, marker="ahG")
    add(f'<circle cx="296" cy="766" r="13" fill="#fff" stroke="{LINE}" stroke-width="2"/>')
    text(296, 767, "+", 20, weight="bold")
    text(340, 766, "노이즈", 15, "#666", anchor="start")
    dots("M236,766 L296,766 L296,714", 0.2, 1.0, GT, 3)
    glow(*B["nz"], VIOLET, pulses([1.0], 0.9), rx=12)

    end = forward(0.4)                       # ≈ 3.0
    glow(*B["dit"], VIOLET, show(end, end + 1.6), rx=28)
    dit_pass(end)
    glow(*B["dec"], VIOLET, pulses([end + 0.8], 0.8), rx=22)
    glow(*B["outb"], VIOLET, show(end + 1.1, T - 0.4), rx=12)

    # 채점판: 예측 vs 정답
    PX, PY, PW, PH = 1500, 380, 284, 300
    rect(PX, PY, PW, PH, "#fff", rx=14, stroke="#cbd5e1", sw=1.5)
    text(PX + 18, PY + 26, "정답과 비교", 18, weight="bold", anchor="start")
    gx, gy, gw, gh = PX + 18, PY + 48, PW - 36, 120
    for k in range(len(SETS)):                    # 장면마다 정답 · 예측 곡선이 다르다
        add(f'<g opacity="{1 if k == 0 else 0}">{cyc(k)}')
        random.seed(1 + k)
        shift = random.uniform(-0.15, 0.15)
        def curve(noise, seed):
            random.seed(seed)
            pts = []
            for i in range(25):
                u = i / 24
                base = math.sin(u * math.pi * (1.3 + 0.15 * k) + shift * 6) * 0.38 + u * 0.25
                pts.append(base + random.uniform(-noise, noise))
            return pts
        tv, pv = curve(0, 1), curve(0.2, 99 + k)
        Y = lambda v: gy + gh / 2 - v * gh / 1.4
        path("M" + " L".join(f"{gx + i / 24 * gw:.1f},{Y(v):.1f}" for i, v in enumerate(tv)), GT, 3, marker=None, extra='opacity="0"', inner=show(5.0))
        path("M" + " L".join(f"{gx + i / 24 * gw:.1f},{Y(v):.1f}" for i, v in enumerate(pv)), VIOLET, 3, dash="6 5", marker=None, extra='opacity="0"', inner=show(4.6))
        for i in range(0, 25, 3):
            add(f'<line x1="{gx + i / 24 * gw:.1f}" y1="{Y(tv[i]):.1f}" x2="{gx + i / 24 * gw:.1f}" y2="{Y(pv[i]):.1f}" stroke="{RED}" stroke-width="3" opacity="0">{show(5.6)}</line>')
        add("</g>")
    text(PX + 18, PY + 188, "━ 정답", 14, GT, "start", weight="bold")
    text(PX + 92, PY + 188, "┅ 예측", 14, VIOLET, "start", weight="bold")
    text(PX + 166, PY + 188, "┃ 오차", 14, RED, "start", weight="bold")
    text(PX + PW / 2, PY + 220, "매번 다른 장면 64개씩", 15, "#444", weight="bold", extra='opacity="0"', inner=show(7.8))
    for k, lab in enumerate(CYCLE_LABEL):
        add(f'<g opacity="{1 if k == 0 else 0}">{cyc(k)}')
        text(PX + PW / 2, PY + 251, f"학습 {lab}번째", 26, TRAIN, weight="bold", extra='opacity="0"', inner=show(7.8))
        add("</g>")
    text(PX + PW / 2, PY + 281, "69,000번 = 전체 데이터 약 10바퀴", 14, "#666", extra='opacity="0"', inner=show(7.8))
    path("M1480,522 L1500,522", LINE, 2)
    dots("M1440,522 L1500,522", end + 1.5, end + 1.8, VIOLET, 2, 0.1)
    path(f"M128,806 L128,832 L{PX + PW / 2},832 L{PX + PW / 2},{PY + PH + 4}", GT, 2, dash="6 6", marker="ahG")
    dots(f"M128,806 L128,832 L{PX + PW / 2},832 L{PX + PW / 2},{PY + PH}", 3.6, 5.0, GT, 3, 0.12)

    # 오차를 거꾸로 보내 학습 부분만 고친다 (역전파)
    bp = f"M{PX + PW / 2},{PY} L{PX + PW / 2},-22 L571,-22 L571,14"
    path(bp, TRAIN, 3, dash="9 6", marker="ahO", extra='opacity="0"', inner=show(6.4))
    path("M1060,-22 L1060,326", TRAIN, 3, dash="9 6", marker="ahO", extra='opacity="0"', inner=show(6.4))
    dots(bp, 6.5, 7.6, TRAIN, 4, 0.1, 7)
    dots("M1060,-22 L1060,326", 7.0, 7.6, TRAIN, 3, 0.1, 7)
    add(f'<g opacity="0">{show(6.4)}<rect x="1160" y="-36" width="290" height="28" rx="14" fill="#fff7ed" stroke="{TRAIN}" stroke-width="1.5"/>'
        f'<text x="1305" y="-21" text-anchor="middle" dominant-baseline="middle" font-family="{SANS}" font-size="15" font-weight="bold" fill="#c2410c">'
        f'오차만큼 주황 부분만 조금씩 수정</text></g>')
    glow(*B["top8"], TRAIN, pulses([7.6, 8.4, 9.2, 10.0], 0.7), rx=8, sw=6)
    glow(*B["head"], TRAIN, pulses([7.7, 8.5, 9.3, 10.1], 0.7), rx=30, sw=6)

    # 단계 자막
    steps = [(0.0, 2.9, "① 시연 데이터를 넣는다 — 정답 동작에는 노이즈를 섞는다"),
             (2.9, 4.5, "② 모델이 노이즈를 걷어 낸 동작을 예측한다"),
             (4.5, 6.4, "③ 예측을 사람의 정답 동작과 비교한다"),
             (6.4, T - 0.3, "④ 틀린 만큼 조금씩 고치기를, 매번 다른 장면으로 69,000번 반복")]
    for a, b, s in steps:
        text(900, 866, s, 22, weight="bold", extra='opacity="0"', inner=show(a, b, fade=0.15))
    add(f'<text x="1784" y="866" text-anchor="end" dominant-baseline="middle" font-family="{SANS}" font-size="15" fill="#666">'
        f'학습: RTX 5090 · 392회 시연 · 10 epoch</text>')
    return uniq(svg_wrap("GR00T N1.6 학습 흐름", H, out), "t-")


# ================================================================ 추론
def infer_svg(video=False):
    global T
    T = 12.0
    out.clear()
    arch("infer_video" if video or HOLES is not None else "infer")

    # 카메라 찰칵
    for (x, y, w, h), t in (((14, 24, 164, 123), 0.1), ((184, 24, 80, 60), 0.25), ((184, 88, 80, 60), 0.4)):
        add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#fff" opacity="0">{kf("opacity", [(t, 0), (t + 0.05, 0.85), (t + 0.4, 0)])}</rect>')
    end = forward(0.4)                       # ≈ 3.0

    # 무작위 → 4번 다듬기 (K 반복)
    add(f'<polyline points="1433,654 1433,800 296,800 296,722" fill="none" stroke="{LINE}" stroke-width="2" '
        f'stroke-dasharray="2 4" marker-end="url(#ah)"/>')
    text(866, 826, "4번 반복해 무작위 동작 → 정확한 동작으로 다듬기", 22)
    glow(*B["nz"], VIOLET, pulses([1.0], 0.9), rx=12)
    for k in range(4):
        t = end + k * 1.0
        dit_pass(t)
        if k < 3:
            dots("M1433,654 L1433,800 L296,800 L296,714", t + 0.95, t + 1.05 + 0.0, VIOLET, 1, 0, 6)
        # 가운데 열 사이 빈 칸(883~974)에 단계 표시
        add(f'<g opacity="0">{show(t, t + 0.95 if k < 3 else end + 4.2, fade=0.05)}'
            f'<rect x="888" y="588" width="80" height="62" rx="10" fill="#fff" stroke="{VIOLET}" stroke-width="2"/>'
            f'<text x="928" y="606" text-anchor="middle" dominant-baseline="middle" font-family="{SANS}" font-size="14" fill="{VIOLET}" font-weight="bold">다듬기</text>'
            f'<text x="928" y="631" text-anchor="middle" dominant-baseline="middle" font-family="{SANS}" font-size="20" fill="{VIOLET}" font-weight="bold">{k + 1} / 4</text></g>')
    glow(*B["dit"], VIOLET, show(end, end + 4.0), rx=28)
    glow(*B["dec"], VIOLET, pulses([end + 0.6 + k for k in range(4)], 0.6), rx=22)
    # 동작 상자 테두리가 회색 → 보라 (점점 정확해짐)
    for k in range(4):
        add(f'<rect x="1386" y="393" width="93" height="259" rx="12" fill="{VIOLET}" fill-opacity="{0.06 + 0.06 * k:.2f}" '
            f'stroke="{VIOLET}" stroke-width="{2 + k}" opacity="0">{show(end + 1.0 + k, end + 2.0 + k if k < 3 else end + 5.6, fade=0.05)}</rect>')

    # 현재 각도 + 움직일 양 → 로봇
    t_out = end + 4.2                        # ≈ 7.2
    line(1480, 522, 1512, 522, True)
    add(f'<circle cx="1534" cy="522" r="20" fill="#fff" stroke="{LINE}" stroke-width="2.4"/>')
    text(1534, 523, "+", 30, weight="bold")
    text(1534, 424, ["현재", "각도"], 15, "#444", lh=18)
    line(1534, 450, 1534, 498, True)
    text(1534, 574, ["움직일", "양"], 14, "#444", lh=18)
    line(1556, 522, 1578, 522, True)
    dots("M1480,522 L1582,522", t_out, t_out + 0.5, VIOLET, 3, 0.08)
    photo("n16_robot_action.jpg", 1582, 440, 204, 153, crop=0 if video or HOLES is not None else None)
    glow(1582, 440, 204, 153, GT, show(t_out + 0.5, t_out + 2.4), rx=4)
    text(1684, 623, "로봇 양팔 동작", 20, weight="bold")
    add('<rect x="1600" y="648" width="168" height="12" rx="6" fill="#e2e8f0"/>')
    add(f'<rect x="1600" y="648" width="0" height="12" rx="6" fill="{GT}">'
        + kf("width", [(t_out + 0.5, 0), (t_out + 2.3, 168), (t_out + 2.6, 168), (t_out + 2.7, 0)]) + "</rect>")
    text(1684, 676, "16스텝 중 앞 8스텝 실행", 14, "#444")

    # 실행 후 다시 카메라로 (닫힌 고리)
    loop = "M1684,690 L1684,868 L6,868 L6,90 L14,90"
    path(loop, GT, 3, dash="9 6", marker="ahG")
    dots(loop, t_out + 2.4, t_out + 4.2, GT, 4, 0.12, 7)
    add(f'<rect x="700" y="854" width="460" height="28" rx="14" fill="#ecfdf5" stroke="{GT}" stroke-width="1.5"/>')
    text(930, 869, "8스텝(약 0.27초)마다 다시 찍고 → 다시 계획", 16, GT, weight="bold")

    # 추론 속도
    add(f'<rect x="1091" y="250" width="560" height="44" rx="22" fill="#eff6ff" stroke="#bfdbfe" stroke-width="1.5"/>')
    text(1371, 273, "RTX 5070 Ti 로컬 서빙 · 추론 1회 86 ms", 19, BLUE, weight="bold")

    steps = [(0.0, 3.0, "① 카메라 3대와 지시 문장, 현재 관절 각도를 넣는다"),
             (3.0, 7.2, "② 무작위 동작에서 출발해 4번 다듬어 16스텝 계획을 만든다"),
             (7.2, 9.6, "③ 현재 각도에 더해 앞 8스텝을 실행한다"),
             (9.6, T - 0.3, "④ 다시 찍고 다시 계획 — 물체를 칸에 넣을 때까지 반복")]
    for a, b, s in steps:
        text(900, 910, s, 22, weight="bold", extra='opacity="0"', inner=show(a, b, fade=0.15))
    return uniq(svg_wrap("GR00T N1.6 추론 흐름", H, out), "iv-" if video else "i-")


if __name__ == "__main__":
    tr, inf = train_svg(), infer_svg()
    inf_live = infer_svg(video=True)
    for nm, s in (("train_flow_n16.svg", tr), ("infer_flow_n16.svg", inf)):
        with open(os.path.join(HERE, nm), "w") as f:
            f.write(s)
    html = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>GR00T N1.6 학습·추론 흐름</title>
<style>body{{margin:0;background:#f8fafc;font-family:{SANS}}} section{{max-width:1800px;margin:0 auto;padding:32px 16px}}
h2{{color:#0f172a;font-size:26px;margin:0 0 12px}} svg{{width:100%;height:auto;display:block;background:#fff;border-radius:12px}}
.frame section{{padding:0;max-width:none}} .frame h2{{display:none}} .frame section:not(.on){{display:none}} .frame svg{{border-radius:0}}</style></head><body>
<section id="train"><h2>학습 흐름</h2>{tr}</section>
<section id="infer"><h2>추론 흐름</h2>{inf_live}</section>
<video id="cams" src="infer_trial39.mp4" muted loop autoplay playsinline preload="auto" style="display:none"></video>
<script>
// 실기 평가 영상 한 개(위 · 왼손목 · 오른손목 가로 3칸)를 잘라 카메라 3칸 + 로봇 동작 칸에 같은 순간을 그린다
const vid = document.getElementById('cams');
const cams = [...document.querySelectorAll('canvas.vcam')].map(c => [c, c.getContext('2d'), +c.dataset.crop]);
function draw() {{
  if (vid.readyState >= 2) {{
    const cw = vid.videoWidth / 3, ch = vid.videoHeight;
    for (const [c, g, k] of cams) g.drawImage(vid, k * cw, 0, cw, ch, 0, 0, c.width, c.height);
  }}
  requestAnimationFrame(draw);
}}
vid.play().catch(() => {{}});
requestAnimationFrame(draw);
const m = location.hash.match(/frame=(\\w+)@([\\d.]+)/);
if (m) {{
  document.body.classList.add('frame');
  const sec = document.getElementById(m[1]); sec.classList.add('on');
  const svg = sec.querySelector('svg'); svg.pauseAnimations(); svg.setCurrentTime(parseFloat(m[2]));
}}
</script></body></html>"""
    with open(os.path.join(HERE, "flow_n16.html"), "w") as f:
        f.write(html)
    print("ok", len(tr) // 1024, "KB /", len(inf) // 1024, "KB")
