"""GR00T용 v2 데이터셋의 에피소드 선두 idle 구간 트리밍.

배경(2026-07-16): 시연 녹화 초반 평균 2.8초(최대 6초)의 정지 구간이 있어, GR00T가
배포 시작 조건(홈 자세+정지 장면)에서 "가만히"를 예측하는 정지 어트랙터에 갇힘
(open-loop에선 GT 완벽 추종 — 모델 문제 아님). 각 에피소드에서 처음으로 관절이
1도 이상 움직이는 프레임의 BUFFER(15) 프레임 전까지를 잘라낸다.

정규화는 min_max(min/max는 idle 트리밍에 불변)라 stats.json 재계산 불필요.
episodes.jsonl length·info.json total_frames·global index를 갱신. 비디오는 ffmpeg 컷.

사용: python3 trim_idle_v2.py <dataset_root> <ffmpeg_path>
실행 전 dataset_root 백업 권장.
"""
import json, subprocess, sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(sys.argv[1])
FFMPEG = sys.argv[2] if len(sys.argv) > 2 else "ffmpeg"
FPS = 30
MOVE_DEG = 1.0
BUFFER = 15

data_dir = ROOT / "data/chunk-000"
video_root = ROOT / "videos/chunk-000"
video_keys = [d.name for d in video_root.iterdir() if d.is_dir()]
eps = sorted(data_dir.glob("episode_*.parquet"))

lengths = {}
global_idx = 0
total_trimmed = 0
for f in eps:
    df = pd.read_parquet(f)
    st = np.stack(df["observation.state"].values)
    d = np.abs(np.diff(st, axis=0)).max(axis=1)
    moving = np.where(d > MOVE_DEG)[0]
    k = max(0, (int(moving[0]) if len(moving) else 0) - BUFFER)
    if k > 0:
        df = df.iloc[k:].reset_index(drop=True)
        df["frame_index"] = np.arange(len(df))
        df["timestamp"] = df["timestamp"] - df["timestamp"].iloc[0]
        for vk in video_keys:
            src = video_root / vk / f"{f.stem}.mp4"
            tmp = src.with_suffix(".trim.mp4")
            subprocess.run([FFMPEG, "-y", "-loglevel", "error",
                            "-ss", f"{k/FPS:.4f}", "-i", str(src),
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS),
                            str(tmp)], check=True)
            tmp.replace(src)
    df["index"] = np.arange(global_idx, global_idx + len(df))
    global_idx += len(df)
    df.to_parquet(f, index=False)
    ep_i = int(f.stem.split("_")[1])
    lengths[ep_i] = len(df)
    total_trimmed += k
    print(f"{f.stem}: trim {k}f -> {len(df)}f")

# meta 갱신
ej = ROOT / "meta/episodes.jsonl"
lines = []
for line in ej.read_text().splitlines():
    o = json.loads(line)
    o["length"] = lengths[o["episode_index"]]
    lines.append(json.dumps(o))
ej.write_text("\n".join(lines) + "\n")

info_p = ROOT / "meta/info.json"
info = json.loads(info_p.read_text())
info["total_frames"] = int(global_idx)
info_p.write_text(json.dumps(info, indent=4))

print(f"완료: 총 {total_trimmed}프레임({total_trimmed/FPS:.0f}s) 제거, 남은 {global_idx}프레임")
