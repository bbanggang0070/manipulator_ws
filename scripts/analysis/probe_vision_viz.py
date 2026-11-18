"""고정 SigLIP2 비전 인코더가 화면의 **어디를** 각 물체로 보는지 시각화 (probe_vision_layers.py 후속).

probe_vision_layers.py 는 "이 화면에 red marker 가 있나"를 층별 AUC 로만 쟀다. 여기서는
마지막 층(정책이 실제로 받는 출력)에 같은 MIL-max 선형 프로브를 학습 300ep 첫 화면 전체로
학습한 뒤, 패치(18×18, 한 칸 ≈ 원본 34px)마다 점수를 원본 카메라 화면 위에 겹친다.
프로브는 "있다/없다"만 배웠고 위치는 배운 적이 없다 — 그런데도 점수가 그 물체 자리에
모이면, 인코더 출력 안에서 물체가 구분돼 있다는 시각적 증거가 된다.

입력:  TRAIN_DIR/e000.png… (학습 ep 첫 화면, 640×480) · PLAN(물체 목록) · CK(체크포인트)
출력:  OUT/probe_<이름>.png (원본 + 물체별 히트맵) · OUT/probe_<이름>.mp4 (영상 프레임마다 상자)
  SCENES="A11:path.png,..."  VIDEOS="t11_300:video.mp4,..."  (video.mp4 는 3카메라 가로 이어붙인 것, 왼쪽 640 이 상단)
  CAM=wrist_right (기본 top) — 손목 카메라판. TRAIN_DIR/e000_a.png·e000_c.png(그리퍼가 열리는 순간·닫히기 직전)로
    학습하고, 장면·영상은 해당 카메라 영역(640px)만 잘라 쓴다. 교차검증 AUC 를 OUT/probe_cv_<CAM>.json 에 남긴다.
"""
import csv, glob, json, os, sys
import av, numpy as np, torch, torch.nn.functional as F
from PIL import Image, ImageDraw, ImageFont
from safetensors import safe_open

EAGLE = "/Isaac-GR00T/gr00t/model/modules/nvidia/Eagle-Block2A-2B-v2"
sys.path.insert(0, EAGLE)
import modeling_siglip2 as ms  # noqa
from modeling_siglip2 import Siglip2VisionModel, Siglip2VisionConfig  # noqa
ms.Siglip2PreTrainedModel._init_weights = lambda self, m: None

TRAIN, PLAN, CK, OUT, FONT = sys.argv[1:6]
os.makedirs(OUT, exist_ok=True)
dev = "cuda"
LAB = ["red marker", "blue marker", "black marker", "glue stick", "screwdriver", "toothbrush", "eraser", "yellow straw"]
SHOW = {"red marker": (255, 50, 50), "blue marker": (40, 140, 255), "black marker": (255, 0, 255), "glue stick": (60, 230, 60)}
EDGE, G = 256, 18

vc = Siglip2VisionConfig(**json.load(open(f"{EAGLE}/config.json"))["vision_config"])
vc._attn_implementation = "flash_attention_2"
vm = Siglip2VisionModel(vc).to(dev, torch.bfloat16).eval()
sd = {}
for f in glob.glob(f"{CK}/model-*.safetensors"):
    with safe_open(f, "pt") as h:
        for k in h.keys():
            if k.startswith("backbone.model.vision_model."):
                sd[k[len("backbone.model.vision_model."):]] = h.get_tensor(k)
vm.load_state_dict(sd, strict=False)

# 학습 전처리와 같은 경로: 640×480 → letterbox 640² → 256 → 중앙 0.95 → 256 → 252(28 배수)
C = int(round(EDGE * 0.95)); O = (EDGE - C) // 2
SC = 640 / EDGE                       # 256 → 640² 배율
X0, SPAN = O * SC, C * SC             # 패치 격자가 덮는 정사각형 영역 (640² 좌표)
PAD_Y = 80                            # letterbox 위쪽 패딩


def prep(img):
    t = torch.from_numpy(np.asarray(img)).permute(2, 0, 1).float()[None]
    t = F.pad(t, (0, 0, PAD_Y, PAD_Y))
    t = F.interpolate(t, size=(EDGE, EDGE), mode="bicubic", align_corners=False)
    t = t[..., O:O + C, O:O + C]
    t = F.interpolate(t, size=(EDGE, EDGE), mode="bicubic", align_corners=False).clamp(0, 255)
    t = F.interpolate(t, size=(252, 252), mode="bicubic", align_corners=False).clamp(0, 255)
    return ((t / 255 - 0.5) / 0.5).to(dev, torch.bfloat16)


