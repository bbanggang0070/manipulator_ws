"""캘리브레이션 **전에** 두 팔의 관절 상태를 본다.

왜 필요한가 — 두 가지를 미리 거른다.

  ① **엔코더 끝에 걸린 관절**
     `lerobot-calibrate` 의 homing 단계는 `offset = 현재위치 - 2047` 을 서보에 쓴다.
     Feetech 는 이 값을 12비트 부호-크기로 저장해 **크기가 2047을 못 넘는다.**
     관절이 0 이나 4095 근처면 그 자리에서 터진다:
         ValueError: Magnitude 2048 exceeds 2047
     실제로 shoulder_pan 이 원시 위치 1 이어서 겪었다(2026-10-02).
     중간에 터지면 `reset_calibration()` 이 이미 서보 레지스터를 건드린 뒤라
     팔이 어정쩡한 상태로 남는다.

  ② **리더와 팔로워의 자세가 서로 다름** ← 텔레오프가 어긋나는 주원인
     homing 은 **누른 그 순간의 자세를 중앙으로 삼는다.** 리더를 A자세에서,
     팔로워를 B자세에서 캘리브레이션하면 두 팔의 "중앙"이 달라져서
     텔레오프 내내 그 차이만큼 어긋난다. 각 관절을 나란히 놓고 비교한다.

사용:
  cd ~/manipulator_ws/envs/lerobot
  uv run python ../../setup/data/check_joints.py           # 한 번 읽고 판정
  uv run python ../../setup/data/check_joints.py --watch   # 보면서 두 팔 맞추기
"""
import sys

EDGE_HARD = 2047      # 이걸 넘으면 캘리브레이션이 실패한다
EDGE_WARN = 1800      # 여유가 적다
MID = 2047


def open_arm(kind, port, dev_id):
    """버스를 열고 캘리브레이션 정규화를 끈 상태로 둔다(원시값을 보기 위해)."""
    if kind == "follower":
        from lerobot.robots.so_follower import SOFollower as C, SOFollowerConfig as Cfg
    else:
        from lerobot.teleoperators.so_leader import SOLeader as C, SOLeaderConfig as Cfg
    cfg = Cfg(port=port)
    cfg.id = dev_id
    cfg.calibration_dir = None
    dev = C(cfg)
    dev.bus.connect()
    dev.bus.reset_calibration()
    return dev


def read_arm(kind, port, dev_id):
    dev = open_arm(kind, port, dev_id)
    try:
        return dict(dev.bus.sync_read("Present_Position", normalize=False))
    finally:
        dev.bus.disconnect()


def watch():
    """두 팔을 **보면서 맞추는** 모드.

    캘리브레이션 전에 해야 하는 두 가지를 눈으로 확인하며 할 수 있다.
      · 각 관절을 가동범위 가운데(2047)로
      · 리더와 팔로워를 **같은 자세**로  ← 이게 어긋나면 텔레오프가 평생 어긋난다
    버스는 한 번만 열고 계속 읽는다(reset_calibration 을 반복하지 않는다).
    """
    import time
    devs = {}
    for kind, port, dev_id in (("follower", "/dev/ttyFOLLOWER", "follower"),
                               ("leader", "/dev/ttyLEADER", "leader")):
        try:
            devs[kind] = open_arm(kind, port, dev_id)
        except Exception as e:
            print(f"  ❌ {kind}: {type(e).__name__}: {e}")
    if len(devs) < 2:
        for d in devs.values():
            d.bus.disconnect()
        return 1

    print("""
  ┌──────────────────────────────────────────────────────────────────┐
  │ 두 팔을 맞추세요 — 토크가 꺼져 있으니 손으로 움직이면 됩니다      │
  │                                                                  │
  │  목표 ①  모든 관절이 가운데(2047) 근처  → '중앙' 칸이 작아야 함   │
  │  목표 ②  리더와 팔로워가 같은 자세      → '차이' 칸이 작아야 함   │
  │                                                                  │
  │  둘 다 ✅ 가 되면 Ctrl+C 로 끝내고 캘리브레이션하세요             │
  └──────────────────────────────────────────────────────────────────┘
""")
    try:
        while True:
            rows, ok_all = [], True
            for n in devs["follower"].bus.motors:
                f = devs["follower"].bus.sync_read("Present_Position", [n], normalize=False)[n]
                l = devs["leader"].bus.sync_read("Present_Position", [n], normalize=False)[n]
                d = l - f
                cf, cl = abs(f - MID), abs(l - MID)
                edge = max(cf, cl)
                m = []
                if edge > EDGE_HARD:
                    m.append("❌끝")
                elif edge > EDGE_WARN:
                    m.append("⚠️끝")
                if abs(d) > 400:
                    m.append("⚠️차이")
                if m:
                    ok_all = False
                rows.append(f"  {n:<15}{f:>8}{l:>8}{d:>8}{max(cf, cl):>8}   "
                            + (" ".join(m) if m else "✅"))
            print("\033[2J\033[H", end="")
            print(f"  {'관절':<15}{'팔로워':>8}{'리더':>8}{'차이':>8}{'중앙편차':>8}   판정")
            print("  " + "─" * 62)
            print("\n".join(rows))
            print("\n  " + ("✅ 준비 완료 — Ctrl+C 후 캘리브레이션하세요"
                             if ok_all else "⏳ 조정 중 (차이·중앙편차를 줄이세요)"))
            time.sleep(0.3)
    except KeyboardInterrupt:
        print("\n  종료.")
    finally:
        for d in devs.values():
            d.bus.disconnect()
    return 0


