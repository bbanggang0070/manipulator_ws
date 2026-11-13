# 경량화 계획 — 발표 피드백 교차 검증과 차후 연구 방향

> 작성 2026-11-13. 기준: 캡스톤 최종 발표(태그 `capstone-final`) 결과와 심사 피드백.
> 최종 모델 `gr00t_bi_cleanup392_llm8_n16_8bit/checkpoint-69000` — 평가 B 60회 완전 성공 73%(44/60, 95% CI 61~83%).
> 강화학습 쪽 계획은 [DSRL_PLAN.md](DSRL_PLAN.md)에 따로 있다. 이 문서는 **모델 경량화**를 다룬다.

---

## 0. 한 줄 요약

| 피드백 | 문헌이 말하는 것 | 우리 대응 |
|---|---|---|
| ① 3B인데 왜 양자화 안 했나 | 양자화는 **추론** 메모리·속도를 줄이는 수단이지 성공률을 올리는 수단이 아니다. 4-bit로 메모리 절반 이하, 성공률은 거의 유지(OpenVLA). 단 **action head와 projector는 양자화에 민감**(QVLA) | 1단계: VLM만 INT8/INT4로 양자화해 평가 B 재측정. 2주 안에 끝나는 가장 싼 실험 |
| ② 파운데이션 파인튜닝 말고 한 게 없다 → 경량 모델 + 언어 | 0.5B VLM 백본으로 7B와 같은 LIBERO 성공률(VLA-Adapter 97.3% vs OpenVLA-OFT 97.1%). 그러나 **VLM 사전학습이 없는 소형 모델은 언어를 무시하는 경향**이 문헌(LangGap)과 우리 P4·P6 실험에서 모두 확인됨 | 2단계: 사전학습된 소형 VLM(SmolVLA 450M · VLA-Adapter 0.5B)에 우리 392ep를 올려 같은 평가 B로 비교. ACT+텍스트는 **대조군**으로만 |
| ② 서보 떨림 정밀 제어 | 떨림의 1차 원인은 서보 PID·백래시(약 1°)·전압. 정책 쪽은 **청크 경계 불연속**이 원인이고 단순 저역통과 필터는 권장되지 않음(RTC, LiPo) | 3단계: 서보 설정 → 청크 경계 후처리 → 잔차 RL 순서로, 각 단계마다 궤적 저크(jerk)와 성공률을 같이 측정 |

**경량화 목표(제안)**: 파라미터 ≤ 1B · 5090 한 장에서 학습 ≤ 10 GPU-시간 · 평가 B 60회에서 완전 성공 ≥ 70% 유지.
세 조건을 동시에 만족하는 모델이 나오면 "GR00T 3B가 필요했는가"에 대한 답이 된다. 못 나오면 그 자체가 3B를 쓴 근거가 된다.

---

## 1. 피드백 ① — 양자화·경량화를 왜 안 했나

### 1.1 우리가 실제로 한 것과 안 한 것

| 항목 | 한 것 | 안 한 것 |
|---|---|---|
| 학습 메모리 | **8-bit AdamW**(optimizer state 양자화)로 5090 32GB에 맞춤. VLM 위 8층 + action head만 학습 | 가중치 양자화 학습(QAT), LoRA |
| 추론 | bf16, 5070 Ti 16GB, 청크당 70~90ms(약 11~14Hz, 16스텝 중 8스텝 실행) | 가중치 INT8/INT4, TensorRT |

즉 "경량화를 전혀 안 했다"는 아니지만, 심사가 물은 **모델 가중치 양자화**는 하지 않았다. 안 한 이유는 분명히 말할 수 있다 — 추론 속도가 병목이 아니었고(서보 명령 주기 > 추론 지연), 실패는 물체 선택(언어 결합)에서 났다. 양자화는 그 실패를 줄이지 못한다.

### 1.2 문헌 교차 검증

