# 원본: setup/gr00t/client/eval_lerobot.py (NVIDIA, Apache-2.0) — 양팔(bi_so_follower)판.
#
# 바뀐 것은 셋뿐이다. 나머지(ensemble·async·crossfade·rerun·파일 로깅·STOP_ON_REST)는
# robot_state_keys/camera_keys에 대해 이미 제네릭하게 쓰여 있어 **그대로 재사용**한다 —
# 단일팔판을 두 번 만들 이유가 없다.
#   1) 카메라 3대(left_top·left_wrist·right_wrist) → policy가 기대하는 이름
#      (top·wrist_left·wrist_right, bi_so100_config.py/modality.json과 일치)으로 재매핑
#   2) state/action이 12차원 · 4그룹(left_arm·left_gripper·right_arm·right_gripper)으로 쪼개진다
#   3) _JOINTS·_REST_BACK_JOINT가 12관절(좌우 wrist_roll 둘 다)을 본다
#
# STOP_ON_REST 는 robot_state_keys 12개를 보므로 "한쪽이라도 아직 안 돌아왔으면 안 끝난다"가
# 저절로 성립한다(§4-3 요구사항). 단 판정 기준은 양팔판에서 "근처+정지"로 바꿨다(아래 _REST_STILL).
#
# 사용 예:
#   cd setup/p6_real_bimanual/gr00t/client
#   uv run --project ../../../../envs/lerobot python eval_lerobot_bi.py \
#     --robot.type=bi_so_follower \
#     --robot.left_arm_config.port=/dev/ttyFOLLOWER_L \
#     --robot.right_arm_config.port=/dev/ttyFOLLOWER_R \
#     --robot.id=bi_follower \
#     --robot.left_arm_config.cameras="{top: {...}, wrist: {...}}" \
#     --robot.right_arm_config.cameras="{wrist: {...}}" \
#     --policy_host=127.0.0.1 --policy_port=5555 \
#     --lang_instruction="Put the red marker into the black bin"

import logging
import os
import sys
import threading
import time

# ── 아래 블록(_STEP_DT ~ _REST_BACK_JOINT 직전)은 eval_lerobot.py와 동일 — 원본 주석 참조 ──
_STEP_DT = float(os.environ.get("STEP_DT", "0.033"))
_ASYNC = os.environ.get("ASYNC", "1") == "1"
_JPEG = os.environ.get("JPEG", "1") == "1"
_JPEG_Q = int(os.environ.get("JPEG_Q", "90"))
_ENSEMBLE = os.environ.get("ENSEMBLE", "1") == "1"
# 0.8 = 단일팔 cleanup 실측 최적(2026-10-10 스윕). 양팔 스윕은 아직 없다 — 원본 기본값 0.1은
# 옛 청크 비중이 커서 물체 위에서 얼어붙는 경향이 있었다(단일팔 W=0.3 에서도 타임아웃 27%).
_ENS_W = float(os.environ.get("ENSEMBLE_W", "0.8"))
_ENS_TARGET = float(os.environ.get("ENS_TARGET", "0"))
_ENS_W_MIN, _ENS_W_MAX = 0.1, 5.0
_GRIP_BLEND = os.environ.get("GRIP_BLEND", "1") == "1"
_GRIP_MED = int(os.environ.get("GRIP_MED", "0"))
_CROSSFADE = int(os.environ.get("CROSSFADE", "0"))
_MAX_SEC = float(os.environ.get("MAX_SEC", "0"))

