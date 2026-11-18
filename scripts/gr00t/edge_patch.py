"""입력 해상도(`shortest_image_edge`)를 **실제로** 바꾸기 위한 컨테이너 내부 패치.

왜 패치가 필요한가 — 이 값은 네 겹으로 막혀 있다 (2026-09-30 실측):

  ① `launch_finetune.py` CLI에 없다
  ② `FinetuneConfig`에 없어서 `config.model`로 전달되지 않는다
  ③ 데이터클래스 기본값(256)을 바꿔도 **체크포인트 config.json이 256을 실어 와 덮어쓴다**
  ④ `setup.py`가 `AutoProcessor.from_pretrained(..., shortest_image_edge=...)`로 넘기지만
     `from_pretrained`의 화이트리스트에 그 키가 없어 **조용히 버려진다**:

         override_keys = ["random_rotation_angle", "color_jitter_params",
                          "use_relative_action", "extra_augmentation_config"]

  ①③④를 차례로 고치는 동안 **로그는 640이라고 찍으면서 실제로는 256으로 돌았다.**
  판정기 필터·자산 배포 누락과 같은 종류의 조용한 실패다. 그래서 이 스크립트는
  앵커를 못 찾으면 **반드시 죽고**, `--verify`로 실제 출력 크기를 찍어 확인한다.

패치 지점이 한 곳인 이유:
  `GR00TN1d6Processor.__init__`은 전달받은 **지역 변수** `shortest_image_edge`를
  (a) `self.shortest_image_edge`에 넣고 (b) 트랜스폼 빌더에 넘긴다.
  그래서 `__init__` 첫 줄에서 지역 변수를 다시 묶으면 두 경로가 한 번에 잡히고,
  런처(`launch_finetune.py` / `launch_cotrain.py`)가 무엇이든 상관없다.

체크포인트 일관성 (448 스모크로 실측 확인, 2026-09-30):
  `save_pretrained`가 `"shortest_image_edge": self.shortest_image_edge`를
  `processor_config.json`에 쓴다. 448로 학습한 체크포인트는 448을 싣고 나가고,
  `from_pretrained`가 그걸 읽으므로 **서빙 쪽에는 이 패치가 필요 없다.**
  학습/추론 해상도 불일치는 구조적으로 생기지 않는다.

  ⚠️ 단, 같은 체크포인트의 **`config.json`(모델 설정)에는 256이 남는다.**
     해상도를 실제로 정하는 것은 processor 쪽이므로 동작에는 영향이 없지만,
     나중에 `config.json`만 보고 "256으로 학습했다"고 오독하기 쉽다.
     학습 해상도는 **`processor_config.json`을 봐야 한다.**
       processor_config.json : 448   ← 실제로 쓰인 값
       config.json           : 256   ← 무시해도 되는 잔재

실측 비용 (RTX 5090 32GB · 유효 배치 64 · worker 2 · 12 step):

  edge  이미지토큰(2캠)  step시간   배수   peak VRAM  peak RAM   12k step
  256        166         2.75 s   1.00×    22.7 GB    17.9 GB     9.2 h   ← 기본값
  448        512         3.50 s   1.27×    23.2 GB    23.3 GB    11.7 h
  640       1044         6.00 s   2.18×    24.1 GB    30.7 GB    20.0 h

  ⚠️ 병목은 GPU가 아니라 **호스트 RAM**이다. worker 8개로 640을 돌리면
     `DataLoader worker is killed by signal: Killed`로 죽는다(OOM killer).
     학습 스크립트가 EDGE>256이면 worker를 2로 내린다.

사용 (컨테이너 안에서, 학습 시작 전):
  GR00T_SHORTEST_EDGE=448 python3 /tmp/edge_patch.py --verify
"""
import argparse
import os
import sys

TARGET = "/Isaac-GR00T/gr00t/model/gr00t_n1d6/processing_gr00t_n1d6.py"

# __init__의 첫 실행문. 여기 앞에 끼워 넣어야 지역 변수가 쓰이기 전에 바뀐다.
ANCHOR = "        self.modality_configs = parse_modality_configs(modality_configs)"

MARK = "# [edge_patch]"

INJECT = f"""{MARK} 해상도 오버라이드 — 지역 변수를 쓰기 전에 다시 묶는다.
        #   self.shortest_image_edge 와 트랜스폼 빌더가 **둘 다** 이 지역 변수를 쓴다.
        #   체크포인트에서 온 값(256)보다 환경변수가 우선한다.
        _edge = os.environ.get("GR00T_SHORTEST_EDGE")
        if _edge:
            shortest_image_edge = int(_edge)
            image_target_size = None   # 구 경로가 살아 있으면 해상도를 되돌린다
            image_crop_size = None
            print(f"[edge_patch] shortest_image_edge = {{shortest_image_edge}}", flush=True)
"""


