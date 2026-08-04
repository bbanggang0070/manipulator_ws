#!/usr/bin/env bash
# 실기 데이터(so101_blocktask_real, **로컬** v3.0)의 (episode, frame) 자세+카메라 프레임을 추출해
# setup/gr00t/real_pose_ref/ 에 저장 → real_pose_align.py 가 POSE_REF=real_pose_ref 로 비교에 사용.
# (extract_sim_pose.sh 의 실기 로컬판 — 5090 불필요. 카메라 top→front, wrist→wrist.)
#
# 사용: ./extract_real_pose.sh [EPISODE] [FRAME_OR_FRAC]
#   EPISODE       : 에피소드 번호 (기본 0)
#   FRAME_OR_FRAC : 정수=프레임번호 / 소수(0~1)=에피소드 내 비율 (0=시작/rest, 0.5=중간). 기본 0
# 예: ./extract_real_pose.sh 0 0        # ep0 시작(rest)
#     ./extract_real_pose.sh 3 0.5      # ep3 중간
#
# ⚠️ 후반(파지) 프레임 자세는 팔이 아래로 내려가므로 real_pose_align 실행 시 e-stop 주의.
set -e
EP="${1:-0}"; FF="${2:-0}"
DS="${DS:-$HOME/.cache/huggingface/lerobot/heongyu/so101_blocktask_real}"
REF="$(cd "$(dirname "$0")" && pwd)/real_pose_ref"
mkdir -p "$REF"

cd "$HOME/manipulator_ws/envs/lerobot"
uv run python - "$DS" "$REF" "$EP" "$FF" <<'PY'
import sys, os, glob, json
import pandas as pd, numpy as np
DS, REF, EP, FF = sys.argv[1], sys.argv[2], int(sys.argv[3]), float(sys.argv[4])
epm = sorted(glob.glob(DS+"/meta/episodes/**/*.parquet", recursive=True))
E = pd.concat([pd.read_parquet(f) for f in epm], ignore_index=True)
row = E[E.episode_index==EP].iloc[0]
L = int(row["length"]); frm = int(FF*L) if FF < 1 else int(FF); frm = max(0, min(frm, L-1))
dfi = int(row["data/file_index"]); dci = int(row["data/chunk_index"])
D = pd.read_parquet(f"{DS}/data/chunk-{dci:03d}/file-{dfi:03d}.parquet")
de = D[D.episode_index == EP].reset_index(drop=True)
st = np.array(de.iloc[frm]["observation.state"]).tolist()
J = ["shoulder_pan.pos","shoulder_lift.pos","elbow_flex.pos","wrist_flex.pos","wrist_roll.pos","gripper.pos"]
# real_pose_align.py 와 파일명 호환(sim_pose_*)을 유지해 POSE_REF 로만 전환되게 한다.
json.dump({"dataset":os.path.basename(DS),"episode":EP,"frame":frm,"length":L,"joints":J,"state":st},
          open(REF+"/sim_pose_state.json","w"))
fps = 30.0
for name, key in {"front":"observation.images.top", "wrist":"observation.images.wrist"}.items():
    fci = int(row[f"videos/{key}/chunk_index"]); ffi = int(row[f"videos/{key}/file_index"])
    ts = float(row[f"videos/{key}/from_timestamp"]) + frm/fps
    vid = f"{DS}/videos/{key}/chunk-{fci:03d}/file-{ffi:03d}.mp4"
    os.system(f'ffmpeg -v error -y -ss {ts} -i "{vid}" -frames:v 1 "{REF}/sim_pose_{name}.jpg"')
print("ep", EP, "frame", frm, "/", L, "| state:", [round(x,1) for x in st])
PY

echo "→ real_pose_ref 갱신 완료: $REF"
echo "이제: cd ~/manipulator_ws/envs/lerobot && POSE_REF=real_pose_ref uv run python ../../setup/gr00t/real_pose_align.py"
