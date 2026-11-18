"""4층·8층 모델 비교 그림 — probe_llm_layers.py(층별 프로브)·probe_lang_swap.py(물체 단어 바꾸기) 결과를 나란히.

  OUT/cmp_auc.png                층별 프로브 AUC (상단·오른손목, 두 모델 겹쳐 그림)
  OUT/cmp_attn_<case>_<cam>.png  물체 단어 attention — 위 줄 4층, 아래 줄 8층 (같은 층 구간 평균)
  OUT/cmp_attn_layers.png        층마다 "지시 단어 attention 이 지시 물체 쪽에 얼마나 몰렸나"
  OUT/cmp_probe_<case>.png       out(=action head 입력) 층 프로브 점수 지도 — glue stick · black marker
  OUT/cmp_act.png                물체 단어별 오른팔 예측 궤적 — 4층(점선) · 8층(실선)
  OUT/cmp_summary.json           표에 옮길 숫자
사용: python3 probe_compare_viz.py D4 D8 FONT OUT   (D4·D8 = 각 모델 출력 폴더)
"""
import json, os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

D4, D8, FONT, OUT = sys.argv[1:5]
os.makedirs(OUT, exist_ok=True)
font_manager.fontManager.addfont(FONT)
plt.rcParams["font.family"] = font_manager.FontProperties(fname=FONT).get_name()
font = ImageFont.truetype(FONT, 26)
EDGE, G = 256, 9
C = int(round(EDGE * 0.95)); O = (EDGE - C) // 2
X0, SPAN, PAD_Y = O * 640 / EDGE, C * 640 / EDGE, 80
COL = {"red marker": (255, 60, 60), "blue marker": (50, 150, 255), "black marker": (255, 0, 255),
       "glue stick": (60, 230, 60)}
CI = {"top": 0, "wrist_left": 1, "wrist_right": 2}
CAM_KO = {"top": "상단", "wrist_right": "오른손목"}
LAB = ["red marker", "blue marker", "black marker", "glue stick", "screwdriver", "toothbrush", "eraser", "yellow straw"]
M = {"4": D4, "8": D8}
summary = {}


def overlay(img, m, col, lo, hi):
    a0, a1 = int(X0), int(X0 + SPAN)
    up = np.asarray(Image.fromarray(m.astype(np.float32), mode="F").resize((a1 - a0, a1 - a0), Image.BILINEAR))
    sq = np.zeros((640, 640), np.float32)
    sq[a0:a1, a0:a1] = up
    w = np.clip((sq[PAD_Y:PAD_Y + 480] - lo) / (hi - lo + 1e-9), 0, 1)[..., None]
    base = img.astype(np.float32) * 0.45
    return Image.fromarray((base * (1 - w) + np.array(col, np.float32) * w * 0.85 + base * w * 0.3).clip(0, 255).astype(np.uint8))


def grid(img, rows, row_titles, head, path, lo=None, hi=None):
    """rows = [[(map, title, col), ...], ...] — 같은 색 범위(줄 사이 비교 가능)."""
    vals = np.concatenate([m.ravel() for r in rows for m, _, _ in r])
    lo = np.percentile(vals, 70) if lo is None else lo
    hi = vals.max() if hi is None else hi
    ncol = 1 + max(len(r) for r in rows)
    cv = Image.new("RGB", (640 * ncol, 44 + 480 * len(rows)), (32, 32, 32))
    for ri, (r, rt) in enumerate(zip(rows, row_titles)):
        p0 = Image.fromarray(img.copy())
        ImageDraw.Draw(p0).text((10, 8), rt, font=font, fill="white", stroke_width=3, stroke_fill="black")
        cv.paste(p0, (0, 44 + 480 * ri))
        for ci, (m, t, c) in enumerate(r):
            p = overlay(img, m, c, lo, hi)
            ImageDraw.Draw(p).text((10, 8), t, font=font, fill="white", stroke_width=3, stroke_fill="black")
            cv.paste(p, (640 * (ci + 1), 44 + 480 * ri))
    ImageDraw.Draw(cv).text((12, 8), head, font=font, fill="white")
    s = 0.5 if ncol >= 5 else 0.6
    cv.resize((int(cv.width * s), int(cv.height * s)), Image.LANCZOS).save(path)