| 논문 | 모델 | 결과 | 우리에게 주는 함의 |
|---|---|---|---|
| OpenVLA (Kim et al. 2024) | 7B | **4-bit 양자화가 bf16과 같은 성공률**, GPU 메모리 절반 이하. **8-bit는 오히려 느려짐**(양자화 커널 오버헤드, A5000에서 1.2Hz) → 제어 주기가 바뀌어 성공률 하락 | 8-bit는 속도 이득이 없을 수 있다. 4-bit weight-only가 현실적 |
| EaqVLA (2025) | OpenVLA, LIBERO | GPTQ > RTN. 8-bit는 원본에 가장 가깝고 4-bit는 성공률이 조금 떨어짐 | OpenVLA 논문과 4-bit 결론이 다르다. **벤치마크·방법에 따라 갈린다** → 직접 재야 한다 |
| QVLA (2026) | OpenVLA·OFT | 비전 인코더는 양자화에 강건, **projector와 action head는 민감** — 공격적으로 양자화하면 붕괴. 채널별 양자화는 INT4에서도 원본 유지 | GR00T의 DiT(32층 action head)는 bf16으로 두고 VLM만 양자화하는 **혼합 정밀도**가 안전 |
| ActQuant (2026) | π0.5 | 기존 방법은 3 bpw 아래에서 붕괴 | flow-matching 계열(GR00T와 같은 구조)도 sub-4-bit는 아직 연구 단계 |
| BitVLA (2025) | 1.58-bit 전체 | OpenVLA-OFT INT4와 비슷한 LIBERO 성능, 메모리 1.4GB vs 4.7GB. **로봇 사전학습 없음** | 극단 경량화의 상한선 참고용. 실기 검증이 없다 |
| GR00T N1.7 on Jetson Thor (NVIDIA) | 3B | TensorRT + NVFP4 혼합 양자화로 125ms → 39.9ms(3.1배). FP8은 약 44ms | NVIDIA 공식 경로가 있다. 단 **N1.7 기준**이고 Thor에서 INT8은 FP16 대비 이득이 없다는 포럼 보고가 여럿 |

**결론**: 양자화는 "했어야 할 당연한 것"이 아니라 **배포 요구가 생겼을 때 하는 것**이다. 우리 배포 환경(5070 Ti 16GB, bf16 3B 추론 가능)에서는 요구가 없었다. 하지만 심사의 질문에 **수치로 답하려면** 한 번은 해 봐야 한다 → §5 1단계.

### 1.3 발표 답변 스크립트

> 학습에서는 8-bit AdamW로 optimizer 메모리를 양자화해 5090 한 장에 맞췄고, 추론은 bf16으로 70~90ms라 서보 제어 주기보다 빨라 병목이 아니었습니다. 가중치 양자화는 메모리와 속도를 줄이지 성공률을 올리지는 않는다는 것이 OpenVLA 등의 결과이고, 저희 실패는 물체 선택(언어 결합)에서 났기 때문에 우선순위를 데이터에 두었습니다. 다만 VLM만 INT4로 양자화하고 action head는 bf16으로 두는 혼합 정밀도로 같은 평가를 다시 돌려 수치로 확인할 계획입니다.

---

## 2. 피드백 ② — "파인튜닝 말고 한 게 없다" → 경량 아키텍처

### 2.1 먼저 짚을 것: 이번 프로젝트의 기여는 어디에 있었나

모델 구조를 바꾸지 않은 것은 사실이다. 0% → 73%의 변화는 다음에서 왔고, 이것은 문헌이 2025~26년에 와서야 정리한 문제와 정확히 같다.

| 우리가 한 것 | 같은 문제를 다룬 문헌 |
|---|---|
| 층별 선형 프로브로 "보는 건 되는데(비전 AUC 0.98~1.00) 지시 단어와 잇는 층이 학습 범위 밖"임을 찾고 VLM 학습 층을 4 → 8로 확장 | VLM4VLA (ICLR 2026): 24개 VLM 비교, **비전 인코더가 병목**, 일반 VLM 성능은 로봇 성능을 거의 예측 못 함 |
| 배치만 봐도 답이 정해지는 데이터 구조 발견 → 같은 배치·다른 지시문 **대조 시연 92회** 추가 (통계: 19 vs 2, McNemar p<0.001) | LangGap (2026): SOTA VLA 대부분이 **언어를 무시**. 장면 고정·지시문만 바꾸는 평가에서 드러남. LangForce (2026): 지시문 마스킹 진단, 데이터셋의 지시문 중 2% 미만만 언어적으로 고유 |
| 50ep마다 칸 배치 교체(6종) → 칸 넣기 33% → 97% | Lin et al. (ICLR 2025) 데이터 스케일링: **환경·물체 다양성이 양보다 중요**, 한 조건당 50회 넘으면 추가 효과 미미 |

