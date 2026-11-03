#!/usr/bin/env python3
"""발표용 애니메이션 블록도 생성 — 학습 흐름 / 추론 흐름 (SMIL SVG + 미리보기 HTML).

python3 make_flow_anim.py <카메라 썸네일 폴더>
  → train_flow.svg, infer_flow.svg, flow_anim.html (같은 폴더)
모든 애니메이션은 dur=T, repeatCount=indefinite 로 같은 주기를 공유하므로
svg.setCurrentTime(t) 한 번으로 임의 시점 프레임을 정확히 재현할 수 있다 (GIF 렌더용).
"""
import base64, math, os, random, sys

HERE = os.path.dirname(os.path.abspath(__file__))
THUMB = sys.argv[1] if len(sys.argv) > 1 else HERE
W, H = 1720, 720

C = dict(bg="#F8FAFC", white="#FFFFFF", border="#E2E8F0", title="#0F172A", cardT="#1E293B",
         body="#475569", muted="#94A3B8", blue="#2563EB", blueBg="#EFF6FF", cyan="#0EA5E9",
         cyanBg="#ECFEFF", green="#059669", greenBg="#ECFDF5", sub="#F1F5F9", red="#DC2626",
         orange="#EA580C", orangeBg="#FFF7ED", violet="#7C3AED", violetBg="#F5F3FF")
FONT = "'IBM Plex Sans KR','Noto Sans KR','Noto Sans CJK KR',sans-serif"
MONO = "'JetBrains Mono','DejaVu Sans Mono',monospace"


def img64(name):
    with open(os.path.join(THUMB, name), "rb") as f:
        return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()


class Anim:
    """한 장의 SVG. 모든 키프레임은 초 단위로 받고 주기 T 의 비율로 바꾼다."""

    def __init__(self, T):
        self.T, self.out = T, []

    def add(self, s):
        self.out.append(s)

    # ---- 키프레임 ----
    def kf(self, attr, pts, extra=""):
        pts = sorted(pts)
        if pts[0][0] > 0:
            pts = [(0, pts[0][1])] + pts
        if pts[-1][0] < self.T:
            pts = pts + [(self.T, pts[-1][1])]
        kt = ";".join(f"{t / self.T:.4f}" for t, _ in pts)
        vs = ";".join(str(v) for _, v in pts)
        return (f'<animate attributeName="{attr}" dur="{self.T}s" repeatCount="indefinite" '
                f'keyTimes="{kt}" values="{vs}" {extra}/>')

    def show(self, t0, t1=None, fade=0.25, lo=0, hi=1):
        """t0 에 나타나서 t1 에 사라지는 opacity 키프레임 (t1=None 이면 주기 끝 직전까지)."""
        t1 = self.T - 0.3 if t1 is None else t1
        return self.kf("opacity", [(0, lo), (max(t0 - 0.001, 0), lo), (t0 + fade, hi),
                                   (t1, hi), (min(t1 + fade, self.T), lo)])

    def pulse(self, t0, t1, attr="opacity", lo=0, hi=1):
        m = (t0 + t1) / 2
        return self.kf(attr, [(t0, lo), (m, hi), (t1, lo)])

    # ---- 도형 ----
    def rect(self, x, y, w, h, fill, stroke=None, r=12, sw=1, extra="", inner="", dash=None):
        st = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
        da = f' stroke-dasharray="{dash}"' if dash else ""
        return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}"{st}{da} {extra}>{inner}</rect>'

    def text(self, x, y, s, size=16, color=None, weight=400, anchor="start", font=FONT, extra="", inner=""):
        color = color or C["body"]
        return (f'<text x="{x}" y="{y}" font-family="{font}" font-size="{size}" font-weight="{weight}" '
                f'fill="{color}" text-anchor="{anchor}" {extra}>{s}{inner}</text>')

    def card(self, x, y, w, h, fill=None, stroke=None, r=12):
        return self.rect(x, y, w, h, fill or C["white"], stroke or C["border"], r=r, extra='filter="url(#sh)"')

    def dots(self, path, t0, t1, color, n=4, gap=0.12, r=6):
        """경로를 따라 흐르는 점 n 개 — 데이터가 이동하는 모습."""
        s = []
        for i in range(n):
            a, b = t0 + i * gap, t1 + i * gap
            kt = f"0;{a / self.T:.4f};{b / self.T:.4f};1"
            s.append(
                f'<circle r="{r}" fill="{color}" opacity="0">'
                f'<animateMotion dur="{self.T}s" repeatCount="indefinite" path="{path}" '
                f'keyPoints="0;0;1;1" keyTimes="{kt}" calcMode="linear"/>'
                + self.kf("opacity", [(0, 0), (a - 0.001, 0), (a + 0.05, 1), (b - 0.05, 1), (b, 0)])
                + "</circle>")
        return "".join(s)

    def arrow(self, path, color=None, sw=2, dash=None, extra="", inner=""):
        color = color or C["muted"]
        da = f' stroke-dasharray="{dash}"' if dash else ""
        return (f'<path d="{path}" fill="none" stroke="{color}" stroke-width="{sw}"{da} '
                + ('' if "marker-end" in extra else 'marker-end="url(#ah)" ') + f'{extra}>{inner}</path>')

    def svg(self, title):
        defs = f"""<defs>
<filter id="sh" x="-10%" y="-10%" width="120%" height="130%"><feDropShadow dx="0" dy="2" stdDeviation="4" flood-color="#000" flood-opacity="0.05"/></filter>
<filter id="glow" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="8"/></filter>
<marker id="ah" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{C['muted']}"/></marker>
<marker id="ahr" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{C['orange']}"/></marker>
<marker id="ahg" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{C['green']}"/></marker>
</defs>"""
        style = ('<style>@import url("https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;600;700'
                 '&amp;family=JetBrains+Mono:wght@500&amp;display=swap");</style>')
        return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
                f'viewBox="0 0 {W} {H}" width="{W}" height="{H}"><title>{title}</title>{style}{defs}'
                f'<rect width="{W}" height="{H}" fill="{C["bg"]}"/>' + "".join(self.out) + "</svg>")

    def svg_uniq(self, title, pfx):
        s = self.svg(title)
        for i in ("sh", "glow", "ahr", "ahg", "ah"):
            s = s.replace(f'id="{i}"', f'id="{pfx}{i}"').replace(f"url(#{i})", f"url(#{pfx}{i})")
        return s


