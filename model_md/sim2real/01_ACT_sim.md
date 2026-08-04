# S1. ACT — Sim-to-Real (from-scratch, 로컬 5070Ti)

> **역할**: sim-to-real 기준선. 실기 기준선(T1 80%)과 동일하게 from-scratch 학습이 sim 데이터로도
> 성립하는지, 그리고 **시각 도메인 갭에 가장 취약할 것**이라는 가설(언어·사전학습 없음)을 검증.
> 상위 계획: [05_SimToReal.md](05_SimToReal.md) | 실기 결과: [report/ACT_report.md](../report/ACT_report.md)

## 모델 개요 (sim 경로)

| 항목 | 내용 |
|---|---|
| 학습 방식 | from-scratch (`lerobot-train --policy.type=act`), 사전학습 없음 |
| 학습 위치 | **로컬 RTX 5070Ti** (실기 ACT와 동일 장비 — VRAM ~6GB) |
| 데이터 | sim 50ep (Vials-To-Rack-DR, 리더암 teleop) — 실기 레시피와 동일 batch 8 / 100k steps |
| sim 추론 | lerobot `policy_server`(act 지원) + sim 공용 어댑터 |
| 실기 전이 | 기존 `setup/act/eval_act_*.sh` 경로 그대로 (체크포인트만 교체) |
| 예상 리스크 | 시각 갭 최민감 (DR 수집이 성패 좌우) |

## 데이터 요구·처리

- sim 데이터셋 그대로 사용 (카메라 키 임의 허용 — ACT는 매핑 불필요)
- **idle 트리밍 적용** (GR00T 실측 교훈 — `setup/gr00t/trim_idle_v2.py`는 v2용이므로
  v3 데이터면 트리밍 로직만 이식) — 적용 여부는 sim 데이터 idle 실측 후 결정

## 진행 절차

- [ ] **1. 학습** (Phase 2)
  - [ ] sim 50ep 확보 확인 (frames 수 기록: ____)
  - [ ] `train_act_sim.sh` 작성 (batch 8 / 100k / save 20k — 실기 스크립트 변형)
  - [ ] 학습 + loss 곡선 확인 (실기 v1: 0.05 수렴 참고)
- [ ] **2. sim 평가** (Phase 3)
  - [ ] policy_server(act) 기동 + sim 어댑터 연결 dry-run
  - [ ] sim SR 10회 (초기 위치 변화, DR-Eval 환경)
- [ ] **3. 실기 전이** (Phase 4)
  - [ ] 실기 소품·씬 준비 (sim 태스크와 근사)
  - [ ] zero-shot 전이 10회 (5지점·goto_home·개입금지)
- [ ] **4. co-training** — sim 50ep + 실기 50ep 혼합 재학습 → 실기 재측정 10회

## 완결 체크리스트 (게이트)

- [ ] sim SR 10회 + real 전이 10회 + co-train 10회 기록
- [ ] 대표 클립 각 1개 (sim 성공 / real 전이 성공·실패)
- [ ] 요약 카드
- [ ] 로그·클립 백업

## 리스크 & 대응

| 리스크 | 대응 |
|---|---|
| 시각 도메인 갭으로 전이 0% 가능 | DR 데이터 필수, sim 카메라 포즈를 실기 top/wrist 구도와 근사 |
| from-scratch라 sim 데이터 품질에 전적 의존 | 수집 규칙 엄수(성공 종결·idle 최소) |
| 5070Ti에서 sim(어댑터 평가)과 학습 경합 | 학습과 sim 평가 시간 분리 |

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
- **수치**: sim __/10, 전이 __/10, co-train __/10 (기준 real-only: T1 80%)
- **관찰 메모**:
- **갭 해석** (sim↔real 차이 원인):

## 참고 자료

- ACT/ALOHA 논문: arXiv:2304.13705 (시각 의존 구조 근거)
- 실기 기준선: [report/ACT_report.md](../report/ACT_report.md) — T1 80% (30ep)
- DR 근거: Tobin et al. 2017, arXiv:1703.06907
