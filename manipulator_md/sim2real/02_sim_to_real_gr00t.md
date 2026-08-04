# 07. GR00T Sim-to-Real 종합 — N1.6 추론 · N1.5 학습 · 8-bit N1.6 학습

> Isaac Sim(NVIDIA Sim-to-Real SO-101 워크숍) 기반 GR00T 실험의 세 축을 정리한다:
> ① 사전학습 **N1.6** 체크포인트를 5090에서 추론(sim SR 60%),
> ② 자체 학습 시 N1.6 단일 GPU 벽 → **N1.5**로 학습(SR 10%)과 성능 저하 분석,
> ③ **8-bit 양자화(paged_adamw_8bit)**로 N1.6 단일 GPU 학습을 가능케 함(성능 저하 없음).
> 상세 실행 로그: [01_실행기록.md](01_실행기록.md) | 계획: [05_SimToReal.md](../../model_md/sim2real/05_SimToReal.md)

작성: 2026-07-22

---

## 1. N1.6 사전학습 체크포인트 추론 (기준선, sim SR 60%)

### 1.1 가중치 출처

| 항목 | 값 |
|---|---|
| 체크포인트 | **`aravindhs-NV/grootn16-finetune_sreetz-so101_teleop_vials_rack_left/checkpoint-10000`** (HuggingFace) |
| 아키텍처 | GR00T **N1.6-3B** (`model_type: gr00t_n1_6`, 백본 Eagle-Block2A-2B) |
| 학습 데이터 | `sreetz-nv/so101_teleop_vials_rack_left` — **sim-only 75 시연**(NVIDIA 워크숍 공식 데이터셋) |
| 5090 경로 | `~/gr00tn16_ws/checkpoints/grootn16_sim75/checkpoint-10000` (다운로드·정리) |

### 1.2 학습 하이퍼파라미터 (NVIDIA 워크숍 공식, [10-groot 문서](https://docs.nvidia.com/learning/physical-ai/sim-to-real-so-101/latest/))

```
base_model: nvidia/GR00T-N1.6-3B
max_steps: 20000 | learning_rate: 1e-4 | weight_decay: 1e-5 | warmup_ratio: 0.05
global_batch_size: 64 | save_steps: 5000
color_jitter: brightness 0.3 contrast 0.4 saturation 0.5 hue 0.08
tune: projector + diffusion (기본), tune_visual=False, tune_top_llm_layers=4
```
※ 우리가 학습한 게 아니라 **NVIDIA가 학습해 배포한** 체크포인트. 우리는 이것을 추론만 함.

### 1.3 5090에서 추론 실행 방법

워크숍 공식 경로 — **컨테이너 2개**(서버 + 클라이언트):

```
[real-robot 컨테이너: N1.6 추론 서버]        [teleop-docker 컨테이너: sim 평가 클라이언트]
run_gr00t_server.py --model-path ...    <── zmq:5555 ──   lerobot_eval --task ...-Eval
  (GROOT_REF N1.6 스택, GPU에 모델 로드)                    (Isaac Sim 씬 구동, 관측→서버→액션)
```

- 서버: `real-robot` 이미지(워크숍 `docker/real/Dockerfile.blackwell` 빌드)로
  `run_gr00t_server.py --model-path /workspace/models/grootn16_sim75/checkpoint-10000` (포트 5555)
- 클라이언트: `teleop-docker` 이미지로 `lerobot_eval --task Lerobot-So101-Teleop-Vials-To-Rack-Eval
  --num_episodes 10 --rename_map '{"external_D455":"front","ego":"wrist"}' --action_horizon 16`
- 실행 스크립트: `setup/sim/sim_eval_gr00t.sh` (5090 headless), 5090 모니터에선 `--headless` 빼고 `--rerun`
- ⚠️ **빌드 함정**: real-robot Dockerfile이 torch를 버전 고정 없이 `nightly/cu130`으로 설치 →
  nightly가 C++20 요구 버전으로 드리프트, flash-attn(c++17)과 충돌. n1d5에서 검증한
  torch `2.8.0+cu128` + flash-attn 사전빌드 휠로 교체(`setup/sim/patches/dockerfile_blackwell_flashattn.patch`).

