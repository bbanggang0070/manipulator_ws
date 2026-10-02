"""선반 배치용 카메라 뷰어 — **모델이 보는 것까지** 같이 띄운다.

팔을 켜지 않고 카메라만 본다. 선반을 놓고 색지를 붙이면서 화각을 맞추는 용도다.

왜 "모델이 보는 것"을 같이 띄우나:
  학습·추론은 원본 640×480이 아니라 **레터박스 후 256×256**을 본다
  (GR00T N1.6의 `shortest_image_edge=256`, `setup/gr00t/edge_patch.py` 참고).
  눈으로는 칸 색이 잘 보여도 256²에서 뭉개지면 모델에게는 없는 정보다.
  sim에서 `brown`과 `black`이 바로 그렇게 구별되지 않았다.
  **오른쪽 패널(모델 시점)에서 네 칸 색이 서로 구별되는지**를 기준으로 삼는다.

Rerun 패널:
  top / wrist          원본 (640×480)
  top_model / wrist_model   모델 입력 (256×256) ← 판단은 이걸로
  guide                top 위에 4등분 세로선 — 칸을 균등하게 놓는 데 쓴다

사용:
  cd ~/manipulator_ws/envs/lerobot
  uv run python ../../setup/data/view_cams.py              # 기본
  uv run python ../../setup/data/view_cams.py --no-guide   # 안내선 끄기
  uv run python ../../setup/data/view_cams.py --edge 448   # 448로 올렸을 때를 보고 싶으면
"""
import argparse
import sys
import time

import cv2
import numpy as np
import rerun as rr

CAMS = {"top": "/dev/cam_top", "wrist": "/dev/cam_wrist"}


def model_view(img, edge):
    """학습 파이프라인과 같은 전처리 — 레터박스로 정사각 패딩 후 edge로 축소.

    gr00t의 `LetterBoxPad()` + `SmallestMaxSize(edge)` 와 같은 결과를 낸다.
    보간은 INTER_AREA — 축소에 쓰는 것이 같다.
    """
    h, w = img.shape[:2]
    side = max(h, w)
    pad = np.zeros((side, side, 3), dtype=img.dtype)
    y0, x0 = (side - h) // 2, (side - w) // 2
    pad[y0:y0 + h, x0:x0 + w] = img
    return cv2.resize(pad, (edge, edge), interpolation=cv2.INTER_AREA)


def draw_guide(img, n=4):
    """4등분 세로선 + 중앙 가로선. 칸을 프레임에 균등하게 넣는 데 쓴다."""
    out = img.copy()
    h, w = out.shape[:2]
    for i in range(1, n):
        x = w * i // n
        cv2.line(out, (x, 0), (x, h), (0, 255, 255), 1, cv2.LINE_AA)
    cv2.line(out, (0, h // 2), (w, h // 2), (0, 160, 160), 1, cv2.LINE_AA)
    for i in range(n):
        cv2.putText(out, str(i + 1), (w * i // n + w // (2 * n) - 8, 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2, cv2.LINE_AA)
    return out


def open_cam(path, w=640, h=480, fps=30):
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        return None
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
    cap.set(cv2.CAP_PROP_FPS, fps)
    return cap


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--edge", type=int, default=256,
                    help="모델 입력 한 변. 기본 256 (학습 기본값과 같다)")
    ap.add_argument("--no-guide", action="store_true", help="4등분 안내선 끄기")
    ap.add_argument("--fps", type=float, default=15.0, help="표시 주기")
    a = ap.parse_args()

    caps = {}
    for name, path in CAMS.items():
        c = open_cam(path)
        if c is None:
            sys.exit(f"❌ {path} 를 열 수 없습니다. 연결과 권한을 확인하세요.")
        caps[name] = c

    rr.init("shelf_setup", spawn=True)
    print(f"""
  ┌────────────────────────────────────────────────────────────────┐
  │ 선반 배치 뷰어 — Rerun 창에서 확인하세요                        │
  ├────────────────────────────────────────────────────────────────┤
  │ top / wrist             원본 640×480                            │
  │ top_model / wrist_model **모델이 보는 것** ({a.edge}×{a.edge})            │
  │                                                                 │
  │ 판단 기준:                                                      │
  │  · 오른쪽(모델 시점)에서 네 칸 색이 **서로 구별되는가**          │
  │  · 4칸이 전부 프레임 안에 들어오는가 (잘리면 그 칸은 정보가 없다)│
  │  · 안내선 1~4가 칸과 대략 맞는가                                │
  │                                                                 │
  │ Ctrl+C 로 종료                                                  │
  └────────────────────────────────────────────────────────────────┘
""")
    period = 1.0 / a.fps
    t0 = time.time()
    try:
        while True:
            rr.set_time("t", duration=time.time() - t0)
            for name, cap in caps.items():
                ok, frame = cap.read()
                if not ok:
                    continue
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                shown = rgb
                if name == "top" and not a.no_guide:
                    shown = draw_guide(rgb)
                rr.log(name, rr.Image(shown))
                rr.log(f"{name}_model", rr.Image(model_view(rgb, a.edge)))
            time.sleep(period)
    except KeyboardInterrupt:
        print("\n  종료합니다.")
    finally:
        for c in caps.values():
            c.release()


if __name__ == "__main__":
    main()