→ 피드백 ②에 대한 정직한 답은 "구조는 안 바꿨지만, **무엇을 학습시킬지와 어떤 데이터가 필요한지**를 실험으로 찾았고 그것이 문헌의 최신 결론과 일치한다"이다. 그 위에서 경량화는 **다음 질문**으로 자연스럽다: 그 결론이 작은 모델에서도 성립하는가.

### 2.2 "ACT에 text tokenizer를 붙이면 되지 않나"에 대한 검증

| 근거 | 내용 | 판단 |
|---|---|---|
| MT-ACT / RoboAgent (2023) | ACT에 FiLM으로 언어 조건화, 7,500 시연·38 과제. 미지 상황에서 기존 대비 40% 우위 | **된다.** 단 텍스트 인코더는 사전학습(CLIP/BERT)이고, 과제는 "어떤 스킬을 할지"를 고르는 수준 |
| NL-ACT (커뮤니티) | all-mpnet-base-v2 임베딩을 ACT 인코더 입력에 추가 | 구현 난이도는 낮다(1~2일) |
| Yell At Your Robot (RSS 2024) | 언어 조건 BC를 저수준 정책으로, 언어 교정을 상위 정책에 반영 | ACT류로 언어 조건화한 선례. 수치는 논문 확인 필요 |
| **우리 P4 실험** | 같은 장면·다른 지시문 데이터로 이어학습하면 언어를 못 배움 → 파운데이션에서 새로 학습해야 했음 | 언어 결합은 **사전학습된 VLM의 중간층**이 하고 있었다. ACT에는 그 층이 없다 |
| LangGap (2026) | 타깃 데이터 증강으로 단일 과제 언어 격차는 좁혀지지만 **과제 다양성이 늘면 다시 떨어짐** | 우리 32종 지시문·8물체·4색은 "다양성이 늘어난" 쪽 |

**판단**: ACT + 텍스트는 "지시문 32종 중 무엇인지"를 **분류**하는 데는 충분할 수 있다(8물체 × 4색은 결국 32-way 분류). 그러나 **보지 못한 물체·표현으로의 확장은 기대하기 어렵고**, 우리 데이터가 가진 지름길(배치 → 답)을 가장 쉽게 타는 구조다. 따라서 **대조군**으로 돌린다 — 되면 "이 과제에는 VLM이 필요 없었다"는 중요한 결과이고, 안 되면 VLM 백본을 쓴 근거가 된다. 어느 쪽이든 발표할 수 있다.

### 2.3 경량 VLA 후보 비교

| 모델 | 파라미터 | VLM 사전학습 | 로봇 사전학습 | 보고된 성능 | 학습 자원(보고) | 우리 과제 적합성 |
|---|---|---|---|---|---|---|
| **SmolVLA** (HF 2025) | 450M (action expert ~100M) | SmolVLM2 | **SO-100 커뮤니티 데이터 ~23k ep** | 실기 SO-100 78.3% (π0 61.7%), LIBERO ~87% | A100 1장 20k step 약 3.5h; RTX 3090 약 10h; VRAM batch 16에 4.4GB | **최우선.** 같은 로봇 계열, LeRobot 네이티브, 우리 데이터 포맷 그대로. VLM은 동결·action expert만 학습이 기본 |
| **VLA-Adapter** (2025) | 0.5B (Qwen2.5-0.5B) + 97M 정책 | Prismatic | 없음 | LIBERO 97.3% (OpenVLA-OFT 7B 97.1%), 219Hz | 낮은 VRAM(논문 주장) | 2순위. 로봇 사전학습 없이 LIBERO SOTA → "VLM 백본 + 작은 정책"의 대표. 저자가 **실기 일반화는 약하다**고 명시 |
| **FLOWER** (CoRL 2025) | 950M (Florence-2 절반 + flow transformer) | Florence-2 | 200 H100시간 | CALVIN SOTA, 실기 주방 61% (OpenVLA 31%) | 미세조정 4 GPU × 4h | GR00T와 가장 닮은 구조(VLM + flow). 1B 상한선 후보 |
| TinyVLA (2024) | 70M~1.4B | Pythia 계열 | 없음 | OpenVLA 대비 +25.7%p, 지연 1/20 | LoRA로 5%만 학습 | 구현 코드 성숙도 확인 필요 |
| MiniVLA (Stanford 2024) | 1B | Qwen 0.5B | Bridge 등 | LIBERO-90 82%(VQ 청킹+히스토리) ≈ OpenVLA 62% 상회. 실기는 과제마다 엇갈림(가지 집기 14% vs 66%) | — | 실기 결과가 들쭉날쭉 → 참고용 |
| BitVLA (2025) | 2B, 1.58-bit | BitNet b1.58 | 없음 | OFT-INT4 수준, 1.4GB | — | 극단 참고. 실기 없음 |
| GR00T N1.6 (현재) | 3B (Cosmos-Reason-2B + DiT 32층) | O | O (대규모) | **우리 평가 B 73%** | 5090 1장, 8-bit AdamW, 1000 step당 약 48분 실측 → 69k step ≈ 55시간 | 기준선 |

