"""실기 카메라를 sim 학습 환경 구도에 맞추는 정렬 도구 (Phase E 사전).

로봇·서버 없이 top/wrist 카메라 실시간 영상만 rerun으로 띄우고, sim 학습 기준 프레임을
나란히 표시해 물리 카메라 각도를 sim과 비슷하게 조정할 수 있게 한다.

- real/front  = /dev/cam_top   (sim external_D455 대응)
- real/wrist  = /dev/cam_wrist (sim ego 대응)
- sim_ref/*   = sim 학습 데이터 기준 프레임 (정적, 비교용)

실행(로컬): cd ~/manipulator_ws/envs/lerobot && uv run python ../../setup/gr00t/rerun_cam_align.py
종료: Ctrl+C
"""
import os
import sys
import time

import cv2
import numpy as np
import rerun as rr

W, H, FPS = 640, 480, 30
CAMS = {"front": "/dev/cam_top", "wrist": "/dev/cam_wrist"}
ASSETS = os.path.join(os.path.dirname(__file__),
                      "../../manipulator_md/sim2real/08_T1_sim2real/assets")
SIM_REF = {"front": "sim_ref_front.jpg", "wrist": "sim_ref_wrist.jpg"}


def open_cam(path):
    dev = os.path.realpath(path)
    cap = cv2.VideoCapture(dev, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, H)
    cap.set(cv2.CAP_PROP_FPS, FPS)
    if not cap.isOpened():
        print(f"❌ 카메라 열기 실패: {path} ({dev})", flush=True)
        return None
    print(f"✓ 카메라 열림: {path} -> {dev}", flush=True)
    return cap


def main():
    rr.init("blocktask_cam_align", spawn=True)

    # sim 기준 프레임(정적) 표시
    for name, fn in SIM_REF.items():
        p = os.path.join(ASSETS, fn)
        img = cv2.imread(p)
        if img is not None:
            rr.log(f"sim_ref/{name}", rr.Image(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)), static=True)
            print(f"✓ sim 기준 표시: sim_ref/{name} ({fn})", flush=True)
        else:
            print(f"⚠️ sim 기준 없음: {p}", flush=True)

    caps = {name: open_cam(path) for name, path in CAMS.items()}
    if all(c is None for c in caps.values()):
        print("카메라를 하나도 못 열었습니다. 연결 확인.", flush=True)
        sys.exit(1)

    print("\n▶ rerun 뷰어에서 real/front·real/wrist 를 sim_ref/* 와 비교하며 카메라 각도 조정.")
    print("  종료: Ctrl+C\n", flush=True)
    try:
        while True:
            for name, cap in caps.items():
                if cap is None:
                    continue
                ok, frame = cap.read()
                if ok:
                    rr.log(f"real/{name}", rr.Image(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
            time.sleep(1.0 / FPS)
    except KeyboardInterrupt:
        print("\n종료.", flush=True)
    finally:
        for c in caps.values():
            if c is not None:
                c.release()


if __name__ == "__main__":
    main()