@torch.no_grad()
def feat(img):
    return vm(pixel_values=[prep(img)]).last_hidden_state.reshape(-1, vc.hidden_size).float()  # 324×1152


plan = list(csv.DictReader(open(PLAN)))
CAM = os.environ.get("CAM", "top")
XOFF = {"top": 0, "wrist_left": 640, "wrist_right": 1280}[CAM]
if CAM == "top":
    # 상단: 학습 ep 첫 화면 — 계획표의 물체가 전부 화면에 있다
    files = [f"{TRAIN}/e{e:03d}.png" for e in range(len(glob.glob(f"{TRAIN}/e*.png")))]
    eps = list(range(len(files)))
    Y = torch.tensor([[o in [x.strip() for x in plan[e]["objects"].split(",")] for o in LAB] for e in eps],
                     dtype=torch.float32, device=dev)
    M = torch.ones_like(Y)
else:
    # 손목: 그리퍼가 열리는 순간(_a)·닫히기 직전(_c) — 확실히 보이는 건 지시 물체뿐이다.
    # 지시 물체 = 있음, 장면에 없는 물체 = 없음, 장면에 있지만 지시 안 된 물체 = 학습에서 제외(보일 수도 안 보일 수도)
    files = sorted(glob.glob(f"{TRAIN}/e*_?.png"))
    eps = [int(os.path.basename(f)[1:4]) for f in files]
    objs = [[x.strip() for x in plan[e]["objects"].split(",")] for e in eps]
    Y = torch.tensor([[o == plan[e]["target"] for o in LAB] for e in eps], dtype=torch.float32, device=dev)
    M = torch.tensor([[o == plan[e]["target"] or o not in ob for o in LAB] for e, ob in zip(eps, objs)],
                     dtype=torch.float32, device=dev)
X = torch.stack([feat(Image.open(f).convert("RGB")) for f in files])
mu, sdv = X.mean((0, 1), keepdim=True), X.std((0, 1), keepdim=True) + 1e-5
X = (X - mu) / sdv


def fit(idx):
    W = torch.zeros(X.shape[-1], len(LAB), device=dev, requires_grad=True)
    b = torch.zeros(len(LAB), device=dev, requires_grad=True)
    opt = torch.optim.Adam([W, b], lr=1e-2, weight_decay=1e-3)
    for _ in range(300):
        l = F.binary_cross_entropy_with_logits((X[idx] @ W).amax(1) + b, Y[idx], reduction="none")
        loss = (l * M[idx]).sum() / M[idx].sum()
        opt.zero_grad(); loss.backward(); opt.step()
    return W.detach(), b.detach(), loss.item()


if CAM != "top":
    # 에피소드 단위 5겹 교차검증 — 학습에 안 쓴 ep 의 화면에서 지시 물체 vs 장면에 없는 물체 AUC
    ue = sorted(set(eps)); rng = np.random.RandomState(0); rng.shuffle(ue)
    fold = {e: i % 5 for i, e in enumerate(ue)}
    S = torch.zeros_like(Y)
    for k in range(5):
        tr = [i for i, e in enumerate(eps) if fold[e] != k]
        te = [i for i, e in enumerate(eps) if fold[e] == k]
        W_, b_, _ = fit(tr)
        S[te] = (X[te] @ W_).amax(1) + b_

    def roc_auc_score(y, s_):  # 순위 기반 AUC (sklearn 없이)
        r = s_.argsort().argsort() + 1.0
        n1 = y.sum(); n0 = len(y) - n1
        return (r[y > 0].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)
    cv = {}
    for j, o in enumerate(LAB):
        m = M[:, j] > 0
        y, s_ = Y[m, j].cpu().numpy(), S[m, j].cpu().numpy()
        if 0 < y.sum() < len(y):
            cv[o] = round(float(roc_auc_score(y, s_)), 3)
    print("손목 교차검증 AUC", cv)
    json.dump(cv, open(f"{OUT}/probe_cv_{CAM}.json", "w"), ensure_ascii=False)
W, b, loss = fit(list(range(len(files))))
print(f"프로브 학습 화면 {len(files)}장, 최종 loss {loss:.3f}")


def score(img):
    s = ((feat(img) - mu[0]) / sdv[0]) @ W + b          # 324×8 패치 로짓
    p = torch.sigmoid(s).reshape(G, G, -1).cpu().numpy()
    return p, torch.sigmoid(s.amax(0)).cpu().numpy()     # 패치별, 화면 전체(있음 확률)


