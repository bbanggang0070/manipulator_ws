"""양팔 버전 rest_gate — setup/p5_real_cleanup/rest_gate.py의 BiSOLeader 판.

왜 필요한가: setup/p5_real_cleanup/rest_gate.py 는 SOLeader(단일팔) 하나만 읽는다.
양팔은 **두 리더가 동시에** rest 기준 안에 들어와야 한다 — 한쪽만 맞고
다른 쪽이 흔들리면 그 팔의 시작 자세 편차가 그대로 데이터에 남는다
(단일팔에서 겪은 rest 흔들림 문제, bi_manipulator_plan.md §3-2 참고).

쓰는 법 (setup/p6_real_bimanual/data/record_bi.sh 가 자동으로 호출한다):
  python3 rest_gate_bi.py --set   <데이터셋루트>
  python3 rest_gate_bi.py --check <데이터셋루트>
  python3 rest_gate_bi.py --show  <데이터셋루트>

⚠️ setup/p5_real_cleanup/rest_gate.py 와 같은 이유로 reset_calibration()을 부르지 않는다
   (정규화값만 읽으므로 불필요 — 캘리브레이션 레지스터를 건드리지 않는다).
"""
import argparse
import json
import os
import select
import sys

TOL = float(os.environ.get("REST_TOL", "6.0"))
# wrist_roll은 그리퍼가 물체를 쥔 방향과 무관한 자유도라 작업 성패에 영향이 없다 —
# eval_lerobot.py의 STOP_ON_REST가 이미 같은 이유로 이 관절만 허용 오차를 15°로
# 풀어 둔 전례가 있다(실기 cleanup v3, wrist_roll straggler 때문에 "성공했는데
# 타임아웃"하던 문제). 양팔 12관절을 동시에 6° 안에 넣는 건 단일팔보다 훨씬
# 어렵고, 2026-10-14 실측으로도 wrist_roll이 반복해서 10~13°에 걸렸다 — 같은
# 자유도이므로 같은 처방을 쓴다. 다른 관절(파지·배치에 직접 쓰이는)은 그대로 6°.
#   ⚠️ 여기 키에는 ".pos" 접미사를 붙이지 않는다 — read_leaders()가 sync_read()를
#      직접 써서 raw 모터 이름("wrist_roll")을 쓰기 때문이다(get_observation()의
#      "{motor}.pos" 관례와 다르다). ".pos"를 붙였다가 매칭이 전혀 안 돼 계속
#      기본 6°로 떨어진 적이 있다(2026-10-14) — 고칠 때 또 틀리지 않도록 적어 둔다.
TOL_JOINT = {"wrist_roll": float(os.environ.get("REST_TOL_WRIST_ROLL_DEG", "15"))}
FILE = "rest_pose_bi.json"


def tol_for(key):
    bare = key.removeprefix("left_").removeprefix("right_")
    return TOL_JOINT.get(bare, TOL)


def paths(root):
    inside = os.path.join(root, FILE)
    staged = os.path.join(os.path.dirname(os.path.abspath(root)),
                          f".{os.path.basename(os.path.normpath(root))}_{FILE}")
    write = inside if os.path.isdir(root) else staged
    return [inside, staged], write


def read_leaders():
    from lerobot.teleoperators.bi_so_leader import BiSOLeader as C, BiSOLeaderConfig as Cfg
    from lerobot.teleoperators.so_leader import SOLeaderConfig as ArmCfg

    left = ArmCfg(port=os.environ.get("LEADER_L_PORT", "/dev/ttyLEADER_L"))
    right = ArmCfg(port=os.environ.get("LEADER_R_PORT", "/dev/ttyLEADER_R"))
    cfg = Cfg(left_arm_config=left, right_arm_config=right)
    cfg.id = "bi_leader"
    cfg.calibration_dir = None
    dev = C(cfg)
    dev.connect(calibrate=False)
    try:
        left_pos = {f"left_{k}": float(v)
                    for k, v in dev.left_arm.bus.sync_read("Present_Position").items()}
        right_pos = {f"right_{k}": float(v)
                     for k, v in dev.right_arm.bus.sync_read("Present_Position").items()}
        return {**left_pos, **right_pos}
    finally:
        dev.disconnect()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--set", action="store_true")
    g.add_argument("--check", action="store_true")
    g.add_argument("--show", action="store_true")
    a = ap.parse_args()
    reads, path = paths(a.root)
    found = next((p for p in reads if os.path.exists(p)), None)

    if a.show:
        if not found:
            print("  기준 자세 없음"); return 1
        t = json.load(open(found))
        print("  기준 자세: " + " · ".join(f"{k} {v:+.1f}" for k, v in t.items()))
        return 0

    if a.set:
        t = read_leaders()
        json.dump(t, open(path, "w"), indent=1)
        print("  ✅ 기준 자세 저장(양팔): " +
              " · ".join(f"{k} {v:+.1f}" for k, v in t.items()))
        return 0

    # --check
    if not found:
        print("  기준 자세가 없어 **지금 자세**를 기준으로 삼습니다.")
        print("  양팔 리더를 모두 거치대에 놓은 상태인지 확인하세요.")
        input("  준비됐으면 Enter ")
        json.dump(read_leaders(), open(path, "w"), indent=1)
        print("  ✅ 저장했습니다. 이후 에피소드는 이 자세와 대조합니다.")
        return 0

    tgt = json.load(open(found))
    # 실패 메시지는 찍지 않는다 — 리더를 rest에 놓으면 조용히 재측정하다가 허용치 안에
    # 들어오는 순간 OK 한 줄만 찍고 넘어간다(매번 뜨는 관절별 오차 로그가 수집 중 방해됐다).
    # 오차를 안고 그냥 진행하려면 g + Enter (화면에는 안내 없이 받는다).
    while True:
        cur = read_leaders()
        d = {k: cur.get(k, 0.0) - v for k, v in tgt.items()}
        # 관절마다 허용 오차가 다르므로 "오차 절댓값"이 아니라 "허용치를 넘은 정도"
        # 로 가장 급한 관절을 고른다. 전부 허용치 이내면 넘은 정도가 전부 음수다.
        worst = max(d, key=lambda k: abs(d[k]) - tol_for(k))
        if abs(d[worst]) <= tol_for(worst):
            print(f"  ✅ 시작 자세 OK (최대 오차 {abs(d[worst]):.1f}° ≤ {tol_for(worst)}°, 양팔)")
            return 0
        try:
            ready, _, _ = select.select([sys.stdin], [], [], 0.3)
        except (OSError, ValueError):
            ready = []
        if ready:
            line = sys.stdin.readline()
            if line == "":          # EOF — 터미널이 없으면 막지 않는다
                return 0
            if line.strip().lower() == "g":
                print("  ⚠️  오차를 안고 진행합니다 — 검증기의 시작 자세 편차가 올라갑니다")
                return 0


if __name__ == "__main__":
    sys.exit(main())
