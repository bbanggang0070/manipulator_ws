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
    ap.add_argument("--force", action="store_true", help="--write 시 기존 지문을 덮어쓴다")
    a = ap.parse_args()
    if a.show:
        return cmd_show()
    if a.write:
        return cmd_write(a.write, a.force)
    return cmd_check(a.check)


if __name__ == "__main__":
    sys.exit(main())
