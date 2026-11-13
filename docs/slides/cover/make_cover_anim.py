#!/usr/bin/env python3
"""표지 애니메이션 — 오른손목 카메라가 실제로 검은 마커에 다가가 잡는 영상 위에 탐색 · 고정 · 추적 상자를 얹는다.

python3 make_cover_anim.py [--fps 20] [--jobs 12]
  → cover_wrist_detect.svg  (영상 위에 겹치는 HUD · bounding box 층, SMIL 10초 뒤 멈춤)
    cover_wrist_src.mp4     (밑에 까는 손목 카메라 구간 720×540)
    cover_wrist_detect.html (미리보기 — 영상 + SVG 층, 클릭하면 처음부터)
    cover_wrist_detect.mp4 / .gif (Figma 표지 칸 720×900 용 합성본)

원본 = 평가 19 “Put the black marker into the white bin” 의 오른손목 화면(1920×480 중 x 1280~1920, 10fps) 2.5~11.5초
+ 마지막 장면 1초 정지 = 10초. 상자 좌표는 원본 640×480 에서 0.5초 간격으로 직접 잡은 값을 보간한다.
타임라인(초): 0~0.5 화면 켜짐 · 0.5~2.5 상자가 빨대 · 빨간 마커 · 빈 곳을 헤맴 · 2.5 검은 마커에 고정 → 다가가며 추적 · 8.6 잡기
"""
import argparse, os, shutil, subprocess, tempfile
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "../../../inf_video/07_real_eval_bi/bi392llm8_A/trial19_t01/video.mp4")
CHROME = shutil.which("google-chrome") or "google-chrome"
W, H = 720, 900                  # Figma 표지 칸
VY, VS = 180, 720 / 640          # 영상 칸: y 180~720, 원본 640×480 → 720×540
T0, T = 2.5, 10.0                # 원본 시작 시각 · 전체 길이
SANS = "'IBM Plex Sans KR', 'Noto Sans CJK KR', Helvetica, Arial, sans-serif"
MONO = "'JetBrains Mono', 'DejaVu Sans Mono', Menlo, monospace"
SEARCH, LOCK, OK, BG = "#f59e0b", "#3b82f6", "#22c55e", "#0f172a"
LOCK_T, GRASP_T = 2.5, 8.6

# (출력 시각, x, y, w, h) — 원본 640×480 좌표. 2.5초까지는 헤매는 자리, 이후는 검은 마커
BOX = [(0.5, 240, 150, 160, 130), (0.9, 210, 0, 100, 250), (1.3, 330, 0, 105, 200), (1.7, 420, 180, 150, 120),
       (2.0, 300, 20, 140, 180), (2.3, 250, 0, 150, 230),
       (2.5, 230, 0, 125, 215), (3.0, 205, 0, 142, 258), (3.5, 212, 0, 182, 268), (4.0, 195, 0, 135, 290),
       (4.5, 252, 0, 95, 275), (5.0, 252, 0, 118, 320), (5.5, 270, 0, 165, 395), (6.0, 285, 0, 215, 478), (6.5, 305, 0, 260, 478),
       (7.0, 305, 0, 260, 478), (7.5, 300, 0, 255, 478), (8.0, 195, 0, 215, 478), (T, 195, 0, 215, 478)]


def kt(ts):
    return ";".join(f"{t / T:.4f}" for t in ts)


def anim(attr, pts, spline=True):
    """pts = [(시각, 값)] — 0초 값으로 시작해 마지막 값에서 멈춘다."""
    if pts[0][0] > 0:
        pts = [(0, pts[0][1])] + pts
    if pts[-1][0] < T:
        pts = pts + [(T, pts[-1][1])]
    sp = f' calcMode="spline" keySplines="{";".join(["0.45 0 0.3 1"] * (len(pts) - 1))}"' if spline else ""
    return (f'<animate attributeName="{attr}" dur="{T}s" fill="freeze"{sp} keyTimes="{kt([t for t, _ in pts])}" '
            f'values="{";".join(str(v) for _, v in pts)}"/>')


def step(attr, pts):
    return (f'<animate attributeName="{attr}" dur="{T}s" fill="freeze" calcMode="discrete" '
            f'keyTimes="{kt([t for t, _ in pts])}" values="{";".join(str(v) for _, v in pts)}"/>')


def box_anim(pts):
    m = lambda i, v: round(v * VS + (VY if i == 2 else 0), 1)
    return "".join(anim(a, [(b[0], m(i, b[i])) for b in pts], spline=False) for i, a in ((1, "x"), (2, "y"), (3, "width"), (4, "height")))


