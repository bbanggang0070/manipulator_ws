"""캘리브레이션 지문 — 수집 도중/전후에 캘리브레이션이 바뀌면 **탐지**한다.

왜 필요한가:
  캘리브레이션을 바꾸면 리더→팔로워 매핑과 관절 공간이 달라진다. 그런데 그 변화는
  데이터 어디에도 기록되지 않아 **아무 경고 없이** 데이터셋을 서로 안 맞는 두
  덩어리로 가른다. 이 프로젝트에서 조용한 실패에 이미 여러 번 당했다
  (판정기 필터, 자산 배포 누락, 빈 지시문).

  특히 위험한 두 지점:
    · 단계 사이 — 80ep → +80 → +90으로 나눠 모으는데 중간에 재캘리브레이션하면
      앞뒤가 다른 공간이 된다
    · 학습 후 배포 전 — 학습한 관절 공간과 다른 공간으로 추론하면 정책이 깨진다

  그래서 **수집 시작 시 지문을 데이터셋 폴더에 남기고**, 이후 수집 재개와
  검증 때마다 현재 캘리브레이션과 대조한다.

사용:
  python3 calib_fingerprint.py --write <데이터셋루트>   # 지문 기록(없을 때만)
  python3 calib_fingerprint.py --check <데이터셋루트>   # 대조 (불일치면 exit 1)
  python3 calib_fingerprint.py --show                   # 현재 지문만 출력
"""
import argparse
import glob
import hashlib
import json
import os
import sys
from datetime import datetime

CALIB_DIR = os.path.expanduser("~/.cache/huggingface/lerobot/calibration")
SNAP_NAME = "calibration_snapshot.json"


def fingerprint():
    """현재 캘리브레이션 파일들의 해시. `.bak`은 제외한다(백업은 바뀌어도 무관)."""
    out = {}
    for p in sorted(glob.glob(os.path.join(CALIB_DIR, "**", "*.json"), recursive=True)):
        if p.endswith(".bak"):
            continue
        rel = os.path.relpath(p, CALIB_DIR)
        with open(p, "rb") as f:
            out[rel] = hashlib.sha256(f.read()).hexdigest()[:16]
    return out


def snap_path(root):
    return os.path.join(os.path.expanduser(root), SNAP_NAME)


# lerobot 클래스 이름이 캘리브레이션 폴더를 정한다(타입 이름이 아니다).
#   SO101Follower.name == 'so_follower'  → robots/so_follower/<id>.json
#   SO101Leader.name   == 'so_leader'    → teleoperators/so_leader/<id>.json
# 그래서 --robot.type=so101_follower 로 돌려도 so_follower/ 를 읽고 쓴다.
LIVE = [("팔로워", "robots/so_follower/follower.json"),
        ("리더  ", "teleoperators/so_leader/leader.json")]

# 양팔(bi-manipulator) 버전 — BiSOFollower/BiSOLeader가 내부적으로 서브암을
# f"{id}_left"/f"{id}_right"로 만들어 **같은 so_follower/so_leader 폴더**에
# 저장한다(클래스 이름이 폴더를 정하므로). id는 setup/p6_real_bimanual/data/record_bi.sh 와
# 맞춰야 한다. fingerprint()는 CALIB_DIR 전체를 긁으므로 --check/--write는
# 수정 없이 그대로 이 파일들도 감지한다 — 이 배너는 표시용일 뿐이다.
LIVE_BI = [("왼팔 팔로워", "robots/so_follower/bi_follower_left.json"),
           ("오른팔 팔로워", "robots/so_follower/bi_follower_right.json"),
           ("왼팔 리더  ", "teleoperators/so_leader/bi_leader_left.json"),
           ("오른팔 리더  ", "teleoperators/so_leader/bi_leader_right.json")]


def cmd_banner(live=LIVE):
    """수집·텔레오프가 **실제로 쓸** 캘리브레이션을 한눈에 보여 준다.

    스크립트가 어떤 캘리브레이션으로 도는지 화면에 안 나오면, 재캘리브레이션을
    했는지 안 했는지조차 확인할 수 없다. 시작할 때마다 찍는다.
    """
    fp = fingerprint()
    missing = False
    print("  캘리브레이션 (이 실행에 적용됨)")
    for label, rel in live:
        full = os.path.join(CALIB_DIR, rel)
        if not os.path.exists(full):
            print(f"    {label}  ❌ 없음: {rel}")
            missing = True
            continue
        mt = datetime.fromtimestamp(os.path.getmtime(full)).strftime("%Y-%m-%d %H:%M")
        print(f"    {label}  {fp.get(rel, '?')}  ({mt})  {rel}")
    if missing:
        print("    → lerobot-calibrate 로 먼저 캘리브레이션하세요")
        return 1
    return 0