# ① 층별 프로브 AUC
A = {n: json.load(open(f"{d}/llm_layers_auc.json")) for n, d in M.items()}
fig, axs = plt.subplots(1, 2, figsize=(13, 4.6))
summary["auc"] = {}
for ax, cam in zip(axs, ("top", "wrist_right")):
    keys = list(A["4"]["auc"][cam].keys())
    xs = list(range(len(keys)))
    for n, ls in (("4", "--"), ("8", "-")):
        a = A[n]["auc"][cam]
        mean = [np.mean(list(a[k].values())) for k in keys]
        ax.plot(xs, mean, ls, color="k", lw=2.4, label=f"{n}층 모델 · 물체 평균")
        for o in ("red marker", "blue marker", "black marker", "glue stick"):
            if o in a[keys[0]]:
                ax.plot(xs, [a[k].get(o, np.nan) for k in keys], ls, color=np.array(COL[o]) / 255, lw=1.2, alpha=0.8,
                        label=f"{n}층 · {o}" if cam == "wrist_right" else None)
        summary["auc"].setdefault(cam, {})[n] = {k: round(float(np.mean(list(a[k].values()))), 3) for k in keys}
        summary["auc"][cam][n + "_obj"] = {k: a[k] for k in ("0", "8", "12", "14", "16", "out") if k in a}
    ax.axvspan(9 - 0.5, 13 - 0.5, color="orange", alpha=0.12, label="8층 모델만 학습한 층 (8~11)")
    ax.axvspan(13 - 0.5, 16 + 0.5, color="green", alpha=0.08, label="두 모델 다 학습한 층 (12~15)")
    ax.set_xticks(xs); ax.set_xticklabels(["입력" if k == "0" else k if k == "out" else str(int(k) - 1) for k in keys], fontsize=8)
    ax.set_xlabel("언어 모델 층 출력 (입력 = mlp1 출력, out = action head 입력)")
    ax.set_ylabel("교차검증 AUC"); ax.set_ylim(0.45, 1.01); ax.grid(alpha=0.3)
    ax.set_title(f"{CAM_KO[cam]} 카메라 — 이미지 토큰에서 물체 구분 (n={A['4']['n'][cam]})", fontsize=11)
axs[1].legend(fontsize=7, ncol=2, loc="lower left")
fig.suptitle("층별 선형 프로브: 0~7층은 두 모델이 비트 단위로 같다 — 차이는 8층부터", fontsize=12)
fig.tight_layout(); fig.savefig(f"{OUT}/cmp_auc.png", dpi=110); plt.close(fig)

# ② 물체 단어 attention — 4층/8층 같은 화면
Z = {n: np.load(f"{d}/lang_swap.npz") for n, d in M.items()}
R = {n: json.load(open(f"{d}/lang_swap.json")) for n, d in M.items()}
cases = list(R["4"].keys())
SPANS = {"12~15층": slice(12, 16), "8~11층": slice(8, 12)}
for case in cases:
    objs = R["4"][case]["objects"]
    for cam in ("top", "wrist_right"):
        img = Z["4"][f"{case}/{cam}"]
        sl = slice(CI[cam] * G * G, (CI[cam] + 1) * G * G)
        rows, rts = [], []
        for n in ("4", "8"):
            for sn, sp in SPANS.items():
                rows.append([(Z[n][f"{case}/{o}/attn_obj"][sp][:, sl].mean(0).reshape(G, G), f"'{o}'", COL[o]) for o in objs])
                rts.append(f"{n}층 모델 · {sn}")
        grid(img, rows, rts, f"{case} {CAM_KO[cam]} — 이미지 토큰이 물체 단어를 참조하는 정도 (네 줄 같은 색 범위)",
             f"{OUT}/cmp_attn_{case}_{cam}.png")

# ③ 층마다 attention 의 "단어 특이성" — 단어를 바꾸면 attention 지도가 얼마나 달라지나 (1 - 평균 상관)
fig, axs = plt.subplots(1, 2, figsize=(13, 4.2))
summary["attn_spec"] = {}
for ax, cam in zip(axs, ("top", "wrist_right")):
    sl = slice(CI[cam] * G * G, (CI[cam] + 1) * G * G)
    for n, ls in (("4", "--"), ("8", "-")):
        allc = []
        for case in cases:
            objs = R[n][case]["objects"]
            maps = np.stack([Z[n][f"{case}/{o}/attn_obj"][:, sl] for o in objs])  # O×L×81
            L = maps.shape[1]
            spec = []
            for l in range(L):
                c = np.corrcoef(maps[:, l])
                spec.append(1 - c[np.triu_indices(len(objs), 1)].mean())
            allc.append(spec)
        allc = np.array(allc)
        ax.plot(range(L), allc.mean(0), ls, color="k", lw=2.2, label=f"{n}층 모델")
        summary["attn_spec"].setdefault(cam, {})[n] = [round(float(v), 3) for v in allc.mean(0)]
    ax.axvspan(7.5, 11.5, color="orange", alpha=0.12); ax.axvspan(11.5, 15.5, color="green", alpha=0.08)
    ax.set_xlabel("언어 모델 층"); ax.set_ylabel("1 − 단어 간 attention 지도 상관")
    ax.set_title(f"{CAM_KO[cam]} — 물체 단어마다 다른 곳을 보나 (높을수록 단어별로 다름)", fontsize=10)
    ax.grid(alpha=0.3); ax.legend()
