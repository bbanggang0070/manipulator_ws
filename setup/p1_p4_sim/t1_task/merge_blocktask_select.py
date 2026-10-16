"""v2.1 세션들을 병합하되 **세션별로 에피소드를 선별**할 수 있다 (v4 200ep 구성용).

merge_blocktask_v2.py와 같은 동작(에피소드 재번호, meta 재구성, stats 길이가중 집계)에
선별 기능만 더했다. v4는 잔여 131ep 중 **블록-박스 근접 상위 35개만** 쓰기 때문이다
(전부 넣으면 원거리 데이터가 분모를 키워 근접 비율이 54.5%→39%로 희석된다).

사용:
  python merge_blocktask_select.py <OUT> <선별목록.txt> <세션:ALL|SELECT> ...
    선별목록.txt: 한 줄에 `<세션명>/file-NNN` (analyze_dataset_geometry.py 출력 형식)
    ALL    = 세션 전체 사용
    SELECT = 선별목록에 있는 에피소드만 사용

에피소드 번호 대응: v3.0의 `file-NNN` → 변환된 v2.1의 `episode_NNNNNN`.
v3.0에서 파일당 에피소드가 1개임을 확인하고 쓴다(meta/episodes/*.parquet 수 == total_episodes).
불일치 시 선별이 엉뚱한 에피소드를 고르므로 **아래 개수 검증에서 중단**한다.
"""
import json, glob, os, shutil, sys
import numpy as np
import pandas as pd

ROOT = "/data/heongyu"
OUT_NAME = sys.argv[1]
SEL_FILE = sys.argv[2]
SPEC = [a.split(":") for a in sys.argv[3:]]        # [(세션, ALL|SELECT), ...]
SESS = [s for s, _ in SPEC]
MODE = dict(SPEC)
OUT = os.path.join(ROOT, OUT_NAME)

# 선별 목록 → {세션: {에피소드번호}}
SELECT = {}
for line in open(SEL_FILE):
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    sess, fname = line.rsplit("/", 1)
    SELECT.setdefault(sess, set()).add(int(fname.split("-")[1]))
for s, m in SPEC:
    if m == "SELECT":
        got = len(SELECT.get(s, ()))
        print(f"선별 {s}: {got}개")
        if got == 0:
            sys.exit(f"❌ {s}에 대한 선별 항목이 없다 — 목록의 세션명을 확인하라")


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
        if MODE.get(s) == "SELECT" and le not in SELECT.get(s, ()):
            continue
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
    if MODE.get(s) == "SELECT" and kept != len(SELECT.get(s, ())):
        sys.exit(f"❌ {s}: 선별 {len(SELECT.get(s, ()))}개 중 {kept}개만 채택됨 "
                 f"— file-NNN ↔ episode_NNNNNN 대응이 어긋났을 수 있다")

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