def main():
    if "--watch" in sys.argv:
        return watch()
    arms = {}
    for kind, port, dev_id in (("follower", "/dev/ttyFOLLOWER", "follower"),
                               ("leader", "/dev/ttyLEADER", "leader")):
        try:
            arms[kind] = read_arm(kind, port, dev_id)
        except Exception as e:
            print(f"  ❌ {kind} 읽기 실패: {type(e).__name__}: {e}")
            print(f"     전원과 {port} 연결을 확인하세요")

    # 한쪽이라도 못 읽으면 "괜찮다"고 말하면 안 된다. 텔레오프는 두 팔이 다 있어야 한다.
    if len(arms) < 2:
        print()
        print("  ❌ 두 팔을 모두 읽지 못했습니다 — 캘리브레이션 이전의 문제입니다.")
        print("     모터가 응답하지 않으면 캘리브레이션을 다시 해도 소용없습니다.")
        print()
        print("     'Missing motor IDs' 가 보였다면 그 관절의 서보가 끊겼거나")
        print("     보호 모드에 들어간 것입니다. 흔한 원인:")
        print("       · 가동범위 끝에 물려 과부하 → 서보 보호 모드 (전원 재인가로 풀림)")
        print("       · 데이지체인 케이블 접촉 불량 (해당 모터와 그 앞단)")
        print()
        print("     조치: ① 팔 전원을 껐다 켠다  ② 해당 모터 케이블을 다시 꽂는다")
        print("           ③ 손으로 그 관절을 가동범위 **가운데**로 옮긴다")
        print("           ④ 이 스크립트를 다시 돌려 6개가 모두 보이는지 확인")
        if arms:
            print()
            print(f"     (읽힌 팔: {', '.join(arms)})")
        return 1
    if not arms:
        return 1

    names = list(next(iter(arms.values())))
    print(f"\n  원시 엔코더 위치 (0~4095 · 중앙 {MID})\n")
    hdr = f"  {'관절':<16}" + "".join(f"{k:>12}" for k in arms) + f"{'차이':>9}   판정"
    print(hdr)
    print("  " + "─" * (len(hdr) - 2))

    blocked, mismatch = [], []
    for n in names:
        vals = {k: a.get(n) for k, a in arms.items()}
        row = f"  {n:<16}" + "".join(f"{v:>12}" for v in vals.values())
        diff = ""
        if len(vals) == 2 and None not in vals.values():
            d = vals["leader"] - vals["follower"]
            diff = f"{d:>9}"
            if abs(d) > 400:
                mismatch.append((n, d))
        marks = []
        for k, v in vals.items():
            if v is None:
                continue
            if abs(v - MID) > EDGE_HARD:
                blocked.append((k, n, v))
                marks.append(f"❌{k} 끝에 걸림")
            elif abs(v - MID) > EDGE_WARN:
                marks.append(f"⚠️ {k} 거의 끝")
        if abs(vals.get("leader", MID) - vals.get("follower", MID)) > 400 if len(vals) == 2 else False:
            marks.append("⚠️ 두 팔 자세 차이 큼")
        print(row + diff + "   " + (" · ".join(marks) if marks else "✅"))

    print()
    if blocked:
        print("  ❌ 이대로 캘리브레이션하면 실패합니다 (Magnitude 2048 exceeds 2047)")
        for k, n, v in blocked:
            print(f"       {k}의 {n} 가 {v} — 가동범위 가운데로 옮기세요")
    if mismatch:
        print("  ⚠️  리더와 팔로워의 자세가 많이 다릅니다")
        for n, d in mismatch:
            print(f"       {n}: 차이 {d}")
        print("       homing 은 **누른 순간의 자세를 중앙으로 삼습니다.**")
        print("       두 팔을 **같은 자세**로 맞춘 뒤 캘리브레이션해야 텔레오프가 맞습니다.")
    if not blocked and not mismatch:
        print("  ✅ 캘리브레이션을 시작해도 좋습니다")
    return 1 if blocked else 0


if __name__ == "__main__":
    sys.exit(main())
