"""수집 시작 자세(rest)를 **매 에피소드 같게** 맞추는 게이트.

왜 필요한가 (1차 수집 2026-10-06 실패에서):
  80ep 의 첫 프레임 자세 표준편차가 wrist_flex ±14.3° · gripper ±11.0° ·
  wrist_roll ±9.0° 였다. rest 가 이만큼 흔들리면 두 가지가 망가진다.
    ① **배포 홈 자세를 정할 수 없다.** goto_home_*.py 는 "학습 시작 분포의 평균"
       으로 출발해야 하는데, 그 평균이 넓게 퍼져 있으면 어디로 가도 분포 가장자리다.
       실제로 옛 홈(so101_blocktask_real 기준)과 18.3° 어긋난 채 평가를 돌렸고
       모델이 물체를 집지 못했다.
    ② 같은 지시문·같은 배치인데 시작 자세가 다르면 **그 차이가 행동 차이로
       학습된다** — 대응쌍이 측정하려는 언어 신호에 잡음을 얹는다.

쓰는 법 (record_real_lang.sh 가 자동으로 호출한다):
  python3 rest_gate.py --set   <데이터셋루트>   # 지금 리더 자세를 기준으로 저장
  python3 rest_gate.py --check <데이터셋루트>   # 기준 안에 들 때까지 대기
  python3 rest_gate.py --show  <데이터셋루트>

⚠️ 읽기만 하고 **장비 상태를 바꾸지 않는다.** 캘리브레이션 레지스터를 건드렸다가
   다음 연결에서 "Mismatch between calibration values..." 가 뜬 적이 있다.
   여기서는 reset_calibration() 을 아예 부르지 않는다(정규화값만 쓰므로 불필요).
"""
import argparse
import json
import os
import sys
import time

TOL = float(os.environ.get("REST_TOL", "6.0"))     # 관절당 허용 오차(°)
FILE = "rest_pose.json"


def paths(root):
    """(읽을 때 우선순위 순서, 지금 쓸 경로) 를 돌려준다.

    ⚠️ **데이터셋 폴더를 만들면 안 된다.** lerobot 의 LeRobotDataset.create 는
       `root.mkdir(exist_ok=False)` 로 만들기 때문에, 첫 에피소드 전에 우리가
       폴더를 만들어 두면 `FileExistsError` 로 수집이 아예 시작되지 않는다
       (2026-10-07 실제 발생). 그래서 폴더가 아직 없으면 **옆에** 적어 두고,
       첫 저장이 끝난 뒤 record_real_lang.sh 가 안으로 옮긴다.
    """
    inside = os.path.join(root, FILE)
    staged = os.path.join(os.path.dirname(os.path.abspath(root)),
                          f".{os.path.basename(os.path.normpath(root))}_{FILE}")
    write = inside if os.path.isdir(root) else staged
    return [inside, staged], write


def read_leader():
    from lerobot.teleoperators.so_leader import SOLeader as C, SOLeaderConfig as Cfg
    cfg = Cfg(port=os.environ.get("LEADER_PORT", "/dev/ttyLEADER"))
    cfg.id = "leader"
    # ⚠️ SOLeaderConfig 에는 calibration_dir 필드가 **없는데** 베이스 클래스
    #    Teleoperator.__init__ 이 config.calibration_dir 을 읽는다. 안 넣으면
    #    AttributeError 로 죽는다. None = 기본 캘리브레이션 폴더를 쓴다.
    cfg.calibration_dir = None
    dev = C(cfg)
    dev.connect(calibrate=False)
    try:
        return {k: float(v) for k, v in dev.bus.sync_read("Present_Position").items()}
    finally:
        dev.disconnect()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--set", action="store_true", help="지금 자세를 기준으로 저장")
    g.add_argument("--check", action="store_true", help="기준 안에 들 때까지 대기")
    g.add_argument("--show", action="store_true")
    a = ap.parse_args()
    reads, path = paths(a.root)
    found = next((p for p in reads if os.path.exists(p)), None)

    if a.show:
        if not found:
            print("  기준 자세 없음"); return 1
        t = json.load(open(found))
        print("  기준 자세: " + " · ".join(f"{k.split('.')[0]} {v:+.1f}" for k, v in t.items()))
        return 0

    if a.set:
        t = read_leader()
        json.dump(t, open(path, "w"), indent=1)
        print("  ✅ 기준 자세 저장: " +
              " · ".join(f"{k.split('.')[0]} {v:+.1f}" for k, v in t.items()))
        return 0

    # --check
    if not found:
        # 첫 에피소드 — 기준이 없으면 지금 자세를 기준으로 삼는다.
        print("  기준 자세가 없어 **지금 자세**를 기준으로 삼습니다.")
        print("  리더를 거치대에 놓은 상태인지 확인하세요.")
        input("  준비됐으면 Enter ")
        json.dump(read_leader(), open(path, "w"), indent=1)
        print("  ✅ 저장했습니다. 이후 에피소드는 이 자세와 대조합니다.")
        return 0

    tgt = json.load(open(found))
    for i in range(1000):
        cur = read_leader()
        d = {k: cur.get(k, 0.0) - v for k, v in tgt.items()}
        worst = max(d, key=lambda k: abs(d[k]))
        if abs(d[worst]) <= TOL:
            print(f"  ✅ 시작 자세 OK (최대 오차 {abs(d[worst]):.1f}° ≤ {TOL}°)")
            return 0
        print(f"  ⏸ 리더를 rest 로 되돌리세요 — 최대 오차 {abs(d[worst]):.1f}° "
              f"({worst.split('.')[0]} {d[worst]:+.1f}°)")
        print("     " + " · ".join(f"{k.split('.')[0]}{v:+.0f}" for k, v in d.items()))
        # 사람이 손으로 맞추는 동안 기다린다. Enter 를 치면 그대로 진행한다
        # (물리적으로 못 맞추는 상황에서 수집을 막아 세우지는 않는다).
        try:
            r = input("     맞췄으면 Enter · 그냥 진행하려면 g + Enter: ").strip().lower()
        except EOFError:
            return 0
        if r == "g":
            print("  ⚠️  오차를 안고 진행합니다 — 검증기의 시작 자세 편차가 올라갑니다")
            return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