> 주의: 위 수치는 대부분 저자 보고이고 벤치마크가 서로 달라 **직접 비교는 불가**하다. 같은 평가 B 60회에서 다시 재는 것만이 공정하다.

### 2.4 "사전학습된 비전 인코더만 가져와 구조를 바꾼다"는 아이디어의 검증

사용자의 가설: 큰 모델을 통째로 가져와 일부만 학습하는 것보다, **가벼운 사전학습 비전 인코더**를 가져와 구조를 새로 짜는 것이 효율적이다.

| 근거 | 결과 | 가설에 대한 판정 |
|---|---|---|
| VLM4VLA (ICLR 2026) | 비전 인코더 **동결 시 모든 모델·벤치마크에서 큰 성능 하락**(예: 46.75 → 25.50). 실기 Bridge에서도 동결하면 개선 안 됨. 언어 쪽 동결은 영향 작음 | 가져온 인코더를 **동결하면 안 된다**. 학습(또는 LoRA)해야 한다 |
| OpenVLA (2024) | VLM 연구와 달리 VLA에서는 비전 인코더 미세조정이 **훨씬 높은 성공률**, 동결 시 불안정 | 같은 결론 |
| SPEAR-1 (2025) | 학습 가능한 SigLIP ≫ 동결 SigLIP. 동결 후 2k step만 풀어도 비슷 | "먼저 동결, 나중에 짧게 풀기"가 비용 절충안 |
| DSPv2 (2025) | DINOv2 동결 70% vs 미세조정·LoRA 90% | 같은 결론, LoRA로 충분 |
| HyperVLA (2025) | 미세조정 DINOv2 > CLIP, 동결 DINOv2 > 동결 SigLIP | 인코더 선택은 **DINOv2 계열**이 유리하다는 반복 보고 |
| Theia (CoRL 2024) | CLIP+DINOv2+ViT를 증류한 소형 인코더가 교사보다 로봇 학습 성능 높음. ImageNet 150 GPU시간 | 소형 인코더 후보. 피처 노름 엔트로피가 높은 인코더가 좋다는 가설 제시 |
| Hansen et al. (2022) "On Pre-Training for Visuo-Motor Control" | 증강 + 얕은 ConvNet **처음부터 학습**이 동결 사전학습 표현과 놀랍도록 비슷, 실기 포함 | 사전학습 인코더가 **항상** 이기는 건 아니다 |
| Dasari et al. (CoRL 2023) | ImageNet 등 일반 데이터셋이 로봇 데이터셋만큼 경쟁력 있음. **시뮬 벤치마크는 실기의 대리가 아님** | 시뮬 수치로 결정하지 말 것 |
| **우리 비전 프로브** | 최종 모델 비전 특징으로 물체 분류 AUC 0.98~1.00. 비전은 동결 상태에서도 충분 | **우리 과제에서 병목은 비전이 아니라 언어 → 물체 결합** |

