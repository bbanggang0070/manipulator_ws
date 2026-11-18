"""고정 SigLIP2 비전 인코더 층별 선형 프로브 — 물체(마커 색 등) 존재 정보가 몇 층부터 있나.

입력: 학습 에피소드 첫 프레임 상단 카메라, 학습과 같은 전처리(letterbox→256→중앙 0.95 crop→256).
프로브: 패치 토큰마다 선형 점수 → 최댓값(작은 물체가 어느 패치에 있든 잡히도록) → 로지스틱.
에피소드 단위 5-fold 교차검증 AUC.
"""
import csv, glob, json, os, sys, time
import av, numpy as np, torch, torch.nn.functional as F
from safetensors import safe_open

EAGLE = "/Isaac-GR00T/gr00t/model/modules/nvidia/Eagle-Block2A-2B-v2"
sys.path.insert(0, EAGLE)
import modeling_siglip2 as ms  # noqa
from modeling_siglip2 import Siglip2VisionModel, Siglip2VisionConfig  # noqa
ms.Siglip2PreTrainedModel._init_weights = lambda self, m: None  # 가중치는 체크포인트에서 덮어쓴다

DS, CK, PLAN, OUT = sys.argv[1:5]
EDGE = int(os.environ.get("EDGE", "256"))
dev = "cuda"

vc = Siglip2VisionConfig(**json.load(open(f"{EAGLE}/config.json"))["vision_config"])
vc._attn_implementation = "flash_attention_2"
vm = Siglip2VisionModel(vc).to(dev, torch.bfloat16).eval()
sd = {}
for f in glob.glob(f"{CK}/model-*.safetensors"):
    with safe_open(f, "pt") as h:
        for k in h.keys():
            if k.startswith("backbone.model.vision_model."):
                sd[k[len("backbone.model.vision_model."):]] = h.get_tensor(k)
miss, unexp = vm.load_state_dict(sd, strict=False)
print("가중치", len(sd), "missing", len(miss), "unexpected", len(unexp), miss[:3], unexp[:3])


def frame0(ep):
    p = f"{DS}/videos/chunk-000/observation.images.left_top/episode_{ep:06d}.mp4"
    with av.open(p) as c:
        for fr in c.decode(video=0):
            return fr.to_ndarray(format="rgb24")