# ── 작업이 끝나면 스스로 멈춘다 — eval_lerobot.py와 같은 이유(§원본 주석 참조).
#    양팔판 차이: _rest0/_dev/_back_ok가 robot_state_keys 12개 전부를 보므로
#    **두 팔 모두** rest 조건을 만족해야 끝난다(한쪽만 보고 멈추는 위험 없음, bi_manipulator_plan.md §4-3).
#    양팔판 판정 = "크게 움직인 뒤(REST_LEAVE) 시작 자세 근처(REST_BACK, 느슨)에서 멈춰 있음(REST_STILL)".
#    단일팔처럼 "시작 자세 6° 이내"만 보면 안 끝난다 — 2026-10-16 ck21000 trial02: 작업을 48s에 끝내고
#    rest로 돌아왔는데 시작 순간 처져 있던 오른팔 elbow(103°→95°)·pan·왼팔 elbow가 6°를 넘어
#    150s 타임아웃까지 대기. 300ep 사람 시연도 끝-시작 6° 기준으론 43%만 "복귀"로 판정된다.
#    그래서 위치 허용치는 넓히고(20°), 대신 "REST_HOLD 동안 모든 관절 움직임 < REST_STILL" 을 요구한다.
_STOP_ON_REST = os.environ.get("STOP_ON_REST", "0") == "1"
_REST_LEAVE = float(os.environ.get("REST_LEAVE_DEG", "20"))
_REST_BACK = float(os.environ.get("REST_BACK_DEG", "20"))
_REST_STILL = float(os.environ.get("REST_STILL_DEG", "1.5"))
_REST_HOLD = float(os.environ.get("REST_HOLD_SEC", "2.0"))
# wrist_roll 느슨한 허용치 — 단일팔과 같은 이유(그리퍼 성패와 무관한 자유도). 좌우 둘 다 느슨하게.
_REST_BACK_JOINT = {
    "left_wrist_roll.pos": float(os.environ.get("REST_BACK_WROLL_DEG", "30")),
    "right_wrist_roll.pos": float(os.environ.get("REST_BACK_WROLL_DEG", "30")),
}
_grip_hist = {}

# ── 'q' 한 번(Enter 불필요)으로 이 시행만 끝낸다 — 가망 없는 시행을 MAX_SEC 까지 기다리지 않기 위함.
#    Ctrl+C 와 달리 부모(cleanup_eval_bi.py)까지 신호가 가지 않아 배치가 끊기지 않고, 타임아웃과
#    같은 경로(return → atexit)로 끝나 video.mp4·csv 가 정상 마무리된다. 터미널이 아니면(파이프 등) 꺼진다.
_USER_STOP = threading.Event()


def _key_watch():
    import select
    import sys
    import termios
    import tty

    if not sys.stdin.isatty():
        return
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)

    def _restore():
        # 시행 중 눌린 다른 키가 다음 결과 입력(input())으로 새지 않게 버린다
        termios.tcflush(fd, termios.TCIFLUSH)
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

    import atexit

    atexit.register(_restore)
    tty.setcbreak(fd)
    print("[key] 'q' = 이 시행 종료하고 결과 입력으로 넘어가기", flush=True)
    while not _USER_STOP.is_set():
        if select.select([fd], [], [], 0.2)[0] and os.read(fd, 1) in (b"q", b"Q"):
            _USER_STOP.set()


def _adaptive_w(infer_ms, step_dt):
    if _ENS_TARGET <= 0 or not infer_ms or infer_ms <= 0:
        return _ENS_W
    gap = max(infer_ms / 1000.0 / max(step_dt, 1e-6), 0.5)
    import math as _m
    w = -_m.log(max(1.0 - _ENS_TARGET, 1e-6)) / gap
    return min(max(w, _ENS_W_MIN), _ENS_W_MAX)


def _jpeg_encode_videos(obs_dict):
    import cv2
    import numpy as np

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
import numpy as np
from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig  # noqa: F401
from lerobot.robots import Robot, RobotConfig, bi_so_follower, make_robot_from_config  # noqa: F401
from lerobot.utils.utils import init_logging, log_say

import sys as _sys
# service.py는 단일팔 클라이언트 폴더에만 둔다 — 실기 클라이언트 규약 자체가 로봇 종류와
# 무관해 복제할 이유가 없다(이 파일 머리말과 같은 "재사용 우선" 원칙).
_sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "gr00t", "client"))
from service import ExternalRobotInferenceClient

