"""실기 팔을 sim 데이터의 특정 프레임 자세로 재현 + 그 프레임의 sim 카메라 이미지와 나란히 rerun 표시.
팔 자세가 sim과 동일하므로, real vs sim 카메라 뷰의 차이 = 순수 카메라 위치 차이 → 정밀 정렬 가능.

기준 데이터: setup/gr00t/pose_ref/ (sim_pose_state.json + sim_pose_front.jpg + sim_pose_wrist.jpg)
  = sim_so101_blocktask_v2 episode0 frame0 (rest 자세). sim state는 leader/real 프레임이라 실기에 그대로 사용.

실행(로컬): cd ~/manipulator_ws/envs/lerobot && uv run python ../../setup/gr00t/real_pose_align.py
종료: Ctrl+C.  ⚠️ 실기 팔이 sim 자세로 움직입니다 — e-stop 대기.
"""
import json
import os
import sys
import time

import cv2
import numpy as np
import rerun as rr

from lerobot.robots.so_follower.so_follower import SOFollower
from lerobot.robots.so_follower.config_so_follower import SOFollowerRobotConfig

# 기준 프레임 디렉터리. 기본은 sim(pose_ref). 실기 dataset 비교는 POSE_REF=real_pose_ref 로 전환
# (extract_real_pose.sh 가 생성). 상대경로면 이 파일 기준으로 해석 → 하위호환(기본값 불변).
_here = os.path.dirname(os.path.abspath(__file__))
_ref = os.environ.get("POSE_REF", "pose_ref")
REF = _ref if os.path.isabs(_ref) else os.path.join(_here, _ref)
d = json.load(open(os.path.join(REF, "sim_pose_state.json")))
TARGET = {j: float(v) for j, v in zip(d["joints"], d["state"])}
front_ref = cv2.imread(os.path.join(REF, "sim_pose_front.jpg"))
wrist_ref = cv2.imread(os.path.join(REF, "sim_pose_wrist.jpg"))

# 선택적 오버레이: 90% 시절(2026-07-30) 배포 프레임 = 알려진-정상 화각. 있으면 era90/* 로 추가 표시.
# (real_success_w03.mp4 frame0에서 front/wrist 분리. top 카메라 각도를 '그때'로 되돌리는 기준)
_ERA90 = os.path.join(_here, "pose_ref_era90")
era90_front = cv2.imread(os.path.join(_ERA90, "front.jpg"))
era90_wrist = cv2.imread(os.path.join(_ERA90, "wrist.jpg"))

CAMS = {"front": "/dev/cam_top", "wrist": "/dev/cam_wrist"}
W, H, FPS = 640, 480, 30


def open_cam(path):
    cap = cv2.VideoCapture(os.path.realpath(path), cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, H)
    cap.set(cv2.CAP_PROP_FPS, FPS)
    if not cap.isOpened():
        print(f"❌ 카메라 열기 실패: {path}", flush=True)
        return None
    return cap


def main():
    print(f"sim 기준 자세(ep{d['episode']} frame{d['frame']}): "
          + ", ".join(f"{j.split('.')[0]}={v:.1f}" for j, v in TARGET.items()), flush=True)
    rr.init("real_pose_align", spawn=True)
    if front_ref is not None:
        rr.log("sim_ref/front", rr.Image(cv2.cvtColor(front_ref, cv2.COLOR_BGR2RGB)), static=True)
    if wrist_ref is not None:
        rr.log("sim_ref/wrist", rr.Image(cv2.cvtColor(wrist_ref, cv2.COLOR_BGR2RGB)), static=True)
    if era90_front is not None:
        rr.log("era90/front", rr.Image(cv2.cvtColor(era90_front, cv2.COLOR_BGR2RGB)), static=True)
        print("✓ 90% 시절 오버레이: era90/front", flush=True)
    if era90_wrist is not None:
        rr.log("era90/wrist", rr.Image(cv2.cvtColor(era90_wrist, cv2.COLOR_BGR2RGB)), static=True)

    r = None
    for attempt in range(6):
        try:
            r = SOFollower(SOFollowerRobotConfig(
                port="/dev/ttyFOLLOWER", id="follower", cameras={}, max_relative_target=6.0))
            r.connect()
            break
        except Exception as e:
            print(f"connect 재시도 {attempt+1}/6: {type(e).__name__}", flush=True)
            r = None
            time.sleep(2)
    if r is None:
        print("로봇 연결 실패 (/dev/ttyFOLLOWER, 전원 확인)", flush=True)
        sys.exit(1)

    caps = {n: open_cam(p) for n, p in CAMS.items()}
    print("\n▶ 실기 팔을 sim 자세로 유지하며 카메라 스트리밍 중.\n"
          "  rerun에서 real/front vs sim_ref/front (및 wrist)를 겹쳐 보며 카메라 위치를 미세 조정.\n"
          "  종료: Ctrl+C\n", flush=True)
    try:
        while True:
            r.send_action(TARGET)  # sim 자세 유지 (MRT=6 클램프로 서서히 도달)
            for n, cap in caps.items():
                if cap is None:
                    continue
                ok, f = cap.read()
                if ok:
                    rr.log(f"real/{n}", rr.Image(cv2.cvtColor(f, cv2.COLOR_BGR2RGB)))
            time.sleep(1.0 / FPS)
    except KeyboardInterrupt:
        print("\n종료.", flush=True)
    finally:
        for c in caps.values():
            if c is not None:
                c.release()
        try:
            r.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    main()
