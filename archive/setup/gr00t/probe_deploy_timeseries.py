#!/usr/bin/env python
"""배포 dry-run 전 구간을 서버에 재주입해, 좌측 어트랙터로 굳는 지점을 찾는다.

선행 결과(2026-07-20):
  - 학습 분포 관측에서는 영상 효과 >> state 효과 → vis2에 시각 그라운딩 존재
  - 배포 첫 프레임 단독 주입은 pan≈0 (실패 미재현) → 정적 인식 실패가 아님
  → 실패는 closed-loop에서 시간에 따라 축적된다. 어디서/왜 굳는지 본다.

각 청크의 (관측 영상, 그 시점 실제 state)를 주입해 예측 pan을 얻고,
실제 실행된 state 궤적과 나란히 비교한다.
  - 예측이 항상 "현재 state 근처"만 내놓으면 → state 추종(어트랙터), 시각 미반영
  - 예측이 큐브 쪽으로 향하는데 실행이 안 따라갔다면 → 실행/클램프 문제

실행(5090): python ~/probe_deploy_timeseries.py
"""
import csv
import glob
import sys

import numpy as np
from PIL import Image

LANG = "Pick up the red cube and place it in the black box"
FRAMEDIR = "/tmp/deployframes"

sys.path.insert(0, "/home/airlab/gr00t_remote/Isaac-GR00T-n1d5")
from gr00t.eval.service import ExternalRobotInferenceClient  # noqa: E402


def main():
    rows = list(csv.DictReader(open(f"{FRAMEDIR}/chunks.csv")))
    frames = sorted(glob.glob(f"{FRAMEDIR}/f*.png"))
    client = ExternalRobotInferenceClient(host="localhost", port=5555)

    print(f"청크 {len(rows)}개 / 프레임 {len(frames)}개\n")
    print(f"{'chunk':>6} {'실제state_pan':>13} │ {'예측pan[0]':>10} {'[7]':>8} {'[15]':>8} │ "
          f"{'예측Δ(끝-state)':>15}")
    print("─" * 76)

    for i in range(0, min(len(rows), len(frames)), 6):
        r = rows[i]
        state = np.array([float(r[f"state_{j}"]) for j in
                          ("shoulder_pan.pos", "shoulder_lift.pos", "elbow_flex.pos",
                           "wrist_flex.pos", "wrist_roll.pos", "gripper.pos")], dtype=np.float64)
        img = np.array(Image.open(frames[i]).convert("RGB"))
        front, wrist = img[:, :640], img[:, 640:]
        obs = {
            "video.front": front[np.newaxis, ...],
            "video.wrist": wrist[np.newaxis, ...],
            "state.single_arm": state[:5][np.newaxis, ...],
            "state.gripper": state[5:6][np.newaxis, ...],
            "annotation.human.task_description": [LANG],
        }
        pan = client.get_action(obs)["action.single_arm"][:, 0]
        h = len(pan)
        print(f"{i:>6} {state[0]:>13.1f} │ {pan[0]:>10.1f} {pan[min(7,h-1)]:>8.1f} "
              f"{pan[h-1]:>8.1f} │ {pan[h-1]-state[0]:>15.1f}")

    print("─" * 76)
    print("Δ가 계속 음수면 매 청크 왼쪽으로 밀어내는 것(어트랙터).")
    print("Δ가 0 근처면 현재 자세 유지만 하는 것(무결정).")


if __name__ == "__main__":
    main()