def svg():
    search = [b for b in BOX if b[0] <= LOCK_T]
    track = [b for b in BOX if b[0] >= LOCK_T]
    # 고정 뒤 라벨은 상자 아래 끝을 따라가되 영상 칸 안에 머문다
    lab_y = [(b[0], round(min(VY + (b[2] + b[4]) * VS + 6, VY + 540 - 30), 1)) for b in track]
    lab_x = [(b[0], round(b[1] * VS, 1)) for b in track]
    hud = "".join(f'<path d="M{x},{y + dy * 26} L{x},{y} L{x + dx * 26},{y}" fill="none" stroke="#fff" stroke-opacity="0.8" stroke-width="3"/>'
                  for x, y, dx, dy in ((16, VY + 16, 1, 1), (W - 16, VY + 16, -1, 1), (16, VY + 524, 1, -1), (W - 16, VY + 524, -1, -1)))
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="오른손목 카메라가 검은 마커를 찾아 다가가 잡는 장면">
<title>Wrist camera approach</title>
<rect width="{W}" height="{VY}" fill="{BG}"/><rect y="{VY + 540}" width="{W}" height="{H - VY - 540}" fill="{BG}"/>
<rect y="{VY}" width="{W}" height="540" fill="{BG}">{anim("opacity", [(0, 1), (0.5, 0)])}</rect>
<!-- 헤매는 상자 -->
<rect fill="{SEARCH}" fill-opacity="0.07" stroke="{SEARCH}" stroke-width="3" stroke-dasharray="10 7" rx="4" opacity="0">
  {box_anim(search)}{step("opacity", [(0, 0), (0.5, 1), (LOCK_T, 0), (T, 0)])}</rect>
<!-- 고정 후 추적 상자 -->
<g opacity="0">{step("opacity", [(0, 0), (LOCK_T, 1), (T, 1)])}
  <rect fill="{LOCK}" fill-opacity="0.08" stroke="{LOCK}" stroke-width="3.5" rx="4">{box_anim(track)}
    {step("stroke", [(0, LOCK), (GRASP_T, OK), (T, OK)])}{step("fill", [(0, LOCK), (GRASP_T, OK), (T, OK)])}</rect>
  <g>{anim("opacity", [(0, 0), (LOCK_T, 0), (LOCK_T + 0.3, 1)])}
    <rect height="26" rx="4" fill="{LOCK}" width="150">{anim("x", lab_x, False)}{anim("y", lab_y, False)}{step("fill", [(0, LOCK), (GRASP_T, OK), (T, OK)])}</rect>
    <text font-family="{MONO}" font-size="15" font-weight="bold" fill="#fff">{anim("x", [(t, v + 8) for t, v in lab_x], False)}{anim("y", [(t, v + 18) for t, v in lab_y], False)}black marker</text>
  </g>
</g>
<rect x="0" width="{W}" height="3" fill="#fff" opacity="0">{anim("y", [(0, VY), (0.5, VY), (LOCK_T, VY + 540)], False)}{step("opacity", [(0, 0), (0.5, 0.35), (LOCK_T, 0), (T, 0)])}</rect>
{hud}
<!-- 위 띠: 카메라 · 지시문 -->
<circle cx="40" cy="52" r="7" fill="#ef4444"><animate attributeName="opacity" dur="1s" repeatCount="10" values="1;0.2;1"/></circle>
<text x="56" y="58" font-family="{MONO}" font-size="17" font-weight="bold" fill="#fff">WRIST CAM · RIGHT ARM</text>
<text x="{W - 32}" y="58" text-anchor="end" font-family="{MONO}" font-size="15" fill="#94a3b8">LIVE</text>
<text x="32" y="104" font-family="{MONO}" font-size="19" fill="#e2e8f0">“Put the black marker</text>
<text x="32" y="132" font-family="{MONO}" font-size="19" fill="#e2e8f0">  into the white bin”</text>
<!-- 아래 띠: 상태 -->
<g font-family="{MONO}" font-size="19" font-weight="bold">
  <text x="32" y="{VY + 590}" fill="{SEARCH}" opacity="0">{step("opacity", [(0, 0), (0.5, 1), (LOCK_T, 0), (T, 0)])}● SEARCHING…</text>
  <text x="32" y="{VY + 590}" fill="#93c5fd" opacity="0">{step("opacity", [(0, 0), (LOCK_T, 1), (GRASP_T, 0), (T, 0)])}● LOCKED · APPROACHING</text>
  <text x="32" y="{VY + 590}" fill="{OK}" opacity="0">{step("opacity", [(0, 0), (GRASP_T, 1), (T, 1)])}● GRASP</text>
