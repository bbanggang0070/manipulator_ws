"""Wrist 카메라 초점 조정 + 가로선 아티팩트 실시간 관찰 도구.

실행:  cd ~/manipulator_ws/envs/lerobot && uv run python ../../setup/hardware/wrist_cam_tune.py
종료:  Ctrl+C

사용법:
  1. rerun 뷰어 창이 뜨면 wrist 영상과 sharpness(선명도) 그래프가 보인다.
  2. 렌즈 링을 천천히 돌리며 sharpness 값이 최대가 되게 조정 (그리퍼 앞 ~15cm 물체 기준).
  3. 조정 후 팔을 움직이거나 케이블을 흔들며 가로선이 뜨는지 관찰.
     가로선 프레임은 자동 감지되어 터미널에 카운트가 찍힌다.
"""
import cv2
import numpy as np
import rerun as rr

rr.init("wrist_cam_tune", spawn=True)

cap = cv2.VideoCapture("/dev/cam_wrist")
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
cap.set(cv2.CAP_PROP_FPS, 30)

prev = None
artifacts = 0
i = 0
print("조정 시작 — Ctrl+C로 종료")
try:
    while True:
        ok, frame = cap.read()
        if not ok:
            print("frame drop!")
            continue
        i += 1
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        sharp = cv2.Laplacian(gray, cv2.CV_64F).var()  # 클수록 선명

        # 가로선/찢김 감지: 평탄한 행 or 행 간 급격한 불연속
        g = gray.astype(np.int16)
        flat_rows = int((g.var(axis=1) < 3).sum())
        if prev is not None:
            rowdiff = np.abs(g - prev).mean(axis=1)
            jumps = int((np.abs(np.diff(rowdiff)) > 40).sum())
        else:
            jumps = 0
        prev = g

        is_bad = flat_rows > 15 or jumps > 8
        if is_bad:
            artifacts += 1
            print(f"[{i}] ⚠️ 아티팩트 감지 (누적 {artifacts}) flat={flat_rows} jump={jumps}")

        rr.set_time(sequence=i, timeline="frame")
        rr.log("wrist", rr.Image(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
        rr.log("sharpness", rr.Scalars(sharp))
        rr.log("artifact", rr.Scalars(1.0 if is_bad else 0.0))
        if i % 30 == 0:
            print(f"[{i}] sharpness={sharp:.0f}  아티팩트 누적={artifacts}")
except KeyboardInterrupt:
    pass
finally:
    cap.release()
    print(f"\n총 {i}프레임, 아티팩트 {artifacts}회")
