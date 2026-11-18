"""양팔 rest(홈) 자세 — goto_home_bi.py(시행 전 초기화)와 client/eval_lerobot_bi.py(시행 끝 복귀)가 같이 쓴다.
값의 근거(300ep 첫 프레임 state 중앙값, 2026-10-16)는 goto_home_bi.py 머리말 참고.
"""
TARGET = {
    "left_shoulder_pan.pos": 3.6, "left_shoulder_lift.pos": -98.0, "left_elbow_flex.pos": 90.3,
    "left_wrist_flex.pos": 71.8, "left_wrist_roll.pos": -2.6, "left_gripper.pos": 2.1,
    "right_shoulder_pan.pos": -0.4, "right_shoulder_lift.pos": -98.4, "right_elbow_flex.pos": 91.9,
    "right_wrist_flex.pos": 73.4, "right_wrist_roll.pos": -0.2, "right_gripper.pos": 1.8,
}