#################################################################################
# rerun 실시간 시각화 — eval_lerobot.py와 동일
_RERUN = os.environ.get("RERUN", "1") == "1"
if _RERUN:
    import rerun as rr

    rr.init("gr00t_infer_bi", spawn=True)
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
# 파일 로깅 + 영상 녹화 — eval_lerobot.py와 동일 구조. _JOINTS만 12개(좌우)로 늘었다.
import csv as _csv
from datetime import datetime as _dt

_LOGDIR = os.environ.get(
    "LOGDIR",
    os.path.expanduser(f"~/manipulator_ws/logs/gr00t_infer_bi/{_dt.now():%Y%m%d_%H%M%S}"),
)
os.makedirs(_LOGDIR, exist_ok=True)
_ARM_JOINTS = ["shoulder_pan.pos", "shoulder_lift.pos", "elbow_flex.pos",
               "wrist_flex.pos", "wrist_roll.pos", "gripper.pos"]
_JOINTS = [f"left_{j}" for j in _ARM_JOINTS] + [f"right_{j}" for j in _ARM_JOINTS]
_chunk_f = open(f"{_LOGDIR}/chunks.csv", "w", buffering=1)
_chunk_w = _csv.writer(_chunk_f)
_chunk_w.writerow(["chunk", "infer_ms"] + [f"state_{j}" for j in _JOINTS])
_act_f = open(f"{_LOGDIR}/actions.csv", "w", buffering=1)
_act_w = _csv.writer(_act_f)
_act_w.writerow(["chunk", "i", "t_ms"] + [f"sent_{j}" for j in _JOINTS])
_VID = {"w": None}
_VIDEO_FPS = int(os.environ.get("VIDEO_FPS", "10"))
_VID_EVERY = max(1, round(30 / _VIDEO_FPS))
_CHUNK = {"n": 0, "t0": None}
print(f"[LOG] {_LOGDIR}")

import atexit as _atexit


@_atexit.register
def _finalize_video():
    if _VID["w"] is not None:
        _VID["w"].release()
    _chunk_f.close()
    _act_f.close()


def _log_chunk(observation_dict, camera_keys, infer_ms):
    import time as _t

    if _CHUNK["t0"] is None:
        _CHUNK["t0"] = _t.perf_counter()
    st = [observation_dict.get(j, float("nan")) for j in _JOINTS]
    _chunk_w.writerow([_CHUNK["n"], f"{infer_ms:.0f}"] + [f"{v:.2f}" for v in st])
    _CHUNK["n"] += 1


def _log_video(observation_dict, camera_keys):
    """카메라 3대(top·wrist_left·wrist_right)를 가로로 이어붙여 한 프레임으로 남긴다."""
    import cv2
    import numpy as _np

    imgs = [observation_dict[k] for k in camera_keys if k in observation_dict]
    if not imgs:
        return
    frame = _np.concatenate(imgs, axis=1)
    if _VID["w"] is None:
        h, w = frame.shape[:2]
        for _cc in ("avc1", "mp4v"):
            w_ = cv2.VideoWriter(f"{_LOGDIR}/video.mp4",
                                 cv2.VideoWriter_fourcc(*_cc), _VIDEO_FPS, (w, h))
            if w_.isOpened():
                if _cc == "mp4v":
                    print("  ⚠️ H.264 인코더가 없어 mp4v 로 저장합니다 — 브라우저 재생 불가.")
                _VID["w"] = w_
                break
            w_.release()
    _VID["w"].write(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))


def _log_action(sent):
    import time as _t

    t_ms = (_t.perf_counter() - (_CHUNK["t0"] or _t.perf_counter())) * 1e3
    _act_w.writerow([_CHUNK["n"] - 1, _FRAME["i"], f"{t_ms:.0f}"]
                    + [f"{float(sent.get(j, float('nan'))):.2f}" for j in _JOINTS])