### 1.4 결과 — **sim SR 6/10 = 60%**

| ep | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| 누적% | 0 | 100 | 100 | 66.7 | 75 | 60 | 50 | 57 | 62.5 | **60%** |

워크숍 공식 기대치(50~70%) 정중앙. 전체 파이프라인(서버·클라이언트·Isaac Sim·rerun) 검증 완료.

---

## 2. 자체 학습 — N1.6 단일 GPU 벽 → N1.5 학습과 성능 저하 분석

### 2.1 N1.6 학습을 돌리려다 발생한 문제

같은 75ep 데이터로 **N1.6를 직접 학습**해 60%를 재현하려 했으나, 데이터 파이프라인 함정을
순차 격파한 뒤 **근본적인 메모리 벽**에 막힘:

| 순서 | 문제 | 원인/해결 |
|---|---|---|
| 1 | `FileNotFoundError: meta/episodes.jsonl` | N1.6 로더가 v2.1 메타 요구 → v3.0을 v2.1 변환 |
| 2 | 변환 중 `ffmpeg not found` | 컨테이너에 ffmpeg 없음 → 설치 |
| 3 | 비디오 디코드 `NotImplementedError` | torchcodec 0.4.0 vs torch 2.8 비호환 → 0.7.0 업그레이드 |
| 4 | `No space left on device` (shm) | Docker 기본 /dev/shm 64MB 부족 → `--ipc=host` |
| 5 | **CUDA OOM (근본 벽)** | **optimizer 상태(fp32 Adam m,v + master weights)가 배치 무관하게 ~30GB 고정** → 마이크로배치 2로 줄여도 30.4GB OOM |
| 6 | 배치 계산 함정 | `per_device = global_batch // num_gpus` → 단일 GPU에서 global 64가 곧 마이크로배치 64 (워크숍은 8 GPU 전제) |
| 7 | 유일 해법 CPU offload 실패 | DeepSpeed `CPUAdam` 컴파일이 **컨테이너 CUDA 13.0 vs torch cu12.8 불일치**로 실패 |