def patch(path=TARGET):
    if not os.path.exists(path):
        sys.exit(f"❌ 대상 없음: {path} — 컨테이너 안에서 실행하는 게 맞나요?")
    s = open(path).read()

    if MARK in s:
        print("  이미 패치됨 — 건너뜀")
        return False

    n = s.count(ANCHOR)
    if n != 1:
        sys.exit(f"❌ 앵커를 {n}번 찾았다(1이어야 함). GR00T 버전이 바뀌었다.\n"
                 f"   앵커: {ANCHOR.strip()}\n"
                 f"   {path} 의 __init__ 첫 줄을 보고 ANCHOR를 갱신할 것.")

    if "import os" not in s.split("class ")[0]:
        sys.exit("❌ 모듈에 `import os`가 없다 — INJECT가 NameError를 낸다. 확인 필요.")

    open(path, "w").write(s.replace(ANCHOR, INJECT + ANCHOR))
    print(f"  ✅ 패치 완료: {path}")
    return True


def verify(ckpt="nvidia/GR00T-N1.6-3B"):
    """**실제 production 경로**로 프로세서를 만들어 해상도를 확인한다.

    트랜스폼 빌더를 직접 부르는 것으로는 부족하다 — 조용히 되돌아간 지점이
    `from_pretrained`가 체크포인트 값(256)을 쓰는 곳이었기 때문이다.
    그래서 체크포인트에서 진짜로 불러와 `self.shortest_image_edge`를 본다.
    """
    import numpy as np

    sys.path.insert(0, "/Isaac-GR00T")
    from gr00t.model.gr00t_n1d6.processing_gr00t_n1d6 import Gr00tN1d6Processor

    want = os.environ.get("GR00T_SHORTEST_EDGE")
    if not want:
        print("  ⏸ GR00T_SHORTEST_EDGE 미설정 — 기본값(256)으로 돈다")
        return
    want = int(want)

    p = Gr00tN1d6Processor.from_pretrained(ckpt)
    got = p.shortest_image_edge
    print(f"  체크포인트 {ckpt} 에서 로드 → shortest_image_edge = {got}")
    if got != want:
        sys.exit(f"❌ {want}를 요청했는데 프로세서는 {got}이다 — 패치가 안 먹었다.\n"
                 f"   (체크포인트 processor_config.json의 값이 그대로 쓰인 것)")

    # 로그를 믿지 않는다. 실제 이미지를 통과시켜 출력 크기를 잰다.
    src = np.zeros((480, 640, 3), dtype=np.uint8)
    out = p.eval_image_transform(image=src)["image"]
    h, w = out.shape[:2]
    print(f"  트랜스폼 실제 출력: {w}x{h}")
    if want not in (w, h):
        sys.exit(f"❌ 출력이 {w}x{h}다 — 트랜스폼까지 전달되지 않았다.")

    # 토큰 수까지 센다. 학습 비용은 여기에 비례한다.
    try:
        from PIL import Image
        from transformers import AutoProcessor
        P = "/Isaac-GR00T/gr00t/model/modules/nvidia/Eagle-Block2A-2B-v2"
        proc = AutoProcessor.from_pretrained(P, trust_remote_code=True)
        pil = Image.fromarray(out)
        conv = [{"role": "user", "content": [{"type": "text", "text": "Pick up the red block"},
                                             {"type": "image", "image": pil},
                                             {"type": "image", "image": pil}]}]
        text = proc.apply_chat_template(conv, tokenize=False, add_generation_prompt=False)
        b = proc(text=[text], images=[pil, pil], return_tensors="pt")
        ntok = int((b["input_ids"] == 151669).sum())
        print(f"  이미지 토큰(카메라 2대): {ntok}  ·  전체 시퀀스 {b['input_ids'].shape[1]}")
        print("  기준: 256 -> 166토큰 · 448 -> 512토큰 · 640 -> 1044토큰")
    except Exception as e:  # 토큰 계수는 부가 정보다. 실패해도 패치 검증은 끝났다.
        print(f"  (토큰 계수 생략: {e})")
    print("  ✅ 검증 통과")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true", help="패치 후 실제 출력 크기를 확인한다")
    ap.add_argument("--path", default=TARGET)
    ap.add_argument("--ckpt", default="nvidia/GR00T-N1.6-3B",
                    help="검증에 쓸 체크포인트 — 실제 학습 출발점과 같게 주는 게 좋다")
    a = ap.parse_args()
    patch(a.path)
    if a.verify:
        verify(a.ckpt)
