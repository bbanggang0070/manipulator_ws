"""실기 클라이언트(eval_lerobot.py의 ExternalRobotInferenceClient)와 호환되는 GR00T N1.6 서버.

컨테이너의 run_gr00t_server.py는 PolicyServer를 써서 handler(**data)로 언팩 → 실기 클라이언트가
보내는 평탄 키(video.front 등)를 kwargs로 받아 실패한다. 대신 실기 클라이언트 service.py와 동일한
BaseInferenceServer(handler를 단일 positional dict로 호출)로 Gr00tPolicy를 감싸 서빙한다.

- Gr00tPolicy.get_action(obs)는 (action_dict, info) 튜플 → action_dict만 반환(클라이언트가 기대하는 형식).
- 실행: 컨테이너 내부에서. service.py는 /srv 에 마운트.
  python3 /srv/serve_blocktask_realclient.py --model-path /workspace/models/<CKPT>
"""
import argparse
import sys

import numpy as np

sys.path.insert(0, "/srv")  # 마운트된 service.py (실기 클라이언트와 동일 규약)
from service import BaseInferenceServer

from gr00t.data.embodiment_tags import EmbodimentTag
from gr00t.policy.gr00t_policy import Gr00tPolicy

parser = argparse.ArgumentParser()
parser.add_argument("--model-path", required=True)
parser.add_argument("--host", default="0.0.0.0")
parser.add_argument("--port", type=int, default=5555)
args = parser.parse_args()

print(f"Loading Gr00tPolicy from {args.model_path} ...", flush=True)
policy = Gr00tPolicy(
    embodiment_tag=EmbodimentTag.NEW_EMBODIMENT,
    model_path=args.model_path,
    device="cuda",
)
MC = policy.modality_configs  # video/state/language modality_keys


def _to_nested(obs):
    """실기 클라이언트 평탄 형식(video.front (B,H,W,C) 등) → Gr00tPolicy 중첩 형식.
    video: uint8 (B,T,H,W,C) / state: float32 (B,T,D) / language: list[list[str]] (B)(T=1)."""
    import cv2

    video = {}
    for vk in MC["video"].modality_keys:
        raw = obs[f"video.{vk}"]
        if isinstance(raw, dict) and "__jpeg__" in raw:  # JPEG 압축 전송 → 디코드
            frames = [cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_COLOR) for b in raw["__jpeg__"]]
            arr = np.stack(frames, axis=0)  # (B,H,W,C)
        else:
            arr = np.asarray(raw)
        if arr.ndim == 4:  # (B,H,W,C) → (B,1,H,W,C)
            arr = arr[:, None, ...]
        video[vk] = arr.astype(np.uint8)
    state = {}
    for sk in MC["state"].modality_keys:
        arr = np.asarray(obs[f"state.{sk}"], dtype=np.float32)
        if arr.ndim == 2:  # (B,D) → (B,1,D)
            arr = arr[:, None, :]
        state[sk] = arr
    lang_val = None
    for cand in ("annotation.human.task_description", "task", "annotation.human.coarse_action"):
        if cand in obs:
            lang_val = obs[cand]
            break
    if isinstance(lang_val, str):
        lang_val = [lang_val]
    if not lang_val:
        lang_val = [""]
    language = {lk: [[str(s)] for s in lang_val] for lk in MC["language"].modality_keys}
    return {"video": video, "state": state, "language": language}


def _get_action(observations):
    result = policy.get_action(_to_nested(observations))
    action = result[0] if isinstance(result, tuple) else result
    # 서버 반환: {'single_arm': (B=1,H,D), 'gripper': (B=1,H,1)}
    # 실기 클라이언트 기대: {'action.single_arm': (H,D), ...} — 'action.' 접두사 + 배치 차원 제거
    out = {}
    for k, v in action.items():
        arr = np.asarray(v)
        if arr.ndim >= 2 and arr.shape[0] == 1:  # (B=1,H,D) → (H,D)
            arr = arr[0]
        out[k if str(k).startswith("action.") else f"action.{k}"] = arr
    return out


server = BaseInferenceServer(host=args.host, port=args.port)
server.register_endpoint("get_action", _get_action)
print("Registered 'get_action' (flat->nested transform). Ready to serve real client.", flush=True)
server.run()
