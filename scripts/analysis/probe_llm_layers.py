"""언어 모델 층마다 이미지 토큰에 물체 정보가 남아 있나 — probe_vision_viz.py(4-1)의 층별 확장.

4-1 은 고정된 비전 인코더 출력만 봤다. 그런데 4층·8층 모델은 비전 인코더·mlp1·언어 모델 0~7층이
**비트 단위로 같고**, 8층(또는 12층)부터만 다르다. 그래서 "어느 모델이 물체를 더 잘 보나"는
언어 모델을 통과하는 동안 이미지 토큰(카메라당 9×9)에서 물체 구분이 유지·강화되는지로 재야 한다.

  층 0 = 언어 모델 입력(mlp1 출력) · 층 k = k번째 디코더 층 출력 · out = backbone 출력(action head 입력)
  프로브: 4-1 과 같은 MIL-max 선형 프로브(토큰마다 점수 → 최댓값 → 로지스틱), 에피소드 단위 5겹 교차검증 AUC
    top         : 학습 ep 첫 화면, 계획표 물체 = 있음 / 나머지 = 없음
    wrist_right : 그리퍼가 열리는 순간·닫히기 직전(TRAIN_RW/info.json 의 i0·ic), 지시 물체 = 있음,
                  장면에 없는 물체 = 없음, 장면에 있지만 지시 안 된 물체 = 제외
  지시문은 모든 화면에 같은 중립 문장(INSTR)을 넣는다 — 실제 지시문을 넣으면 물체 단어가 이미지 토큰으로
  새어 들어가 "보고 안 것"과 "글자로 안 것"이 섞인다.

출력: OUT/llm_layers_auc.json · OUT/llm_layers_maps.npz (SCENES 화면의 층별 9×9 점수 지도)
사용: python3 probe_llm_layers.py CK DS PLAN TRAIN_RW_INFO OUT
  SCENES="이름:시행폴더:청크,..."  (평가 시행 video.mp4 의 그 청크 프레임)
"""
import csv, json, os, sys
import av, numpy as np, pandas as pd, torch, torch.nn.functional as F
from gr00t.data.embodiment_tags import EmbodimentTag
from gr00t.policy.gr00t_policy import Gr00tPolicy

CK, DS, PLAN, INFO, OUT = sys.argv[1:6]
INSTR = os.environ.get("INSTR", "Put the object into the black bin")
NEP = int(os.environ.get("NEP", "300"))
os.makedirs(OUT, exist_ok=True)
dev = "cuda"
LAB = ["red marker", "blue marker", "black marker", "glue stick", "screwdriver", "toothbrush", "eraser", "yellow straw"]
CAMK = {"top": "left_top", "wrist_left": "left_wrist", "wrist_right": "right_wrist"}
CI = {"top": 0, "wrist_left": 1, "wrist_right": 2}

policy = Gr00tPolicy(embodiment_tag=EmbodimentTag.NEW_EMBODIMENT, model_path=CK, device=dev)
MC = policy.modality_configs
bb = policy.model.backbone
lm = bb.model.language_model
IMG_TOK = bb.model.config.image_token_index
NL = len(lm.model.layers)

cap = {}
lm.model.layers[0].register_forward_pre_hook(
    lambda m, a, k: cap.__setitem__(0, (a[0] if a else k["hidden_states"])[0].detach()), with_kwargs=True)
for li, layer in enumerate(lm.model.layers):
    layer.register_forward_hook(lambda m, a, o, li=li: cap.__setitem__(li + 1, (o[0] if isinstance(o, tuple) else o)[0].detach()))
bb.register_forward_hook(lambda m, a, o: cap.update(out=o["backbone_features"][0].detach(), ids=a[0]["input_ids"][0]))
KEYS = list(range(NL + 1)) + ["out"]


def run(cams, st):
    obs = {"video": {k: cams[k][None, None].copy() for k in MC["video"].modality_keys},
           "state": {}, "language": {lk: [[INSTR]] for lk in MC["language"].modality_keys}}
    sl = {"left_arm": (0, 5), "left_gripper": (5, 6), "right_arm": (6, 11), "right_gripper": (11, 12)}
    for sk in MC["state"].modality_keys:
        lo, hi = sl[sk]
        obs["state"][sk] = st[lo:hi][None, None].astype(np.float32)
    cap.clear()
    torch.manual_seed(0)
    with torch.no_grad():
        policy.get_action(obs)
    pos = torch.where(cap["ids"] == IMG_TOK)[0]
    n = len(pos) // 3
    return {k: cap[k][pos].reshape(3, n, -1).half().cpu() for k in KEYS}  # 층 → 3×81×D


def frames_at(path, idx):
    out, want = {}, set(idx)
    with av.open(path) as c:
        for i, f in enumerate(c.decode(video=0)):
            if i in want:
                out[i] = f.to_ndarray(format="rgb24")
                if len(out) == len(want):
                    break
    return out