def prep(img):
    t = torch.from_numpy(img).permute(2, 0, 1).float()[None]
    h, w = t.shape[-2:]
    s = max(h, w)
    t = F.pad(t, ((s - w) // 2, s - w - (s - w) // 2, (s - h) // 2, s - h - (s - h) // 2))
    t = F.interpolate(t, size=(EDGE, EDGE), mode="bicubic", align_corners=False)
    c = int(round(EDGE * 0.95)); o = (EDGE - c) // 2
    t = t[..., o:o + c, o:o + c]
    t = F.interpolate(t, size=(EDGE, EDGE), mode="bicubic", align_corners=False).clamp(0, 255)
    r = max(28, round(EDGE / 28) * 28)  # Eagle smart_resize: 28 배수 (256 → 252)
    t = F.interpolate(t, size=(r, r), mode="bicubic", align_corners=False).clamp(0, 255)
    return ((t / 255 - 0.5) / 0.5)


plan = list(csv.DictReader(open(PLAN)))
eps = [json.loads(l) for l in open(f"{DS}/meta/episodes.jsonl")]
N = len(eps)
LAB = ["red marker", "blue marker", "black marker", "glue stick", "screwdriver", "toothbrush", "eraser", "yellow straw"]
Y = np.zeros((N, len(LAB)), np.float32)
for e in range(N):
    assert eps[e]["tasks"][0] == plan[e]["instruction"], (e, eps[e]["tasks"], plan[e]["instruction"])
    objs = [o.strip() for o in plan[e]["objects"].split(",")]
    for j, o in enumerate(LAB):
        Y[e, j] = o in objs
print("에피소드", N, "라벨 양성 수", dict(zip(LAB, Y.sum(0).astype(int))))

feats = None
t0 = time.time()
with torch.no_grad():
    for e in range(N):
        x = prep(frame0(e)).to(dev, torch.bfloat16)
        hs = vm(pixel_values=[x], output_hidden_states=True).hidden_states  # (L+1) × [1,T,1152]
        if feats is None:
            L, T = len(hs), hs[0].reshape(-1, hs[0].shape[-1]).shape[0]
            print("hidden 모양", tuple(hs[0].shape), tuple(hs[-1].shape))
            feats = torch.zeros(L, N, T, hs[0].shape[-1], dtype=torch.float16, device=dev)
            print("층(임베딩 포함)", L, "토큰", T)
        for l in range(L):
            feats[l, e] = hs[l].reshape(-1, hs[l].shape[-1]).half()
print(f"특징 추출 {time.time()-t0:.0f}s")


def auc(s, y):
    o = np.argsort(s); r = np.empty(len(s)); r[o] = np.arange(1, len(s) + 1)
    p = y.sum(); n = len(y) - p
    return (r[y == 1].sum() - p * (p + 1) / 2) / (p * n)


# 같은 배치 그룹(대응쌍·4연속)은 한 fold 에 — 장면을 외워 맞히는 누수를 막는다
rng = np.random.default_rng(0)
gid = np.array([int(plan[e]["group"]) for e in range(N)])
ug = rng.permutation(np.unique(gid))
fold = np.array([{g: i % 5 for i, g in enumerate(ug)}[g] for g in gid])
print("그룹", len(ug), "fold 크기", np.bincount(fold))
Yt = torch.tensor(Y, device=dev)
res = {}
for l in range(feats.shape[0]):
    X = feats[l].float()
    mu, sd_ = X.mean((0, 1), keepdim=True), X.std((0, 1), keepdim=True) + 1e-5
    X = (X - mu) / sd_
    scores = np.zeros_like(Y)
    for k in range(5):
        tr, te = torch.tensor(fold != k, device=dev), torch.tensor(fold == k, device=dev)
        W = torch.zeros(X.shape[-1], len(LAB), device=dev, requires_grad=True)
        b = torch.zeros(len(LAB), device=dev, requires_grad=True)
        opt = torch.optim.Adam([W, b], lr=1e-2, weight_decay=1e-3)
        for it in range(300):
            z = (X[tr] @ W).amax(1) + b
            loss = F.binary_cross_entropy_with_logits(z, Yt[tr])
            opt.zero_grad(); loss.backward(); opt.step()
        with torch.no_grad():
            scores[fold == k] = ((X[te] @ W).amax(1) + b).cpu().numpy()
    res[l] = [float(auc(scores[:, j], Y[:, j])) for j in range(len(LAB))]
    print(f"층 {l:2d} " + " ".join(f"{a:.2f}" for a in res[l]), flush=True)
json.dump({"labels": LAB, "auc": res, "edge": EDGE}, open(OUT, "w"), ensure_ascii=False, indent=1)

# ── 평가 A 화면으로 외부 검증: 학습 300ep 전체로 프로브를 학습하고 평가 당일 첫 화면에 적용 ──
EV = os.environ.get("EVAL_DIR")
if EV:
    from PIL import Image
    rows = list(csv.DictReader(open(os.environ["EVAL_CSV"])))
    Ye, Xe = [], []
    with torch.no_grad():
        for r in rows:
            f = f"{EV}/t{int(r['trial']):02d}.png"
            if not os.path.exists(f):
                continue
            objs = [o.strip() for o in r["objects"].split(",")]
            Ye.append([o in objs for o in LAB])
            hs = vm(pixel_values=[prep(np.array(Image.open(f).convert("RGB"))).to(dev, torch.bfloat16)], output_hidden_states=True).hidden_states
            Xe.append(torch.stack([h.reshape(-1, h.shape[-1]).half() for h in hs]))
    Ye = np.array(Ye, np.float32); Xe = torch.stack(Xe, 1)  # L × M × T × C
    print("평가 A 화면", Ye.shape[0], "양성 수", dict(zip(LAB, Ye.sum(0).astype(int))))
    for l in (1, 2, 4, 8, 14, 20, 27):
        X = feats[l].float(); mu, sd_ = X.mean((0, 1), keepdim=True), X.std((0, 1), keepdim=True) + 1e-5
        X = (X - mu) / sd_; XE = (Xe[l].float() - mu) / sd_
        W = torch.zeros(X.shape[-1], len(LAB), device=dev, requires_grad=True)
        b = torch.zeros(len(LAB), device=dev, requires_grad=True)
        opt = torch.optim.Adam([W, b], lr=1e-2, weight_decay=1e-3)
        for it in range(300):
            loss = F.binary_cross_entropy_with_logits((X @ W).amax(1) + b, Yt)
            opt.zero_grad(); loss.backward(); opt.step()
        with torch.no_grad():
            s = ((XE @ W).amax(1) + b).cpu().numpy()
        a = [auc(s[:, j], Ye[:, j]) if 0 < Ye[:, j].sum() < len(Ye) else float("nan") for j in range(len(LAB))]
        acc = ((s > 0) == (Ye > 0)).mean(0)
        print(f"평가A 층 {l:2d} AUC " + " ".join(f"{x:.2f}" for x in a) + " | 정확도 " + " ".join(f"{x:.2f}" for x in acc), flush=True)
