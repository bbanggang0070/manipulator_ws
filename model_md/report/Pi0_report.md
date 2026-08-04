# π0 (3B) 모델 진행 보고서 — Zero-shot 불가 → 원격 5090 FT (부분 성공, 보류)

> 작성일: 2026-07-14 | zero-shot 불가 판정 → 5090 원격 정책 서버 구축 → LoRA/expert-only FT까지
> 프로젝트: 단일 SO-ARM101 매니퓰레이터로 4개 모델(ACT / SmolVLA / π0 / GR00T N1.5) 비교.
> 본 문서는 세 번째 모델 **π0**의 zero-shot 불가 규명, 원격 파인튜닝 인프라 구축, 두 차례
> 파인튜닝(LoRA·expert-only)과 그 진단, 그리고 **"부분 인식·접근하나 미완성 → 보류"** 판정까지 정리한다.

---

## 1. Zero-shot 불가 판정

로컬 5070 Ti(16GB)로 `lerobot/pi0_base`를 우리 로봇에 바로 추론 시도했으나 근본적으로 불가.

| 원인 | 내용 |
|---|---|
| 체크포인트 스키마 | `lerobot/pi0`는 구버전 PI0Config(현재 lerobot 0.6.1 비호환) → `lerobot/pi0_base` 사용 |
| **카메라 키 불일치** | pi0_base는 `base_0_rgb`·`left_wrist_0_rgb`·`right_wrist_0_rgb`(3캠) 기대. 우리는 top/wrist(2캠) |
| **차원 불일치** | pi0_base state/action = **32차원**(멀티임바디먼트 패딩). 우리 SO-101 = 6차원 |
| rename 불가 | async robot_client에 rename_map 옵션 없음 → 억지 매핑조차 불가 |

SmolVLA zero-shot과 **동일한 부류의 불가**(미학습 임바디먼트 + 3캠·32차원 전제). zero-shot은
설정 문제가 아니라 base 모델이 파인튜닝을 전제로 설계된 결과다.

---

## 2. 원격 5090 정책 서버 인프라 (재사용 가능 자산)

로컬 5070 Ti는 π0 FT 불가(LoRA >22.5GB, full >70GB). 공용 **RTX 5090(32GB)** 을 원격 정책
서버로 구축 — 로봇은 로컬 유지, 관측을 gRPC로 5090에 보내 추론(async inference).

```
[로컬 5070Ti + 로봇]                      [5090 서버]
robot_client ──관측(gRPC)──▶  policy_server (π0 GPU 추론)
   로봇 실행  ◀──액션청크────
```

- Docker 이미지 `lerobot-gpu:local`(공식 Dockerfile.internal, 전 정책 지원)
- HF 캐시: pi0_base 14GB + **gated `google/paligemma-3b-pt-224` 토크나이저를 개인 토큰 없이
  로컬에서 파일만 복사** + 서버 `HF_HUB_OFFLINE=1`
- 방화벽: 로컬 PC IP로만 8080 허용
- 스크립트: `setup/pi0/remote_5090/`(정본) → 5090 `~/pi0_remote/` 배포
- **추론 지연 ~120~140ms/청크** (50액션=1.65초 분량) — 원격이 병목 아님(async가 은닉)

---

## 3. 파인튜닝 1차 — LoRA (실패)

`setup/pi0/remote_5090/pi0-train.sh`(초기 버전): `--peft` LoRA, r=16/α=32, 어댑터만 학습.

| 항목 | 값 |
|---|---|
| 학습 params | **1.4M** (전체 4B 중 어댑터만) |
| 최종 loss | **0.074에서 정체**(step 23k부터 평탄) |
| 결과 | 큐브 미접근, 목적 없는 배회 |

**판정**: LoRA 용량 부족 — 새 임바디먼트의 시각-운동 매핑을 학습하기엔 어댑터가 너무 작음.

---

## 4. 파인튜닝 2차 — expert-only (부분 성공)

VLM 백본 freeze + action expert 전체 학습(SmolVLA가 50% 낸 레시피).
`--policy.train_expert_only=true --policy.freeze_vision_encoder=true`, bf16 + gradient_checkpointing.

| 항목 | LoRA | expert-only |
|---|---|---|
| 학습 params | 1.4M | **578M** (400배↑) |
| 최종 loss | 0.074 정체 | **0.039~0.043** (epoch 13.9) |
| 동작 | 배회 | **느리지만 큐브 인식·접근 수행** (미완성) |

체크포인트: `pi0_t1_expert`(full model 8.3GB). loss가 LoRA 벽(0.074)을 확실히 돌파.

### 4.1 관찰 — 부분 인식·접근하나 미완성

rerun 영상·로그상 팔이 **느리게나마 빨간 큐브를 인식하고 접근**하지만, 파지·배치까지
완결하지 못하고 큐브 근처에서 소극적으로 진동한다.

- 관절 궤적 순변화/총변화 = **0.03~0.04** (큐브 근처에서 작은 폭 왕복 = 접근하나 확신 없음)
- 그리퍼 변화폭 작음(파지 동작 미약)
- 끊김: 추론 지연은 짧으나 `latest_only`에서 청크 경계 큐 고갈로 **15~20% 스텝이 >100ms 프리즈**

### 4.2 원인 배제 (저비용 요인 전부 소진)

| 후보 | 검증 | 결과 |
|---|---|---|
| max_relative_target(클램프) | 로그 `cmd`=`sent` 확인 | 무관(클램프 미발동) |
| 청크 aggregation 진동 | `weighted_average`→`latest_only` | 진동은 aggregation 아티팩트였음, 배회는 잔존 |
| 관측 전처리 불일치 | 체크포인트↔데이터셋 stats maxdiff **<1e-6**, 이미지 경로 동일 | 완전 일치(문제 없음) |
| flow-matching 샘플링 | `num_inference_steps` 10→25 | 개선 없음(순/총 0.034) |

→ 전처리·제어 파라미터는 모두 정상. 남은 원인은 **정책 competence**: 50ep·frozen vision으로는
큐브 그라운딩이 약함(loss 0.04 평탄도 이와 부합).

---

## 5. 판정 — 부분 성공, 보류

> **π0는 원격 FT로 "느리게나마 큐브 인식·접근"까지는 도달했으나 task 완결(파지·배치)에는
> 미달.** 저비용 튜닝은 모두 소진했고, 남은 개선 여지는 다음과 같으나 이번엔 보류하고
> GR00T로 넘어간다. π0는 추후 재도전.

**향후 재도전 시 우선 시도 (미착수):**
1. **vision encoder 학습 허용**(`freeze_vision_encoder=false`) — 시각 특징을 SO-101 큐브에 적응(그라운딩 직접 겨냥). VRAM 조정 필요.
2. 학습 증량(steps↑, epoch을 SmolVLA 수준 24+로) — 단 loss가 이미 평탄해 폭은 제한적.
3. `chunk_size_threshold`↑로 끊김(큐 고갈) 완화.
4. π0.5(`lerobot/pi05_base`)로 교체 — 인터페이스 동일, `train_expert_only` 권장(공식 문서).

**재사용 자산**: 5090 원격 서버 인프라(§2)·정규화 검증 방법·진단 로깅(action cmd/sent + dt)은
GR00T·π0 재도전에 그대로 활용 가능.

---

*관련: [model_md/03_Pi0.md](../03_Pi0.md), [report/SmolVLA_report.md](SmolVLA_report.md)(동일 형식),
[setup/pi0/](../../setup/pi0/)(클라이언트·런처·5090 서버측 스크립트)*
