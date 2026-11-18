"""비전 인코더를 **낮은 학습률로** 미세조정하기 위한 실행 래퍼 (컨테이너 안에서 실행).

GR00T 의 `--tune-visual` 은 사전학습된 SigLIP2(27층) 가중치에서 이어 학습하지만
(처음부터 재학습이 아니다), 옵티마이저가 파라미터 그룹 하나라서 비전 인코더도
action head 와 같은 학습률(1e-4)로 움직인다. 사전학습 ViT 에는 큰 값이라 300ep 같은
작은 데이터에서는 일반 시각 지식을 잃고 과적합하기 쉽다.

이 래퍼는 launch_finetune.py 를 그대로 실행하되 두 가지를 덧씌운다.
  ① VIS_LR_MULT  (기본 0.1) — 비전 인코더·mlp1 의 학습률 = 기본 학습률 × 이 값
  ② VIS_TOP_LAYERS (기본 0 = 전체) — 위쪽 N 층(+post_layernorm·head·mlp1)만 풀고
     embeddings·아래층은 고정. 아래층은 색·모서리 같은 일반 특징이라 그대로 두는 편이 안전하다.
  ③ LLM_TOP_LAYERS (기본 비움 = 설정값 4) — 언어 모델(16층) 중 위쪽 몇 층을 학습할지.
     launch_finetune 에 이 옵션이 없어(모델 설정 기본값 4 고정) 여기서 덮어쓴다.
①② 는 `--tune-visual` 이 있을 때만, ③ 은 값을 줬을 때만 바뀐다.

사용 (train_bi_cleanup.sh 가 TUNE_VISUAL=1 일 때 이 경로로 실행):
  VIS_LR_MULT=0.1 VIS_TOP_LAYERS=8 python3 /tmp/vision_lr_patch.py \
      gr00t/experiment/launch_finetune.py --tune-visual ...
"""
import os
import runpy
import sys

sys.path.insert(0, os.getcwd())

MULT = float(os.environ.get("VIS_LR_MULT", "0.1"))
TOP = int(os.environ.get("VIS_TOP_LAYERS", "0"))
LLM_TOP = os.environ.get("LLM_TOP_LAYERS", "")
VIS_KEYS = ("vision_model", "mlp1")

from gr00t.model.modules import eagle_backbone as eb  # noqa: E402
from gr00t.experiment import trainer as tr  # noqa: E402
from transformers import Trainer  # noqa: E402

_orig_set = eb.EagleBackbone.set_trainable_parameters


def _set_trainable(self, tune_llm, tune_visual, tune_top_llm_layers):
    if LLM_TOP:
        tune_top_llm_layers = int(LLM_TOP)
    _orig_set(self, tune_llm, tune_visual, tune_top_llm_layers)
    if LLM_TOP:
        n = sum(p.numel() for p in self.model.language_model.parameters() if p.requires_grad)
        print(f"[vision_lr_patch] 언어 모델 위쪽 {tune_top_llm_layers}/{len(self.model.language_model.model.layers)}층 학습 — 파라미터 {n/1e6:.1f}M")
    if not (tune_visual and TOP > 0):
        return
    vm = self.model.vision_model.vision_model
    layers = vm.encoder.layers
    vm.embeddings.requires_grad_(False)
    for layer in layers[: len(layers) - TOP]:
        layer.requires_grad_(False)
    n = sum(p.numel() for p in self.model.vision_model.parameters() if p.requires_grad)
    print(f"[vision_lr_patch] 비전 인코더 위쪽 {TOP}/{len(layers)}층만 학습 — 학습 파라미터 {n/1e6:.1f}M")


eb.EagleBackbone.set_trainable_parameters = _set_trainable

if LLM_TOP:
    # 모델 config 에도 넣어 체크포인트 config.json 에 실제 층 수가 남게 한다
    # (안 넣으면 4 로 저장돼 추론 때 8~11층이 fp32 가 아닌 bf16 으로 올라온다)
    from transformers import AutoModel  # noqa: E402
    _orig_fp = AutoModel.from_pretrained.__func__

    @classmethod
    def _from_pretrained(cls, *a, **kw):
        kw["tune_top_llm_layers"] = int(LLM_TOP)
        return _orig_fp(cls, *a, **kw)

    AutoModel.from_pretrained = _from_pretrained


def _create_optimizer(self):
    if self.optimizer is not None:
        return self.optimizer
    opt_cls, kw = Trainer.get_optimizer_cls_and_kwargs(self.args, self.model)
    decay = set(self.get_decay_parameter_names(self.model))
    base = self.args.learning_rate
    groups = {}
    for n, p in self.model.named_parameters():
        if not p.requires_grad:
            continue
        vis = any(k in n for k in VIS_KEYS)
        key = (self.args.weight_decay if n in decay else 0.0, base * MULT if vis else base, vis)
        groups.setdefault(key, []).append(p)
    params = [{"params": v, "weight_decay": wd, "lr": lr} for (wd, lr, _), v in groups.items()]
    for (wd, lr, vis), v in groups.items():
        print(f"[vision_lr_patch] {'비전' if vis else '그 외'} lr={lr:.1e} wd={wd:g} "
              f"파라미터 {sum(p.numel() for p in v)/1e6:.1f}M")
    self.optimizer = opt_cls(params, **kw)
    return self.optimizer


if "--tune-visual" in sys.argv:
    tr.Gr00tTrainer.create_optimizer = _create_optimizer
    print(f"[vision_lr_patch] 비전 학습률 × {MULT} · 위쪽 층 {TOP or '전체'}")

script = sys.argv[1]
sys.argv = sys.argv[1:]
runpy.run_path(script, run_name="__main__")
