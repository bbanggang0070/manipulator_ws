"""실기 카메라를 **기준 구도**에 맞추는 정렬 도구 (수집·배포 전 필수).

왜 필요한가:
  GR00T는 이미지에서 직접 행동을 뽑으므로 **카메라 구도가 곧 입력 분포**다.
  구도가 틀어지면 같은 모델도 성능이 무너진다. 실제로 이 프로젝트에서
  카메라·팔 드리프트가 반복 관측됐고, v2가 카메라 오프셋 0으로 학습돼
  현재 씬에서 재측정이 불가능해진 전례가 있다.

기준(`--ref`):
  · **sim_v4** (기본) — **현재 학습 중인 sim 씬(v3/v4)의 구도**. `pose_ref_sim_v4/`
    실기 환경을 sim에 맞춰 만들어 놓았으므로, **실기 카메라도 sim 구도에 맞춰야**
    sim에서 낸 성공률이 실기로 옮겨진다. 수집·배포는 이쪽 기준.
    v4 수집 영상 40개의 프레임3을 **중앙값 합성** → 블록·박스가 지워지고 고정 구조만 남는다.
  · era90 — 실기 SR 90%를 낸 시점의 실기 구도. 다만 그건 **v2 시절 sim에 맞춘 것**이고,
    v3에서 카메라 오프셋이 (0,0)→(0.03,0.02)로 바뀌어 현재 sim과 어긋난다.
    "그때로 되돌리고 싶을 때"만 쓴다.
  · sim_v2 — 7/27자 sim 프레임(오프셋 0 시절). 이력 참고용.

⚠️ sim은 렌더, 실기는 사진이라 **질감·색이 달라 일치도 상한이 낮다**(1.00은 안 나온다).
   overlay에서 **벽 모서리·바닥 경계·로봇 베이스가 겹치는지**를 주로 보고,
   dx·dy는 방향 지시로 쓴다.

뷰(rerun):
  real/*     현재 카메라
  ref/*      기준 프레임 (정적)
  overlay/*  현재 + 기준을 반반 블렌딩  ← **정렬은 이걸 보면서 한다**
  diff/*     |현재 − 기준| — 맞을수록 어두워진다

콘솔에는 **일치도**(1.00이 완전 일치)와 **기준 대비 어긋난 방향·픽셀**을 함께 찍는다.
나란히 놓고 눈으로만 맞추면 미세한 회전·높이 차를 놓치고, 어느 쪽으로 움직여야 할지도 모른다.

실행(로컬):
  cd ~/manipulator_ws/envs/lerobot && uv run python ../../setup/gr00t/rerun_cam_align.py
  # sim 구도와 비교:  ... rerun_cam_align.py --ref sim
종료: Ctrl+C
"""
import argparse
import os
import sys
import time

import cv2
import numpy as np
import rerun as rr

W, H, FPS = 640, 480, 30
CAMS = {"front": "/dev/cam_top", "wrist": "/dev/cam_wrist"}
HERE = os.path.dirname(os.path.abspath(__file__))
REFS = {
    # 기본. **현재 학습 중인 sim 씬(v3/v4)의 실제 구도**를 재현한다.
    # v4 수집 영상 40개의 프레임3을 중앙값 합성한 것이라 블록·박스가 지워지고
    # 고정 구조(벽·바닥·로봇 홈 자세)만 남아 정렬 기준으로 적합하다.
    "sim_v4": {"front": os.path.join(HERE, "pose_ref_sim_v4/front.jpg"),
               "wrist": os.path.join(HERE, "pose_ref_sim_v4/wrist.jpg")},
    # 실기 SR 90%를 낸 시점의 실기 구도. **v2 시절 sim에 맞춰 정렬한 것**이라
    # v3에서 카메라 오프셋이 (0,0)→(0.03,0.02)로 바뀐 뒤로는 현재 sim과 어긋난다.
    # "그때 상태로 되돌리고 싶을 때"만 쓴다.
    "era90":  {"front": os.path.join(HERE, "pose_ref_era90/front.jpg"),
               "wrist": os.path.join(HERE, "pose_ref_era90/wrist.jpg")},
    # 7/27자 sim 프레임 — 오프셋 0 시절이라 **현재 sim과 다르다.** 이력 참고용.
    "sim_v2": {"front": os.path.join(HERE, "../../manipulator_md/sim2real/08_T1_sim2real/assets/sim_ref_front.jpg"),
               "wrist": os.path.join(HERE, "../../manipulator_md/sim2real/08_T1_sim2real/assets/sim_ref_wrist.jpg")},
}


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