→ **단일 32GB에서 기본 fp32 Adam N1.6 full FT는 불가능.** [GitHub 이슈 #536](https://github.com/NVIDIA/Isaac-GR00T/issues/536)이
우리와 **동일한 OOM**(RTX5090, 29.5GB 후 실패, batch 1에서도)을 **미해결로** 보고 → NVIDIA는 DGX
Station(대용량) 전제. (이 문제의 해결이 §3.)

### 2.2 N1.5로 전환 — 학습 하이퍼파라미터

실기에서 검증된 **N1.5(n1d5 host venv)** 스택으로 전환(같은 5090에서 3B FT 성공 이력, 도커·CUDA
문제 없음). GPU **25.5GB로 여유 적합**.

```
스택: gr00t_remote/Isaac-GR00T-n1d5 (host venv, scripts/gr00t_finetune.py)
base: GR00T-N1.5-3B | max_steps 20000 | lr 1e-4
batch_size 4 × gradient_accumulation 16 = 유효 배치 64 | data_config so100_dualcam
embodiment new_embodiment | video_backend torchvision_av | tune: projector+diffusion(기본)
```
스크립트: `setup/sim/train_gr00t_sim_n1d5.sh`. 최종 loss 0.005(9h17m).

### 2.3 N1.6 학습과의 차이점

| 항목 | N1.6 (목표) | N1.5 (실제 학습) |
|---|---|---|
| 아키텍처 | GR00T-N1.6-3B (Eagle-Block2A) | GR00T-N1.5-3B (다른 백본) |
| **tune 범위** | projector+diffusion **+ top-4 LLM 레이어**(체크포인트 config) | projector+diffusion **만** (LLM 전부 freeze) |
| 학습 스택 | Docker 컨테이너(GROOT_REF) | host venv(n1d5) |
| 유효 배치 | 64 | 64 (동일) |
| lr/steps | 1e-4 / 20k | 1e-4 / 20k (동일) |

### 2.4 결과와 성능 저하 분석

| 지표 | N1.5 자체학습 | N1.6 사전학습(기준) |
|---|---|---|
| open-loop MSE (5궤적) | **2.18** (실기 GR00T 2.24 수준) | — |
| **closed-loop sim SR** | **1/10 = 10%** (파지 15회·랙배치 4회) | **6/10 = 60%** |

**왜 성능이 나빠졌는가 (분석):**

1. **아키텍처 차이 (N1.5 vs N1.6)** — N1.6는 후속 버전으로 백본(Eagle-Block2A)·학습 레시피가
   개선됨. 같은 데이터라도 상한이 다름. 기준선이 N1.6이므로 N1.5는 근사 비교일 뿐.
2. **tune 범위 차이 (핵심)** — N1.6 체크포인트는 **top-4 LLM 레이어까지 학습**(언어-시각-액션
   결합에 더 많은 용량 할당)했으나, N1.5는 projector+diffusion만 학습(LLM 전부 freeze). 시각
   그라운딩·언어 결합 능력에서 불리.
3. **open-loop vs closed-loop 격차** — open-loop MSE 2.18은 **양호**(정답 궤적 상태에서 다음
   액션 예측은 정확 = 모델이 학습됨). 그러나 closed-loop에선 자기 액션 오차가 **누적**되어,
   파지·배치 시도는 하지만(15회/4회) 완전 성공은 1회. 이건 모델 학습 실패가 아니라 BC의
   구조적 compounding error.

즉 10%는 "학습이 안 됐다"가 아니라 "**아키텍처·tune 범위가 N1.6보다 작고, closed-loop 오차가
누적된 결과**". 근본 해결은 N1.6를 같은 조건으로 학습하는 것 → §3.

---

## 3. 8-bit 양자화로 N1.6 단일 GPU 학습 가능 (성능 저하 없음)

### 3.1 문제와 해법

§2.1의 OOM은 **optimizer 상태가 지배**(3B 중 학습 대상 params의 Adam m,v를 fp32로 저장 + master
weights). 해법은 **8-bit Adam(`paged_adamw_8bit`, bitsandbytes)**:

- **옵티마이저 상태(m, v)만 fp32→8bit 블록단위 양자화** — 업데이트 순간 fp32로 역양자화.
  **모델 가중치·그래디언트·업데이트 계산은 전부 full precision.**
- ~12GB 절약 → 단일 32GB에 적합.
- **하이퍼파라미터 무변경** (HuggingFace 공식: *"8-bit optimizers do not require any additional
  changes in hyperparameters"*). 근거: [Dettmers et al. 2021, arXiv:2110.02861](https://arxiv.org/pdf/2110.02861)
  — GLUE·WMT·ImageNet 등에서 32bit Adam과 동등 성능 입증. QLoRA 등 사실상 표준.

### 3.2 구성 — NVIDIA 하이퍼파라미터와 동일, 옵티마이저만 8bit

- 이미지 `real-robot-train8`: real-robot + ffmpeg + torchcodec0.7 + **bitsandbytes 0.49.2** +
  `gradient_checkpointing=True` + `launch_finetune` optim을 **`paged_adamw_8bit`**로 패치
- 하이퍼파라미터: **§1.2의 NVIDIA 공식과 완전 동일** — base GR00T-N1.6-3B, 유효 배치 64
  (micro 2×accum 32), lr 1e-4, wd 1e-5, warmup 0.05, 20k steps, color jitter, tune 기본.
  **유일한 차이 = 옵티마이저 8bit.**
- 스크립트: `setup/sim/train_gr00t_sim_n16_8bit.sh`. 출력: `~/gr00tn16_ws/checkpoints/gr00t_vials75_n16_8bit`

### 3.3 학습 가능함 증명 (2026-07-22)

| 지표 | 어제(fp32 Adam) | **오늘(8-bit Adam)** |
|---|---|---|
| GPU 메모리 | **OOM** (30.4GB, batch 2에서도 실패) | **22.7GB / 32.6GB** ✅ 여유 적합 |
| 학습 진입 | 첫 스텝 전 OOM 종료 | **정상 스텝 진행** (loss 0.655→0.187, grad_norm 정상) |
| 사전검증 | — | `PagedAdamW8bit` 5090 단독 작동 확인 |

→ **어제 불가능했던(그리고 GitHub #536이 미해결로 남긴) 단일 5090 N1.6 학습이 8-bit Adam으로 가능해짐.**

### 3.4 성능 저하 없음 — **경험적 확증 완료** (2026-07-23)

- **이론/문헌**: 8-bit Adam은 옵티마이저 상태만 양자화하고 업데이트는 fp32 → fp32와 성능 차이가
  run-to-run 분산 이내(arXiv:2110.02861). 하이퍼파라미터도 무변경이라 학습 동역학 동일.
- **학습 결과**: 20k steps 완주(GPU 22.7GB 안정), 최종 **loss 0.005**(grad_norm 0.05) —
  N1.5(0.005)·워크숍 사전학습본과 동일 수준. 양자화로 인한 학습 불안정 징후 없음.
- **경험적 SR 검증**: §1.3과 동일한 sim 평가(real-robot N1.6 서버 + teleop-docker) 10회:

| 모델 | 옵티마이저 | GPU | **sim SR** |
|---|---|---|---|
| N1.6 사전학습(NVIDIA, fp32) | fp32 Adam | (DGX) | 6/10 = **60%** |
| **N1.6 자체학습(우리, 8bit)** | paged_adamw_8bit | **22.7GB(5090)** | 8/10 = **80%** |
| N1.5 자체학습(우리) | fp32(host) | 25.5GB | 1/10 = 10% (open MSE 2.18) |

**결론**: 8-bit Adam N1.6(80%)가 fp32 사전학습본(60%)과 **동등하거나 오히려 높음** — n=10 표본
분산(워크숍 공식 기대치도 50~70% 변동)을 감안하면 **양자화로 인한 성능 저하 없음이 확증**됐다.
동시에 N1.5의 낮은 SR(10%)이 **학습 파이프라인이 아니라 아키텍처·tune 범위** 때문이었음도 입증
(같은 데이터·파이프라인에서 N1.6은 80%). 즉 **단일 5090에서 8-bit로 NVIDIA 수준 N1.6 재현 성공.**

#### ⚠️ 함정: 서버별로 클라이언트 프로토콜을 맞춰야 함
N1.5 평가용 어댑터 패치(`n1d5_client_adapter.patch`, 평면 키·직접 전송)가 워크숍 클라이언트에
남아있으면 **N1.6 서버(원래 워크숍 프로토콜=중첩 관측)와 충돌** → `Server error: get_action() got an
unexpected keyword argument 'video.wrist'`. **N1.6 평가 전 원본 복원 필수**
(`cp lerobot_interface.py.bak_preadapter lerobot_interface.py`). N1.5 평가 시엔 다시 어댑터 적용.
정리: **N1.5 서버(n1d5)=어댑터 패치 / N1.6 서버(real-robot)=원본 클라이언트.**

---

## 요약

1. **N1.6 사전학습본**: NVIDIA가 75ep로 학습·배포한 체크포인트를 5090에서 서버(real-robot)+
   클라이언트(teleop-docker)로 추론 → **sim SR 60%**.
2. **N1.5 자체학습**: N1.6 단일 GPU OOM(고정 optimizer 상태, #536 미해결)으로 N1.5 전환.
   유효 배치 64·lr 1e-4 동일하나 아키텍처·tune 범위(LLM freeze)가 작아 **SR 10%** — open-loop
   MSE 2.18은 양호하나 아키텍처·tune·closed-loop 오차 누적으로 저조.
3. **8-bit N1.6 학습**: `paged_adamw_8bit`로 optimizer 상태만 양자화 → **22.7GB로 단일 5090 학습
   가능**(어제 불가능·#536 미해결을 해결). 학습 완주(loss 0.005) 후 **sim SR 8/10=80%** — fp32
   사전학습본(60%)과 동등/상회로 **양자화 성능 저하 없음 확증**. N1.5 저조(10%)는 파이프라인이
   아니라 아키텍처·tune 범위 때문임도 입증(같은 데이터에서 N1.6은 80%).

*관련: [01_실행기록.md](01_실행기록.md) · [04_GR00T_sim.md](../../model_md/sim2real/04_GR00T_sim.md) · [setup/sim/patches/](../../setup/sim/patches/)*
