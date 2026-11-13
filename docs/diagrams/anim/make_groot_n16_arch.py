#!/usr/bin/env python3
"""GR00T N1.6 구조도 — groot_n1_architecture.html(N1 논문 그림 재현)을 N1.6 + 우리 과제에 맞게 수정.

python3 make_groot_n16_arch.py  →  groot_n16_architecture.svg / .html (같은 폴더)
블록 이름은 원래 용어(Vision Encoder, State Encoder, DiT 등), 설명은 쉬운 말. 학습 = 주황(Action head 는 점선 묶음), 고정 = 눈송이.
(전문 용어판은 groot_n16_architecture_tech.svg / .html 로 따로 보관)
입력 이미지 = 실기 평가 영상의 카메라 3대, 출력 이미지 = 같은 시행의 위 카메라(왼팔이 칸에 넣는 순간).
"""
import base64, os

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 1800, 960
DY = 40                      # make_flow_n16.py 와 같은 캔버스 · 같은 위치 → 슬라이드에서 겹쳐 넘겨도 블록이 그대로
SANS = "Helvetica, Arial, 'IBM Plex Sans KR', 'Noto Sans CJK KR', sans-serif"
MONO = "Menlo, Consolas, 'Courier New', monospace"
MATH = "'Cambria Math', 'STIX Two Math', 'Times New Roman', serif"
INK, LINE, BOX = "#111", "#555", "#f2f2f2"
GREEN, NEW, TRAIN = "#dde9d3", "#2563eb", "#f97316"

out = []
add = out.append


def img(name):
    with open(os.path.join(HERE, name), "rb") as f:
        return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()


def rect(x, y, w, h, fill=BOX, rx=16, stroke=LINE, sw=2.2, extra=""):
    add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" {extra}/>')


def text(x, y, lines, size=22, color=INK, anchor="middle", font=SANS, weight="normal", lh=None):
    if isinstance(lines, str):
        lines = [lines]
    lh = lh or size * 1.25
    y0 = y - lh * (len(lines) - 1) / 2
    spans = "".join(f'<tspan x="{x}" y="{y0 + i * lh:.1f}">{s}</tspan>' for i, s in enumerate(lines))
    add(f'<text text-anchor="{anchor}" dominant-baseline="middle" font-family="{font}" font-size="{size}" '
        f'font-weight="{weight}" fill="{color}">{spans}</text>')


def rich(x, y, parts, size=22, anchor="middle"):
    """한 줄 안에서 색이 다른 글자 — parts: [(글자, 색, 굵기)]"""
    spans = "".join(f'<tspan fill="{c}" font-weight="{w}">{s}</tspan>' for s, c, w in parts)
    add(f'<text x="{x}" y="{y}" text-anchor="{anchor}" dominant-baseline="middle" font-family="{SANS}" '
        f'font-size="{size}">{spans}</text>')