fig.tight_layout(); fig.savefig(f"{OUT}/cmp_attn_layers.png", dpi=110); plt.close(fig)

# ④ VLM 출력 변화(1 - cos) — 기준 단어 대비, 카메라별 평균
summary["feat"] = {}
for case in cases:
    objs = R["4"][case]["objects"]
    ref = "glue stick" if "glue stick" in objs else "black marker"
    for n in ("4", "8"):
        z = Z[n]
        for cam in ("top", "wrist_right"):
            sl = slice(CI[cam] * G * G, (CI[cam] + 1) * G * G)
            v = {}
            for o in objs:
                if o == ref:
                    continue
                a = z[f"{case}/{ref}/feat"][z[f"{case}/{ref}/img_pos"][sl]]
                b = z[f"{case}/{o}/feat"][z[f"{case}/{o}/img_pos"][sl]]
                v[o] = round(float((1 - (a * b).sum(1) / np.linalg.norm(a, axis=1) / np.linalg.norm(b, axis=1)).mean()), 4)
            summary["feat"].setdefault(case, {}).setdefault(n, {})[cam] = v

# ⑤ 프로브 점수 지도 (out 층)
P = {n: np.load(f"{d}/llm_layers_maps.npz") for n, d in M.items()}
scenes = sorted({k.split("/")[0] for k in P["4"].files})
for sc in scenes:
    for cam in ("top", "wrist_right"):
        img = P["4"][f"{sc}/{cam}/img"]
        rows, rts = [], []
        for n in ("4", "8"):
            for lk in ("8", "out"):  # 키 8 = 7번 층 출력 (두 모델이 같은 마지막 층)
                s = P[n][f"{sc}/{cam}/{lk}"]
                rows.append([(s[:, LAB.index(o)].reshape(G, G), f"'{o}' 점수", COL[o]) for o in ("glue stick", "black marker", "red marker", "blue marker")])
                rts.append(f"{n}층 모델 · {'7번 층 출력(두 모델 같음)' if lk == '8' else 'action head 입력'}")
        grid(img, rows, rts, f"{sc} {CAM_KO[cam]} — 층별 프로브가 물체라고 본 위치 (0.5 이상만 칠함)",
             f"{OUT}/cmp_probe_{sc}_{cam}.png", lo=0.5, hi=1.0)

# ⑥ 예측 궤적
fig, axs = plt.subplots(2, len(cases), figsize=(3.3 * len(cases), 6.4), squeeze=False)
summary["act"] = {}
for j, case in enumerate(cases):
    st = np.array(R["4"][case]["state"])
    for n, ls in (("4", "--"), ("8", "-")):
        for o in R[n][case]["objects"]:
            a = Z[n][f"{case}/{o}/act_right_arm"]
            c = np.array(COL[o]) / 255
            summary["act"].setdefault(case, {}).setdefault(n, {})[o] = {
                "pan_end": round(float(a[:, -1, 0].mean() - st[6]), 2), "pan_sd": round(float(a[:, -1, 0].std()), 2),
                "elbow_end": round(float(a[:, -1, 2].mean() - st[8]), 2)}
            for i, k in enumerate((0, 2)):
                y = np.concatenate([np.full((a.shape[0], 1), st[6 + k]), a[:, :, k]], 1).mean(0)
                axs[i, j].plot(y, ls, color=c, lw=2, label=f"{n}층 {o}" if j == 0 else None)
    axs[0, j].set_title(f"{case} · shoulder_pan", fontsize=9); axs[1, j].set_title(f"{case} · elbow_flex", fontsize=9)
    for i in range(2):
        axs[i, j].grid(alpha=0.3)
axs[0, 0].legend(fontsize=6)
fig.suptitle("같은 화면·상태·시드 8개에서 물체 단어만 바꾼 오른팔 예측 평균 — 점선 4층, 실선 8층", fontsize=11)
fig.tight_layout(); fig.savefig(f"{OUT}/cmp_act.png", dpi=105); plt.close(fig)

json.dump(summary, open(f"{OUT}/cmp_summary.json", "w"), ensure_ascii=False, indent=1)
print("그림 저장", OUT)