# ---------------------------------------------------------------- 공통 부품
def robot(a, x, y, s, moves, color=None):
    """간단한 로봇팔 아이콘 (받침 + 두 마디 + 집게). moves: [(t, 어깨각, 팔꿈치각)]"""
    color = color or C["blue"]
    sh = [(t, f"{q1} 0 0") for t, q1, _ in moves]
    el = [(t, f"{q2} 0 {-70}") for t, _, q2 in moves]
    tr = lambda pts: a.kf("transform", pts).replace('attributeName="transform"',
                                                    'attributeName="transform" attributeType="XML" type="rotate"').replace("<animate ", "<animateTransform ")
    return (f'<g transform="translate({x},{y}) scale({s})">'
            f'<rect x="-30" y="-6" width="60" height="14" rx="4" fill="{C["cardT"]}"/>'
            f'<g>{tr(sh)}'
            f'<rect x="-9" y="-78" width="18" height="78" rx="9" fill="{color}"/>'
            f'<circle cx="0" cy="0" r="12" fill="{C["cardT"]}"/>'
            f'<g transform="translate(0,0)"><g>{tr(el)}'
            f'<rect x="-8" y="-136" width="16" height="66" rx="8" fill="{color}" opacity="0.85"/>'
            f'<circle cx="0" cy="-70" r="10" fill="{C["cardT"]}"/>'
            f'<path d="M-12,-136 L-12,-156 M12,-136 L12,-156" stroke="{C["cardT"]}" stroke-width="6" stroke-linecap="round"/>'
            f'</g></g></g></g>')


def wave(x, y, w, h, noise, seed, n=40):
    random.seed(seed)
    pts = []
    for i in range(n + 1):
        u = i / n
        base = math.sin(u * math.pi * 1.6) * 0.38 + u * 0.25
        pts.append((x + u * w, y + h / 2 - (base + random.uniform(-noise, noise)) * h / 1.4))
    return "M" + " L".join(f"{px:.1f},{py:.1f}" for px, py in pts)


def refine(a, x, y, w, h, t0, step):
    """흐릿한(잡음) 동작 → 4번 다듬어 매끈한 동작. 각 단계를 순서대로 보여 준다."""
    noises = [0.55, 0.32, 0.16, 0.06, 0.0]
    cols = [C["muted"], C["muted"], C["violet"], C["violet"], C["violet"]]
    s = [a.rect(x, y, w, h, C["white"], C["border"], r=8)]
    for k, nz in enumerate(noises):
        a0 = t0 + k * step
        a1 = a0 + step if k < 4 else None
        s.append(f'<path d="{wave(x + 12, y + 8, w - 24, h - 16, nz, 7 + k)}" fill="none" stroke="{cols[k]}" '
                 f'stroke-width="{3 if k == 4 else 2}" stroke-linecap="round" opacity="0">'
                 + a.show(a0, a1 if a1 is None else a1 - 0.05, fade=0.15) + "</path>")
    labels = ["처음엔 무작위", "다듬기 1", "다듬기 2", "다듬기 3", "다듬기 4 → 완성"]
    for k, lb in enumerate(labels):
        a0 = t0 + k * step
        a1 = a0 + step - 0.05 if k < 4 else None
        s.append(a.text(x + w / 2, y + h + 22, lb, 14, C["violet"] if k else C["muted"], 600, "middle",
                        extra='opacity="0"', inner=a.show(a0, a1, fade=0.1)))
    return "".join(s)


