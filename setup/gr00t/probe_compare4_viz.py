"""네 모델(데이터 300/392ep × 언어 모델 학습 4/8층) 요약 비교 — probe_compare_viz.py 의 2×2 판.

probe_compare_viz.py 는 두 모델 그림(attention 지도·점수 지도)을 그린다. 여기서는 그 숫자를
네 모델 한 그림·한 표로 모은다.
  OUT/cmp4_auc.png       층별 프로브 AUC(물체 평균 + 마커 3색) — 상단·오른손목
  OUT/cmp4_attn.png      층마다 물체 단어 attention 의 단어 특이성(1 − 단어 간 지도 상관)
  OUT/cmp4_act.png       장면별 물체 단어에 따른 예측 pan·elbow 차이(0.5초 뒤, 시드 8개 평균)
  OUT/cmp4_summary.json
사용: python3 probe_compare4_viz.py D300_4 D300_8 D392_4 D392_8 FONT OUT
"""
import json, os, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

*DS, FONT, OUT = sys.argv[1:7]
os.makedirs(OUT, exist_ok=True)
font_manager.fontManager.addfont(FONT)
plt.rcParams["font.family"] = font_manager.FontProperties(fname=FONT).get_name()
NAMES = ["300ep·4층", "300ep·8층", "392ep·4층", "392ep·8층"]
STY = {"300ep·4층": ("tab:gray", "--"), "300ep·8층": ("tab:gray", "-"),
       "392ep·4층": ("tab:blue", "--"), "392ep·8층": ("tab:blue", "-")}
M = dict(zip(NAMES, DS))
G = 9
CI = {"top": 0, "wrist_right": 2}
CAM_KO = {"top": "상단", "wrist_right": "오른손목"}
MK = ("red marker", "blue marker", "black marker")
S = {}

# ① AUC
A = {n: json.load(open(f"{d}/llm_layers_auc.json"))["auc"] for n, d in M.items()}
fig, axs = plt.subplots(2, 2, figsize=(13, 8))
S["auc"] = {}
for j, cam in enumerate(("top", "wrist_right")):
    keys = list(A[NAMES[0]][cam].keys())
    xs = range(len(keys))
    for n in NAMES:
        c, ls = STY[n]; a = A[n][cam]
        allm = [np.mean(list(a[k].values())) for k in keys]
        mk = [np.mean([a[k][o] for o in MK if o in a[k]]) for k in keys]
        axs[0, j].plot(xs, allm, ls, color=c, lw=2, label=n)
        axs[1, j].plot(xs, mk, ls, color=c, lw=2, label=n)
        S["auc"].setdefault(cam, {})[n] = {"all": {k: round(float(v), 3) for k, v in zip(keys, allm)},
                                           "marker": {k: round(float(v), 3) for k, v in zip(keys, mk)},
                                           "out_obj": a["out"]}
    for i, t in enumerate(("물체 8종 평균", "마커 3색 평균")):
        ax = axs[i, j]
        ax.axvspan(8.5, 12.5, color="orange", alpha=0.12); ax.axvspan(12.5, 16.5, color="green", alpha=0.08)
        ax.set_xticks(list(xs)); ax.set_xticklabels(["입력" if k == "0" else k if k == "out" else str(int(k) - 1) for k in keys], fontsize=8)
        ax.set_ylim(0.5 if i else 0.75, 1.01); ax.grid(alpha=0.3); ax.legend(fontsize=8)
        ax.set_title(f"{CAM_KO[cam]} · {t} — 이미지 토큰에서 물체 구분 AUC", fontsize=10)
fig.suptitle("층별 선형 프로브 (주황 8~11층 = 8층 모델만 학습, 초록 12~15층 = 모두 학습, out = action head 입력)", fontsize=11)
fig.tight_layout(); fig.savefig(f"{OUT}/cmp4_auc.png", dpi=105); plt.close(fig)