</g>
<rect x="32" y="{VY + 612}" width="{W - 64}" height="6" rx="3" fill="#334155"/>
<rect x="32" y="{VY + 612}" height="6" rx="3" fill="{LOCK}" width="0">{anim("width", [(0, 0), (LOCK_T, 0), (GRASP_T, W - 64)], False)}{step("fill", [(0, LOCK), (GRASP_T, OK), (T, OK)])}</rect>
<text x="32" y="{VY + 650}" font-family="{SANS}" font-size="16" fill="#94a3b8">GR00T N1.6 · 오른팔이 지시한 물체로 다가가 집는다</text>
</svg>"""


def page(s, video=True):
    v = ('<video id="v" src="cover_wrist_src.mp4" muted playsinline autoplay preload="auto" '
         f'style="position:absolute;left:0;top:{VY / H * 100:.2f}%;width:100%"></video>') if video else ""
    return ('<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Wrist camera approach</title><style>html,body{margin:0;background:' + ("#0f172a" if video else "transparent") + '}'
            'main{position:relative;width:min(720px,100vw);margin:0 auto;cursor:pointer}svg{position:relative;width:100%;height:auto;display:block}'
            'p{text-align:center;color:#94a3b8;font:14px sans-serif}</style></head>'
            f'<body><main>{v}{s}</main>' + ('<p>클릭하면 처음부터 다시 재생</p>' if video else '') +
            '<script>const s=document.querySelector("svg"),v=document.getElementById("v");'
            'document.querySelector("main").addEventListener("click",()=>{s.setCurrentTime(0);s.unpauseAnimations();if(v){v.currentTime=0;v.play();}});'
            'const m=location.hash.match(/t=([\\d.]+)/);if(m){s.pauseAnimations();s.setCurrentTime(parseFloat(m[1]));}</script></body></html>')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fps", type=int, default=20)
    ap.add_argument("--jobs", type=int, default=12)
    a = ap.parse_args()
    base = os.path.join(HERE, "cover_wrist_detect")
    src = os.path.join(HERE, "cover_wrist_src.mp4")
    run = lambda c: subprocess.run(["ffmpeg", "-v", "error", "-y"] + c, check=True)
    hold = T - 9.0
    run(["-ss", str(T0), "-t", "9", "-i", SRC, "-vf", f"crop=640:480:1280:0,scale=720:540,fps={a.fps},tpad=stop_mode=clone:stop_duration={hold}",
         "-an", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", src])
    s = svg()
    open(base + ".svg", "w").write(s)
    open(base + ".html", "w").write(page(s))
    tmp = tempfile.mkdtemp(prefix="cover_")
    open(f"{tmp}/f.html", "w").write(page(s, video=False))
    n = int(T * a.fps)

    def shoot(i):
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--default-background-color=00000000",
                        f"--window-size={W},{H}", "--virtual-time-budget=2000", f"--screenshot={tmp}/{i:04d}.png",
                        f"file://{tmp}/f.html#t={min(i / a.fps, T - 0.01):.3f}"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    with ThreadPoolExecutor(a.jobs) as ex:
        list(ex.map(shoot, range(n)))
    comp = ["-f", "lavfi", "-i", f"color={BG}:s={W}x{H}:r={a.fps}:d={T}", "-i", src, "-framerate", str(a.fps), "-i", f"{tmp}/%04d.png",
            "-filter_complex", f"[0][1]overlay=0:{VY}[b];[b][2]overlay=0:0,format=yuv420p,trim=duration={T}[o]", "-map", "[o]"]
    run(comp + ["-c:v", "libx264", "-crf", "18", "-movflags", "+faststart", base + ".mp4"])
    # GIF 는 한 번만 재생(-loop -1)하고 마지막 장면(잡은 순간)에서 멈춘다
    run(["-i", base + ".mp4", "-vf", "fps=10,scale=480:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];"
         "[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle", "-loop", "-1", base + ".gif"])
    shutil.rmtree(tmp)
    for f in (base + ".svg", base + ".html", src, base + ".mp4", base + ".gif"):
        print(os.path.basename(f), os.path.getsize(f) // 1024, "KB")


if __name__ == "__main__":
    main()