def plan_bar(a, x, y, cw, t_fill, t_exec, t_end, gap=4):
    """16칸 동작 계획 막대. 앞 8칸은 실제 실행."""
    s = []
    for i in range(16):
        cx = x + i * (cw + gap)
        ti = t_fill + i * 0.06
        col = C["violet"]
        s.append(a.rect(cx, y, cw, 34, C["sub"], C["border"], r=5))
        s.append(a.rect(cx, y, cw, 34, col, r=5, extra='opacity="0"', inner=a.show(ti, t_end, fade=0.08,
                                                                                  hi=0.35 if i >= 8 else 1)))
        if i < 8:
            te = t_exec + i * 0.18
            s.append(a.rect(cx - 2, y - 2, cw + 4, 38, "none", C["green"], r=6, sw=3, extra='opacity="0"',
                            inner=a.show(te, t_end, fade=0.06)))
    return "".join(s)


def model_shell(a, x, y, w, h, sub):
    return (a.rect(x, y, w, h, C["blueBg"], C["blue"], r=20, sw=2, dash="0") +
            a.rect(x + 24, y - 18, 268, 36, C["blue"], r=18) +
            a.text(x + 158, y + 6, "GR00T N1.6 로봇 AI 모델", 17, "#fff", 700, "middle") +
            a.text(x + w - 24, y + 30, sub, 14, C["blue"], 500, "end"))