def _norm_gray(img):
    """밝기·대비 정규화 + Hanning 창. 조명이 달라도 구조만 비교하기 위함."""
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    g = (g - g.mean()) / (g.std() + 1e-6)
    return g * cv2.createHanningWindow(g.shape[::-1], cv2.CV_32F)


def _edges(img):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    g = cv2.GaussianBlur(g, (5, 5), 0)
    m = cv2.magnitude(cv2.Sobel(g, cv2.CV_32F, 1, 0, 3),
                      cv2.Sobel(g, cv2.CV_32F, 0, 1, 3))
    return (m - m.mean()) / (m.std() + 1e-6)


def compare(cur, ref):
    """(일치도, dx, dy, 응답) — 조정 **방향**까지 알려준다.

    · 일치도 = 엣지 정규화 상호상관. 1.0이 완전 일치, 어긋날수록 감소.
      실측 단조성: 0px 1.00 / 5px 0.47 / 15px 0.27 / 40px 0.15 → **가까워지는지 알 수 있다.**
    · dx, dy = 위상 상관으로 구한 **기준 대비 현재 영상의 이동량(px)**.
      실측으로 5/15/40px 이동을 정확히 복원했다.
    · 응답 = 위상 상관 신뢰도. **회전·틸트가 섞이면 급격히 떨어진다**
      (실측: 평행이동 0.95~1.00 vs 2° 회전 0.32, 8° 회전 0.21).
      즉 응답이 낮으면 "평행이동으로는 안 맞는다 = 각도를 봐야 한다"는 신호다.

    앞선 시도(엣지 절대차의 중앙값)는 5px든 40px든 0.949로 **포화**해 조정 가이드로 쓸 수 없었다.
    밝기 변화에는 세 지표 모두 무반응이다(실측: 밝기 +40에서 일치도 1.00, dx=dy=0).
    """
    (dx, dy), resp = cv2.phaseCorrelate(_norm_gray(ref), _norm_gray(cur))
    score = float((_edges(cur) * _edges(ref)).mean())
    return score, dx, dy, float(resp)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", choices=list(REFS), default="sim_v4",
                    help="정렬 기준 (기본 sim_v4 = 현재 학습 중인 sim 씬 구도)")
    ap.add_argument("--alpha", type=float, default=0.5, help="overlay 블렌딩 비율(현재 쪽)")
    ap.add_argument("--save-ref", metavar="DIR",
                    help="종료 시 현재 프레임을 DIR/front.jpg·wrist.jpg 로 저장 — "
                         "정렬을 마친 뒤 '이 상태'를 다음 세션의 기준으로 남길 때 쓴다")
    args = ap.parse_args()

    rr.init("blocktask_cam_align", spawn=True)
    print(f"\n▶ 정렬 기준: {args.ref}", flush=True)

    refs = {}
    for name, p in REFS[args.ref].items():
        img = cv2.imread(p)
        if img is None:
            print(f"⚠️ 기준 없음: {p}", flush=True)
            continue
        if img.shape[:2] != (H, W):
            img = cv2.resize(img, (W, H))
        refs[name] = img
        rr.log(f"ref/{name}", rr.Image(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)), static=True)
        print(f"✓ 기준 표시: ref/{name}", flush=True)

    caps = {name: open_cam(path) for name, path in CAMS.items()}
    if all(c is None for c in caps.values()):
        print("카메라를 하나도 못 열었습니다. 연결 확인.", flush=True)
        sys.exit(1)

    print("""
  ┌──────────────────────────────────────────────────────────────┐
  │ rerun 뷰어에서 **overlay/front** 를 보며 카메라를 조정한다.  │
  │   · 겹친 상이 하나로 보이면 정렬됨                           │
  │   · diff/* 가 어두워질수록 좋음                              │
  │   · 아래 '일치'가 **커지는** 방향으로 (1.00이 완전 일치)     │
  │   · '기준 대비 →12px ↓5px' = 현재 영상이 그만큼 밀려 있음    │
  │     → 카메라를 그 반대로 옮기면 맞는다                       │
  │ 조정 후 반드시 나사를 조여 고정. 종료: Ctrl+C                │
  └──────────────────────────────────────────────────────────────┘

  ※ 기준 사진에는 블록·박스가 특정 위치에 찍혀 있다. 지금 테이블이 비어 있거나
    물체 위치가 다르면 그만큼 일치도가 깎인다 — **1.00은 안 나온다.**
    가능하면 ref/* 를 보고 박스를 비슷한 자리에 놓은 뒤 맞추면 훨씬 정확하다.
    (dx·dy는 화면 전체 구조가 지배하므로 물체가 달라도 방향 지시는 유효하다)
""", flush=True)

    best = {k: -1e9 for k in caps}
    last = 0.0
    try:
        while True:
            info = {}
            for name, cap in caps.items():
                if cap is None:
                    continue
                ok, frame = cap.read()
                if not ok:
                    continue
                rr.log(f"real/{name}", rr.Image(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
                ref = refs.get(name)
                if ref is None:
                    continue
                ov = cv2.addWeighted(frame, args.alpha, ref, 1 - args.alpha, 0)
                rr.log(f"overlay/{name}", rr.Image(cv2.cvtColor(ov, cv2.COLOR_BGR2RGB)))
                rr.log(f"diff/{name}", rr.Image(cv2.cvtColor(cv2.absdiff(frame, ref), cv2.COLOR_BGR2RGB)))
                sc, dx, dy, resp = compare(frame, ref)
                info[name] = (sc, dx, dy, resp)
                best[name] = max(best[name], sc)
                rr.log(f"score/{name}", rr.Scalars(sc))

            now = time.time()
            if info and now - last > 0.4:
                last = now
                for n, (sc, dx, dy, resp) in info.items():
                    ar = f"{'→' if dx > 0 else '←'}{abs(dx):4.0f}px  {'↓' if dy > 0 else '↑'}{abs(dy):4.0f}px"
                    tip = "" if resp >= 0.4 else "  ⚠ 회전·틸트 차 (평행이동으로 안 맞음)"
                    star = " ⭐" if sc >= best[n] - 1e-9 else ""
                    print(f"  {n:<6} 일치 {sc:5.2f} (최고 {best[n]:5.2f}){star}"
                          f"  | 기준 대비 {ar}  응답 {resp:4.2f}{tip}")
                print("\033[F" * len(info), end="", flush=True)
            time.sleep(1.0 / FPS)
    except KeyboardInterrupt:
        print("\n" * (len(caps) + 1), flush=True)
        print("최종 최고 일치도:", {k: round(v, 2) for k, v in best.items()}, flush=True)
        print("종료.", flush=True)
    finally:
        if args.save_ref:
            os.makedirs(args.save_ref, exist_ok=True)
            for name, cap in caps.items():
                if cap is None:
                    continue
                ok, frame = cap.read()
                if ok:
                    out = os.path.join(args.save_ref, f"{name}.jpg")
                    cv2.imwrite(out, frame)
                    print(f"  기준 저장: {out}", flush=True)
        for c in caps.values():
            if c is not None:
                c.release()


if __name__ == "__main__":
    main()
