"""probe_lang_swap.py 결과 그림 — 카메라 화면 위에 9×9 토큰 지도 + 오른팔 예측 궤적.

  OUT/lang_attn_<case>[_<cam>].png   물체 단어마다: 이미지 토큰 → 물체 단어 attention (12~15층 평균)
  OUT/lang_feat_<case>[_<cam>].png   기준 물체 대비 VLM 출력 변화(1 - cos) 지도
  (CAMS="top,wrist_right" — 상단은 접미사 없음)
  OUT/lang_act.png           물체 단어별 오른팔 shoulder_pan·elbow 예측 (16스텝, 시드 8개)
"""
import json, os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

D, FONT = sys.argv[1:3]
z = np.load(f"{D}/lang_swap.npz")
R = json.load(open(f"{D}/lang_swap.json"))
font_manager.fontManager.addfont(FONT)
plt.rcParams["font.family"] = font_manager.FontProperties(fname=FONT).get_name()
font = ImageFont.truetype(FONT, 26)

EDGE, G = 256, 9
C = int(round(EDGE * 0.95)); O = (EDGE - C) // 2
X0, SPAN, PAD_Y = O * 640 / EDGE, C * 640 / EDGE, 80
COL = {"red marker": (255, 60, 60), "blue marker": (50, 150, 255), "black marker": (255, 0, 255),
       "glue stick": (60, 230, 60)}
TOP = slice(12, 16)  # 학습된 위 4층


def overlay(img, m, col, lo, hi):
    """9×9 값을 원본 좌표로 펴서 겹친다 (lo 이하는 칠하지 않음)."""
    a0, a1 = int(X0), int(X0 + SPAN)
    up = np.asarray(Image.fromarray(m.astype(np.float32), mode="F").resize((a1 - a0, a1 - a0), Image.BILINEAR))
    sq = np.zeros((640, 640), np.float32)
    sq[a0:a1, a0:a1] = up
    w = np.clip((sq[PAD_Y:PAD_Y + 480] - lo) / (hi - lo + 1e-9), 0, 1)[..., None]
    base = img.astype(np.float32) * 0.45
    return Image.fromarray((base * (1 - w) + np.array(col, np.float32) * w * 0.85 + base * w * 0.3).clip(0, 255).astype(np.uint8))


def panel_row(img, maps, titles, cols, head, path):
    vals = np.concatenate([m.ravel() for m in maps])
    lo, hi = np.percentile(vals, 70), vals.max()
    ims = [Image.fromarray(img)]
    ImageDraw.Draw(ims[0]).text((10, 8), "카메라 원본", font=font, fill="white", stroke_width=3, stroke_fill="black")
    for m, t, c in zip(maps, titles, cols):
        p = overlay(img, m, c, lo, hi)
        ImageDraw.Draw(p).text((10, 8), t, font=font, fill="white", stroke_width=3, stroke_fill="black")
        ims.append(p)
    cv = Image.new("RGB", (640 * len(ims), 480 + 44), (32, 32, 32))
    for i, p in enumerate(ims):
        cv.paste(p, (640 * i, 44))
    ImageDraw.Draw(cv).text((12, 8), head, font=font, fill="white")
    s = 3 / 5 if len(ims) <= 5 else 1 / 2
    cv.resize((int(cv.width * s), int(cv.height * s)), Image.LANCZOS).save(path)


CAMS = [c for c in os.environ.get("CAMS", "top,wrist_right").split(",")]
CAM_KO = {"top": "상단", "wrist_left": "왼손목", "wrist_right": "오른손목"}
CI = {"top": 0, "wrist_left": 1, "wrist_right": 2}
for case, r in R.items():
    objs = r["objects"]
    when = "시작 화면" if r["chunk"] == 0 else f"{r['chunk']}번째 추론 시점"
    ref = "black marker" if "black marker" in objs and "glue stick" not in objs else objs[0]
    for cam in CAMS:
        img = z[f"{case}/{cam}"]
        sl = slice(CI[cam] * G * G, (CI[cam] + 1) * G * G)
        sfx = "" if cam == "top" else f"_{cam}"
        head = f"{case.split('_')[0]} {CAM_KO[cam]} 카메라 · {when}"
        # ① attention
        maps = [z[f"{case}/{o}/attn_obj"][TOP][:, sl].mean(0).reshape(G, G) for o in objs]
        panel_row(img, maps, [f"'{o}' 단어를 참조" for o in objs], [COL[o] for o in objs],
                  f"{head} — 이미지 토큰이 지시문 물체 단어를 참조하는 정도 (언어모델 12~15층 평균)",
                  f"{D}/lang_attn_{case}{sfx}.png")
        # ② VLM 출력 변화 — 기준: t11 은 black(실제로 집은 것), t13 은 glue stick(지시 대상)
        maps, titles, cols = [], [], []
        for o in objs:
            if o == ref:
                continue
            A = z[f"{case}/{ref}/feat"][z[f"{case}/{ref}/img_pos"][sl]]
            B = z[f"{case}/{o}/feat"][z[f"{case}/{o}/img_pos"][sl]]
            d = 1 - (A * B).sum(1) / np.linalg.norm(A, axis=1) / np.linalg.norm(B, axis=1)
            maps.append(d.reshape(G, G)); titles.append(f"{ref.split()[0]} → {o.split()[0]} 로 바꿨을 때"); cols.append((255, 200, 0))
        panel_row(img, maps, titles, cols,
                  f"{head} — 물체 단어만 바꿨을 때 VLM 출력(action head 입력)이 달라진 위치",
                  f"{D}/lang_feat_{case}{sfx}.png")

# ③ 예측 궤적
cases = [c for c in R if not c.endswith("start")] + [c for c in R if c.endswith("start")]
fig, axs = plt.subplots(2, len(cases), figsize=(3.6 * len(cases), 6.4), squeeze=False)
for j, case in enumerate(cases):
    r = R[case]
    st = np.array(r["state"])
    for o in r["objects"]:
        a = z[f"{case}/{o}/act_right_arm"]  # seeds×16×5
        c = np.array(COL[o]) / 255
        for i, (jn, k) in enumerate([("shoulder_pan", 0), ("elbow_flex", 2)]):
            ax = axs[i, j]
            y = np.concatenate([np.full((a.shape[0], 1), st[6 + k]), a[:, :, k]], 1)
            ax.plot(y.T, color=c, alpha=0.25, lw=0.8)
            ax.plot(y.mean(0), color=c, lw=2.2, label=o)
            ax.set_title(f"{case} · 오른팔 {jn}", fontsize=10)
            ax.set_xlabel("예측 스텝 (30Hz)")
            ax.grid(alpha=0.3)
axs[0, 0].legend(fontsize=8)
fig.suptitle("같은 화면·같은 상태·같은 노이즈 시드 8개에서 물체 단어만 바꾼 예측 (굵은 선 = 평균)", fontsize=11)
fig.tight_layout()
fig.savefig(f"{D}/lang_act.png", dpi=110)
print("그림 저장")
