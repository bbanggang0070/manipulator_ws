# examples/SO100/so100_config.py 의 양팔판.
#
# 단일팔 so100_config는 state/action 키가 single_arm(5)·gripper(1) 둘뿐이다.
# 양팔은 BiSOFollower가 주는 12차원을 modality.json(이 폴더에 같이 둔 파일)과
# 똑같은 순서로 넷으로 쪼갠다 — left_arm(5)·left_gripper(1)·right_arm(5)·
# right_gripper(1), info.json의 action.names 순서(left_* 다음 right_*)와 반드시
# 일치해야 한다(bi_manipulator_plan.md §4-1).
#
# 카메라는 top(위, RGB)·wrist_left(왼팔 손목)·wrist_right(오른팔 손목) 3대다.
from gr00t.configs.data.embodiment_configs import register_modality_config
from gr00t.data.embodiment_tags import EmbodimentTag
from gr00t.data.types import (
    ActionConfig,
    ActionFormat,
    ActionRepresentation,
    ActionType,
    ModalityConfig,
)


bi_so100_config = {
    "video": ModalityConfig(
        delta_indices=[0],
        modality_keys=["top", "wrist_left", "wrist_right"],
    ),
    "state": ModalityConfig(
        delta_indices=[0],
        modality_keys=[
            "left_arm",
            "left_gripper",
            "right_arm",
            "right_gripper",
        ],
    ),
    "action": ModalityConfig(
        delta_indices=list(range(16)),
        modality_keys=[
            "left_arm",
            "left_gripper",
            "right_arm",
            "right_gripper",
        ],
        action_configs=[
            ActionConfig(
                rep=ActionRepresentation.RELATIVE,
                type=ActionType.NON_EEF,
                format=ActionFormat.DEFAULT,
            ),
            ActionConfig(
                rep=ActionRepresentation.ABSOLUTE,
                type=ActionType.NON_EEF,
                format=ActionFormat.DEFAULT,
            ),
            ActionConfig(
                rep=ActionRepresentation.RELATIVE,
                type=ActionType.NON_EEF,
                format=ActionFormat.DEFAULT,
            ),
            ActionConfig(
                rep=ActionRepresentation.ABSOLUTE,
                type=ActionType.NON_EEF,
                format=ActionFormat.DEFAULT,
            ),
        ],
    ),
    "language": ModalityConfig(
        delta_indices=[0],
        modality_keys=["annotation.human.task_description"],
    ),
}

register_modality_config(bi_so100_config, embodiment_tag=EmbodimentTag.NEW_EMBODIMENT)