def line(x1, y1, x2, y2, arrow=False, color=LINE, dash=None, sw=2):
    da = f' stroke-dasharray="{dash}"' if dash else ""
    me = ' marker-end="url(#ah)"' if arrow else ""
    add(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{sw}"{da}{me}/>')


def token(x, y, fill, stroke, s=19):
    add(f'<rect x="{x}" y="{y:.1f}" width="{s}" height="{s}" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>')


def math(x, y, base, sub, delta=False, size=24):
    d = f'<tspan font-style="normal" fill="{NEW}">Δ</tspan>' if delta else ""
    add(f'<text x="{x}" y="{y}" text-anchor="middle" dominant-baseline="middle" font-size="{size}" fill="{INK}" '
        f'font-family="{MATH}">{d}<tspan font-style="italic">{base}</tspan>'
        f'<tspan font-style="italic" font-size="{size * 0.8:.0f}" dy="7">{sub}</tspan></text>')


def snowflake(cx, cy, r=12, sw=2.0):
    arms = []
    for k in range(6):
        b = r * 0.45
        arms.append(f'<g transform="rotate({k * 60} {cx} {cy})"><line x1="{cx}" y1="{cy}" x2="{cx}" y2="{cy - r}"/>'
                    f'<line x1="{cx}" y1="{cy - b}" x2="{cx - r * 0.3:.1f}" y2="{cy - r * 0.7:.1f}"/>'
                    f'<line x1="{cx}" y1="{cy - b}" x2="{cx + r * 0.3:.1f}" y2="{cy - r * 0.7:.1f}"/></g>')
    add(f'<g stroke="#4d8ff0" stroke-width="{sw}" stroke-linecap="round">' + "".join(arms) + "</g>")


def photo(name, x, y, w, h, label=None):
    add(f'<image href="{img(name)}" x="{x}" y="{y}" width="{w}" height="{h}" preserveAspectRatio="xMidYMid slice"/>')
    add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="none" stroke="{LINE}" stroke-width="1.5"/>')
    if label:
        lw = sum(13.5 if ord(ch) > 0x1100 else 7.5 for ch in label) + 10  # 한글은 폭이 넓다
        add(f'<rect x="{x + 3}" y="{y + h - 21}" width="{lw}" height="18" rx="3" fill="#000" fill-opacity="0.6"/>')
        add(f'<text x="{x + 8}" y="{y + h - 11.5}" dominant-baseline="middle" font-family="{SANS}" font-size="13" fill="#fff">{label}</text>')


# ------------------------------------------------------------------ 입력: 카메라 3대 + 지시문
photo("n16_cam_top.jpg", 14, 24, 164, 123, "위")
photo("n16_cam_right.jpg", 184, 24, 80, 60, "오른손목")
photo("n16_cam_left.jpg", 184, 88, 80, 60, "왼손목")
text(139, 168, "카메라 3대", 17, weight="bold")
text(139, 228, "지시 문장", 17, weight="bold")
add(f'<text text-anchor="start" dominant-baseline="middle" font-family="{MONO}" font-size="16" fill="{INK}">'
    f'<tspan x="16" y="256">“Put the screwdriver</tspan><tspan x="16" y="278">into the black bin”</tspan></text>')
line(266, 110, 281, 110)
line(266, 263, 281, 263)

# Vision Encoder(고정) · Text Tokenizer
rect(281, 25, 142, 175)
text(352, 108, ["Vision", "Encoder"], 22)
snowflake(402, 46, 11)
rect(281, 228, 142, 78)
text(352, 267, ["Text", "Tokenizer"], 22)
line(423, 110, 451, 110, True)
line(423, 263, 451, 263, True)

# 이미지 토큰(카메라 3대 = 3묶음) · 단어 토큰
def vis_tokens(x):
    for g in range(3):
        for k in range(3):
            token(x, 27 + g * 60 + k * 18, "#c8a3ea", "#6e5a8e", 16)
    for k in range(4):
        token(x, 218 + k * 23.7, "#2f6fca", "#1e3f78")


vis_tokens(456)

# VLM — 언어 모델 위 8층 학습 / 아래 8층 고정
rect(493, 17, 156, 305, rx=22)
text(571, 46, "VLM", 22, weight="bold")
text(571, 68, "언어 모델 16층", 14, "#444")
add(f'<rect x="507" y="84" width="128" height="104" rx="8" fill="{TRAIN}" stroke="#c2410c" stroke-width="1.5"/>')
text(571, 136, ["위 8층", "학습"], 16, "#fff", weight="bold", lh=21)
add('<rect x="507" y="194" width="128" height="116" rx="8" fill="#e5e5e5" stroke="#999" stroke-width="1.5"/>')
snowflake(571, 232, 13)
text(571, 274, ["아래 8층", "고정"], 15, "#444", weight="bold", lh=20)
vis_tokens(665)

# VLM 출력 → DiT cross-attention
line(695, 167, 1003, 167)
add('<rect x="798" y="135" width="110" height="24" rx="12" fill="#f8fafc" stroke="#cbd5e1" stroke-width="1"/>')
text(853, 148, "VLM 출력", 14, "#444", weight="bold")

# 범례 · 제목
rect(1091, 82, 40, 40, TRAIN, rx=8, stroke="#c2410c")
text(1151, 102, "우리 데이터로 학습", 21, anchor="start")
snowflake(1111, 152, 16, 3.0)
text(1151, 152, "사전학습 그대로 고정", 21, anchor="start")
rect(1091, 184, 40, 40, GREEN, rx=8)
text(1151, 204, "로봇 전용 모듈 (양팔 12관절)", 21, anchor="start")

# Action head 전체 = 학습 (점선 묶음)
add(f'<rect x="404" y="330" width="968" height="452" rx="30" fill="none" stroke="{TRAIN}" stroke-width="2.5" stroke-dasharray="10 7"/>')
add(f'<rect x="1188" y="316" width="168" height="28" rx="14" fill="#fff7ed" stroke="{TRAIN}" stroke-width="1.5"/>')
text(1272, 330, "Action head · 학습", 15, "#c2410c", weight="bold")

# Robot State → State Encoder
text(132, 382, "Robot State", 22)
text(132, 408, "(현재 관절 각도)", 16, "#666")
line(356, 391, 420, 391)
rect(420, 341, 163, 103, GREEN)
text(501, 392, ["State", "Encoder"], 22)
line(583, 391, 630, 391, True)
token(665, 367, "#d9646b", "#8a3a3e")
token(665, 392, "#d9646b", "#8a3a3e")

# Noised Action → Action Encoder
text(132, 568, "Noised Action", 22)
text(132, 596, "(무작위 동작에서 출발)", 16, "#666")
add(f'<rect x="250" y="450" width="93" height="260" rx="12" fill="none" stroke="{LINE}" stroke-width="2.2" stroke-dasharray="8 6"/>')
text(296, 487, "동작 1", 19)
text(296, 539, "동작 2", 19)
text(296, 612, "⋮", 24)
text(296, 676, "동작 16", 19)
line(356, 579, 420, 579)
rect(420, 464, 163, 235, GREEN)
text(501, 582, ["Action", "Encoder"], 22)
line(583, 579, 630, 579, True)
for k in range(9):
    token(665, 474 + k * 23.8, "#fdf0dd", "#9a8a72")

# DiT 32층
line(695, 525, 720, 525, True)
rect(721, 341, 415, 369, rx=28)
for x, lb in ((747, "Cross-Attention"), (825, "Self-Attention"), (974, "Cross-Attention"), (1053, "Self-Attention")):
    rect(x, 357, 58, 336, "#d9d9d9", rx=10)
    add(f'<text x="{x + 29}" y="525" text-anchor="middle" dominant-baseline="middle" font-family="{SANS}" font-size="22" '
        f'fill="{INK}" transform="rotate(90 {x + 29} 525)">{lb}</text>')
line(776, 167, 776, 356, True)   # VLM 출력 → cross-attention (DiT 상자 위에 그려야 화살촉이 보임)
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

# Action Decoder → 앞으로 16스텝
rect(1206, 357, 151, 342, GREEN, rx=22)
text(1281, 524, ["Action", "Decoder"], 22)
line(1357, 522, 1383, 522, True)
text(1433, 376, "앞으로 16스텝", 17, weight="bold")
add(f'<rect x="1386" y="393" width="93" height="259" rx="12" fill="none" stroke="{LINE}" stroke-width="2.2" stroke-dasharray="8 6"/>')
text(1433, 430, "동작 1", 19)
text(1433, 484, "동작 2", 19)
text(1431, 555, "⋮", 24)
text(1433, 618, "동작 16", 19)

# 현재 각도 + 움직일 양 = 목표 각도
line(1480, 522, 1512, 522, True)
add(f'<circle cx="1534" cy="522" r="20" fill="#fff" stroke="{LINE}" stroke-width="2.4"/>')
text(1534, 523, "+", 30, weight="bold")
text(1534, 424, ["현재", "각도"], 15, "#444", lh=18)
line(1534, 450, 1534, 498, True)
text(1534, 574, ["움직일", "양"], 14, "#444", lh=18)
line(1556, 522, 1578, 522, True)

# 출력: 로봇 양팔 실행
photo("n16_robot_action.jpg", 1582, 440, 204, 153)
text(1684, 623, "로봇 양팔 동작", 20, weight="bold")

# K = 4 반복
add(f'<polyline points="1433,654 1433,800 296,800 296,722" fill="none" stroke="{LINE}" stroke-width="2" '
    f'stroke-dasharray="2 4" marker-end="url(#ah)"/>')
text(866, 826, "4번 반복해 무작위 동작 → 정확한 동작으로 다듬기", 22)

svg = (f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" xmlns="http://www.w3.org/2000/svg" role="img" '
       f'aria-label="GR00T N1.6 model architecture"><title>GR00T N1.6 Architecture</title><defs>'
       f'<marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
       f'<path d="M0,0 L10,5 L0,10 z" fill="{LINE}"/></marker></defs>'
       f'<rect width="{W}" height="{H}" fill="#fff"/>\n<g transform="translate(0,{DY})">\n' + "\n".join(out) + "\n</g></svg>")
with open(os.path.join(HERE, "groot_n16_architecture.svg"), "w") as f:
    f.write(svg)
html = ('<!doctype html>\n<html lang="ko"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n<title>GR00T N1.6 Architecture</title>\n'
        '<style>\n  html, body { margin: 0; background: #fff; }\n'
        f'  main {{ max-width: {W}px; margin: 0 auto; padding: 16px; box-sizing: border-box; }}\n'
        '  svg { width: 100%; height: auto; display: block; }\n</style></head>\n<body><main>\n' + svg + '\n</main></body></html>\n')
with open(os.path.join(HERE, "groot_n16_architecture.html"), "w") as f:
    f.write(html)
print("ok", len(svg) // 1024, "KB")
