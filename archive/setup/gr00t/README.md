# GR00T N1.5 셋업 (SO-101, 원격 5090 FT)

NVIDIA `nvidia/GR00T-N1.5-3B`를 SO-101에 파인튜닝. SO-100/101은 사전학습 미포함(OOD)이라
zero-shot 불가 전제 → 바로 **new_embodiment full FT**. 로컬 16GB로는 FT 빠듯 → **5090(32GB)**
에서 학습, 추론은 GR00T inference server(5090) + eval client(로컬 로봇).

## pi0에서 터진 문제 → GR00T 사전 점검 (2026-07-14)

| pi0 문제 | GR00T 대응 | 상태 |
|---|---|---|
| 잘못된 체크포인트 버전 | `nvidia/GR00T-N1.5-3B` 단일 공식 | ✅ |
| gated 의존성(paligemma 토큰) | GR00T-N1.5-3B public, gated 없음 | ✅ 유리 |
| **카메라 키 불일치(pi0 #1 실패)** | **modality.json `original_key`로 매핑** — `front`←`observation.images.top` | ✅ 정식 해결 |
| state/action 차원(pi0는 32 vs 6) | so100 modality = 6-dim(single_arm[0:5]+gripper[5:6]) — **우리와 완전 일치** | ✅ 유리 |
| LoRA 용량 부족(배회) | 5090 32GB **full FT(~25GB)** → LoRA 회피 | ✅ 근본 해결 |
| frozen vision 그라운딩 약함 | full FT는 diffusion+VLM 학습(default) | ✅ |
| 전처리/정규화 불일치 | GR00T 자체 정규화 스택, dry-run 선확인 | 대비 |
| 급동작(안전) | eval client에 `max_relative_target` 적용 | 대비 |
| rsync 데이터 파일 권한(600) | 5090 복사 후 `chmod -R o+rX` | 대비 |
| eval 프로토콜 confound | SmolVLA v2/v3와 **동일 5점/소형마킹** eval | 대비 |

## 카메라 매핑 (핵심)

우리 데이터셋 키: `observation.images.top`, `observation.images.wrist` (state/action 6-dim).
GR00T `so100_dualcam` data-config는 `front`·`wrist` 뷰 기대 → `modality.json`에서:
- `front.original_key = observation.images.top`  (top → GR00T front)
- `wrist.original_key = observation.images.wrist`

→ `modality.json`을 각 데이터셋 `meta/`에 복사하면 GR00T-LeRobot 호환 완성.

## 환경 (5090)

- 위치: `~/gr00t_remote/Isaac-GR00T` (uv, Python 3.12, CUDA 12.8, torch 2.9, flash-attn 사전빌드휠)
- pyproject 수정: `required-environments` x86_64 전용 + aarch64 torchcodec 경로휠(LFS 포인터) 소스 제거
- ⚠️ torchcodec는 ffmpeg 4-7 필요 → 5090에 `sudo apt install ffmpeg`(Ubuntu 24.04=6.x, OK) 또는
  FT 시 `--video-backend torchvision_av`로 우회
- 체크포인트: `nvidia/GR00T-N1.5-3B`(public), FT 출력 `~/gr00t_remote/checkpoints/`

## 진행 순서

1. [진행중] 환경 설치(`uv sync`)
2. 데이터: T1/T2에 `modality.json` 추가 → 5090 복사(권한 o+rX)
3. Full FT (5090): `scripts/gr00t_finetune.py --data-config so100_dualcam --embodiment-tag new_embodiment`
4. 추론: `scripts/inference_service.py --server` (5090) + `eval_lerobot.py`(로컬, 클램프)
5. 측정: SmolVLA와 동일 5점/소형마킹 eval, T1/T2 각 10회

## 참고
- 공식 튜토리얼: https://huggingface.co/blog/nvidia/gr00t-n1-5-so101-tuning
- Isaac-GR00T: https://github.com/NVIDIA/Isaac-GR00T