#################################################################################
# bi_so100_config.py의 modality_keys=["top","wrist_left","wrist_right"]와 일치시키는 매핑.
# robot.cameras 키는 BiSOFollower가 "left_"/"right_" 접두사를 붙여 만든다(bi_so_follower.py).
_CAM_MAP = {"left_top": "top", "left_wrist": "wrist_left", "right_wrist": "wrist_right"}


class BiGr00tRobotInferenceClient:
    """eval_lerobot.py의 Gr00tRobotInferenceClient 양팔판.

    단일팔은 modality_keys=["single_arm","gripper"](6차원)이었다. 양팔은 12차원을
    bi_so100_config.py/modality.json과 같은 순서로 넷으로 쪼갠다 — left_arm(5)·
    left_gripper(1)·right_arm(5)·right_gripper(1), info.json action.names 순서와 동일
    (BiSOFollower._motors_ft가 left_* 다음 right_* 순으로 주므로 그대로 맞아떨어진다).
    """

    def __init__(self, host="localhost", port=5555, camera_keys=None,
                 robot_state_keys=None, show_images=False):
        self.policy = ExternalRobotInferenceClient(host=host, port=port)
        self.camera_keys = camera_keys or []
        self.robot_state_keys = robot_state_keys or []
        self.show_images = show_images
        assert len(self.robot_state_keys) == 12, (
            f"robot_state_keys should be size 12, but got {len(self.robot_state_keys)}")
        self.modality_keys = ["left_arm", "left_gripper", "right_arm", "right_gripper"]
        self._slices = [(0, 5), (5, 6), (6, 11), (11, 12)]

    def get_action(self, observation_dict, lang: str):
        obs_dict = {
            f"video.{_CAM_MAP.get(key, key)}": observation_dict[key] for key in self.camera_keys
        }

        state = np.array([observation_dict[k] for k in self.robot_state_keys])
        for mk, (lo, hi) in zip(self.modality_keys, self._slices):
            obs_dict[f"state.{mk}"] = state[lo:hi].astype(np.float64)
        obs_dict["annotation.human.task_description"] = lang

        for k in obs_dict:
            if isinstance(obs_dict[k], np.ndarray):
                obs_dict[k] = obs_dict[k][np.newaxis, ...]
            else:
                obs_dict[k] = [obs_dict[k]]

        if _JPEG:
            obs_dict = _jpeg_encode_videos(obs_dict)

        action_chunk = self.policy.get_action(obs_dict)

        lerobot_actions = []
        action_horizon = action_chunk[f"action.{self.modality_keys[0]}"].shape[0]
        for i in range(action_horizon):
            lerobot_actions.append(self._convert_to_lerobot_action(action_chunk, i))
        return lerobot_actions

    def _convert_to_lerobot_action(self, action_chunk, idx):
        concat_action = np.concatenate(
            [np.atleast_1d(action_chunk[f"action.{key}"][idx]) for key in self.modality_keys],
            axis=0,
        )
        assert len(concat_action) == len(self.robot_state_keys), "this should be size 12"
        return {key: concat_action[i] for i, key in enumerate(self.robot_state_keys)}


#################################################################################


def print_yellow(text):
    print("\033[93m {}\033[00m".format(text))


@dataclass
class EvalConfig:
    robot: RobotConfig
    policy_host: str = "localhost"
    policy_port: int = 5555
    action_horizon: int = 8
    lang_instruction: str = "Put the red marker into the black bin"
    play_sounds: bool = False
    timeout: int = 60  # (미사용 — 실제 한계는 MAX_SEC 환경변수다)
    show_images: bool = False


# ── 시행이 어떻게 끝나든(q·타임아웃·STOP_ON_REST·Ctrl+C·서버 끊김 등 예외) 팔을 떨어뜨리지 않는다.
#    예전엔 프로세스 종료 시 Robot.__del__ → disconnect() 가 토크를 꺼서(lerobot 기본
#    disable_torque_on_disconnect=True) 공중에 있던 팔이 바닥으로 떨어졌다(2026-10-16 타임아웃 시행).
#    지금은: ① 토크는 끝까지 유지 ② 그 자리에 잠깐 정지 ③ 관절 공간 직선 보간으로 천천히 rest 복귀.
#    복귀에 실패해도 토크를 끄지 않는다(팔은 그 자리에 버틴다) — 종료 코드 3 으로 알린다.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from home_pose_bi import TARGET as _REST_TARGET  # noqa: E402

