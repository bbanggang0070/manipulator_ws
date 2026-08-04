# S3. π0 — Sim-to-Real (expert-only FT, 5090)

> **역할**: 실기에서 "부분 인식·접근, 완결 미달"로 보류된 π0가 **sim의 통제된 환경에서는
> 완결까지 가는지** 검증 — 실기 한계가 데이터/도메인 문제인지 모델 계열 한계인지 분리.
> 상위 계획: [05_SimToReal.md](05_SimToReal.md) | 실기 결과: [report/Pi0_report.md](../report/Pi0_report.md) (보류)

## 모델 개요 (sim 경로)

| 항목 | 내용 |
|---|---|
| 학습 방식 | `lerobot/pi0_base` FT — **`train_expert_only=true` + `freeze_vision_encoder=true`** |
| 학습 위치 | **5090** (`setup/pi0/remote_5090/pi0-train.sh` 변형, bf16+grad ckpt, batch 8 / 50k) |
| 근거 | 실기 실측: LoRA(1.4M) loss 0.074 정체·배회 → expert-only(578M) 0.04 도달·부분 접근. π0.5 공식 문서도 동일 방식 권장 |
| sim 추론 | 기존 **async 정책 서버**(5090:8080) + sim 공용 어댑터 (실기 인프라 재사용) |
| 실기 전이 | 기존 `infer_pi0_t1_remote_ft.sh` (클램프·rerun·CSV 계측 포함) |
| zero-shot | 시도 안 함 — 3캠·32차원 불일치로 불가 판정 완료 (실기 §1) |

## 데이터 요구·처리

- sim 50ep(DR) → 5090 복사 시 **`chmod -R o+rX`** (컨테이너 uid 1001 읽기 — 실기에서 실측한 함정)
- idle 트리밍 적용 검토
- 정규화 stats는 데이터셋 meta 자동 사용 (실기에서 체크포인트↔데이터셋 일치 검증 완료)

## 진행 절차

- [ ] **1. 학습** (Phase 2)
  - [ ] 데이터 5090 복사 + 권한 처리
  - [ ] `pi0-train.sh` sim 변형으로 학습 (loss 추이 기록 — 0.04 벽 통과 여부 주시)
- [ ] **2. sim 평가** (Phase 3)
  - [ ] async 서버(체크포인트 경로) 기동 + sim 어댑터 dry-run
  - [ ] sim SR 10회
- [ ] **3. 실기 전이** (Phase 4) — zero-shot 10회
- [ ] **4. co-training** → 실기 재측정 10회

## 완결 체크리스트 (게이트)

- [ ] sim 10회 + 전이 10회 + co-train 10회 (**sim에서도 완결 미달이면 "π0 계열 한계 재현"으로 판정하고 무리한 튜닝 생략** — 실기 보류 결정과 일관)
- [ ] 대표 클립 / 요약 카드 / 백업

## 리스크 & 대응

| 리스크 | 대응 |
|---|---|
| frozen vision 한계가 sim에서도 재현 | 판정 기준 명확화(위): 재현 시 조기 종료. 여유 시 vision unfreeze 1회 시도(실기 향후안과 동일) |
| 추론 지연(3B)로 sim 평가 루프 저속 | async 구조라 완충. denoising steps 조정 여지 |
| 5090에서 sim 렌더+π0 서버 VRAM 경합 | sim 평가 시 5090은 서버 전용, sim은 로컬에서 구동 (또는 순차 실행) |

## 결과 기록

### Sim 평가 (10회)
| 시행 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | SR |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 결과 | | | | | | | | | | | /10 |

### Real zero-shot 전이 (10회)
| 시행 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | SR |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 결과 | | | | | | | | | | | /10 |

### Co-training 후 실기 (10회)
| 시행 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | SR |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 결과 | | | | | | | | | | | /10 |

### 요약 카드
- **수치**: sim __/10, 전이 __/10, co-train __/10 (기준 real-only: 보류 — 부분 접근)
- **loss**: 학습 최종 ____ (실기 expert-only 0.039~0.043 대비)
- **관찰 메모** / **갭 해석**:

## 참고 자료

- 실기 실측(LoRA→expert-only 진단): [report/Pi0_report.md](../report/Pi0_report.md)
- π0.5 공식 문서(train_expert_only 권장): https://huggingface.co/docs/lerobot/pi05
- π0/π0-FAST 소개: https://huggingface.co/blog/pi0
- SO-ARM101 π0 FT 사례: https://ghuijo.github.io/blog/2025/LeRobot-PI0-Finetuning-Tutorial/
