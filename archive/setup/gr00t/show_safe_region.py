"""cam_top 실시간 화면에 '학습된 블록 위치 영역(안전 영역)'을 겹쳐 표시하는 배치 가이드.

실기 50ep의 블록 시작위치(pose_ref/trained_block_positions.json)를 현재 top 카메라 위에
점·박스로 그려, 블록/물체를 **학습 분포 안**에 놓도록 돕는다. (§6 실험 시 위치 OOD 방지)

⚠️ 카메라 정렬이 학습 화각과 맞아야 픽셀 좌표가 유효 — real_pose_align 으로 정렬 후 사용.
로봇·서버 불필요(카메라만). 실행:
  cd ~/manipulator_ws/envs/lerobot && uv run python ../../setup/gr00t/show_safe_region.py
종료: Ctrl+C
"""
import json
import os
import sys
import time

import cv2
import numpy as np
import rerun as rr

HERE = os.path.dirname(os.path.abspath(__file__))
J = json.load(open(os.path.join(HERE, "pose_ref", "trained_block_positions.json")))
PTS = J["points"]
SX0, SY0, SX1, SY1 = J["bbox_p5_95"]   # 안전 영역(가장자리 이상치 제외)
FX0, FY0, FX1, FY1 = J["bbox_full"]    # 전체 학습 범위
CAM = "/dev/cam_top"
W, H, FPS = 640, 480, 30


def overlay(frame):
    vis = frame.copy()
    # 안전 영역(초록) 반투명 채움 + 테두리
    ov = vis.copy()
    cv2.rectangle(ov, (SX0, SY0), (SX1, SY1), (0, 200, 0), -1)
    vis = cv2.addWeighted(ov, 0.18, vis, 0.82, 0)
    cv2.rectangle(vis, (SX0, SY0), (SX1, SY1), (0, 220, 0), 2)
    # 전체 학습 범위(노랑 점선 느낌 — 실선 얇게)
    cv2.rectangle(vis, (FX0, FY0), (FX1, FY1), (0, 220, 220), 1)
    # 학습 블록 위치 점(초록)
    for x, y in PTS:
        cv2.circle(vis, (int(x), int(y)), 3, (0, 255, 0), -1)
    cv2.putText(vis, "PLACE BLOCK IN GREEN ZONE", (SX0, max(SY0 - 10, 18)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 220, 0), 2)
    return vis


def main():
    print(f"안전영역(5~95%): x[{SX0},{SX1}] y[{SY0},{SY1}]  | 학습점 {len(PTS)}개", flush=True)
    rr.init("place_safe_region", spawn=True)
    dev = os.path.realpath(CAM)
    cap = cv2.VideoCapture(dev, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, H)
    cap.set(cv2.CAP_PROP_FPS, FPS)
    if not cap.isOpened():
        print(f"❌ 카메라 열기 실패: {CAM} ({dev})", flush=True)
        sys.exit(1)
    print("▶ rerun에서 top/guide 보며 블록을 초록 영역 안에 배치. 종료: Ctrl+C", flush=True)
    try:
        while True:
            ok, frame = cap.read()
            if ok:
                vis = overlay(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                rr.log("top/guide", rr.Image(vis))
            time.sleep(1.0 / FPS)
    except KeyboardInterrupt:
        print("\n종료.", flush=True)
    finally:
        cap.release()


if __name__ == "__main__":
    main()