def cmd_show():
    fp = fingerprint()
    if not fp:
        print(f"  ⚠️  캘리브레이션 파일이 없다: {CALIB_DIR}")
        return 1
    print(f"  현재 캘리브레이션 ({CALIB_DIR})")
    for k, v in fp.items():
        full = os.path.join(CALIB_DIR, k)
        mt = datetime.fromtimestamp(os.path.getmtime(full)).strftime("%Y-%m-%d %H:%M")
        print(f"    {k:<42} {v}  ({mt})")
    return 0


def cmd_write(root, force=False):
    sp = snap_path(root)
    if not os.path.isdir(os.path.dirname(sp)):
        print(f"  ⏸ 데이터셋 폴더가 아직 없다 — 첫 에피소드 뒤에 기록된다")
        return 0
    if os.path.exists(sp) and not force:
        return cmd_check(root)
    fp = fingerprint()
    if not fp:
        print(f"  ⚠️  캘리브레이션이 없어 지문을 남기지 못했다")
        return 0
    with open(sp, "w") as f:
        json.dump({"written": datetime.now().isoformat(timespec="seconds"),
                   "calibration": fp}, f, indent=2)
    print(f"  ✅ 캘리브레이션 지문 기록 — {os.path.basename(sp)}")
    for k, v in fp.items():
        print(f"       {k} {v}")
    return 0


def cmd_check(root):
    sp = snap_path(root)
    if not os.path.exists(sp):
        print(f"  ⏸ 지문 없음 ({SNAP_NAME}) — 대조 건너뜀")
        return 0
    saved = json.load(open(sp))
    old, new = saved["calibration"], fingerprint()
    if old == new:
        print(f"  ✅ 캘리브레이션 일치 (기록 {saved['written'][:16]})")
        return 0

    print("  ❌ 캘리브레이션이 수집 시작 때와 다르다")
    for k in sorted(set(old) | set(new)):
        a, b = old.get(k, "(없음)"), new.get(k, "(없음)")
        if a != b:
            print(f"       {k}\n         수집 시작: {a}\n         현재     : {b}")
    print("""
  이게 왜 문제인가:
    캘리브레이션이 바뀌면 관절 공간이 달라진다. 지금 이어서 모으면 데이터셋이
    **서로 안 맞는 두 덩어리**가 되고, 학습해도 어느 쪽도 제대로 못 배운다.

  선택지:
    ① 캘리브레이션을 되돌린다 (백업이 있다면 — follower_*.json.bak)
    ② 지금까지 모은 것을 버리고 새 이름으로 다시 시작한다
    ③ 의도한 교체였다면 --write --force 로 지문을 갱신한다
       (앞서 모은 에피소드가 새 캘리브레이션과 맞을 때만)

  ⚠️ 학습을 마친 뒤에도 배포 전까지 캘리브레이션을 바꾸면 안 된다.
     학습한 관절 공간과 다른 공간으로 추론하게 된다.
""")
    return 1


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", metavar="ROOT")
    g.add_argument("--check", metavar="ROOT")
    g.add_argument("--show", action="store_true")
    g.add_argument("--banner", action="store_true",
                   help="실제로 쓰이는 두 파일만 한 줄씩 — 스크립트 시작 배너용")
    g.add_argument("--banner-bi", action="store_true",
                   help="양팔(bi_follower_left/right, bi_leader_left/right) 네 파일 배너")
    ap.add_argument("--force", action="store_true", help="--write 시 기존 지문을 덮어쓴다")
    a = ap.parse_args()
    if a.banner:
        return cmd_banner()
    if a.banner_bi:
        return cmd_banner(LIVE_BI)
    if a.show:
        return cmd_show()
    if a.write:
        return cmd_write(a.write, a.force)
    return cmd_check(a.check)


if __name__ == "__main__":
    sys.exit(main())
