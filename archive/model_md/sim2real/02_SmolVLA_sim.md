# S2. SmolVLA — Sim-to-Real (FT, 로컬 5070Ti)

> **역할**: 경량 VLA의 sim 데이터 FT 유효성 + 사전학습(SO-100)이 sim 도메인 갭을 완충하는지 검증.
> 상위 계획: [05_SimToReal.md](05_SimToReal.md) | 실기 결과: [report/SmolVLA_report.md](../report/SmolVLA_report.md) (SR ~20% 천장)

## 모델 개요 (sim 경로)

| 항목 | 내용 |
|---|---|
| 학습 방식 | `lerobot/smolvla_base` FT (`--policy.pretrained_path`) |
| 학습 위치 | **로컬 RTX 5070Ti** (실기 FT와 동일 — VRAM ~6GB) |
| 하이퍼파라미터 | batch 16, **steps = epoch 기준 산정** (목표 epoch 20~25, steps = epoch×frames/16) |
| 언어 명령 | sim 태스크 문장 고정 (단일 문장 — 실기 관례 유지) |
| sim 추론 | lerobot `policy_server`(smolvla) + sim 공용 어댑터 |
| 실기 전이 | 기존 `setup/smolvla/eval_smolvla_*_ft*.sh` 경로 (체크포인트 교체) |

## 데이터 요구·처리

- sim 50ep(DR) 그대로. **frames 수 확인 후 steps 계산이 필수 절차** —
  근거: 실기 실측에서 동일 steps로 데이터만 커지면 epoch 반감 → SR 급락(v2 30%),
  epoch 통제(v3)로 원인 분리함 (report §10~11)
- idle 트리밍 적용 검토 (ACT와 공통)

## 진행 절차

- [ ] **1. 학습** (Phase 2)
  - [ ] sim frames 확인: ____ → steps 산정: ____ (epoch ≈ ____)
  - [ ] `train_smolvla_sim.sh` 작성·학습 (loss 목표 ~0.01 이하, 실기 v1~v3: 0.006~0.010)
- [ ] **2. sim 평가** (Phase 3)
  - [ ] policy_server(smolvla) + 어댑터 dry-run
  - [ ] sim SR 10회 (DR-Eval)
- [ ] **3. 실기 전이** (Phase 4) — zero-shot 10회 (5지점·goto_home·개입금지)
- [ ] **4. co-training** — sim+real 혼합 재학습 → 실기 재측정 10회

## 완결 체크리스트 (게이트)

- [ ] sim 10회 + 전이 10회 + co-train 10회
- [ ] 대표 클립 (sim 1 + real 1)
- [ ] 요약 카드 / 로그·클립 백업

## 리스크 & 대응

| 리스크 | 대응 |
|---|---|
| epoch 미달로 저성능 (실기 v2 재연) | steps를 epoch 기준으로 산정하는 절차를 게이트화 |
| 실기 천장(~20%)이 sim에도 나타날 가능성 | sim SR로 "데이터 품질 vs 모델 한계" 분리 — sim에서 높으면 실기 데이터 품질 문제 시사 |
| 단일 언어문장 → 시각 shortcut | DR로 배경 다양화가 완충 |

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
- **수치**: sim __/10, 전이 __/10, co-train __/10 (기준 real-only: T1 v1 50% / v3 20%)
- **관찰 메모**:
- **갭 해석**:

## 참고 자료

- SmolVLA 논문(50-demo·FT 프로토콜): arXiv:2506.01844
- 실기 실측(epoch 통제·eval 교란): [report/SmolVLA_report.md](../report/SmolVLA_report.md) §10~11
- 커뮤니티 FT 사례: ggando.com (RTX3090/batch64/20k)
