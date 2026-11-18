#!/usr/bin/env bash
# 카메라 빠른 점검: 링크 존재 → MJPG 동시 스트림 fps → 스냅샷 저장
cd "$(dirname "$0")/../../envs/lerobot" || exit 1

echo "── 장치 링크"
ls -l /dev/cam_top /dev/cam_wrist /dev/cam_side /dev/ttyLEADER /dev/ttyFOLLOWER 2>&1

echo "── MJPG 동시 스트림 테스트 (3초)"
uv run python - <<'EOF'
import cv2, time, os
out = os.path.expanduser("~/manipulator_ws/scripts/hardware/snapshots")
os.makedirs(out, exist_ok=True)
caps = {}
for name in ["top", "wrist", "side"]:
    c = cv2.VideoCapture(f"/dev/cam_{name}")
    c.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    c.set(cv2.CAP_PROP_FRAME_WIDTH, 640); c.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    c.set(cv2.CAP_PROP_FPS, 30)
    caps[name] = c
for _ in range(10):
    for c in caps.values(): c.read()
t0 = time.time(); n = {k: 0 for k in caps}; last = {}
while time.time() - t0 < 3:
    for k, c in caps.items():
        ok, f = c.read()
        if ok: n[k] += 1; last[k] = f
for k, c in caps.items():
    fps = n[k] / 3
    print(f"  {k}: {fps:.1f} fps {'✅' if fps > 28 else '⚠️ 저하'}")
    if k in last:
        cv2.imwrite(f"{out}/{k}.jpg", last[k])
    c.release()
print(f"  스냅샷 저장: {out}/top.jpg, wrist.jpg, side.jpg")
EOF