# ================================================================ 1. 학습 흐름
def train_svg():
    T = 13.0
    a = Anim(T)
    add = a.add

    # ① 데이터 (왼쪽)
    add(a.text(0, 28, "① 우리가 모은 시연 데이터", 22, C["title"], 700))
    add(a.text(0, 54, "사람이 두 팔을 직접 조종해 392번 시범을 보였습니다", 15))
    cards = [(80, 150, "카메라 영상 3개", "위 · 왼손목 · 오른손목"),
             (246, 78, "지시 문장", ""),
             (340, 78, "로봇 관절 상태", "두 팔 12개 관절의 현재 각도"),
             (434, 96, "정답 동작", "사람이 실제로 움직인 방향")]
    for i, (cy, ch, t1, t2) in enumerate(cards):
        hl = C["green"] if i == 3 else None
        add(a.card(0, cy, 380, ch, stroke=hl))
        add(a.text(20, cy + 32, t1, 20, C["cardT"], 600))
        if t2:
            add(a.text(20, cy + 58, t2, 15))
    for k, nm in enumerate(["cam_top.jpg", "cam_left.jpg", "cam_right.jpg"]):
        add(f'<image href="{img64(nm)}" x="{20 + k * 118}" y="146" width="104" height="78" '
            f'preserveAspectRatio="xMidYMid slice" style="clip-path: inset(0 round 6px)"/>')
    add(a.rect(20, 280, 340, 30, C["sub"], r=6))
    add(a.text(32, 300, '"Put the glue into the cyan bin"', 14, C["cardT"], 500, font=MONO))
    # 정답 동작 미니 그래프
    add(f'<path d="{wave(236, 446, 124, 34, 0, 1, 24)}" fill="none" stroke="{C["green"]}" stroke-width="3" stroke-linecap="round"/>')
    add(a.text(0, 560, "※ 정답 동작은 모델에 넣지 않고, 맞혔는지 채점할 때만 씁니다", 14, C["muted"]))

    # GR00T 본체
    MX, MY, MW, MH = 470, 100, 700, 450
    add(model_shell(a, MX, MY, MW, MH, "NVIDIA 공개 모델을 우리 작업에 맞게 추가 학습"))
    # VLM
    VX, VY, VW, VH = 500, 150, 330, 370
    add(a.rect(VX, VY, VW, VH, C["white"], C["border"], r=14, extra='filter="url(#sh)"'))
    add(a.rect(VX, VY, VW, VH, "none", C["cyan"], r=14, sw=4, extra='opacity="0"', inner=a.show(1.4, 3.6)))
    add(a.text(VX + 20, VY + 36, "VLM", 24, C["cyan"], 700))
    add(a.text(VX + 80, VY + 36, "보고 · 읽는 부분", 20, C["cardT"], 600))
    add(a.text(VX + 20, VY + 62, "사진과 문장을 함께 이해합니다", 15))
    add(a.rect(VX + 20, VY + 84, VW - 40, 82, C["sub"], r=8))
    add(a.text(VX + 36, VY + 116, "눈 — 사진 이해", 17, C["cardT"], 600))
    add(a.text(VX + 36, VY + 142, "이미 잘 보므로 그대로 둠", 14))
    add(a.rect(VX + VW - 92, VY + 102, 56, 26, C["white"], C["border"], r=13))
    add(a.text(VX + VW - 64, VY + 120, "고정", 13, C["muted"], 600, "middle"))
    add(a.rect(VX + 20, VY + 180, VW - 40, 166, C["sub"], r=8))
    add(a.text(VX + 36, VY + 210, "언어 모델 — 16층", 17, C["cardT"], 600))
    add(a.text(VX + 36, VY + 236, "문장 뜻 + 사진 내용 연결", 14))
    for i in range(16):  # 16층 막대, 위 8층은 학습
        ly = VY + 330 - i * 5.4
        col = C["orange"] if i >= 8 else C["border"]
        add(f'<rect x="{VX + 36}" y="{ly:.1f}" width="150" height="3.6" rx="1.8" fill="{col}"/>')
    add(a.rect(VX + 200, VY + 252, 90, 26, C["orangeBg"], C["orange"], r=13))
    add(a.text(VX + 245, VY + 270, "위 8층 학습", 13, C["orange"], 600, "middle"))
    add(a.rect(VX + 200, VY + 300, 90, 26, C["white"], C["border"], r=13))
    add(a.text(VX + 245, VY + 318, "아래 8층 고정", 13, C["muted"], 600, "middle"))
    # 학습 단계에서 주황 층이 깜빡임 (수정되는 중)
    add(f'<rect x="{VX + 30}" y="{VY + 284}" width="162" height="50" rx="6" fill="{C["orange"]}" opacity="0">'
        + a.kf("opacity", [(7.1, 0), (7.4, 0.25), (7.7, 0.05), (8.0, 0.25), (8.3, 0.05), (8.6, 0.25), (8.9, 0)]) + "</rect>")

    # Action head
    AX, AY, AW, AH = 870, 150, 280, 370
    add(a.rect(AX, AY, AW, AH, C["white"], C["border"], r=14, extra='filter="url(#sh)"'))
    add(a.rect(AX, AY, AW, AH, "none", C["violet"], r=14, sw=4, extra='opacity="0"', inner=a.show(3.4, 5.4)))
    add(a.text(AX + 20, AY + 36, "Action head", 22, C["violet"], 700))
    add(a.text(AX + 20, AY + 62, "동작을 만드는 부분", 17, C["cardT"], 600))
    add(a.text(AX + 20, AY + 86, "이해한 내용 + 관절 상태로", 14))
    add(a.text(AX + 20, AY + 106, "앞으로 16걸음 동작을 그림", 14))
    add(refine(a, AX + 20, AY + 130, AW - 40, 120, 3.6, 0.38))
    add(a.rect(AX + 20, AY + 300, AW - 40, 50, C["sub"], r=8))
    add(a.text(AX + AW / 2, AY + 322, "전부 학습", 15, C["orange"], 700, "middle"))
    add(a.text(AX + AW / 2, AY + 341, "(동작 만드는 법을 새로 익힘)", 13, C["body"], 400, "middle"))
    add(f'<rect x="{AX + 20}" y="{AY + 300}" width="{AW - 40}" height="50" rx="8" fill="{C["orange"]}" opacity="0">'
        + a.kf("opacity", [(7.1, 0), (7.4, 0.25), (7.7, 0.05), (8.0, 0.25), (8.3, 0.05), (8.6, 0.25), (8.9, 0)]) + "</rect>")

    # 내부 연결: VLM → AH
    add(a.arrow(f"M{VX + VW},{VY + 260} L{AX - 4},{VY + 260}"))
    add(a.text((VX + VW + AX) / 2, VY + 248, "이해한 내용", 13, C["body"], 500, "middle"))
    add(a.dots(f"M{VX + VW},{VY + 260} L{AX},{VY + 260}", 3.0, 3.5, C["cyan"], 3, 0.1))

    # 입력 화살표 (데이터 → 모델)
    p_cam = f"M380,155 C430,155 440,{VY + 130} {VX - 4},{VY + 130}"
    p_txt = f"M380,285 C430,285 440,{VY + 230} {VX - 4},{VY + 230}"
    p_jnt = f"M380,379 C430,379 420,{MY + MH + 16} 520,{MY + MH + 16} L{AX + 60},{MY + MH + 16} L{AX + 60},{AY + AH + 4}"
    add(a.arrow(p_cam)); add(a.arrow(p_txt)); add(a.arrow(p_jnt))
    add(a.dots(p_cam, 0.3, 1.4, C["cyan"], 4))
    add(a.dots(p_txt, 0.5, 1.6, C["cyan"], 3))
    add(a.dots(p_jnt, 0.6, 2.6, C["blue"], 3, 0.15))

    # ② 채점 (오른쪽)
    RX = 1250
    add(a.text(RX, 28, "② 채점하기", 22, C["title"], 700))
    add(a.text(RX, 54, "모델이 그린 동작과 정답을 비교", 15))
    add(a.card(RX, 100, 470, 230))
    add(a.text(RX + 20, 132, "예측 동작 vs 정답 동작", 18, C["cardT"], 600))
    gx, gy, gw, gh = RX + 24, 150, 420, 150
    gtrue = wave(gx, gy, gw, gh, 0, 1, 24)
    gpred = wave(gx, gy, gw, gh, 0.22, 99, 24)
    add(f'<path d="{gtrue}" fill="none" stroke="{C["green"]}" stroke-width="3" stroke-linecap="round" opacity="0">' + a.show(5.6) + "</path>")
    add(f'<path d="{gpred}" fill="none" stroke="{C["violet"]}" stroke-width="3" stroke-dasharray="7 5" stroke-linecap="round" opacity="0">' + a.show(5.3) + "</path>")
    # 차이 막대 (빨강)
    random.seed(99)
    for i in range(0, 25, 3):
        u = i / 24
        base = math.sin(u * math.pi * 1.6) * 0.38 + u * 0.25
        random.seed(99); nz = [random.uniform(-0.22, 0.22) for _ in range(25)]
        yt = gy + gh / 2 - base * gh / 1.4
        yp = gy + gh / 2 - (base + nz[i]) * gh / 1.4
        add(f'<line x1="{gx + u * gw:.1f}" y1="{yt:.1f}" x2="{gx + u * gw:.1f}" y2="{yp:.1f}" stroke="{C["red"]}" stroke-width="3" opacity="0">'
            + a.show(6.2, fade=0.2) + "</line>")
    add(a.text(RX + 24, 322, "━ 정답", 13, C["green"], 600) + a.text(RX + 100, 322, "┅ 모델 예측", 13, C["violet"], 600)
        + a.text(RX + 210, 322, "┃ 차이(틀린 정도)", 13, C["red"], 600))
    # 정답이 채점판으로 이동
    p_ans = f"M380,500 C420,500 410,{MY + MH + 34} 520,{MY + MH + 34} L1200,{MY + MH + 34} Q1215,{MY + MH + 34} 1215,{MY + MH + 19} L1215,305 Q1215,290 1230,290 L{RX - 4},290"
    add(a.arrow(p_ans, C["green"], 2, "6 6", extra='marker-end="url(#ahg)"'))
    add(a.dots(p_ans, 4.6, 5.6, C["green"], 3))
    # 예측이 채점판으로
    p_pred = f"M{AX + AW},{AY + 190} C{AX + AW + 50},{AY + 190} {RX - 40},215 {RX - 4},215"
    add(a.arrow(p_pred))
    add(a.dots(p_pred, 5.0, 5.5, C["violet"], 3, 0.08))

    # ③ 고치기 (피드백)
    add(a.text(RX, 380, "③ 틀린 만큼 고치기", 22, C["title"], 700))
    add(a.text(RX, 406, "주황색 부분만 조금씩 수정됩니다", 15))
    p_fb = f"M{RX - 4},488 L{MX + MW + 6},488"
    add(a.arrow(p_fb, C["orange"], 3, "8 6", extra='marker-end="url(#ahr)" opacity="0"', inner=a.show(6.8)))
    add(a.dots(p_fb, 6.9, 7.6, C["orange"], 4, 0.1, 7))
    add(a.card(RX, 426, 470, 124, fill=C["orangeBg"], stroke="#FED7AA"))
    add(a.text(RX + 24, 470, "이 과정을 반복", 18, C["cardT"], 600))
    # 반복 카운터
    counts = ["1", "10", "1,000", "20,000", "69,000"]
    for k, cn in enumerate(counts):
        t0 = 7.4 + k * 0.45
        t1 = 7.4 + (k + 1) * 0.45 - 0.02 if k < 4 else None
        add(a.text(RX + 24, 528, f"× {cn} 번", 40, C["orange"], 700, font=MONO, extra='opacity="0"', inner=a.show(t0, t1, fade=0.05)))
    add(a.text(RX + 446, 528, "학습 약 392바퀴", 14, C["body"], 500, "end"))

    # ④ 학습 후 → 동작 (하단 띠)
    BY = 600
    add(a.rect(0, BY, W, 120, C["white"], C["border"], r=14, extra='filter="url(#sh)"'))
    add(a.rect(0, BY, W, 120, C["greenBg"], C["green"], r=14, sw=2, extra='opacity="0"', inner=a.show(9.6, 12.4)))
    add(a.text(28, BY + 48, "④ 학습이 끝나면", 22, C["title"], 700))
    add(a.text(28, BY + 78, "정답 없이도 스스로 동작을 그려 냅니다", 15))
    steps = [(330, "새 카메라 영상 + 지시 문장"), (720, "학습된 GR00T N1.6"), (1080, "16걸음 동작 계획")]
    for k, (sx, lb) in enumerate(steps):
        add(a.rect(sx, BY + 34, 300 if k != 2 else 260, 52, C["sub"], r=10))
        add(a.text(sx + (150 if k != 2 else 130), BY + 66, lb, 17, C["cardT"], 600, "middle"))
    add(a.arrow(f"M634,{BY + 60} L712,{BY + 60}")); add(a.arrow(f"M1024,{BY + 60} L1072,{BY + 60}"))
    add(a.arrow(f"M1344,{BY + 60} L1440,{BY + 60}"))
    add(a.dots(f"M630,{BY + 60} L716,{BY + 60} M716,{BY + 60} L1076,{BY + 60} L1440,{BY + 60}", 9.8, 11.0, C["green"], 3, 0.1))
    add(a.text(1484, BY + 66, "로봇이 움직임", 17, C["green"], 700))
    mv = [(0, 0, 0), (10.9, 0, 0), (11.6, -25, 35), (12.2, 15, -30), (12.8, 0, 0)]
    add(robot(a, 1660, BY + 104, 0.55, mv))
    add(robot(a, 1610, BY + 104, 0.55, [(t, -q1, -q2) for t, q1, q2 in mv], C["cyan"]))
    return a.svg_uniq("GR00T N1.6 학습 흐름", "t-")


