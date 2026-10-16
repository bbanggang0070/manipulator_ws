"""robot_client 런처 — so101_follower 등 로봇 config를 draccus 파싱 전에 등록.

LeRobot의 `python -m lerobot.async_inference.robot_client`는 `so_follower` 서브모듈을
import하지 않아 `--robot.type` 선택지가 비어버린다(레지스트리 미등록). lerobot_record.py는
`from lerobot.robots import so_follower`로 명시 등록하는데 robot_client는 빠뜨림.
이 런처가 로봇/카메라 모듈을 먼저 import해 등록한 뒤 draccus-wrapped main을 호출한다.

추가: 환경변수 RERUN=1이면 SOFollower.get_observation/send_action을 래핑해 카메라·관절 상태·
명령 액션을 rerun에 실시간 로깅한다(async client엔 --display_data가 없어 직접 주입).
→ "정책이 큰 접근을 명령하는데 max_relative_target 클램프가 막는지" vs "정책이 애초에
   작게 움직이는지"를 action/* (명령) 시계열로 구분할 수 있다.
"""

import os
import time

import lerobot.robots.so_follower  # noqa: F401  — so100/so101_follower 등록
from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig  # noqa: F401
from lerobot.async_inference.robot_client import async_client


def _enable_file_logging(path):
    """매 send_action마다 [시간간격 dt(끊김 진단) + action_cmd(명령) + action_sent(클램프후)]를
    CSV로 기록. LOGFILE 환경변수로 활성화. 분석: dt_ms가 33ms(=1/30fps)를 크게 넘으면 큐 고갈=끊김,
    cmd와 sent 차이가 크면 클램프 병목, cmd가 진동하면 정책 불안정."""
    from lerobot.robots.so_follower.so_follower import SOFollower

    os.makedirs(os.path.dirname(path), exist_ok=True)
    f = open(path, "w", buffering=1)
    JOINTS = ["shoulder_pan.pos", "shoulder_lift.pos", "elbow_flex.pos",
              "wrist_flex.pos", "wrist_roll.pos", "gripper.pos"]
    f.write("frame,dt_ms," + ",".join(f"cmd_{j}" for j in JOINTS)
            + "," + ",".join(f"sent_{j}" for j in JOINTS) + "\n")
    st = {"i": 0, "t": None}

    _orig = SOFollower.send_action

    def send_action(self, action):
        now = time.perf_counter()
        dt = 0.0 if st["t"] is None else (now - st["t"]) * 1e3
        st["t"] = now
        cmd = action if isinstance(action, dict) else {}
        sent = _orig(self, action)
        sd = sent if isinstance(sent, dict) else {}
        row = [str(st["i"]), f"{dt:.1f}"]
        row += [f"{float(cmd.get(j, 'nan')):.3f}" if j in cmd else "nan" for j in JOINTS]
        row += [f"{float(sd.get(j, 'nan')):.3f}" if j in sd else "nan" for j in JOINTS]
        f.write(",".join(row) + "\n")
        st["i"] += 1
        return sent

    SOFollower.send_action = send_action


def _enable_rerun():
    import rerun as rr
    from lerobot.robots.so_follower.so_follower import SOFollower

    rr.init("pi0_ft_infer", spawn=True)
    frame = {"i": 0}

    _orig_get = SOFollower.get_observation

    def get_observation(self):
        obs = _orig_get(self)
        i = frame["i"]
        rr.set_time_sequence("frame", i)
        for k, v in obs.items():
            if hasattr(v, "ndim") and getattr(v, "ndim", 0) == 3:
                rr.log(f"camera/{k}", rr.Image(v))
            elif isinstance(k, str) and k.endswith(".pos"):
                try:
                    rr.log(f"state/{k}", rr.Scalars(float(v)))
                except Exception:
                    pass
        return obs

    SOFollower.get_observation = get_observation

    _orig_send = SOFollower.send_action

    def send_action(self, action):
        rr.set_time_sequence("frame", frame["i"])
        frame["i"] += 1
        if isinstance(action, dict):
            for k, v in action.items():  # 명령된 목표(클램프 전) — 정책 의도
                try:
                    rr.log(f"action_cmd/{k}", rr.Scalars(float(v)))
                except Exception:
                    pass
        sent = _orig_send(self, action)  # 실제 전송(클램프 후)
        if isinstance(sent, dict):
            for k, v in sent.items():
                try:
                    rr.log(f"action_sent/{k}", rr.Scalars(float(v)))
                except Exception:
                    pass
        return sent

    SOFollower.send_action = send_action


if __name__ == "__main__":
    if os.environ.get("RERUN") == "1":
        _enable_rerun()
    _logfile = os.environ.get("LOGFILE")
    if _logfile:
        _enable_file_logging(_logfile)
    async_client()
