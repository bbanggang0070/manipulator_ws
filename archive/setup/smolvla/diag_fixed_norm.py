"""[진단용] SmolVLA zero-shot — 정규화 stats를 우리 로봇 실측값으로 오버라이드해서 재시도.

배경: lerobot-record CLI는 SmolVLA(비-GR00T 정책)에 대해 --dataset.rename_map/우리
데이터셋 stats를 정규화 파이프라인에 전혀 반영하지 않는다(코드 확인, factory.py
make_pre_post_processors). smolvla_base 체크포인트에 내장된 정규화 stats는
"so100-blue.buffer.action" 등 임바디먼트별 접두사 키인데, 실제 조회 키는 그냥
"action"/"observation.state"라 매칭이 안 되고 → 정규화가 통째로 스킵된다
(UnnormalizerProcessorStep._apply_transform: `key not in self._tensor_stats` → identity).
결과: 모델이 정규화 안 된 원시 state를 받고, 정규화 안 된 원시 action을 그대로
로봇에 보냄 — 스케일이 완전히 어긋나 "고정된 이상한 자세" 실패로 이어졌을 가능성.

이 스크립트는 make_pre_post_processors()를 직접 호출해 우리 데이터셋
(so101_t1_pickplace)의 실측 mean/std를 "action"/"observation.state" 평범한 키로
주입한다. lerobot-record를 안 쓰므로 데이터셋 저장 없이 관찰만 한다(15초, 스냅샷
주기 저장 + state/action 값 콘솔 출력).

실행: cd ~/manipulator_ws/envs/lerobot && uv run python ../../setup/smolvla/diag_fixed_norm.py
종료: Ctrl+C (또는 자동 60초 후)
"""
import json
import time
from pathlib import Path

import cv2
import numpy as np
import rerun as rr
import torch

from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig
from lerobot.cameras.configs import Cv2Rotation
from lerobot.policies.factory import make_pre_post_processors
from lerobot.policies.smolvla.modeling_smolvla import SmolVLAPolicy
from lerobot.policies.utils import make_robot_action
from lerobot.robots.so_follower.config_so_follower import SOFollowerRobotConfig
from lerobot.robots.so_follower.so_follower import SOFollower
from lerobot.utils.constants import ACTION
from lerobot.utils.control_utils import predict_action

SP = Path("/tmp/claude-1000/-home-airlab-manipulator-ws/93f982be-d5b5-4fcc-866a-6cd265753c60/scratchpad/diag_fixed_norm")
SP.mkdir(parents=True, exist_ok=True)

JOINT_NAMES = ["shoulder_pan.pos", "shoulder_lift.pos", "elbow_flex.pos",
               "wrist_flex.pos", "wrist_roll.pos", "gripper.pos"]

# --- 1. 우리 실측 stats 로드 (plain "action"/"observation.state" 키로) ---
raw_stats = json.loads(
    (Path.home() / ".cache/huggingface/lerobot/heongyu/so101_t1_pickplace/meta/stats.json").read_text()
)
our_stats = {
    "action": {"mean": raw_stats["action"]["mean"], "std": raw_stats["action"]["std"]},
    "observation.state": {
        "mean": raw_stats["observation.state"]["mean"],
        "std": raw_stats["observation.state"]["std"],
    },
}
print("주입할 action stats:", our_stats["action"])

# --- 2. 정책 + 오버라이드된 프로세서 ---
policy = SmolVLAPolicy.from_pretrained("lerobot/smolvla_base")
policy.to("cuda")
policy.eval()

preprocessor, postprocessor = make_pre_post_processors(
    policy.config,
    pretrained_path="lerobot/smolvla_base",
    preprocessor_overrides={
        "device_processor": {"device": "cuda"},
        "normalizer_processor": {"stats": our_stats},
    },
    postprocessor_overrides={
        "unnormalizer_processor": {"stats": our_stats},
    },
)

# 검증: 오버라이드가 실제로 먹었는지 확인
for step in postprocessor.steps:
    if type(step).__name__ == "UnnormalizerProcessorStep":
        print("postprocessor 적용된 키:", list(step.stats.keys()))
        assert ACTION in step.stats, "오버라이드 실패 — action 키가 안 들어감"
        print("✅ 정규화 오버라이드 확인됨")

# --- 3. 로봇 연결 ---
cam_cfg = {
    "camera1": OpenCVCameraConfig(index_or_path="/dev/cam_top", width=640, height=480, fps=30,
                                   fourcc="MJPG", rotation=Cv2Rotation.NO_ROTATION),
    "camera2": OpenCVCameraConfig(index_or_path="/dev/cam_wrist", width=640, height=480, fps=30,
                                   fourcc="MJPG", rotation=Cv2Rotation.NO_ROTATION),
}
# ⚠️ 안전장치: 한 스텝당 관절당 최대 8도까지만 이동 허용 (급점프 방지).
#    temporal_ensemble이 꺼져 있어 청크 경계에서 큰 점프가 나올 수 있음 — 실측 확인(8도 미설정 시 최대 93도 점프).
robot = SOFollower(SOFollowerRobotConfig(port="/dev/ttyFOLLOWER", id="follower", cameras=cam_cfg,
                                          max_relative_target=8.0))
robot.connect()
print("✅ 로봇 연결됨")

device = torch.device("cuda")
task = "Pick up the red cube and place it in the black box"

DURATION_S = 60
SNAPSHOT_EVERY_S = 1.0

rr.init("smolvla_diag_fixed_norm", spawn=True)
print("✅ rerun 뷰어 실행됨 (top/wrist 카메라 + state/action 실시간 표시)")

try:
    t0 = time.time()
    i = 0
    last_snap = -1.0
    while time.time() - t0 < DURATION_S:
        obs = robot.get_observation()
        state = [obs[n] for n in JOINT_NAMES]
        obs_frame = {
            "observation.state": np.array(state, dtype=np.float32),
            "observation.images.camera1": obs["camera1"],
            "observation.images.camera2": obs["camera2"],
        }
        action_values = predict_action(
            observation=obs_frame,
            policy=policy,
            device=device,
            preprocessor=preprocessor,
            postprocessor=postprocessor,
            use_amp=False,
            task=task,
            robot_type=robot.robot_type,
        )
        act_dict = make_robot_action(action_values, {ACTION: {"names": JOINT_NAMES}})
        robot.send_action(act_dict)

        elapsed = time.time() - t0
        rr.set_time(sequence=i, timeline="frame")
        rr.log("camera1_top", rr.Image(obs["camera1"]))
        rr.log("camera2_wrist", rr.Image(obs["camera2"]))
        for name, v in zip(JOINT_NAMES, state):
            rr.log(f"state/{name}", rr.Scalars(v))
        for name, v in act_dict.items():
            rr.log(f"action/{name}", rr.Scalars(v))

        if elapsed - last_snap >= SNAPSHOT_EVERY_S:
            last_snap = elapsed
            print(f"[{elapsed:5.1f}s] state={[f'{v:.1f}' for v in state]}")
            print(f"           action={[f'{v:.1f}' for v in act_dict.values()]}")
            cv2.imwrite(str(SP / f"frame_{int(elapsed):03d}s.jpg"),
                        cv2.cvtColor(obs["camera1"], cv2.COLOR_RGB2BGR))
        i += 1
except KeyboardInterrupt:
    print("중단됨")
finally:
    robot.disconnect()
    print(f"✅ 종료 — 스냅샷: {SP}")
