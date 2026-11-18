#!/usr/bin/env bash
# 하드웨어(로봇 팔 2 + 카메라 2) 연결 후 실행 → udev rule에 채울 식별 정보 출력
set -u

echo "════════ 시리얼 장치 (로봇 팔 어댑터) ════════"
if compgen -G "/dev/ttyACM*" >/dev/null || compgen -G "/dev/ttyUSB*" >/dev/null; then
  for dev in /dev/ttyACM* /dev/ttyUSB*; do
    [ -e "$dev" ] || continue
    echo "── $dev"
    udevadm info -a -n "$dev" 2>/dev/null \
      | grep -E 'ATTRS\{(idVendor|idProduct|serial)\}' | head -6
  done
else
  echo "  (없음 — 로봇 팔을 연결하세요)"
fi

echo ""
echo "════════ 카메라 (v4l) ════════"
if [ -d /dev/v4l/by-id ]; then
  ls -l /dev/v4l/by-id/
  echo ""
  for dev in /dev/video*; do
    [ -e "$dev" ] || continue
    echo "── $dev  (USB 경로: $(udevadm info -q path -n "$dev" 2>/dev/null | grep -oP 'usb\d+/[\d.:-]+' | tail -1))"
  done
else
  echo "  (없음 — 카메라를 연결하세요)"
fi

echo ""
echo "════════ USB 버스 배치 (카메라는 서로 다른 버스에!) ════════"
lsusb -t
