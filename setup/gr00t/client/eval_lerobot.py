# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
This is the new Gr00T policy eval script with so100, so101 robot arm. Based on:
https://github.com/huggingface/lerobot/pull/777

Example command:

```shell

python eval_gr00t_so100.py \
    --robot.type=so100_follower \
    --robot.port=/dev/ttyACM0 \
    --robot.id=lil_guy \
    --robot.cameras="{ wrist: {type: opencv, index_or_path: 9, width: 640, height: 480, fps: 30}, front: {type: opencv, index_or_path: 15, width: 640, height: 480, fps: 30}}" \
    --policy_host=10.112.209.136 \
    --lang_instruction="Grab markers and place into pen holder."
```


First replay to ensure the robot is working:
```shell
python -m lerobot.replay \
    --robot.type=so100_follower \
    --robot.port=/dev/ttyACM0 \
    --robot.id=lil_guy \
    --dataset.repo_id=youliangtan/so100-table-cleanup \
    --dataset.episode=2
```
"""

import logging
import os
import threading
import time

# 스텝 간격(초). 학습 fps=30Hz(0.033s)에 맞춤 → sim보다 빠른 실행으로 인한 덜컹임 완화.
# 실험: STEP_DT=0.02 (빠름/50Hz) ~ 0.05 (느림/부드러움) 환경변수로 조정.
_STEP_DT = float(os.environ.get("STEP_DT", "0.033"))

# 비동기 추론: 현재 청크를 실행하는 동안 다음 청크를 백그라운드에서 미리 받아와 정지 구간 제거.
# 이러면 horizon을 낮춰(closed-loop↑ 파지↑) 도 정지가 안 생겨 부드럽다. ASYNC=0 이면 기존 동기 방식.
_ASYNC = os.environ.get("ASYNC", "1") == "1"

# 카메라 이미지 JPEG 압축 전송: 1.84MB → ~50KB (WiFi 전송지연 제거). JPEG=0 이면 원본(uint8) 전송.
_JPEG = os.environ.get("JPEG", "1") == "1"
_JPEG_Q = int(os.environ.get("JPEG_Q", "90"))

# Temporal ensembling: 매 스텝 관측하며 겹치는 청크들을 블렌딩 → 청크 경계 튐 제거(부드러운 모션).
# ENSEMBLE=0 이면 기존 청크 단위 실행. ENSEMBLE_W: 최신 예측 가중치(클수록 최신만, 0=균등평균).
_ENSEMBLE = os.environ.get("ENSEMBLE", "1") == "1"
_ENS_W = float(os.environ.get("ENSEMBLE_W", "0.1"))


def _jpeg_encode_videos(obs_dict):
    """video.* 값(B,H,W,C uint8)을 JPEG 바이트로 인코딩(채널 순서는 불투명하게 보존)."""
    import cv2

    for k in list(obs_dict.keys()):
        if not k.startswith("video."):
            continue
        arr = np.asarray(obs_dict[k])
        frames = [
            cv2.imencode(".jpg", arr[b], [cv2.IMWRITE_JPEG_QUALITY, _JPEG_Q])[1].tobytes()
            for b in range(arr.shape[0])
        ]
        obs_dict[k] = {"__jpeg__": frames, "shape": list(arr.shape)}
    return obs_dict
from dataclasses import asdict, dataclass
from pprint import pformat

import draccus
import matplotlib.pyplot as plt
import numpy as np
from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig  # noqa: F401
from lerobot.robots import (  # noqa: F401
    Robot,
    RobotConfig,
    make_robot_from_config,
    so_follower,  # lerobot 0.6.x: so100/so101_follower 통합 모듈 (구버전 이름에서 패치)
)
from lerobot.utils.utils import init_logging, log_say

# NOTE:
# Sometimes we would like to abstract different env, or run this on a separate machine
# User can just move this single python class method gr00t/eval/service.py
# to their code or do the following line below
# sys.path.append(os.path.expanduser("~/Isaac-GR00T/gr00t/eval/"))
from service import ExternalRobotInferenceClient

# from gr00t.eval.service import ExternalRobotInferenceClient

#################################################################################
# rerun 실시간 시각화 + 지연 계측 (RERUN=1 기본, pi0 진단 패턴 재사용)
# - camera/*: front/wrist 영상
# - state/*: 관절 상태, action_sent/*: 실제 전송 액션(클램프 후)
# - timing/infer_ms: 서버 추론+왕복 지연, timing/act_dt_ms: send_action 간격(끊김 진단)
import os as _os

_RERUN = _os.environ.get("RERUN", "1") == "1"
if _RERUN:
    import rerun as rr

    rr.init("gr00t_infer", spawn=True)
_FRAME = {"i": 0, "t_act": None}


def _rr_obs(observation_dict, camera_keys, state_keys):
    if not _RERUN:
        return
    rr.set_time_sequence("frame", _FRAME["i"])
    for k in camera_keys:
        v = observation_dict.get(k)
        if v is not None and getattr(v, "ndim", 0) == 3:
            rr.log(f"camera/{k}", rr.Image(v))
    for k in state_keys:
        if k in observation_dict:
            rr.log(f"state/{k}", rr.Scalars(float(observation_dict[k])))


def _rr_action(sent):
    if not _RERUN:
        return
    import time as _time

    now = _time.perf_counter()
    if _FRAME["t_act"] is not None:
        rr.log("timing/act_dt_ms", rr.Scalars((now - _FRAME["t_act"]) * 1e3))
    _FRAME["t_act"] = now
    rr.set_time_sequence("frame", _FRAME["i"])
    _FRAME["i"] += 1
    for k, v in sent.items():
        rr.log(f"action_sent/{k}", rr.Scalars(float(v)))


def _rr_infer_ms(ms):
    if _RERUN:
        rr.set_time_sequence("frame", _FRAME["i"])
        rr.log("timing/infer_ms", rr.Scalars(ms))


#################################################################################
# 파일 로깅 + 영상 녹화 (LOGDIR 환경변수, 기본 on) — 실행 후 오프라인 분석용
# - chunks.csv: 청크별 [관측 state 6, infer_ms]  → 청크 경계 왕복(진동) 진단
# - actions.csv: 스텝별 전송 액션 6              → 청크 내/간 명령 궤적
# - video.mp4: 정책이 본 front|wrist (청크 경계마다 1프레임)
import csv as _csv
from datetime import datetime as _dt

_LOGDIR = _os.environ.get(
    "LOGDIR",
    _os.path.expanduser(f"~/manipulator_ws/logs/gr00t_infer/{_dt.now():%Y%m%d_%H%M%S}"),
)
_os.makedirs(_LOGDIR, exist_ok=True)
_JOINTS = ["shoulder_pan.pos", "shoulder_lift.pos", "elbow_flex.pos",
           "wrist_flex.pos", "wrist_roll.pos", "gripper.pos"]
_chunk_f = open(f"{_LOGDIR}/chunks.csv", "w", buffering=1)
_chunk_w = _csv.writer(_chunk_f)
_chunk_w.writerow(["chunk", "infer_ms"] + [f"state_{j}" for j in _JOINTS])
_act_f = open(f"{_LOGDIR}/actions.csv", "w", buffering=1)
_act_w = _csv.writer(_act_f)
_act_w.writerow(["chunk", "i", f_ := "t_ms"] + [f"sent_{j}" for j in _JOINTS])
_VID = {"w": None}
_CHUNK = {"n": 0, "t0": None}
print(f"[LOG] {_LOGDIR}")

import atexit as _atexit


@_atexit.register
def _finalize_video():
    # Ctrl+C 종료 시에도 mp4 moov atom이 기록되도록 릴리즈 (2026-07-16 깨짐 재발 방지)
    if _VID["w"] is not None:
        _VID["w"].release()
    _chunk_f.close()
    _act_f.close()


def _log_chunk(observation_dict, camera_keys, infer_ms):
    import cv2, time as _t

    if _CHUNK["t0"] is None:
        _CHUNK["t0"] = _t.perf_counter()
    st = [observation_dict.get(j, float("nan")) for j in _JOINTS]
    _chunk_w.writerow([_CHUNK["n"], f"{infer_ms:.0f}"] + [f"{v:.2f}" for v in st])
    imgs = [observation_dict[k] for k in camera_keys if k in observation_dict]
    if imgs:
        import numpy as _np

        frame = _np.concatenate(imgs, axis=1)
        if _VID["w"] is None:
            h, w = frame.shape[:2]
            _VID["w"] = cv2.VideoWriter(f"{_LOGDIR}/video.mp4",
                                        cv2.VideoWriter_fourcc(*"mp4v"), 4, (w, h))
        _VID["w"].write(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
    _CHUNK["n"] += 1


def _log_action(sent):
    import time as _t

    t_ms = (_t.perf_counter() - (_CHUNK["t0"] or _t.perf_counter())) * 1e3
    _act_w.writerow([_CHUNK["n"] - 1, _FRAME["i"], f"{t_ms:.0f}"]
                    + [f"{float(sent.get(j, float('nan'))):.2f}" for j in _JOINTS])


#################################################################################


class Gr00tRobotInferenceClient:
    """The exact keys used is defined in modality.json

    This currently only supports so100_follower, so101_follower
    modify this code to support other robots with other keys based on modality.json
    """

    def __init__(
        self,
        host="localhost",
        port=5555,
        camera_keys=[],
        robot_state_keys=[],
        show_images=False,
    ):
        self.policy = ExternalRobotInferenceClient(host=host, port=port)
        self.camera_keys = camera_keys
        self.robot_state_keys = robot_state_keys
        self.show_images = show_images
        assert (
            len(robot_state_keys) == 6
        ), f"robot_state_keys should be size 6, but got {len(robot_state_keys)} "
        self.modality_keys = ["single_arm", "gripper"]

    def get_action(self, observation_dict, lang: str):
        # first add the images
        obs_dict = {f"video.{key}": observation_dict[key] for key in self.camera_keys}

        # show images
        if self.show_images:
            view_img(obs_dict)

        # Make all single float value of dict[str, float] state into a single array
        state = np.array([observation_dict[k] for k in self.robot_state_keys])
        obs_dict["state.single_arm"] = state[:5].astype(np.float64)
        obs_dict["state.gripper"] = state[5:6].astype(np.float64)
        obs_dict["annotation.human.task_description"] = lang

        # then add a dummy dimension of np.array([1, ...]) to all the keys (assume history is 1)
        for k in obs_dict:
            if isinstance(obs_dict[k], np.ndarray):
                obs_dict[k] = obs_dict[k][np.newaxis, ...]
            else:
                obs_dict[k] = [obs_dict[k]]

        # 카메라 이미지 JPEG 압축(WiFi 전송지연 완화)
        if _JPEG:
            obs_dict = _jpeg_encode_videos(obs_dict)

        # get the action chunk via the policy server
        # Example of obs_dict for single camera task:
        # obs_dict = {
        #     "video.front": np.zeros((1, 480, 640, 3), dtype=np.uint8),
        #     "video.wrist": np.zeros((1, 480, 640, 3), dtype=np.uint8),
        #     "state.single_arm": np.zeros((1, 5)),
        #     "state.gripper": np.zeros((1, 1)),
        #     "annotation.human.action.task_description": [self.language_instruction],
        # }
        action_chunk = self.policy.get_action(obs_dict)

        # convert the action chunk to a list of dict[str, float]
        lerobot_actions = []
        action_horizon = action_chunk[f"action.{self.modality_keys[0]}"].shape[0]
        for i in range(action_horizon):
            action_dict = self._convert_to_lerobot_action(action_chunk, i)
            lerobot_actions.append(action_dict)
        return lerobot_actions

    def _convert_to_lerobot_action(
        self, action_chunk: dict[str, np.array], idx: int
    ) -> dict[str, float]:
        """
        This is a magic function that converts the action chunk to a dict[str, float]
        This is because the action chunk is a dict[str, np.array]
        and we want to convert it to a dict[str, float]
        so that we can send it to the robot
        """
        concat_action = np.concatenate(
            [np.atleast_1d(action_chunk[f"action.{key}"][idx]) for key in self.modality_keys],
            axis=0,
        )
        assert len(concat_action) == len(self.robot_state_keys), "this should be size 6"
        # convert the action to dict[str, float]
        action_dict = {key: concat_action[i] for i, key in enumerate(self.robot_state_keys)}
        return action_dict


#################################################################################


def view_img(img, overlay_img=None):
    """
    This is a matplotlib viewer since cv2.imshow can be flaky in lerobot env
    """
    if isinstance(img, dict):
        # stack the images horizontally
        img = np.concatenate([img[k] for k in img], axis=1)

    plt.imshow(img)
    plt.title("Camera View")
    plt.axis("off")
    plt.pause(0.001)  # Non-blocking show
    plt.clf()  # Clear the figure for the next frame


def print_yellow(text):
    print("\033[93m {}\033[00m".format(text))


@dataclass
class EvalConfig:
    robot: RobotConfig  # the robot to use
    policy_host: str = "localhost"  # host of the gr00t server
    policy_port: int = 5555  # port of the gr00t server
    action_horizon: int = 8  # number of actions to execute from the action chunk
    lang_instruction: str = "Grab pens and place into pen holder."
    play_sounds: bool = False  # whether to play sounds
    timeout: int = 60  # timeout in seconds
    show_images: bool = False  # whether to show images


@draccus.wrap()
def eval(cfg: EvalConfig):
    init_logging()
    logging.info(pformat(asdict(cfg)))

    # Step 1: Initialize the robot
    robot = make_robot_from_config(cfg.robot)
    robot.connect()

    # get camera keys from RobotConfig
    camera_keys = list(cfg.robot.cameras.keys())
    print("camera_keys: ", camera_keys)

    log_say("Initializing robot", cfg.play_sounds, blocking=True)

    language_instruction = cfg.lang_instruction

    # NOTE: for so100/so101, this should be:
    # ['shoulder_pan.pos', 'shoulder_lift.pos', 'elbow_flex.pos', 'wrist_flex.pos', 'wrist_roll.pos', 'gripper.pos']
    robot_state_keys = list(robot._motors_ft.keys())
    print("robot_state_keys: ", robot_state_keys)

    # Step 2: Initialize the policy
    policy = Gr00tRobotInferenceClient(
        host=cfg.policy_host,
        port=cfg.policy_port,
        camera_keys=camera_keys,
        robot_state_keys=robot_state_keys,
    )
    log_say(
        "Initializing policy client with language instruction: " + language_instruction,
        cfg.play_sounds,
        blocking=True,
    )

    # Step 3-ENS: Temporal ensembling 루프 (매 스텝 관측+블렌딩 → 부드러운 모션 + rerun 카메라 실시간)
    if _ENSEMBLE:
        _sh = {"obs": None, "step": 0, "chunks": [], "stop": False, "infer_ms": 0.0}
        _lk = threading.Lock()

        def _infer_loop():
            while not _sh["stop"]:
                with _lk:
                    obs = _sh["obs"]
                    s = _sh["step"]
                if obs is None:
                    time.sleep(0.005)
                    continue
                try:
                    _ti = time.perf_counter()
                    chunk = policy.get_action(obs, language_instruction)  # list[H] action dicts
                    _sh["infer_ms"] = (time.perf_counter() - _ti) * 1e3  # 서버 추론+왕복 실측
                except Exception:
                    continue
                with _lk:
                    _sh["chunks"].append((s, chunk))
                    cur = _sh["step"]
                    _sh["chunks"] = [(cs, c) for (cs, c) in _sh["chunks"] if cs + len(c) > cur]

        obs0 = robot.get_observation()
        _sh["obs"] = obs0
        _sh["chunks"].append((0, policy.get_action(obs0, language_instruction)))
        threading.Thread(target=_infer_loop, daemon=True).start()

        t = 0
        _tl = time.perf_counter()
        while True:
            obs = robot.get_observation()
            _rr_obs(obs, camera_keys, robot_state_keys)  # 매 스텝 → rerun 카메라 부드러움
            with _lk:
                _sh["obs"] = obs
                _sh["step"] = t
                covering = [(cs, c[t - cs]) for (cs, c) in _sh["chunks"] if cs <= t < cs + len(c)]
                n_chunks = len(_sh["chunks"])
            if covering:
                ws = np.array([np.exp(_ENS_W * (cs - t)) for (cs, _) in covering], dtype=np.float64)
                ws /= ws.sum()
                blended = {
                    jk: float(sum(w * float(ad.get(jk, 0.0)) for w, (_, ad) in zip(ws, covering)))
                    for jk in robot_state_keys
                }
                sent = robot.send_action(blended)
                sent = sent if isinstance(sent, dict) else blended
                _rr_action(sent)
                _log_action(sent)
            if t % 8 == 0:  # 30Hz/8 ≈ 4fps — video.mp4 프레임레이트와 일치
                _rr_infer_ms(_sh["infer_ms"])
                _log_chunk(obs, camera_keys, _sh["infer_ms"])
            time.sleep(_STEP_DT)
            if t % 30 == 0:
                _dt = time.perf_counter() - _tl
                _tl = time.perf_counter()
                print(f"[ensemble] step={t} covering={len(covering)} chunks={n_chunks} rate={30/_dt:.0f}Hz")
            t += 1

    # Step 3-CHUNK: 기존 청크 단위 실행 (ENSEMBLE=0)
    _next = {}

    def _prefetch(obs):
        try:
            _next["chunk"] = policy.get_action(obs, language_instruction)
        except Exception as e:  # 실패 시 메인에서 동기 재시도
            _next["err"] = e

    # 최초 청크(동기 1회)
    observation_dict = robot.get_observation()
    _rr_obs(observation_dict, camera_keys, robot_state_keys)
    action_chunk = policy.get_action(observation_dict, language_instruction)

    while True:
        # 다음 청크용 관측 (카메라 2대 읽기 — 여기가 느리면 청크 경계 정지의 원인)
        _to = time.perf_counter()
        obs_next = robot.get_observation()
        _obs_ms = (time.perf_counter() - _to) * 1e3
        _rr_obs(obs_next, camera_keys, robot_state_keys)
        _next.clear()
        th = None
        if _ASYNC:
            th = threading.Thread(target=_prefetch, args=(obs_next,), daemon=True)
            th.start()

        # 현재 청크 실행 (이 동안 다음 청크 추론이 백그라운드로 진행)
        _te = time.perf_counter()
        for i in range(cfg.action_horizon):
            action_dict = action_chunk[i]
            sent = robot.send_action(action_dict)
            sent = sent if isinstance(sent, dict) else action_dict
            _rr_action(sent)
            _log_action(sent)
            time.sleep(_STEP_DT)
        _exec_ms = (time.perf_counter() - _te) * 1e3

        # 다음 청크 확보 — 여기서 기다리는 시간(wait)이 크면 추론이 실행을 못 따라감(정지)
        _tw = time.perf_counter()
        if _ASYNC:
            th.join()
            action_chunk = _next.get("chunk")
            if action_chunk is None:
                action_chunk = policy.get_action(obs_next, language_instruction)
        else:
            action_chunk = policy.get_action(obs_next, language_instruction)
        _wait_ms = (time.perf_counter() - _tw) * 1e3
        _rr_infer_ms(_exec_ms + _wait_ms)
        _log_chunk(obs_next, camera_keys, _exec_ms + _wait_ms)
        # 진단: obs=카메라읽기 / exec=청크실행 / wait=다음청크 대기(정지) — wait·obs가 크면 그게 병목
        print(f"obs={_obs_ms:.0f}  exec={_exec_ms:.0f}  wait(stall)={_wait_ms:.0f} ms  H={cfg.action_horizon}")  # 학습 fps에 맞춰 대기 (STEP_DT env로 조정)


if __name__ == "__main__":
    eval()
