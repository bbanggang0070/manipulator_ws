#!/usr/bin/env python3
"""학습 / 추론 흐름 애니메이션을 MP4 로 녹화 — Figma 슬라이드에 영상으로 넣기 위함.

python3 render_flow_n16_mp4.py [--fps 15] [--jobs 8]
  → train_flow_n16.mp4 (5개 장면 1주기 = 60초), infer_flow_n16.mp4 (평가 영상 길이에 맞춘 48초)

방법: 헤드리스 크롬으로 SVG 를 프레임마다 setCurrentTime(t) 해서 PNG 로 찍는다.
추론은 카메라 3칸 + 로봇 칸을 투명하게 뚫어 두고, ffmpeg 가 그 아래에 실기 평가 영상의
같은 순간(위 · 왼손목 · 오른손목)을 깔아 합성한다 → 입력 화면과 로봇 동작이 프레임 단위로 맞는다.
"""
import argparse, os, shutil, subprocess, tempfile
from concurrent.futures import ThreadPoolExecutor

import make_flow_n16 as F

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "../../../inf_video/07_real_eval_bi/bi392llm8_B/trial39_t05/video.mp4")  # 1920×480, 위|왼손목|오른손목
CHROME = shutil.which("google-chrome") or "google-chrome"


def frame_html(svg):
    return ('<!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0;background:transparent}'
            'svg{display:block}</style></head><body>' + svg +
            '<script>const s=document.querySelector("svg");s.pauseAnimations();'
            's.setCurrentTime(parseFloat(location.hash.slice(1)));</script></body></html>')


def shoot(html, h, frames_dir, fps, n, jobs):
    def one(i):
        out = os.path.join(frames_dir, f"{i:05d}.png")
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                        "--default-background-color=00000000", f"--window-size={F.W},{h}",
                        "--virtual-time-budget=2000", f"--screenshot={out}", f"file://{html}#{i / fps:.4f}"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    with ThreadPoolExecutor(jobs) as ex:
        list(ex.map(one, range(n)))


def encode(cmd):
    subprocess.run(["ffmpeg", "-v", "error", "-y"] + cmd, check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fps", type=int, default=15)
    ap.add_argument("--jobs", type=int, default=8)
    a = ap.parse_args()
    tmp = tempfile.mkdtemp(prefix="flow_n16_")
    x264 = ["-c:v", "libx264", "-crf", "18", "-preset", "slow", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]

    # 학습 — 영상 칸 없음, 5개 장면 × 12초
    svg = F.train_svg()
    h = int(svg.split('height="')[1].split('"')[0])
    html = os.path.join(tmp, "train.html")
    open(html, "w").write(frame_html(svg))
    fd = os.path.join(tmp, "train"); os.makedirs(fd)
    n = int(len(F.SETS) * F.T * a.fps)
    print(f"학습: {n} 프레임 렌더 중…", flush=True)
    shoot(html, h, fd, a.fps, n, a.jobs)
    encode(["-framerate", str(a.fps), "-i", f"{fd}/%05d.png", "-vf", "format=yuv420p"] + x264 +
           [os.path.join(HERE, "train_flow_n16.mp4")])

    # 추론 — 영상 칸을 뚫은 SVG + 그 아래 실기 영상
    F.HOLES = []
    svg = F.infer_svg()
    holes = list(F.HOLES)
    F.HOLES = None
    h = int(svg.split('height="')[1].split('"')[0])
    html = os.path.join(tmp, "infer.html")
    open(html, "w").write(frame_html(svg))
    fd = os.path.join(tmp, "infer"); os.makedirs(fd)
    dur = 4 * F.T                                    # 48초 = 흐름 4주기, 평가 영상(49초)과 거의 같은 길이
    n = int(dur * a.fps)
    print(f"추론: {n} 프레임 렌더 중… (영상 칸 {len(holes)}개)", flush=True)
    shoot(html, h, fd, a.fps, n, a.jobs)
    crop_x = {0: 0, 1: 640, 2: 1280}                # 원본 영상: 위 | 왼손목 | 오른손목
    fc = [f"[0:v]fps={a.fps},split={len(holes)}" + "".join(f"[s{i}]" for i in range(len(holes)))]
    for i, (x, y, w, hh, c) in enumerate(holes):
        fc.append(f"[s{i}]crop=640:480:{crop_x[c]}:0,scale={w}:{hh}[v{i}]")
    prev = "[1:v]"
    for i, (x, y, w, hh, c) in enumerate(holes):
        fc.append(f"{prev}[v{i}]overlay={x}:{y}[b{i}]")
        prev = f"[b{i}]"
    fc.append(f"{prev}[2:v]overlay=0:0,format=yuv420p[out]")
    encode(["-t", f"{dur}", "-i", SRC,
            "-f", "lavfi", "-t", f"{dur}", "-i", f"color=white:s={F.W}x{h}:r={a.fps}",
            "-framerate", str(a.fps), "-i", f"{fd}/%05d.png",
            "-filter_complex", ";".join(fc), "-map", "[out]", "-t", f"{dur}"] + x264 +
           [os.path.join(HERE, "infer_flow_n16.mp4")])
    shutil.rmtree(tmp)
    print("완료")


if __name__ == "__main__":
    main()