**정리**:
1. 가설의 전반부("큰 모델 전체는 비효율")는 자원 면에서 맞다 — 우리 GR00T 학습은 약 55시간, SmolVLA는 보고 기준 3.5~10시간.
2. 가설의 후반부("비전 인코더만 가져오면 된다")는 **절반만 맞다**. 비전 인코더는 가져오되 **미세조정해야** 하고(동결 시 성능 하락이 6편에서 일관), 더 중요한 것은 우리 실패가 비전이 아니라 **언어 결합**에서 났다는 점이다. 비전 인코더 + 언어 임베딩 + 작은 정책 구조에서는 그 결합을 **처음부터 우리 392ep로 배워야** 하는데, LangGap·LangForce·우리 P4 결과는 그게 쉽지 않다고 말한다.
3. 따라서 "비전 인코더만"이 아니라 **"작은 사전학습 VLM(0.5B급) + 작은 action head"**가 문헌이 가리키는 지점이다. SmolVLA·VLA-Adapter가 그 구조이고, 둘 다 7B급과 비슷한 성능을 보고했다.

### 2.5 증류라는 세 번째 길

| 논문 | 방법 | 결과 |
|---|---|---|
| VLA-AD (2026) | OpenVLA-7B / π0.5 교사 → 158M 학생, VLM은 학습 때만 감독 | LIBERO에서 교사와 0.27% 차이, 44배 축소. **시뮬만** |
| RPD (2025) | 큰 VLA를 과제별 소형 전문가로 증류 + PPO | 코드·체크포인트 공개 |
| Princeton 논문 (2026) | π0.5 교사의 **섭동 초기상태 롤아웃**으로 학생 학습 | 분포 변화에 더 강건 |
| PLD (2025) | 잔차 RL 전문가가 실패를 고치고 그 궤적을 generalist에 되증류 | RL 계획(DSRL_PLAN)과 연결 |

우리는 **이미 73%짜리 교사(GR00T 392ep)**가 있고 서빙 인프라도 있다. 교사 롤아웃을 라벨로 써서 소형 학생을 학습하면, 사람 시연을 더 모으지 않고도 학생의 데이터를 늘릴 수 있다. 단 교사의 실패(물체 오선택 8/16)도 같이 배우므로 **성공 롤아웃만 필터**해야 한다 — run.json·평가 CSV가 있어 가능하다.

---

## 3. 서보 떨림과 정밀 제어

### 3.1 원인 분해

