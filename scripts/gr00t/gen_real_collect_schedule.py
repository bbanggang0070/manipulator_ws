"""실기 co-training 수집용 **배치 스케줄** 생성 — 사람이 따라할 수 있는 형태로.

왜 필요한가:
  실기는 박스·블록을 사람이 손으로 놓는다. 그러면 무의식적으로 비슷한 자리에 놓기 쉽고,
  그 결과 sim에서 겪은 것과 **같은 종류의 분포 구멍**이 실기 데이터에 생긴다.
  실제로 기존 실기 50ep는 박스가 **완전히 고정**이었다(픽셀 중심 편차 x 7px, y 4px).
  → 배치를 미리 뽑아 표로 주고, 그대로 따라 놓게 한다.

설계:
  · **층화 추출**(구간을 나눠 각 구간에서 1개씩) — 무작위로 10개를 뽑으면 한쪽에 몰린다
    (실측: 10개 중 7개가 왼쪽). 이 프로젝트에서 표본이 얇을 때 단정하지 말라는 교훈의 적용이다.
  · 박스 자세는 sim v3/v4와 같은 분포(arc r 0.28~0.34m, θ ±66°)를 따른다.
  · **yaw는 ±90°면 충분**하다 — 박스가 직육면체라 180° 회전이 같은 모양이다.
    sim은 ±180°를 쓰지만 실기에서는 조작 부담만 늘 뿐 새로운 정보가 없다.
  · 박스 한 자세당 여러 에피소드를 묶는다(매 ep 박스를 옮기면 너무 느리다).
  · 블록은 **근접(박스에서 8~18cm)을 55%** 배분한다 — v4_200의 근접 비율과 맞춘 것으로,
    sim에서 확인된 취약 구간이다. 실기에서도 같은 구멍을 만들지 않기 위함.

사용:
  python3 gen_real_collect_schedule.py [박스자세수] [자세당ep] > schedule.md
"""
import math
import random
import sys

SEED = 20260807
BOX_R = (0.28, 0.34)        # m, 로봇 base 기준
BOX_TH_DEG = (-66, 66)      # + = 로봇 왼쪽
BOX_YAW_DEG = (-90, 90)     # 직육면체 180° 대칭 → ±90면 전 모양 커버
NEAR_FRAC = 0.55            # 블록을 박스 근처(8~18cm)에 두는 비율
NEAR_CM = (8, 18)
FAR_CM = (20, 30)


def stratified(lo, hi, n, rng):
    """구간을 n등분해 각 구간에서 1개씩 → 커버리지 보장."""
    w = (hi - lo) / n
    return [rng.uniform(lo + i * w, lo + (i + 1) * w) for i in range(n)]


def main():
    poses = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    per = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    rng = random.Random(SEED)

    th = stratified(*BOX_TH_DEG, poses, rng)
    yaw = stratified(*BOX_YAW_DEG, poses, rng)
    rng.shuffle(yaw)                       # 각도와 회전이 상관되지 않게
    r = [math.sqrt(rng.uniform(BOX_R[0] ** 2, BOX_R[1] ** 2)) * 100 for _ in range(poses)]

    total = poses * per
    n_near = round(total * NEAR_FRAC)
    kinds = ["근접"] * n_near + ["보통"] * (total - n_near)
    rng.shuffle(kinds)

    print(f"# 실기 co-training 수집 배치표 — {poses}자세 × {per}ep = **{total}ep**\n")
    print("> 박스를 자세 하나로 놓고 그 자리에서 지정된 수만큼 시연한 뒤 다음 자세로 옮긴다.")
    print("> **각도**: + = 로봇 정면 기준 **왼쪽**, − = **오른쪽** · **거리**: 로봇 base ~ 박스 중심")
    print("> **회전**: 박스를 시계 반대방향(+)으로 돌린 각도\n")
    print("| 자세 | 박스 거리 | 박스 각도 | 박스 회전 | 에피소드별 블록 위치 |")
    print("|---|---|---|---|---|")
    k = 0
    for i in range(poses):
        side = "왼" if th[i] > 5 else ("오른" if th[i] < -5 else "정면")
        blocks = []
        for _ in range(per):
            kind = kinds[k]; k += 1
            lo, hi = NEAR_CM if kind == "근접" else FAR_CM
            blocks.append(f"{kind} {rng.uniform(lo, hi):.0f}cm")
        print(f"| {i+1} | {r[i]:.0f}cm | {th[i]:+.0f}° ({side}) | {yaw[i]:+.0f}° | "
              + " · ".join(blocks) + " |")

    print(f"\n**블록 위치**: '근접 12cm' = 박스 중심에서 12cm 떨어진 곳. 방향은 자유롭게 바꿀 것")
    print(f"(같은 방향만 반복하지 말 것 — 박스 왼쪽/오른쪽/앞/뒤를 골고루).\n")
    print("## 수집 규칙\n")
    print("- **박스 벽에 닿는 배치만 제외**한다. \"붙어 있어 어렵다\"고 빼지 말 것 —")
    print("  sim에서 그 판단 때문에 유효 근접 구간이 통째로 걸러졌고, 그게 v3의 병목이었다.")
    print("- 파지 각도가 안 나오면 **박스 벽을 피해 비스듬히 접근**하는 시연을 일부러 보여줄 것.")
    print("- 성공 종결만 저장한다. 정상 ~70% + 교정(recovery) ~30% 권장.")
    print("- **카메라는 배포와 같은 위치에 고정**한다(top/wrist 모두).")
    print(f"\n<sub>생성: gen_real_collect_schedule.py (seed {SEED}, 층화추출) — "
          f"근접 배분 {NEAR_FRAC*100:.0f}%는 sim v4_200의 근접 비율(54.5%)에 맞춘 값</sub>")


if __name__ == "__main__":
    main()