# ② attention 단어 특이성
Z = {n: np.load(f"{d}/lang_swap.npz") for n, d in M.items()}
R = {n: json.load(open(f"{d}/lang_swap.json")) for n, d in M.items()}
cases = list(R[NAMES[0]].keys())
fig, axs = plt.subplots(1, 2, figsize=(13, 4.2))
S["attn_spec"] = {}
for ax, cam in zip(axs, ("top", "wrist_right")):
    sl = slice(CI[cam] * G * G, (CI[cam] + 1) * G * G)
    for n in NAMES:
        allc = []
        for case in cases:
            objs = R[n][case]["objects"]
            maps = np.stack([Z[n][f"{case}/{o}/attn_obj"][:, sl] for o in objs])
            allc.append([1 - np.corrcoef(maps[:, l])[np.triu_indices(len(objs), 1)].mean() for l in range(maps.shape[1])])
        v = np.array(allc).mean(0)
        c, ls = STY[n]; ax.plot(range(len(v)), v, ls, color=c, lw=2, label=n)
        S["attn_spec"].setdefault(cam, {})[n] = [round(float(x), 3) for x in v]
    ax.axvspan(7.5, 11.5, color="orange", alpha=0.12); ax.axvspan(11.5, 15.5, color="green", alpha=0.08)
    ax.set_xlabel("언어 모델 층"); ax.set_ylabel("1 − 단어 간 attention 지도 상관")
    ax.set_title(f"{CAM_KO[cam]} — 물체 단어마다 다른 곳을 보나", fontsize=10); ax.grid(alpha=0.3); ax.legend(fontsize=8)
fig.tight_layout(); fig.savefig(f"{OUT}/cmp4_attn.png", dpi=105); plt.close(fig)

# ③ VLM 출력 변화 · 예측 동작
S["feat"], S["act"] = {}, {}
for case in cases:
    objs = R[NAMES[0]][case]["objects"]
    ref = "glue stick" if "glue stick" in objs else "black marker"
    for n in NAMES:
        z = Z[n]; st = np.array(R[n][case]["state"])
        for cam in ("top", "wrist_right"):
            sl = slice(CI[cam] * G * G, (CI[cam] + 1) * G * G)
            a = z[f"{case}/{ref}/feat"][z[f"{case}/{ref}/img_pos"][sl]]
            d = []
            for o in objs:
                if o != ref:
                    b = z[f"{case}/{o}/feat"][z[f"{case}/{o}/img_pos"][sl]]
                    d.append((1 - (a * b).sum(1) / np.linalg.norm(a, axis=1) / np.linalg.norm(b, axis=1)).mean())
            S["feat"].setdefault(case, {}).setdefault(n, {})[cam] = round(float(np.mean(d)), 4)
        S["act"].setdefault(case, {})[n] = {o: {"pan": round(float(z[f"{case}/{o}/act_right_arm"][:, -1, 0].mean() - st[6]), 2),
                                                "elbow": round(float(z[f"{case}/{o}/act_right_arm"][:, -1, 2].mean() - st[8]), 2),
                                                "pan_sd": round(float(z[f"{case}/{o}/act_right_arm"][:, -1, 0].std()), 2)}
                                            for o in objs}

fig, axs = plt.subplots(2, len(cases), figsize=(2.9 * len(cases), 6.2), squeeze=False)
COL = {"red marker": "tab:red", "blue marker": "tab:blue", "black marker": "k", "glue stick": "goldenrod"}
seen = set()
for j, case in enumerate(cases):
    for i, k in enumerate(("pan", "elbow")):
        ax = axs[i, j]
        for x, n in enumerate(NAMES):
            for o, v in S["act"][case][n].items():
                ax.scatter(x, v[k], color=COL[o], s=30, label=None if o in seen else o)
                seen.add(o)
        ax.set_xticks(range(4)); ax.set_xticklabels([n.replace("·", "\n") for n in NAMES], fontsize=7)
        ax.set_title(f"{case} · {k} 변화(°)", fontsize=9); ax.grid(alpha=0.3)
fig.legend(loc="upper right", fontsize=8, ncol=4)
fig.suptitle("같은 화면·상태·시드에서 물체 단어만 바꾼 0.5초 뒤 오른팔 예측 — 점이 넓게 퍼질수록 단어가 동작을 바꾼다", fontsize=11)
fig.tight_layout(); fig.savefig(f"{OUT}/cmp4_act.png", dpi=105); plt.close(fig)

json.dump(S, open(f"{OUT}/cmp4_summary.json", "w"), ensure_ascii=False, indent=1)
print("저장", OUT)
