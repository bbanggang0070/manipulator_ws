#!/usr/bin/env bash
# sim 데이터(sim_so101_blocktask_v2, 5090)의 특정 (episode, frame) 자세+카메라 이미지를 추출해
# setup/gr00t/pose_ref/ 에 저장 → real_pose_align.py 가 이걸 재현/비교에 사용.
#
# 사용: ./extract_sim_pose.sh [EPISODE] [FRAME_OR_FRAC]
#   EPISODE       : 에피소드 번호 (기본 0)
#   FRAME_OR_FRAC : 정수=프레임번호 / 소수(0~1)=에피소드 내 비율 (0=시작/rest, 0.5=중간, 0.9=파지직전). 기본 0
# 예: ./extract_sim_pose.sh 0 0.6     # ep0의 60% 지점(접근~파지 국면)
#
# ⚠️ 파지 국면(후반) 자세는 팔이 아래로 내려가므로 real_pose_align 실행 시 e-stop 주의(테이블 충돌 방지).
set -e
EP="${1:-0}"
FF="${2:-0}"
DS="${DS:-sim_so101_blocktask_v2}"
REF="$(cd "$(dirname "$0")" && pwd)/pose_ref"
mkdir -p "$REF"

echo "추출: $DS episode=$EP frame/frac=$FF"
ssh 5090 "docker run --rm -v \$HOME/gr00tn16_ws/sim_data:/data --entrypoint bash real-robot-train8 -c '
mkdir -p /data/_pose_ref
D=/data/heongyu/$DS
python3 -c \"
import pandas as pd, numpy as np, json
df=pd.read_parquet(\\\"\$D/data/chunk-000/episode_$(printf %06d $EP).parquet\\\")
L=len(df); ff=$FF
f=int(ff*L) if ff<1 else int(ff)
f=max(0,min(f,L-1))
st=np.array(df.iloc[f][\\\"observation.state\\\"]).tolist()
J=[\\\"shoulder_pan.pos\\\",\\\"shoulder_lift.pos\\\",\\\"elbow_flex.pos\\\",\\\"wrist_flex.pos\\\",\\\"wrist_roll.pos\\\",\\\"gripper.pos\\\"]
json.dump({\\\"dataset\\\":\\\"$DS\\\",\\\"episode\\\":$EP,\\\"frame\\\":f,\\\"length\\\":L,\\\"joints\\\":J,\\\"state\\\":st}, open(\\\"/data/_pose_ref/sim_pose_state.json\\\",\\\"w\\\"))
print(\\\"frame\\\",f,\\\"/\\\",L,\\\"state:\\\",[round(x,1) for x in st])
open(\\\"/data/_pose_ref/frame.txt\\\",\\\"w\\\").write(str(f))
\"
F=\$(cat /data/_pose_ref/frame.txt)
ffmpeg -v error -y -i \$D/videos/chunk-000/observation.images.external_D455/episode_$(printf %06d $EP).mp4 -vf \"select=eq(n\\,\$F)\" -frames:v 1 /data/_pose_ref/sim_pose_front.jpg
ffmpeg -v error -y -i \$D/videos/chunk-000/observation.images.ego/episode_$(printf %06d $EP).mp4 -vf \"select=eq(n\\,\$F)\" -frames:v 1 /data/_pose_ref/sim_pose_wrist.jpg
'" 2>&1 | grep -vE "NVIDIA|CUDA|Container|docs|NGC|license|Copyright|governed|^=+$|^$" | tail -3

scp -q '5090:~/gr00tn16_ws/sim_data/_pose_ref/sim_pose_state.json' \
       '5090:~/gr00tn16_ws/sim_data/_pose_ref/sim_pose_front.jpg' \
       '5090:~/gr00tn16_ws/sim_data/_pose_ref/sim_pose_wrist.jpg' "$REF/"
echo "→ pose_ref 갱신 완료: $REF"
python3 -c "import json;d=json.load(open('$REF/sim_pose_state.json'));print('  ep',d['episode'],'frame',d['frame'],'/',d['length'],'| state',[round(x,1) for x in d['state']])"
echo "이제: cd ~/manipulator_ws/envs/lerobot && uv run python ../../setup/gr00t/real_pose_align.py"
