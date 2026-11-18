"""여러 v2.1 세션 데이터셋을 하나로 병합 (에피소드 재번호). 컨테이너(real-robot-train8) 안에서 실행.
- 데이터 parquet + 모든 카메라 mp4가 존재하는 에피소드만 채택(불완전/phantom 자동 제외).
- episode_index/index/task_index 재번호, meta(episodes/episodes_stats/tasks/info) 재구성,
  stats.json은 에피소드별 stats를 길이 가중 집계로 재계산.
사용: python merge_blocktask_v2.py <OUT_NAME> <SESS1> <SESS2> ...   (경로는 /data/heongyu/ 하위 이름)
"""
import json, glob, os, shutil, sys
import numpy as np
import pandas as pd

ROOT = "/data/heongyu"
OUT_NAME = sys.argv[1]
SESS = sys.argv[2:]
OUT = os.path.join(ROOT, OUT_NAME)


def vkeys(d):
    base = os.path.join(d, "videos", "chunk-000")
    return sorted(os.listdir(base)) if os.path.isdir(base) else []


ref = os.path.join(ROOT, SESS[0])
VKEYS = vkeys(ref)
ref_info = json.load(open(os.path.join(ref, "meta", "info.json")))
print("video keys:", VKEYS)

if os.path.exists(OUT):
    shutil.rmtree(OUT)
os.makedirs(os.path.join(OUT, "data", "chunk-000"))
for vk in VKEYS:
    os.makedirs(os.path.join(OUT, "videos", "chunk-000", vk))
os.makedirs(os.path.join(OUT, "meta"))

episodes, ep_stats, lengths = [], [], []
ne, gframe = 0, 0
tasks_seen = {}

for s in SESS:
    sd = os.path.join(ROOT, s)
    es = {json.loads(l)["episode_index"]: json.loads(l) for l in open(os.path.join(sd, "meta", "episodes.jsonl"))}
    st = {json.loads(l)["episode_index"]: json.loads(l)["stats"] for l in open(os.path.join(sd, "meta", "episodes_stats.jsonl"))}
    stask = {json.loads(l)["task_index"]: json.loads(l)["task"] for l in open(os.path.join(sd, "meta", "tasks.jsonl"))}
    kept = 0
    for pf in sorted(glob.glob(os.path.join(sd, "data", "chunk-000", "episode_*.parquet"))):
        le = int(os.path.basename(pf).split("_")[1].split(".")[0])
        if not all(os.path.exists(os.path.join(sd, "videos", "chunk-000", vk, f"episode_{le:06d}.mp4")) for vk in VKEYS):
            print(f"  skip {s} ep{le}: 영상 없음"); continue
        if le not in es or le not in st:
            print(f"  skip {s} ep{le}: meta 없음"); continue
        df = pd.read_parquet(pf)
        L = len(df)
        df["episode_index"] = ne
        df["index"] = np.arange(gframe, gframe + L)

        def gt(ti):
            task = stask.get(int(ti), list(stask.values())[0])
            tasks_seen.setdefault(task, len(tasks_seen))
            return tasks_seen[task]
        df["task_index"] = df["task_index"].map(gt)
        df.to_parquet(os.path.join(OUT, "data", "chunk-000", f"episode_{ne:06d}.parquet"))
        for vk in VKEYS:
            shutil.copy(os.path.join(sd, "videos", "chunk-000", vk, f"episode_{le:06d}.mp4"),
                        os.path.join(OUT, "videos", "chunk-000", vk, f"episode_{ne:06d}.mp4"))
        episodes.append({"episode_index": ne, "tasks": es[le].get("tasks", list(stask.values())), "length": L})
        ep_stats.append(st[le])
        lengths.append(L)
        ne += 1; gframe += L; kept += 1
    print(f"{s}: {kept} 에피소드 채택")

# tasks.jsonl
with open(os.path.join(OUT, "meta", "tasks.jsonl"), "w") as f:
    for task, ti in sorted(tasks_seen.items(), key=lambda x: x[1]):
        f.write(json.dumps({"task_index": ti, "task": task}) + "\n")
# episodes.jsonl
with open(os.path.join(OUT, "meta", "episodes.jsonl"), "w") as f:
    for e in episodes:
        f.write(json.dumps(e) + "\n")
# episodes_stats.jsonl
with open(os.path.join(OUT, "meta", "episodes_stats.jsonl"), "w") as f:
    for i, s in enumerate(ep_stats):
        f.write(json.dumps({"episode_index": i, "stats": s}) + "\n")

# stats.json 집계 (길이 가중)
w = np.array(lengths, dtype=float)
tot = int(w.sum())
keys = ep_stats[0].keys()
gstats = {}
for k in keys:
    M = np.stack([np.array(s[k]["mean"], dtype=float) for s in ep_stats])
    S = np.stack([np.array(s[k]["std"], dtype=float) for s in ep_stats])
    mn = np.min(np.stack([np.array(s[k]["min"], dtype=float) for s in ep_stats]), axis=0)
    mx = np.max(np.stack([np.array(s[k]["max"], dtype=float) for s in ep_stats]), axis=0)
    ww = w.reshape([-1] + [1] * (M.ndim - 1))
    gmean = (M * ww).sum(0) / tot
    ex2 = ((S ** 2 + M ** 2) * ww).sum(0) / tot
    gstd = np.sqrt(np.clip(ex2 - gmean ** 2, 0, None))
    gstats[k] = {"min": mn.tolist(), "max": mx.tolist(), "mean": gmean.tolist(), "std": gstd.tolist(), "count": [tot]}
json.dump(gstats, open(os.path.join(OUT, "meta", "stats.json"), "w"))

# info.json
info = dict(ref_info)
info["total_episodes"] = ne
info["total_frames"] = gframe
info["total_videos"] = ne * len(VKEYS)
info["total_tasks"] = len(tasks_seen)
info["total_chunks"] = 1
info["splits"] = {"train": f"0:{ne}"}
json.dump(info, open(os.path.join(OUT, "meta", "info.json"), "w"), indent=4)

print(f"\n병합 완료: {OUT_NAME} — {ne} 에피소드, {gframe} 프레임, mp4 {ne*len(VKEYS)}")