def cell_box(i, j):
    cs = SPAN / G
    return (X0 + j * cs, X0 + i * cs - PAD_Y, X0 + (j + 1) * cs, X0 + (i + 1) * cs - PAD_Y)


def heat(img, pm, col):
    """패치 확률을 원본 좌표로 펴서 색을 겹친다."""
    sq = np.zeros((640, 640), np.float32)
    a0, a1 = int(X0), int(X0 + SPAN)
    up = np.asarray(Image.fromarray((pm * 255).astype(np.uint8)).resize((a1 - a0, a1 - a0), Image.BILINEAR)) / 255
    sq[a0:a1, a0:a1] = up
    m = np.clip((sq[PAD_Y:PAD_Y + 480] - 0.3) / 0.5, 0, 1)[..., None]  # 0.3 이하는 칠하지 않음 (배경 틴트 방지)
    base = np.asarray(img).astype(np.float32) * 0.45
    return Image.fromarray((base * (1 - m) + np.array(col, np.float32) * m + base * m * 0.3).clip(0, 255).astype(np.uint8))


font = ImageFont.truetype(FONT, 26)
font_s = ImageFont.truetype(FONT, 20)

for item in filter(None, os.environ.get("SCENES", "").split(",")):
    name, path, *title = item.split(":")
    img = Image.open(path).convert("RGB").crop((XOFF, 0, XOFF + 640, 480))
    pm, pres = score(img)
    panels = [img.copy()]
    ImageDraw.Draw(panels[0]).text((10, 8), "카메라 원본", font=font, fill="white", stroke_width=3, stroke_fill="black")
    for o, col in SHOW.items():
        k = LAB.index(o)
        h = heat(img, pm[..., k], col)
        ImageDraw.Draw(h).text((10, 8), f"{o}  있음 확률 {pres[k]:.2f}", font=font, fill="white",
                               stroke_width=3, stroke_fill="black")
        panels.append(h)
    canvas = Image.new("RGB", (640 * 5, 480 + 44), (32, 32, 32))
    for i, p in enumerate(panels):
        canvas.paste(p, (640 * i, 44))
    ImageDraw.Draw(canvas).text((12, 8), title[0] if title else name, font=font, fill="white")
    canvas.resize((640 * 5 * 3 // 5, (480 + 44) * 3 // 5), Image.LANCZOS).save(f"{OUT}/probe_{name}.png")
    print(name, {o: round(float(pres[LAB.index(o)]), 2) for o in SHOW})

for item in filter(None, os.environ.get("VIDEOS", "").split(",")):
    name, path, *title = item.split(":")
    with av.open(path) as cin:
        frames = [f.to_image().crop((XOFF, 0, XOFF + 640, 480)) for f in cin.decode(video=0)]
    oc = av.open(f"{OUT}/probe_{name}.mp4", "w")
    st = oc.add_stream("libx264", rate=20)
    st.width, st.height, st.pix_fmt = 640, 540, "yuv420p"
    st.options = {"crf": "24"}
    for fr in frames:
        pm, pres = score(fr)
        im = fr.copy()
        d = ImageDraw.Draw(im)
        for o, col in SHOW.items():
            k = LAB.index(o)
            if pres[k] < 0.5:
                continue
            i, j = np.unravel_index(pm[..., k].argmax(), (G, G))
            x0, y0, x1, y1 = cell_box(i, j)
            pad = 10
            d.rectangle((x0 - pad, y0 - pad, x1 + pad, y1 + pad), outline=col, width=4)
            d.text((x1 + pad + 4, y0 - pad), o.replace(" marker", ""), font=font_s, fill=col,
                   stroke_width=3, stroke_fill="black")
        cv = Image.new("RGB", (640, 540), (32, 32, 32))
        cv.paste(im, (0, 60))
        cd = ImageDraw.Draw(cv)
        cd.text((10, 4), title[0] if title else name, font=font_s, fill="white")
        cd.text((10, 32), "  ".join(f"{o.split()[0]} {pres[LAB.index(o)]:.2f}" for o in SHOW),
                font=font_s, fill=(200, 200, 200))
        for _ in range(2):  # 10fps 원본을 20fps 로 (2배속 아님, 실시간)
            for p in st.encode(av.VideoFrame.from_image(cv)):
                oc.mux(p)
    for p in st.encode():
        oc.mux(p)
    oc.close()
    print(name, "영상", len(frames), "프레임")
