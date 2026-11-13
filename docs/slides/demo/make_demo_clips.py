#!/usr/bin/env python3
"""13장 「시연 영상」 4칸용 클립 — 최종 모델(392회 · 8층) 평가 영상에서 골라 편집한다.

python3 make_demo_clips.py [--speed 2]
  → demo01_full_success.mp4 · demo02_marker.mp4 · demo03_same_scene.mp4 · demo04_new_layout.mp4 (+ 같은 이름 .jpg 포스터)

화면은 칸 비율(약 2.5:1)에 맞춘 1280×512.
  단일 시행: 위 카메라(크게) | 손목 카메라 2대(세로로) | 지시문 · 결과 패널
  03 같은 장면: 두 시행의 위 카메라를 나란히 + 아래 지시문 띠
원본 영상은 1920×480 = 위 | 왼손목 | 오른손목, 10fps.
"""
import argparse, os, subprocess, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
EV = os.path.join(HERE, "../../../inf_video/07_real_eval_bi")
FONT = {"Regular": "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "Bold": "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"}
INK, MUTED, BLUE, GREEN, LINE = "0x0f172a", "0x64748b", "0x2563eb", "0x16a34a", "0xe2e8f0"

# 평가표: manipulator_md/p6_real_bimanual/bi392llm8_eval_B.csv (집기 · 전달 · 칸 모두 성공한 시행만)
SINGLE = [
    ("demo01_full_success", "bi392llm8_A/trial01_t01", ["Put the yellow straw", "into the pink bin"], "노란 빨대 → 분홍 칸", "평가 01 · 학습한 칸 배치"),
    ("demo02_marker", "bi392llm8_A/trial19_t01", ["Put the black marker", "into the white bin"], "검은 마커 → 흰 칸", "평가 19 · 마커 두 개 중"),
    ("demo04_new_layout", "bi392llm8_B/trial43_t01", ["Put the toothbrush", "into the white bin"], "칫솔 → 흰 칸", "평가 43 · 처음 보는 칸 배치"),
]
PAIR = ("demo03_same_scene",
        [("bi392llm8_B/trial37_t02", "① …screwdriver into the white bin  → 흰 칸"),
         ("bi392llm8_B/trial38_t01", "② …screwdriver into the cyan bin  → 청록 칸")])


def dt(tmp, text, x, y, size, color, style="Regular"):
    """drawtext — 글자는 파일로 넘겨 이스케이프 문제를 피한다."""
    p = os.path.join(tmp, f"t{abs(hash((text, x, y)))}.txt")
    open(p, "w").write(text)
    return f"drawtext=fontfile='{FONT[style]}':textfile='{p}':x={x}:y={y}:fontsize={size}:fontcolor={color}"


def run(args):
    subprocess.run(["ffmpeg", "-v", "error", "-y"] + args, check=True)


def encode(src_args, fc, out, speed):
    x264 = ["-c:v", "libx264", "-crf", "20", "-preset", "slow", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an"]
    run(src_args + ["-filter_complex", fc, "-map", "[out]", "-r", str(int(10 * speed))] + x264 + [out + ".mp4"])
    # 포스터: 마지막 장면(물체가 칸에 들어간 뒤)
    run(["-sseof", "-0.5", "-i", out + ".mp4", "-frames:v", "1", "-q:v", "3", out + ".jpg"])


def single(tmp, name, trial, lines, ko, sub, speed):
    PX, PW = 1024, 256
    t = [dt(tmp, "위", 12, 10, 18, "white", "Bold"),
         dt(tmp, "왼손목", 695, 10, 16, "white", "Bold"),
         dt(tmp, "오른손목", 695, 266, 16, "white", "Bold"),
         dt(tmp, "지시문", PX + 22, 26, 16, BLUE, "Bold")]
    t += [dt(tmp, s, PX + 22, 56 + i * 28, 19, INK) for i, s in enumerate(lines)]
    t += [dt(tmp, ko, PX + 22, 128, 22, INK, "Bold")]
    for i, s in enumerate(["물체 집기", "두 팔 전달", "칸 넣기"]):
        t += [dt(tmp, s, PX + 22, 202 + i * 34, 18, INK), dt(tmp, "✓", PX + PW - 44, 200 + i * 34, 20, GREEN, "Bold")]
    t += [dt(tmp, sub, PX + 22, 444, 14, MUTED), dt(tmp, f"{speed:g}배속 재생", PX + 22, 468, 14, MUTED)]
    fc = (f"[0:v]setpts=PTS/{speed},split=3[a][b][c];"
          "[a]crop=640:480:0:0,scale=683:512[top];"
          "[b]crop=640:480:640:0,scale=341:256[lw];"
          "[c]crop=640:480:1280:0,scale=341:256[rw];"
          "color=white:s=1280x512:r=30[bg];"
          "[bg][top]overlay=0:0:shortest=1[v1];[v1][lw]overlay=683:0[v2];[v2][rw]overlay=683:256[v3];"
          f"[v3]drawbox=x={PX}:y=0:w=1:h=512:color={LINE}:t=fill,"
          f"drawbox=x={PX + 22}:y=176:w={PW - 44}:h=1:color={LINE}:t=fill,"
          "drawbox=x=4:y=6:w=34:h=30:color=black@0.45:t=fill,"
          "drawbox=x=687:y=6:w=64:h=28:color=black@0.45:t=fill,"
          "drawbox=x=687:y=262:w=80:h=28:color=black@0.45:t=fill," + ",".join(t) + "[out]")
    encode(["-i", os.path.join(EV, trial, "video.mp4")], fc, os.path.join(HERE, name), speed)


def pair(tmp, name, items, speed):
    srcs, labels = [], []
    for trial, cap in items:
        srcs += ["-i", os.path.join(EV, trial, "video.mp4")]
        labels.append(cap)
    # 짧은 쪽은 마지막 장면으로 늘려 두 화면 길이를 맞춘다
    fc = (f"[0:v]setpts=PTS/{speed},crop=640:480:0:0,tpad=stop_mode=clone:stop_duration=10[l];"
          f"[1:v]setpts=PTS/{speed},crop=640:480:0:0,tpad=stop_mode=clone:stop_duration=10[r];"
          "color=white:s=1280x512:r=30[bg];[bg][l]overlay=0:0[v1];[v1][r]overlay=640:0[v2];"
          f"[v2]drawbox=x=639:y=0:w=2:h=512:color=white:t=fill,"
          + dt(tmp, labels[0], 16, 487, 17, INK, "Bold") + "," + dt(tmp, labels[1], 656, 487, 17, INK, "Bold") + ","
          + dt(tmp, f"같은 배치 · {speed:g}배속", 1280 - 150, 489, 14, MUTED) + "[o]")
    dur = max(float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                               os.path.join(EV, t, "video.mp4")])) for t, _ in items) / speed
    encode(srcs, fc + f";[o]trim=duration={dur:.2f}[out]", os.path.join(HERE, name), speed)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--speed", type=float, default=2.0)
    a = ap.parse_args()
    with tempfile.TemporaryDirectory(prefix="demo_clip_") as tmp:
        for name, trial, lines, ko, sub in SINGLE:
            single(tmp, name, trial, lines, ko, sub, a.speed)
            print(name)
        pair(tmp, PAIR[0], PAIR[1], a.speed)
        print(PAIR[0])


if __name__ == "__main__":
    main()
