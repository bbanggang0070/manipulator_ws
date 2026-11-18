"""시행 초반~갈림 구간에서 물체 단어만 바꿨을 때 — 언제부터 예측 동작이 단어를 따라 갈라지나.

probe_lang_swap.py 를 같은 시행의 여러 청크(T13_c0, T13_c3, ...)에 돌린 결과를 시간축으로 편다.
  · 오른팔 shoulder_pan 예측(16스텝 끝, 현재 상태 대비) — glue 단어 vs black 단어, 시드 8개 짝
    (13~16번은 같은 배치: glue 를 집은 14·16번 파지 pan +5~8, black 을 집은 13·15번 −2~−3 → pan + 쪽이 glue 방향)
  · 같은 비교에서 VLM 출력 변화(glue↔black, 1 − cos) — 상단·오른손목 카메라
  · 실제로 보낸 pan 궤적(actions.csv)
출력: OUT/early_swap.png · OUT/early_swap.json
사용: python3 probe_early_viz.py D8 D4 IV FONT OUT  (IV = 평가 영상 상위 폴더 bi300llm8_A)
"""
import csv, json, os, re, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

D8, D4, IV, FONT, OUT = sys.argv[1:6]
os.makedirs(OUT, exist_ok=True)
font_manager.fontManager.addfont(FONT)
plt.rcParams["font.family"] = font_manager.FontProperties(fname=FONT).get_name()
G = 81
CI = {"top": 0, "wrist_right": 2}
RES = {"8": D8, "4": D4}
Z = {n: np.load(f"{d}/lang_swap.npz") for n, d in RES.items()}
R = {n: json.load(open(f"{d}/lang_swap.json")) for n, d in RES.items()}
TR = {"13": "13번 (black 집음)", "15": "15번 (black 집음)", "14": "14번 (glue 집음, 성공)"}


def feat_d(z, case, a, b, cam):
    sl = slice(CI[cam] * G, (CI[cam] + 1) * G)
    A = z[f"{case}/{a}/feat"][z[f"{case}/{a}/img_pos"][sl]]
    B = z[f"{case}/{b}/feat"][z[f"{case}/{b}/img_pos"][sl]]
    return float((1 - (A * B).sum(1) / np.linalg.norm(A, axis=1) / np.linalg.norm(B, axis=1)).mean())


out = {}
fig, axs = plt.subplots(3, 3, figsize=(15, 10), sharex=True)
for j, t in enumerate(("13", "15", "14")):
    acts = list(csv.DictReader(open(f"{IV}/trial{t}_t01/actions.csv")))
    for n, ls in (("8", "-"), ("4", "--")):
        cases = sorted([c for c in R[n] if c.startswith(f"T{t}_")], key=lambda c: int(c.split("_c")[1]))
        xs, dp, dsd, words, ft, fw = [], [], [], {}, [], []
        for c in cases:
            ch = int(c.split("_c")[1]); st = np.array(R[n][c]["state"])
            xs.append(ch)
            for o in R[n][c]["objects"]:
                a = Z[n][f"{c}/{o}/act_right_arm"][:, -1, 0] - st[6]   # 시드별 pan 변화
                words.setdefault(o, []).append(a.mean())
            g = Z[n][f"{c}/glue stick/act_right_arm"][:, -1, 0]; b = Z[n][f"{c}/black marker/act_right_arm"][:, -1, 0]
            dp.append((g - b).mean()); dsd.append((g - b).std())
            ft.append(feat_d(Z[n], c, "glue stick", "black marker", "top"))
            fw.append(feat_d(Z[n], c, "glue stick", "black marker", "wrist_right"))
        out.setdefault(t, {})[n] = {"chunk": xs, "pan_glue_minus_black": [round(float(v), 2) for v in dp],
                                    "pan_sd": [round(float(v), 2) for v in dsd],
                                    "pan_by_word": {o: [round(float(v), 2) for v in vv] for o, vv in words.items()},
                                    "feat_top": [round(v, 4) for v in ft], "feat_wrist": [round(v, 4) for v in fw]}
        ax = axs[0, j]
        ax.errorbar(xs, dp, yerr=dsd, fmt=ls + "o", color="k" if n == "8" else "gray", ms=4, capsize=2,
                    label=f"{n}층 모델")
        ax2 = axs[1, j]
        ax2.plot(xs, ft, ls + "o", color="tab:orange", ms=3, label=f"{n}층 · 상단")
        ax2.plot(xs, fw, ls + "s", color="tab:purple", ms=3, label=f"{n}층 · 오른손목")
    ax = axs[0, j]
    ax.axhline(0, color="k", lw=0.6)
    ax.set_title(f"{TR[t]} — 예측 pan 차이 (glue 단어 − black 단어)", fontsize=10)
    ax.set_ylabel("0.5초 뒤 pan 차이 (°)\n+ = glue 쪽")
    ax.grid(alpha=0.3); ax.legend(fontsize=8)
    axs[1, j].set_ylabel("VLM 출력 변화 glue↔black\n(1 − cos, 카메라 평균)"); axs[1, j].grid(alpha=0.3)
    axs[1, j].legend(fontsize=7)
    # 실제 궤적
    ch = np.array([int(x["chunk"]) for x in acts]); pan = np.array([float(x["sent_right_shoulder_pan.pos"]) for x in acts])
    el = np.array([float(x["sent_right_elbow_flex.pos"]) for x in acts])
    stp = np.array([int(x["i"]) for x in acts]) / 8.0   # 청크 ≈ 8스텝
    m = (ch >= 0) & (stp <= 31)
    axs[2, j].plot(stp[m], pan[m], color="tab:blue", label="pan (실제로 보낸 값)")
    axs[2, j].set_ylabel("실제 pan (°)"); axs[2, j].grid(alpha=0.3); axs[2, j].set_xlabel("청크 (≈ 8스텝 = 0.27초)")
    a2 = axs[2, j].twinx(); a2.plot(stp[m], el[m], color="tab:red", alpha=0.5)
    a2.set_ylabel("elbow (°, 빨강)", color="tab:red")
    for a in axs[:, j]:
        a.axvspan(12.5, 30, color="purple", alpha=0.04)
fig.suptitle("같은 화면·상태·시드에서 물체 단어만 바꿨을 때 — 언제부터 단어가 팔 방향을 바꾸나 (보라 배경: 오른손목에 물체가 보이는 구간)", fontsize=11)
fig.tight_layout(); fig.savefig(f"{OUT}/early_swap.png", dpi=105)
json.dump(out, open(f"{OUT}/early_swap.json", "w"), ensure_ascii=False, indent=1)
print("저장", OUT)
