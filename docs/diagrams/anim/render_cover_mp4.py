#!/usr/bin/env python3
"""표지 애니메이션(cover_vla.html)을 고품질 MP4 로 녹화 — Figma 슬라이드 표지에 영상으로 넣기 위함.

python3 render_cover_mp4.py [--fps 60] [--jobs 12]
  → cover_vla.mp4     1920×1080 (2배 해상도로 찍어 lanczos 축소 = 슈퍼샘플링)
  → cover_vla_4k.mp4  3840×2160 (같은 프레임 그대로)

- 헤드리스 크롬으로 cover_vla.html?render#t 를 device-scale-factor 2 로 프레임마다 찍는다.
- 글꼴은 fonts/gf 로컬 파일 사용(네트워크 실패로 대체 글꼴이 섞이는 일 방지).
- 색: RGB→YUV 변환을 BT.709 로 하고 태그도 BT.709 로 붙인다(재생기 해석과 일치 → 색 틀어짐 없음).
"""
import argparse, os, shutil, subprocess, tempfile
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
HTML = os.path.join(HERE, "cover_vla.html")
CHROME = shutil.which("google-chrome") or "google-chrome"
T_END = 13.8
COLOR = ["-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv"]


def encode(frames, fps, vf, crf, out):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(fps), "-i", os.path.join(frames, "%05d.png"),
                    "-vf", vf + ":out_color_matrix=bt709:out_range=tv,format=yuv420p",
                    "-c:v", "libx264", "-preset", "slower", "-tune", "animation", "-crf", str(crf), "-profile:v", "high",
                    *COLOR, "-movflags", "+faststart", out], check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fps", type=int, default=60)
    ap.add_argument("--jobs", type=int, default=12)
    ap.add_argument("--keep", help="프레임 PNG 를 이 폴더에 남김")
    a = ap.parse_args()
    n = int(round(T_END * a.fps)) + 1
    tmp = a.keep or tempfile.mkdtemp(prefix="cover_frames_")
    os.makedirs(tmp, exist_ok=True)

    def one(i):
        out = os.path.join(tmp, f"{i:05d}.png")
        for _ in range(3):
            subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--allow-file-access-from-files",
                            "--force-device-scale-factor=2", "--window-size=1920,1080", "--virtual-time-budget=8000",
                            "--run-all-compositor-stages-before-draw",
                            f"--screenshot={out}", f"file://{HTML}?render#{i / a.fps:.4f}"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.path.exists(out) and os.path.getsize(out) > 20000:
                return
        raise RuntimeError(f"frame {i} 실패")

    with ThreadPoolExecutor(a.jobs) as ex:
        list(ex.map(one, range(n)))
    encode(tmp, a.fps, "scale=1920:1080:flags=lanczos", 10, os.path.join(HERE, "cover_vla.mp4"))
    encode(tmp, a.fps, "scale=3840:2160", 12, os.path.join(HERE, "cover_vla_4k.mp4"))
    if not a.keep:
        shutil.rmtree(tmp)
    print("done", n, "frames")


if __name__ == "__main__":
    main()