plan = list(csv.DictReader(open(PLAN)))
info = json.load(open(INFO))
samples = []  # (cam, ep, 층별 81×D)
for e in range(NEP):
    want = {0: "top"}
    inf = info.get(str(e))
    if inf:
        for g in inf["got"]:
            want[inf["i0" if g == "a" else "ic"]] = "wrist_right"
    fr = {c: frames_at(f"{DS}/videos/observation.images.{CAMK[c]}/chunk-000/file-{e:03d}.mp4", list(want))
          for c in CAMK}
    st_all = np.stack(pd.read_parquet(f"{DS}/data/chunk-000/file-{e:03d}.parquet")["observation.state"].values)
    for i, cam in want.items():
        h = run({c: fr[c][i] for c in CAMK}, st_all[i])
        samples.append((cam, e, {k: v[CI[cam]] for k, v in h.items()}))
    if e % 50 == 0:
        print("수집", e, len(samples), flush=True)


def auc(y, s_):
    r = s_.argsort().argsort() + 1.0
    n1 = y.sum(); n0 = len(y) - n1
    return float((r[y > 0].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def fit(X, Y, M, idx):
    W = torch.zeros(X.shape[-1], len(LAB), device=dev, requires_grad=True)
    b = torch.zeros(len(LAB), device=dev, requires_grad=True)
    opt = torch.optim.Adam([W, b], lr=1e-2, weight_decay=1e-3)
    for _ in range(300):
        l = F.binary_cross_entropy_with_logits((X[idx] @ W).amax(1) + b, Y[idx], reduction="none")
        loss = (l * M[idx]).sum() / M[idx].sum()
        opt.zero_grad(); loss.backward(); opt.step()
    return W.detach(), b.detach()


res, probes = {}, {}
for cam in ("top", "wrist_right"):
    S_ = [s for s in samples if s[0] == cam]
    eps = [s[1] for s in S_]
    objs = [[x.strip() for x in plan[e]["objects"].split(",")] for e in eps]
    if cam == "top":
        Y = torch.tensor([[o in ob for o in LAB] for ob in objs], dtype=torch.float32, device=dev)
        M = torch.ones_like(Y)
    else:
        Y = torch.tensor([[o == plan[e]["target"] for o in LAB] for e in eps], dtype=torch.float32, device=dev)
        M = torch.tensor([[o == plan[e]["target"] or o not in ob for o in LAB] for e, ob in zip(eps, objs)],
                         dtype=torch.float32, device=dev)
    ue = sorted(set(eps)); rng = np.random.RandomState(0); rng.shuffle(ue)
    fold = {e: i % 5 for i, e in enumerate(ue)}
    res[cam] = {}
    for k in KEYS:
        X = torch.stack([s[2][k] for s in S_]).to(dev).float()
        mu, sd = X.mean((0, 1), keepdim=True), X.std((0, 1), keepdim=True) + 1e-5
        X = (X - mu) / sd
        Sc = torch.zeros_like(Y)
        for f in range(5):
            tr = [i for i, e in enumerate(eps) if fold[e] != f]
            te = [i for i, e in enumerate(eps) if fold[e] == f]
            W, b = fit(X, Y, M, tr)
            Sc[te] = (X[te] @ W).amax(1) + b
        a = {}
        for j, o in enumerate(LAB):
            m = M[:, j] > 0
            y, s_ = Y[m, j].cpu().numpy(), Sc[m, j].cpu().numpy()
            if 0 < y.sum() < len(y):
                a[o] = round(auc(y, s_), 3)
        res[cam][str(k)] = a
        W, b = fit(X, Y, M, list(range(len(S_))))
        probes[(cam, k)] = (W, b, mu, sd)
        print(cam, k, "평균 AUC", round(float(np.mean(list(a.values()))), 3), flush=True)
json.dump({"instr": INSTR, "n": {c: sum(s[0] == c for s in samples) for c in ("top", "wrist_right")}, "auc": res},
          open(f"{OUT}/llm_layers_auc.json", "w"), ensure_ascii=False, indent=1)

# 평가 화면의 층별 점수 지도 (전체 학습 화면으로 학습한 프로브)
maps = {}
for item in [x for x in os.environ.get("SCENES", "").split(",") if x]:
    name, trial, chunk = item.split(":")
    rows = list(csv.DictReader(open(f"{trial}/chunks.csv")))
    st = np.array([float(v) for kk, v in rows[int(chunk)].items() if kk.startswith("state_")], np.float32)
    acts = list(csv.DictReader(open(f"{trial}/actions.csv")))
    fi = next(int(x["i"]) for x in acts if int(x["chunk"]) == int(chunk)) // 3
    im = frames_at(f"{trial}/video.mp4", [fi])[fi]
    cams = {k: im[:, 640 * i:640 * (i + 1)] for i, k in enumerate(["top", "wrist_left", "wrist_right"])}
    h = run(cams, st)
    for cam in ("top", "wrist_right"):
        maps[f"{name}/{cam}/img"] = cams[cam]
        for k in KEYS:
            W, b, mu, sd = probes[(cam, k)]
            x = (h[k][CI[cam]].to(dev).float()[None] - mu) / sd
            maps[f"{name}/{cam}/{k}"] = torch.sigmoid(x[0] @ W + b).cpu().numpy()  # 81×8
np.savez_compressed(f"{OUT}/llm_layers_maps.npz", **maps)
print("저장", OUT)
