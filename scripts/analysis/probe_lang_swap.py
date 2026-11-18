"""지시문의 물체 단어만 바꿨을 때 VLM 출력과 예측 동작이 어떻게 바뀌는지 (probe_vision_viz.py 후속).

GR00T N1.6 은 VLM 이 문장을 만들지 않는다 — 지시문(앞)과 카메라 3대 이미지(뒤)를 언어 모델 16층에
한 번 통과시킨 토큰별 벡터를 action head(DiT)가 그대로 참조한다. 지시문이 이미지보다 **앞**이고
언어 모델은 앞 토큰만 볼 수 있으므로, 지시문의 정보는 이미지 토큰이 지시문 단어를 참조하는 경로로만
이미지 쪽 표현에 섞인다. 그래서 두 가지를 잰다.

  ① attention: 카메라 3대 이미지 토큰(각 9×9, 한 칸 ≈ 원본 68px)이 지시문의 물체 단어를 얼마나 참조하나
  ② 같은 화면·같은 로봇 상태에서 물체 단어만 바꿔
       - VLM 출력(action head 입력)이 이미지 토큰 위치마다 얼마나 달라지나 (1 - cos)
       - action head 가 예측한 오른팔 관절 궤적이 물체마다 갈라지나 (같은 노이즈 시드로 짝지어 비교)

입력: 평가 시행 폴더(video.mp4 = top|wrist_left|wrist_right 가로, chunks.csv 의 로봇 상태, actions.csv 의 프레임 번호)
출력: OUT/lang_swap.npz · OUT/lang_swap.json  (그림은 probe_lang_swap_viz.py)
  CASES="이름:시행폴더:청크:목적지색:물체1|물체2|...,..."
"""
import csv, json, os, sys
import av, numpy as np, torch
from gr00t.data.embodiment_tags import EmbodimentTag
from gr00t.policy.gr00t_policy import Gr00tPolicy

CK, OUT = sys.argv[1:3]
SEEDS = int(os.environ.get("SEEDS", "8"))
os.makedirs(OUT, exist_ok=True)

policy = Gr00tPolicy(embodiment_tag=EmbodimentTag.NEW_EMBODIMENT, model_path=CK, device="cuda")
MC = policy.modality_configs
model = policy.model
bb = model.backbone
lm = bb.model.language_model
IMG_TOK = bb.model.config.image_token_index

cap = {}
bb.register_forward_hook(lambda m, a, o: cap.update(
    feat=o["backbone_features"][0].float().cpu(), ids=a[0]["input_ids"][0].cpu()))
attn = {}
for li, layer in enumerate(lm.model.layers):
    layer.self_attn.register_forward_hook(
        lambda m, a, o, li=li: attn.__setitem__(li, o[1][0].float().mean(0).cpu()) if o[1] is not None else None)


def load_case(trial, chunk):
    rows = list(csv.DictReader(open(f"{trial}/chunks.csv")))
    st = np.array([float(v) for k, v in rows[chunk].items() if k.startswith("state_")], np.float32)
    acts = list(csv.DictReader(open(f"{trial}/actions.csv")))
    step = next(int(x["i"]) for x in acts if int(x["chunk"]) == chunk)
    fi = step // 3  # 영상은 3스텝마다 한 프레임
    with av.open(f"{trial}/video.mp4") as c:
        for n, f in enumerate(c.decode(video=0)):
            if n == fi:
                im = f.to_ndarray(format="rgb24")
                break
    cams = {k: im[:, 640 * i:640 * (i + 1)] for i, k in enumerate(["top", "wrist_left", "wrist_right"])}
    return cams, st, fi


def run(cams, st, lang, seed, want_attn=False):
    obs = {"video": {k: cams[k][None, None].copy() for k in MC["video"].modality_keys},
           "state": {}, "language": {lk: [[lang]] for lk in MC["language"].modality_keys}}
    sl = {"left_arm": (0, 5), "left_gripper": (5, 6), "right_arm": (6, 11), "right_gripper": (11, 12)}
    for sk in MC["state"].modality_keys:
        lo, hi = sl[sk]
        obs["state"][sk] = st[lo:hi][None, None]
    lm.config._attn_implementation = "eager" if want_attn else "flash_attention_2"
    attn.clear()
    torch.manual_seed(seed)
    with torch.no_grad():
        act = policy.get_action(obs)
    act = act[0] if isinstance(act, tuple) else act
    return {k: np.asarray(v)[0] for k, v in act.items()}


tok = None
try:
    tok = policy.processor.processor.tokenizer
except AttributeError:
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(
        "/Isaac-GR00T/gr00t/model/modules/nvidia/Eagle-Block2A-2B-v2", trust_remote_code=True)

res, arrays = {}, {}
for item in os.environ["CASES"].split(","):
    name, trial, chunk, dest, objs = item.split(":")
    cams, st, fi = load_case(trial, int(chunk))
    for k, v in cams.items():
        arrays[f"{name}/{k}"] = v
    objs = objs.split("|")
    R = {"frame": fi, "chunk": int(chunk), "state": st.tolist(), "objects": objs, "per": {}}
    for o in objs:
        lang = f"Put the {o} into the {dest} bin"
        # ① attention + VLM 출력 (결정적 — 시드 무관)
        run(cams, st, lang, 0, want_attn=True)
        ids = cap["ids"].numpy()
        toks = tok.convert_ids_to_tokens(ids.tolist())
        img_pos = np.where(ids == IMG_TOK)[0]
        n_img = len(img_pos) // 3
        top_pos = img_pos[:n_img]
        # 물체 단어 위치: "the" 다음 ~ "into" 앞
        low = [t.replace("Ġ", "").replace("▁", "").lower() for t in toks]
        i_put = next(i for i in range(len(low)) if low[i] == "put")
        i_the = next(i for i in range(i_put, len(low)) if low[i] == "the")
        i_into = next(i for i in range(i_the, len(low)) if low[i] == "into")
        obj_pos = np.arange(i_the + 1, i_into)
        i_bin = next(i for i in range(i_into, len(low)) if low[i] == "bin")
        dest_pos = np.arange(i_into + 2, i_bin)
        A = torch.stack([attn[l] for l in sorted(attn)])           # L×S×S (헤드 평균)
        a_obj = A[:, img_pos][:, :, obj_pos].sum(-1).numpy()        # L×243 (카메라 3대 × 81)
        a_dest = A[:, img_pos][:, :, dest_pos].sum(-1).numpy()
        arrays[f"{name}/{o}/attn_obj"] = a_obj
        arrays[f"{name}/{o}/attn_dest"] = a_dest
        arrays[f"{name}/{o}/feat"] = cap["feat"].numpy()
        arrays[f"{name}/{o}/img_pos"] = img_pos
        # ② 동작 (같은 시드끼리 물체만 다름)
        acts = [run(cams, st, lang, s) for s in range(SEEDS)]
        for k in acts[0]:
            arrays[f"{name}/{o}/act_{k}"] = np.stack([a[k] for a in acts])
        R["per"][o] = {"lang": lang, "obj_tokens": [toks[i] for i in obj_pos],
                       "dest_tokens": [toks[i] for i in dest_pos], "n_img_per_cam": int(n_img),
                       "seq_len": int(len(ids)), "img_start": int(img_pos[0])}
        print(name, o, R["per"][o]["obj_tokens"], "이미지 토큰/카메라", n_img, flush=True)
    res[name] = R

np.savez_compressed(f"{OUT}/lang_swap.npz", **arrays)
json.dump(res, open(f"{OUT}/lang_swap.json", "w"), ensure_ascii=False, indent=1)
print("저장", OUT)