_REST_DEG_PER_STEP = float(os.environ.get("REST_DEG_PER_STEP", "1.0"))  # 30Hz → 약 30°/s
_REST_OK_DEG = float(os.environ.get("REST_OK_DEG", "8.0"))


def _return_to_rest(robot) -> bool:
    import numpy as _np

    keys = list(_REST_TARGET)
    try:
        q0 = robot.get_observation()
        cur = _np.array([float(q0[k]) for k in keys])
        # ② 그 자리 정지: 현재 위치를 목표로 0.5s 보낸다(남은 청크 목표로 더 가지 않게)
        hold = {k: float(v) for k, v in zip(keys, cur)}
        for _ in range(15):
            robot.send_action(hold)
            time.sleep(0.033)
        goal = _np.array([_REST_TARGET[k] for k in keys])
        n = max(1, int(_np.ceil(_np.abs(goal - cur).max() / _REST_DEG_PER_STEP)))
        print(f"[rest] 그 자리 정지 → rest 로 복귀 ({n * 0.033:.1f}s)", flush=True)
        # ③ 직선 보간(전 관절 같은 비율로 동시에 도착) + 마지막 1s 는 목표 유지로 수렴
        for i in range(1, n + 31):
            a = min(1.0, i / n)
            robot.send_action({k: float(v) for k, v in zip(keys, cur + a * (goal - cur))})
            time.sleep(0.033)
        q1 = robot.get_observation()
        worst = max(abs(float(q1[k]) - _REST_TARGET[k]) for k in keys)
        print(f"[rest] 복귀 완료 (최대 오차 {worst:.1f}°) — 토크 유지", flush=True)
        return worst < _REST_OK_DEG
    except BaseException as e:  # 두 번째 Ctrl+C 포함 — 어떤 경우에도 토크는 끄지 않는다
        print(f"[rest] ⚠️ 복귀 실패({type(e).__name__}: {e}) — 팔은 토크 유지 상태로 그 자리에 있음", flush=True)
        return False


@draccus.wrap()
def eval(cfg: EvalConfig):
    init_logging()
    logging.info(pformat(asdict(cfg)))

    # Ctrl+C 한 번에 SIGINT 가 두 번 온다(터미널 → 이 프로세스, 그리고 uv run 이 한 번 더 전달 —
    # uv 0.11 실측). 두 번째가 rest 복귀를 끊지 않게 0.5s 안의 중복은 버린다. 그 뒤에 일부러 다시
    # 누른 Ctrl+C 는 복귀를 멈추고 그 자리에서 토크 유지(_return_to_rest 의 except).
    import signal as _signal

    _last_int = [0.0]

    def _on_sigint(signum, frame):
        now = time.monotonic()
        dup = now - _last_int[0] < 0.5
        _last_int[0] = now
        if not dup:
            raise KeyboardInterrupt

    _signal.signal(_signal.SIGINT, _on_sigint)

    # ① 종료 시 토크를 끄지 않는다(위 _return_to_rest 주석)
    cfg.robot.left_arm_config.disable_torque_on_disconnect = False
    cfg.robot.right_arm_config.disable_torque_on_disconnect = False
    robot = make_robot_from_config(cfg.robot)
    robot.connect()
    try:
        _eval_main(cfg, robot)
    except KeyboardInterrupt:
        print("\n[stop] Ctrl+C — 시행 종료", flush=True)
    except Exception:
        logging.exception("[stop] 추론 중 예외 — 시행 종료")
    finally:
        _USER_STOP.set()  # 키 감시 스레드 정리
        ok = _return_to_rest(robot)
    sys.exit(0 if ok else 3)


