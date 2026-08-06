"""sweep 영상으로 '조건이 의도대로 적용됐는지' 자동 검증 — 조건별 대조 시트 생성.

각 조건 폴더의 에피소드 첫 프레임을 모아, 블록(빨강 계열)·박스(검정)의 위치를 검출해
 · 조건별 몽타주 이미지(에피소드들을 격자로)
 · 위치 산포 요약(박스가 고정인지 움직이는지, 블록 범위가 넓어졌는지, 색이 바뀌었는지)
을 만든다. 90개 영상을 눈으로 넘겨보는 대신 한 장으로 확인하기 위함.

기대값(통제 설계):
  ref/pos_ood/phys_dr/light_dr/color_*  → 박스 위치 **고정**(산포 ≈ 0)
  box_rand / box_ood / full             → 박스 위치 **분산**
  pos_ood                               → 블록 산포가 ref보다 **넓음**
  color_blue / color_green              → 블록 색조(Hue)가 빨강과 **다름**
  phys_dr                               → 시각적으로 확인 불가(마찰·질량) — 영상으론 ref와 동일해 보이는 게 정상

사용: python3 verify_sweep_conditions.py <영상루트> [출력폴더]
   예: python3 verify_sweep_conditions.py ~/manipulator_ws/inf_video/02_v3_OOD
"""
import glob
import os
import subprocess
import sys

import cv2
import numpy as np


def first_frame(mp4, tmp):
    """AV1 등 cv2가 못 여는 코덱 대비 ffmpeg로 추출."""
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", mp4,
                    "-frames:v", "1", tmp], check=False)
    return cv2.imread(tmp)


def detect_block(img):
    """빨강/파랑/초록 중 가장 뚜렷한 소형 물체 = 큐브. (색 조건 대응)"""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    masks = {
        "red":   cv2.inRange(hsv, (0, 90, 60), (12, 255, 255)) | cv2.inRange(hsv, (168, 90, 60), (180, 255, 255)),
        "blue":  cv2.inRange(hsv, (100, 90, 60), (130, 255, 255)),
        "green": cv2.inRange(hsv, (40, 60, 40), (85, 255, 255)),
    }
    best = (None, None, 0)
    for name, m in masks.items():
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cnts = [c for c in cnts if 20 < cv2.contourArea(c) < 3000]
        if not cnts:
            continue
        c = max(cnts, key=cv2.contourArea)
        a = cv2.contourArea(c)
        if a > best[2]:
            M = cv2.moments(c)
            if M["m00"]:
                best = (name, (int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"])), a)
    return best[0], best[1]


def detect_box(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    m = cv2.inRange(hsv, (0, 0, 0), (180, 255, 60))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cnts = [c for c in cnts if cv2.contourArea(c) > 300]
    if not cnts:
        return None
    M = cv2.moments(max(cnts, key=cv2.contourArea))
    return (int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"])) if M["m00"] else None


def main():
    root = os.path.expanduser(sys.argv[1])
    out = os.path.expanduser(sys.argv[2]) if len(sys.argv) > 2 else os.path.join(root, "_verify")
    os.makedirs(out, exist_ok=True)
    tmp = os.path.join(out, "_f.jpg")

    conds = sorted(d for d in os.listdir(root)
                   if os.path.isdir(os.path.join(root, d)) and not d.startswith("_"))
    print(f"조건 {len(conds)}개: {', '.join(conds)}\n")
    print(f"{'조건':<13} {'ep':>3}  {'박스 산포(px)':>13}  {'블록 산포(px)':>13}  {'블록색'}")
    print("-" * 68)

    for cond in conds:
        mp4s = sorted(glob.glob(os.path.join(root, cond, "*.mp4")))
        if not mp4s:
            continue
        frames, boxes, blocks, colors = [], [], [], []
        for f in mp4s:
            img = first_frame(f, tmp)
            if img is None:
                continue
            frames.append(img)
            b = detect_box(img)
            if b:
                boxes.append(b)
            cname, bl = detect_block(img)
            if bl:
                blocks.append(bl)
                colors.append(cname)

        bx = np.array(boxes) if boxes else np.zeros((0, 2))
        bl = np.array(blocks) if blocks else np.zeros((0, 2))
        # 산포 = x,y 표준편차의 평균(픽셀). 고정이면 ~0
        bx_sd = float(np.mean(np.std(bx, axis=0))) if len(bx) > 1 else 0.0
        bl_sd = float(np.mean(np.std(bl, axis=0))) if len(bl) > 1 else 0.0
        cmode = max(set(colors), key=colors.count) if colors else "?"
        flag = "고정" if bx_sd < 3 else "분산"
        print(f"{cond:<13} {len(frames):>3}  {bx_sd:>8.1f} ({flag})  {bl_sd:>13.1f}  {cmode}")

        # 몽타주(첫 프레임들 격자) — 육안 확인용
        if frames:
            h, w = frames[0].shape[:2]
            sc = 0.34
            th, tw = int(h * sc), int(w * sc)
            cols = 5
            rows = (len(frames) + cols - 1) // cols
            sheet = np.zeros((rows * th, cols * tw, 3), np.uint8)
            for i, fr in enumerate(frames):
                r, c = divmod(i, cols)
                small = cv2.resize(fr, (tw, th))
                cv2.putText(small, os.path.basename(mp4s[i])[:12], (4, 14),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 255, 255), 1)
                sheet[r * th:(r + 1) * th, c * tw:(c + 1) * tw] = small
            cv2.imwrite(os.path.join(out, f"{cond}.jpg"), sheet)

    print(f"\n대조 시트 → {out}/<조건>.jpg")
    print("판정 기준: ref·pos_ood·phys_dr·light_dr·color_* = 박스 '고정' / "
          "box_rand·box_ood·full = 박스 '분산'")


if __name__ == "__main__":
    main()