# ================================================================ 2. 추론 흐름
def infer_svg():
    T = 11.0
    a = Anim(T)
    add = a.add

    add(a.text(0, 28, "① 지금 보이는 것", 22, C["title"], 700))
    add(a.text(0, 54, "카메라 3대가 동시에 찍습니다", 15))
    cams = [("cam_top.jpg", "위 카메라", "물체와 칸이 어디 있는지 전체"),
            ("cam_right.jpg", "오른손목 카메라", "집을 때 물체를 가까이"),
            ("cam_left.jpg", "왼손목 카메라", "건네받고 놓을 때 가까이")]
    for k, (nm, t1, t2) in enumerate(cams):
        cy = 80 + k * 128
        add(a.card(0, cy, 380, 112))
        add(f'<image href="{img64(nm)}" x="12" y="{cy + 10}" width="122" height="92" preserveAspectRatio="xMidYMid slice"/>')
        add(a.rect(12, cy + 10, 122, 92, "#fff", r=4, extra='opacity="0"',
                   inner=a.kf("opacity", [(0.2 + k * 0.25, 0), (0.25 + k * 0.25, 0.9), (0.6 + k * 0.25, 0)])))
        add(a.text(150, cy + 44, t1, 18, C["cardT"], 600))
        add(a.text(150, cy + 70, t2, 14))
    add(a.card(0, 470, 380, 70))
    add(a.text(20, 498, "지시 문장", 15, C["cardT"], 600))
    add(a.text(20, 524, '"Put the glue into the cyan bin"', 13, C["cardT"], 500, font=MONO))
    add(a.card(0, 552, 380, 46))
    add(a.text(20, 581, "로봇 관절 상태 (12개 각도)", 15, C["cardT"], 600))

    MX, MY, MW, MH = 450, 90, 790, 510
    add(model_shell(a, MX, MY, MW, MH, "GPU 컴퓨터에서 계산 (RTX 5070 Ti)"))
    VX, VY, VW, VH = 480, 140, 400, 430
    add(a.rect(VX, VY, VW, VH, C["white"], C["border"], r=14, extra='filter="url(#sh)"'))
    add(a.rect(VX, VY, VW, VH, "none", C["cyan"], r=14, sw=4, extra='opacity="0"', inner=a.show(1.4, 3.8)))
    add(a.text(VX + 20, VY + 36, "VLM", 24, C["cyan"], 700))
    add(a.text(VX + 80, VY + 36, "보고 · 읽는 부분", 20, C["cardT"], 600))
    add(a.text(VX + 20, VY + 62, "사진 3장을 작은 조각으로 나눠 살펴보고", 15))
    add(a.text(VX + 20, VY + 84, "문장의 단어와 짝지어 이해합니다", 15))
    # 사진 → 조각 격자
    for k, nm in enumerate(["cam_top.jpg", "cam_right.jpg", "cam_left.jpg"]):
        ix = VX + 20 + k * 124
        add(f'<image href="{img64(nm)}" x="{ix}" y="{VY + 104}" width="112" height="84" preserveAspectRatio="xMidYMid slice"/>')
        grid = "".join(f'<line x1="{ix + g * 14}" y1="{VY + 104}" x2="{ix + g * 14}" y2="{VY + 188}" />' for g in range(1, 8)) + \
               "".join(f'<line x1="{ix}" y1="{VY + 104 + g * 14}" x2="{ix + 112}" y2="{VY + 104 + g * 14}" />' for g in range(1, 6))
        add(f'<g stroke="#fff" stroke-width="1.5" opacity="0">{grid}' + a.show(1.6 + k * 0.15, 3.8) + "</g>")
    add(a.text(VX + VW / 2, VY + 210, "사진 조각", 13, C["muted"], 500, "middle"))
    words = ["Put", "the", "glue", "into", "the", "cyan", "bin"]
    wx = VX + 24
    for k, wd in enumerate(words):
        ww = 14 + len(wd) * 10
        key = wd in ("glue", "cyan")
        add(a.rect(wx, VY + 226, ww, 28, C["sub"], r=6))
        if key:
            add(a.rect(wx, VY + 226, ww, 28, C["cyanBg"], C["cyan"], r=6, sw=2, extra='opacity="0"', inner=a.show(2.2, 3.8)))
        add(a.text(wx + ww / 2, VY + 245, wd, 14, C["cardT"], 600 if key else 400, "middle", font=MONO))
        wx += ww + 6
    add(a.text(VX + VW / 2, VY + 276, "문장 단어", 13, C["muted"], 500, "middle"))
    # 이해 결과
    add(a.rect(VX + 20, VY + 300, VW - 40, 104, C["sub"], r=10))
    add(a.text(VX + 40, VY + 330, "이해한 내용", 16, C["cardT"], 600))
    for k, (lb, t0) in enumerate([("무엇을 → 풀(glue) 은 여기", 2.5), ("어디로 → 하늘색(cyan) 칸", 2.8)]):
        add(a.text(VX + 40, VY + 360 + k * 26, lb, 15, C["cyan"], 600, extra='opacity="0"', inner=a.show(t0, 10.5)))
    add(a.dots(f"M{VX + VW / 2},{VY + 190} L{VX + VW / 2},{VY + 300}", 2.0, 2.5, C["cyan"], 3, 0.1, 5))

    AX, AY, AW, AH = 920, 140, 290, 430
    add(a.rect(AX, AY, AW, AH, C["white"], C["border"], r=14, extra='filter="url(#sh)"'))
    add(a.rect(AX, AY, AW, AH, "none", C["violet"], r=14, sw=4, extra='opacity="0"', inner=a.show(3.6, 6.0)))
    add(a.text(AX + 20, AY + 36, "Action head", 22, C["violet"], 700))
    add(a.text(AX + 20, AY + 62, "동작을 만드는 부분", 17, C["cardT"], 600))
    add(a.text(AX + 20, AY + 86, "무작위 동작에서 시작해", 14))
    add(a.text(AX + 20, AY + 106, "4번 다듬어 완성합니다", 14))
    add(refine(a, AX + 20, AY + 130, AW - 40, 140, 3.8, 0.45))
    add(a.rect(AX + 20, AY + 320, AW - 40, 86, C["sub"], r=10))
    add(a.text(AX + AW / 2, AY + 352, "결과: 앞으로 16걸음", 16, C["cardT"], 600, "middle"))
    add(a.text(AX + AW / 2, AY + 378, "두 팔 12개 관절 × 16걸음", 14, C["body"], 400, "middle"))
    add(a.arrow(f"M{VX + VW},{VY + 352} L{AX - 4},{VY + 352}"))
    add(a.dots(f"M{VX + VW},{VY + 352} L{AX},{VY + 352}", 3.3, 3.8, C["cyan"], 3, 0.08))

    # 입력 화살표
    for k in range(3):
        p = f"M380,{136 + k * 128} C420,{136 + k * 128} 430,{VY + 146} {VX - 4},{VY + 146}"
        add(a.arrow(p)); add(a.dots(p, 0.4 + k * 0.2, 1.4 + k * 0.2, C["cyan"], 3))
    p_t = f"M380,505 C430,505 430,{VY + 240} {VX - 4},{VY + 240}"
    add(a.arrow(p_t)); add(a.dots(p_t, 0.8, 1.7, C["cyan"], 3))
    p_j = f"M380,575 C600,640 {AX - 60},640 {AX + 40},{AY + AH + 4}"
    add(a.arrow(p_j)); add(a.dots(p_j, 1.0, 3.4, C["blue"], 3, 0.2))

    # ② 동작 계획 → 실행
    RX = 1290
    add(a.text(RX, 28, "② 계획하고 움직이기", 22, C["title"], 700))
    add(a.text(RX, 54, "앞 8걸음만 실행하고 다시 봅니다", 15))
    add(a.card(RX, 90, 430, 200))
    add(a.text(RX + 20, 124, "16걸음 동작 계획", 18, C["cardT"], 600))
    add(plan_bar(a, RX + 18, 144, 21, 6.1, 7.0, 10.4, gap=3.5))
    add(a.text(RX + 18, 206, "실행 (8걸음)", 13, C["green"], 600))
    add(a.text(RX + 412, 206, "버림 → 새 계획으로 교체", 13, C["muted"], 500, "end"))
    add(a.text(RX + 20, 246, "이전 계획과 섞어 부드럽게 이어 붙임", 14))
    add(a.text(RX + 20, 270, "(갑자기 튀는 동작 방지)", 13, C["muted"]))
    p_out = f"M{AX + AW},{AY + 360} C{AX + AW + 40},{AY + 360} {RX - 40},160 {RX - 4},160"
    add(a.arrow(p_out)); add(a.dots(p_out, 5.9, 6.4, C["violet"], 3, 0.08))
    add(a.card(RX, 310, 430, 290))
    add(a.rect(RX, 310, 430, 290, C["greenBg"], C["green"], r=12, sw=2, extra='opacity="0"', inner=a.show(7.0, 8.9)))
    add(a.text(RX + 20, 344, "두 팔 실행", 18, C["cardT"], 600))
    add(a.text(RX + 20, 368, "오른팔이 집어 건네고 · 왼팔이 칸에 놓기", 14))
    mv = [(0, 0, 0), (7.0, 0, 0), (7.7, -30, 40), (8.4, 10, -25), (9.0, 0, 0)]
    add(robot(a, RX + 290, 572, 0.95, mv))
    add(robot(a, RX + 140, 572, 0.95, [(t, -q1, -q2) for t, q1, q2 in mv], C["cyan"]))
    add(a.text(RX + 140, 404, "왼팔", 13, C["muted"], 600, "middle") + a.text(RX + 290, 404, "오른팔", 13, C["muted"], 600, "middle"))

    # ③ 반복 고리 (실행 → 다시 카메라)
    p_loop = f"M{RX + 215},600 L{RX + 215},660 L190,660 L190,604"
    add(a.arrow(p_loop, C["green"], 3, "8 6", extra='marker-end="url(#ahg)"'))
    add(a.dots(p_loop, 9.0, 10.6, C["green"], 4, 0.12, 7))
    add(a.rect(560, 640, 600, 40, C["white"], C["green"], r=20, sw=2))
    add(a.text(860, 667, "③ 8걸음(약 0.3초)마다 다시 찍고 → 다시 계획 → 반복", 16, C["green"], 700, "middle"))
    add(a.text(W - 6, 710, "물체를 칸에 넣고 팔이 제자리로 돌아오면 끝", 14, C["muted"], 500, "end"))
    return a.svg_uniq("GR00T N1.6 추론 흐름", "i-")