def _eval_main(cfg: EvalConfig, robot):

    # BiSOFollower.cameras 는 left_/right_ 접두사가 붙은 이름을 쓴다 — 접두사까지 포함해야
    # robot.get_observation() 의 실제 키(left_top 등)와 맞는다.
    camera_keys = [f"left_{k}" for k in cfg.robot.left_arm_config.cameras.keys()] + \
        [f"right_{k}" for k in cfg.robot.right_arm_config.cameras.keys()]
    print("camera_keys: ", camera_keys)

    log_say("Initializing robot", cfg.play_sounds, blocking=True)

    language_instruction = cfg.lang_instruction

    robot_state_keys = list(robot._motors_ft.keys())
    print("robot_state_keys: ", robot_state_keys)

    policy = BiGr00tRobotInferenceClient(
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

    # ── 이하 Step 3-ENS / Step 3-CHUNK 는 eval_lerobot.py와 완전히 동일 ──
    # (robot_state_keys/camera_keys 에 대해 이미 제네릭하다 — STOP_ON_REST의 _rest0/_back_ok도
    #  dict comprehension이 robot_state_keys 전체를 돌므로 12관절 모두를 자동으로 본다.)
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
                    chunk = policy.get_action(obs, language_instruction)
                    _sh["infer_ms"] = (time.perf_counter() - _ti) * 1e3
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
        threading.Thread(target=_key_watch, daemon=True).start()

        t = 0
        _tl = time.perf_counter()
        _t0 = time.perf_counter()
        _rest0 = None
        _left = False
        _back_since = None
        _still_ref = None
        while True:
            if _USER_STOP.is_set():
                print(f"\n[skip] 'q' 입력 — 시행 종료 (step={t}, {time.perf_counter() - _t0:.0f}s)")
                _sh["stop"] = True
                return
            if _MAX_SEC and time.perf_counter() - _t0 >= _MAX_SEC:
                print(f"\n[timeout] {_MAX_SEC:.0f}s 경과 — 시행 종료 (step={t})")
                _sh["stop"] = True
                return
            obs = robot.get_observation()
            _rr_obs(obs, camera_keys, robot_state_keys)
            if _STOP_ON_REST:
                _q = {k: float(obs[k]) for k in robot_state_keys if k in obs}
                if _rest0 is None:
                    _rest0 = dict(_q)
                _dev = max((abs(_q[k] - _rest0[k]) for k in _rest0 if k in _q), default=0.0)
                _back_ok = all(abs(_q[k] - _rest0[k]) < _REST_BACK_JOINT.get(k, _REST_BACK)
                               for k in _rest0 if k in _q)
                # 정지 판정: 기준 자세(_still_ref)에서 어느 관절이든 REST_STILL 이상 벗어나면 다시 잰다
                _still = _still_ref is not None and all(
                    abs(_q[k] - _still_ref[k]) < _REST_STILL for k in _still_ref if k in _q)
                if not _left:
                    _left = _dev > _REST_LEAVE
                elif _back_ok and _still:
                    if time.perf_counter() - _back_since >= _REST_HOLD:
                        print(f"\n[done] rest 복귀 후 {_REST_HOLD:.0f}s 정지 — 시행 종료 "
                              f"(step={t}, {time.perf_counter() - _t0:.0f}s)")
                        _sh["stop"] = True
                        return
                else:
                    _still_ref, _back_since = dict(_q), time.perf_counter()
            with _lk:
                _sh["obs"] = obs
                _sh["step"] = t
                covering = [(cs, c[t - cs]) for (cs, c) in _sh["chunks"] if cs <= t < cs + len(c)]
                n_chunks = len(_sh["chunks"])
            if covering:
                _w = _adaptive_w(_sh["infer_ms"], _STEP_DT)
                ws = np.array([np.exp(_w * (cs - t)) for (cs, _) in covering], dtype=np.float64)
                ws /= ws.sum()
                blended = {
                    jk: float(sum(w * float(ad.get(jk, 0.0)) for w, (_, ad) in zip(ws, covering)))
                    for jk in robot_state_keys
                }
                if not _GRIP_BLEND:
                    _newest = max(covering, key=lambda p: p[0])[1]
                    for _k in robot_state_keys:
                        if "gripper" not in _k:
                            continue
                        _v = float(_newest.get(_k, blended[_k]))
                        if _GRIP_MED > 1:
                            _h = _grip_hist.setdefault(_k, [])
                            _h.append(_v)
                            if len(_h) > _GRIP_MED:
                                del _h[0]
                            _v = sorted(_h)[len(_h) // 2]
                        blended[_k] = _v
                sent = robot.send_action(blended)
                sent = sent if isinstance(sent, dict) else blended
                _rr_action(sent)
                _log_action(sent)
            if t % 8 == 0:
                _rr_infer_ms(_sh["infer_ms"])
                _log_chunk(obs, camera_keys, _sh["infer_ms"])
            if t % _VID_EVERY == 0:
                _log_video(obs, camera_keys)
            time.sleep(_STEP_DT)
            if t % 30 == 0:
                _dt_ = time.perf_counter() - _tl
                _tl = time.perf_counter()
                print(f"[ensemble] step={t} covering={len(covering)} chunks={n_chunks} "
                      f"rate={30/_dt_:.0f}Hz infer={_sh['infer_ms']:.0f}ms "
                      f"W={_adaptive_w(_sh['infer_ms'], _STEP_DT):.2f}(목표 최신 {_ENS_TARGET:.0%})")
            t += 1

    # Step 3-CHUNK: 기존 청크 단위 실행 (ENSEMBLE=0)
    _next = {}

    def _prefetch(obs):
        try:
            _next["chunk"] = policy.get_action(obs, language_instruction)
        except Exception as e:
            _next["err"] = e

    observation_dict = robot.get_observation()
    _rr_obs(observation_dict, camera_keys, robot_state_keys)
    action_chunk = policy.get_action(observation_dict, language_instruction)
    threading.Thread(target=_key_watch, daemon=True).start()

    _prev_tail = None
    _t0 = time.perf_counter()
    while True:
        if _USER_STOP.is_set():
            print("\n[skip] 'q' 입력 — 시행 종료")
            return
        if _MAX_SEC and time.perf_counter() - _t0 >= _MAX_SEC:
            print(f"\n[timeout] {_MAX_SEC:.0f}s 경과 — 시행 종료")
            return
        _to = time.perf_counter()
        obs_next = robot.get_observation()
        _obs_ms = (time.perf_counter() - _to) * 1e3
        _rr_obs(obs_next, camera_keys, robot_state_keys)
        _next.clear()
        th = None
        if _ASYNC:
            th = threading.Thread(target=_prefetch, args=(obs_next,), daemon=True)
            th.start()

        _te = time.perf_counter()
        for i in range(cfg.action_horizon):
            action_dict = dict(action_chunk[i])
            if _prev_tail is not None and i < _CROSSFADE and i < len(_prev_tail):
                a = (i + 1) / float(_CROSSFADE + 1)
                _old = _prev_tail[i]
                for _k in action_dict:
                    if "gripper" in _k:
                        continue
                    try:
                        action_dict[_k] = (1 - a) * float(_old[_k]) + a * float(action_dict[_k])
                    except (KeyError, TypeError, ValueError):
                        pass
            sent = robot.send_action(action_dict)
            sent = sent if isinstance(sent, dict) else action_dict
            _rr_action(sent)
            _log_action(sent)
            time.sleep(_STEP_DT)
        _exec_ms = (time.perf_counter() - _te) * 1e3
        _prev_tail = (action_chunk[cfg.action_horizon:]
                      if _CROSSFADE > 0 and len(action_chunk) > cfg.action_horizon else None)

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
        _log_video(obs_next, camera_keys)
        print(f"obs={_obs_ms:.0f}  exec={_exec_ms:.0f}  wait(stall)={_wait_ms:.0f} ms  H={cfg.action_horizon}")


if __name__ == "__main__":
    eval()