| 층 | 원인 | 근거 | 우리 상태 |
|---|---|---|---|
| 서보 | Feetech STS3215: 인코더 분해능 0.088°, **백래시 약 1°**(커뮤니티 측정), 반복 정밀도 약 ±0.17°(10cm 레버 ±0.3mm 환산). LeRobot은 접속 시 P=16, I=0, D=32로 낮춰 떨림 억제(I=0이라 중력 하중에서 몇 도 못 미침) | SO-ARM100 이슈 #134, LeRobot 모터 문서 | 기본값 사용. **측정 안 함** |
| 전원·캘리브레이션 | 전압 강하, 1회전 오프셋 잔류(이슈 #5324) | LeRobot 이슈 | calib_fingerprint로 지문 대조만 |
| 정책 → 청크 경계 | 청크(16스텝 중 8 실행) 경계에서 불연속. 관측 시점과 실행 시점의 **지연 불일치**가 저크의 원인(LAGO). 단순 평균·저역통과는 **유효하지 않은 동작**을 만들 수 있음(RTC) | Real-Time Chunking (2025), LiPo (2025), LAGO (2026) | 시간 앙상블 W=0.8(단일팔 실측 최적, 0.1은 얼어붙음), 비동기 추론 |
| 정책 → 파지 정밀도 | 놓친 뒤 재파지 못 함(실패 16회 중 6회) | 교정 데이터 부재 | DSRL_PLAN |

### 3.2 문헌이 권하는 순서

1. **서보 설정부터 측정한다.** PID·가속도 레지스터를 바꾸며 같은 명령 궤적에 대한 추종 오차·정착 시간을 기록. 비용 하루.
2. **청크 경계 후처리**: LiPo(저크 최소화 후처리) 또는 RTC(이미 보낸 접두 동작을 고정하고 나머지만 inpainting). 앙상블 W 스윕(0.3 → 0.8에서 물체 70% → 90%였던 것처럼 성공률에 직접 영향)과 함께 **저크·정착 오차·성공률**을 한 표에.
3. **잔차 RL / HIL-SERL**: HIL-SERL은 실기 1~2.5시간 학습으로 거의 완벽한 성공률, 같은 데이터의 IL 대비 성공률 +101%. 단 **저수준 안전 제어기와 사람 교정**이 전제. 양팔 이미지 입력 RL 선례 있음. 파지·재파지 구간에 한정해 적용.

### 3.3 발표 답변 스크립트

> 서보 떨림은 저희도 겪었고 두 층으로 나눠 봅니다. 서보 자체는 백래시 약 1도, LeRobot 기본 PID로 억제하고 있고, 정책 쪽은 청크 경계에서 생기는 불연속이라 시간 앙상블 가중치를 0.8로 올려 물체 성공률을 70에서 90%로 올렸습니다. 저역통과 필터는 유효하지 않은 동작을 만들 수 있어 쓰지 않았고, 차후에는 청크 경계 후처리(LiPo·RTC)와 파지 구간 잔차 강화학습으로 정밀도를 올릴 계획입니다.

---

## 4. 언어 결합 — 경량화에서 가장 큰 리스크

경량화 실험 전체를 관통하는 질문은 하나다: **작은 모델이 지시문을 실제로 읽는가.**

| 진단 도구 | 방법 | 우리 적용 |
|---|---|---|
| 지시문 마스킹 (LangForce) | 학습·평가 시 지시문을 비우고 성공률 비교. 차이가 없으면 vision-only 정책 | 모든 후보 모델에 **필수**. 평가 B 36회 중 12회를 지시문 공백으로 |
| 장면 고정·지시문만 변경 (LangGap, 우리 대조 시연) | 같은 배치에서 4물체를 번갈아 지시 | 이미 92ep 수집·시연 영상 ①에 포함. 평가 지표로 승격 |
| 층별 프로브 (우리 A5·A6) | 각 층 특징에서 지시 물체 분류 | 소형 VLM에서도 반복 → **어느 층이 결합을 하는지, 몇 층을 풀어야 하는지** |

**우연 수준**은 장면당 2~4물체라 약 35%. 지시문 마스킹 성공률이 이 근처면 언어를 안 쓰는 것이다.

---

## 5. 실행 로드맵

### 5.0 공통 규약

- 평가: **평가 B 60회 프로토콜 그대로**(물체·칸 순서 고정, 처음 보는 배치 24회 포함). 모델당 60회면 95% CI 약 ±12%p라 10%p 차이는 통계적으로 못 가른다 → 두 모델 비교는 **같은 시행 쌍으로 McNemar**.
- 기록: 모델마다 파라미터 수 · 학습 GPU-시간(5090 실측) · 추론 지연(5070 Ti) · VRAM · 완전 성공률 · 지시문 마스킹 성공률. 한 표에.
- 데이터: 392ep 고정. 데이터를 더 모으지 않는다(경량화 효과와 데이터 효과를 분리하기 위해).

### 5.1 단계별

| 단계 | 내용 | 기간 | 산출물 | 성공 기준 |
|---|---|---|---|---|
| **1. GR00T 양자화** | VLM INT8 / INT4 weight-only(GPTQ 또는 bitsandbytes), DiT는 bf16. 추론 지연·VRAM·평가 B 36회 | 1~2주 | 피드백 ① 답변 표 | INT4에서 완전 성공률 하락 ≤ 5%p면 "양자화 가능"으로 보고. 하락 크면 projector/head 민감도(QVLA) 재현으로 보고 |
| **2-a. SmolVLA 미세조정** | LeRobot `smolvla_base` + 392ep. 기본(VLM 동결) vs VLM 위 N층 풀기 vs 비전 인코더 LoRA | 2~3주 | 경량 후보 1 | 평가 B ≥ 60%면 2-c로. 지시문 마스킹 차이 ≥ 20%p |
| **2-b. VLA-Adapter 미세조정** | Qwen2.5-0.5B 백본, 우리 데이터 변환(LeRobot → RLDS/자체 포맷 확인) | 2~3주 (2-a와 병렬) | 경량 후보 2 | 동일 |
| **2-c. 대조군 ACT + 텍스트** | 기존 ACT 코드(P1 `act_so101_t1`)에 NL-ACT 방식으로 mpnet/CLIP 임베딩 추가, FiLM 조건화 | 1주 | "VLM 필요성" 근거 | 지시문 마스킹 차이로 판정. 결과가 어느 쪽이든 보고 |
| **3. 증류** | 2단계 최선 모델을 학생으로, GR00T 392ep **성공 롤아웃**(run.json 필터)을 추가 라벨로 | 2주 | 학생 모델 | 2단계 대비 ≥ +5%p (McNemar) |
| **4. 서보·청크 정밀도** | §3.2 순서. 저크·정착 오차·성공률 표 | 1주 + RL 2주 | 정밀 제어 보고 | 놓친 뒤 종료(6/16) 감소 |
| **5. 비교 보고** | 모든 모델 한 표. "3B가 필요했는가" 결론 | 1주 | 보고서·발표 | — |

총 약 10~12주. 1단계와 2-c는 결과와 무관하게 발표 가치가 있으므로 먼저 한다.

### 5.2 자원 추정 (보고 수치 기반, 실측으로 교체할 것)

| 모델 | 학습(5090 1장) | 추론 VRAM | 근거 |
|---|---|---|---|
| GR00T N1.6 392ep 10ep | 약 55h (1000 step당 48분 × 69k) | bf16 3B, 5070 Ti에서 동작 | 우리 실측 |
| SmolVLA 20k step | 약 4~10h (A100 3.5h · 3090 10h 보고) | batch 16에 4.4GB | 커뮤니티 보고 |
| VLA-Adapter | 미보고. 0.5B라 SmolVLA와 비슷할 것으로 추정 | 낮음(논문 주장) | — |
| ACT + 텍스트 | 수 시간 | < 2GB | P1 경험 |

---

## 6. 반론과 리스크

| 리스크 | 근거 | 대비 |
|---|---|---|
| 소형 모델이 실기에서 시뮬만큼 안 나옴 | VLA-Adapter 저자가 실기 일반화 한계 명시. MiniVLA 실기 과제별 편차 큼. Dasari: 시뮬은 실기 대리 아님 | 시뮬 수치로 모델을 고르지 않고 평가 B로만 판단 |
| 소형 모델이 언어를 무시 | LangGap, 우리 P4 | §4 마스킹 진단을 통과 기준에 넣음 |
| 양자화가 flow 헤드를 망가뜨림 | QVLA, ActQuant | 헤드는 bf16 고정. VLM만 |
| 60회 평가로 차이를 못 가름 | CI ±12%p | 쌍대 비교(McNemar), 필요 시 평가 B를 두 번 |
| 자원 효율을 "학습 시간"으로만 재면 불공정 | GR00T는 사전학습 비용이 숨어 있고, SmolVLA도 30k GPU시간 사전학습 | 보고서에 **미세조정 비용**과 **사전학습 비용**을 분리해 적음 |
| "경량 모델도 결국 남의 사전학습 모델 파인튜닝"이라는 재반론 | 피드백 ②의 본질 | 2-c 대조군(ACT, 사전학습 없음)과 3단계 증류(우리 교사)가 "우리 것"을 만든다 |

---

## 7. 참고 문헌

**양자화**
- Kim et al., *OpenVLA: An Open-Source Vision-Language-Action Model*, 2024 — https://arxiv.org/abs/2406.09246
- *EaqVLA: Encoding-aligned Quantization for VLA Models*, 2025 — https://arxiv.org/abs/2505.21567
- *QVLA: Not All Channels Are Equal in VLA Model's Quantization*, 2026 — https://arxiv.org/abs/2602.03782
- *ActQuant: Sub-4-bit Action-Guided Quantization for VLA Models*, 2026 — https://arxiv.org/abs/2605.24011
- *BitVLA: 1-bit Vision-Language-Action Models*, 2025 — https://arxiv.org/abs/2506.07530
- NVIDIA, *Isaac GR00T N1.7 on Jetson Thor* — https://www.jetson-ai-lab.com/tutorials/groot_n17_on_thor/

**경량 VLA**
- *SmolVLA* (HF, 2025) — https://huggingface.co/blog/smolvla · https://arxiv.org/abs/2506.01844
- *VLA-Adapter: An Effective Paradigm for Tiny-Scale VLA*, 2025 — https://arxiv.org/abs/2509.09372
- *FLOWER: Efficient Vision-Language-Action Flow Policies*, CoRL 2025 — https://arxiv.org/abs/2509.04996
- *TinyVLA*, 2024 — https://arxiv.org/abs/2409.12514
- *MiniVLA* (Stanford) — https://ai.stanford.edu/blog/minivla
- NVIDIA GR00T N1.6 playbook — https://build.nvidia.com/playbooks/gr00t/overview

**비전 인코더·사전학습**
- *VLM4VLA: Revisiting VLMs in VLA Models*, ICLR 2026 — https://arxiv.org/abs/2601.03309
- *SPEAR-1*, 2025 — https://arxiv.org/abs/2511.17411
- *HyperVLA*, 2025 — https://arxiv.org/abs/2510.04898
- *DSPv2*, 2025 — https://arxiv.org/abs/2509.16063
- Shang et al., *Theia: Distilling Diverse Vision Foundation Models for Robot Learning*, CoRL 2024 — https://arxiv.org/abs/2407.20179
- Hansen et al., *On Pre-Training for Visuo-Motor Control*, 2022 — https://arxiv.org/abs/2212.05749
- Dasari et al., *An Unbiased Look at Datasets for Visuo-Motor Pre-Training*, CoRL 2023 — https://arxiv.org/abs/2310.09289
- *X-Distill: Cross-Architecture Vision Distillation*, 2026 — https://arxiv.org/abs/2601.11269

**언어 결합·데이터**
- *LangGap*, 2026 — https://arxiv.org/abs/2603.00592
- *LangForce / BayesianVLA*, 2026 — https://arxiv.org/abs/2601.15197
- Lin et al., *Data Scaling Laws in Imitation Learning for Robotic Manipulation*, ICLR 2025 — https://arxiv.org/abs/2410.18647

**언어 조건 ACT**
- Bharadhwaj et al., *RoboAgent (MT-ACT)*, 2023 — https://arxiv.org/abs/2309.01918
- NL-ACT — https://github.com/krohling/nl-act
- Shi et al., *Yell At Your Robot*, RSS 2024 — https://arxiv.org/abs/2403.12910

**증류**
- *VLA-AD: Offline Semantic Guidance for Efficient VLA Policy Distillation*, 2026 — https://arxiv.org/abs/2605.16241
- *Refined Policy Distillation (RPD)*, 2025 — https://arxiv.org/abs/2503.05833
- *VITA-VLA*, 2025 — https://arxiv.org/abs/2510.09607

**정밀 제어·RL**
- *Real-Time Chunking (RTC)*, 2025 — https://arxiv.org/abs/2506.07339
- *LiPo: Lightweight Post-optimization for Smoothing Action Chunks*, 2025 — https://arxiv.org/abs/2506.05165
- Luo et al., *HIL-SERL*, 2024 — https://arxiv.org/abs/2410.21845
- Wagenmaker et al., *DSRL: Steering Your Diffusion Policy with Latent Space RL*, CoRL 2025 — https://arxiv.org/abs/2506.15799
- Hu et al., *RaC: Scaling Recovery and Correction*, 2025 — https://arxiv.org/abs/2509.07953
- *PLD: Probe, Learn, Distill*, 2025 — https://arxiv.org/abs/2511.14759
- Feetech STS3215 백래시·반복정밀도 측정 — https://github.com/TheRobotStudio/SO-ARM100/issues/134
- LeRobot Feetech 모터 문서(PID 기본값) — https://www.mintlify.com/huggingface/lerobot/motors/feetech

> 수치 표기 원칙: 논문 본문을 직접 읽지 않고 초록·요약으로 확인한 수치는 "보고", 커뮤니티 블로그·이슈 출처는 "커뮤니티 보고"로 적었다. 계획을 실행하기 전에 각 단계에서 인용하는 논문의 표를 직접 확인할 것.