if __name__ == "__main__":
    tr, inf = train_svg(), infer_svg()
    for nm, s in (("train_flow.svg", tr), ("infer_flow.svg", inf)):
        with open(os.path.join(HERE, nm), "w") as f:
            f.write(s)
    # 미리보기 HTML — 두 블록도를 한 페이지에, #frame=<name>@<t> 이면 그 시점에 멈춤 (GIF 렌더용)
    html = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>GR00T 학습·추론 흐름</title>
<style>body{{margin:0;background:{C['bg']};font-family:{FONT}}} section{{padding:40px 100px}}
h2{{color:{C['title']};font-size:28px;margin:0 0 16px}} .frame section{{padding:0}} .frame h2{{display:none}}
.frame section:not(.on){{display:none}}</style></head><body>
<section id="train"><h2>학습 흐름</h2>{tr}</section>
<section id="infer"><h2>추론 흐름</h2>{inf}</section>
<script>
const m = location.hash.match(/frame=(\\w+)@([\\d.]+)/);
if (m) {{
  document.body.classList.add('frame');
  const sec = document.getElementById(m[1]); sec.classList.add('on');
  const svg = sec.querySelector('svg'); svg.pauseAnimations(); svg.setCurrentTime(parseFloat(m[2]));
}}
</script></body></html>"""
    with open(os.path.join(HERE, "flow_anim.html"), "w") as f:
        f.write(html)
    print("ok", len(tr) // 1024, "KB /", len(inf) // 1024, "KB")
