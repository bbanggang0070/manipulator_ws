# Simulator 일반화 성능 확보 — GR00T N1.6 (sim-only)

> **한 줄 목표**: 실기 전이 전에, **시뮬레이터 안에서** pick-and-place의 **높은 성공률**과
> **일반화 성능**을 모두 갖춘 GR00T N1.6 모델을 확보한다.

작성: 2026-08-04 · 상위 진행: [../sim2real/08_T1_sim2real/report2.md](../sim2real/08_T1_sim2real/report2.md)

---

## 1. 배경 & 동기

- 지금까지 GR00T N1.6 VLA로 **sim→real 파이프라인을 완성·검증**했다 (실기 co-training까지, [report2](../sim2real/08_T1_sim2real/report2.md)).
- 그러나 **sim dataset으로 학습한 모델은 "간단한 추론에서 pick&place 성공률 ~80%"만 확인**했고,
  **다양한 환경에서의 일반화 성능은 확인하지 못했다.**
- 일반화를 **실기로 전이한 뒤** 확인하는 것은 **비효율적**이다 — 실기는 리셋·정렬·카메라/팔 드리프트·
  위치 커버리지 제약 등 교란이 크고 시행 비용이 높다 (실기에서 실제로 겪음:
  [report2 §6 관련 실험 로그](../sim2real/08_T1_sim2real/report2.md)).
- 따라서 **시뮬레이터에서 먼저** 성공률·일반화를 끌어올린다. sim은 조건을 프로그램으로 바꿔가며
  **싸고·재현 가능하게·ground-truth 판정**으로 대량 평가할 수 있다.

## 2. 목표

1. **높은 성공률** — 학습 분포 내 pick&place SR을 안정적으로 확보 (현재 sim 80% → 향상).
2. **일반화 성능** — 학습 분포를 벗어난 조건(색·위치·박스 방향·물체·조명)에서도 견디는 정책.
3. 위 둘을 **모두** 만족하는 모델을 확보한 뒤에야 **sim2real + co-training**으로 넘어간다.

## 3. 작업 흐름 (의사결정)

```mermaid
flowchart TD
    A["1) sim-only 모델 추론 재실행<br/>(gr00t_blocktask_v2, 현재 80%)"] --> B{추론 SR 높은가?<br/>(학습 분포 내)}
    B -- 아니오 --> R["2-2) 데이터셋 재수집 + 재학습"]
    B -- 예 --> C{일반화 SR 높은가?<br/>(OOD 조건)}
    C -- 예 --> G["3) 목표 달성 ✅"]
    C -- 아니오 --> D["2-1) 원인 진단<br/>(과적합 vs 데이터 다양성)"]
    D --> D1{같은 분포 held-out<br/>SR 은?}
    D1 -- 높음 --> E["데이터 다양성 부족<br/>→ DR·조건 확대 재수집·재학습"]
    D1 -- 낮음 --> F["학습 부실/과적합<br/>→ 학습 설정 재검토"]
    E --> A
    F --> R
    R --> A
    G --> H["4) sim2real 전이 → co-training<br/>(기존 파이프라인 재사용)"]
```

### 단계별 정의

- **1. 추론 재실행 & 일반화 확인** — sim-only 모델(`gr00t_blocktask_v2_n16_8bit`)로 sim closed-loop
  평가. 학습 분포 내 SR과 OOD 조건 SR을 **각각** 측정한다.
- **2-1. 추론 O / 일반화 X → 원인 진단.** "VLM 과적합"인지 "데이터 다양성 부족"인지는 **아래 §5 기준**으로 가른다.
  (결론부터: 광범위 사전학습된 백본 특성상 순수 VLM 암기 과적합은 드물고, 대개 **파인튜닝이 좁은 sim
  분포에 특화**된 것 → 해법은 **더 다양한 데이터 + 도메인 랜덤화**.)
- **2-2. 추론 X / 일반화 X → 재수집·재학습.** 학습 자체가 부실 → 데이터셋 수집 계획부터 다시.
- **3. 추론 O / 일반화 O → 목표 달성.**
- **4. sim2real + co-training** — 3 달성 시, 실기 전이 후 [report2](../sim2real/08_T1_sim2real/report2.md)에서
  검증한 방식(zero-shot 전이 → 실기 데이터 co-training)을 그대로 적용.

## 4. 일반화 평가 조건 (OOD 축)

각 조건 N회, 블록/물체 위치 무작위, 배포 설정 고정(유일 변수를 '조건'으로).
씬 편집 지점은 [deploy.md §8](../sim2real/08_T1_sim2real/assets/deploy.md) 참조
(`vials_to_rack_env_cfg.py`).

| 축 | 조건 예 | sim 편집 지점 | 난이도 |
|---|---|---|---|
| **위치(공간 커버리지)** | 도달범위 전역 격자 | `reset_block_position` / `BLOCK_REACH_*` | 쉬움 (sim 최대 강점) |
| **큐브 색상** | 빨강 외 5색 | `block_red.spawn.visual_material.diffuse_color` | 쉬움 |
| **박스 방향** | 45° / 90° 회전 | `basket_black.init_state.rot` | 쉬움 |
| **물체 종류** | 다른 소형 물체(YCB류) | `block_base`(CuboidCfg→USD/프리미티브) | 중간 |
| **조명/외형** | 노출·색온도·텍스처·카메라 지터 | `-DR-Eval` 태스크(이미 존재) | 이미 있음 |

> 언어 지시문은 학습(`"Pick up the block..."`)과 **동일 고정** — 색/물체 실험은 *시각 일반화*를 깨끗이 본다.
> (색·물체명 지시문 추종은 별개 축.)

## 5. 진단 기준 — "과적합" vs "데이터 다양성 부족" 가르기 (2-1)

추론은 되는데 일반화가 안 될 때, **같은 분포에서 뽑은 held-out 에피소드**로 평가해 원인을 가른다:

| 학습분포 내 SR | held-out(같은분포) SR | OOD SR | 해석 | 조치 |
|---|---|---|---|---|
| 높음 | **높음** | 낮음 | **분포는 잘 배웠으나 학습 분포가 좁음** (사실상 좁은 분포 과적합) | **데이터 다양성↑ + DR** 재학습 (2-1) |
| 높음 | **낮음** | 낮음 | 학습셋 암기(진짜 과적합) 또는 데이터 규모/학습 부실 | 정규화·데이터 규모·학습 설정 재검토 (→ 2-2 근접) |
| 낮음 | 낮음 | 낮음 | 학습 자체 실패 | **재수집·재학습** (2-2) |

- 실무적으로 GR00T처럼 **광범위 사전학습 VLM**은 순수 암기 과적합이 드물다 → 대부분 **첫 행(다양성 부족)**.
  이때 정답은 **"더 다양한 sim dataset(색·위치·물체·조명 폭 확대) + 도메인 랜덤화(DR)"**.
- 실기에서 관찰한 선례: 50ep 실기 데이터는 **블록 위치 커버리지가 좁아**(깊이 한 띠) 그 밖 위치에서
  실패 — 데이터 커버리지가 일반화를 좌우함을 이미 확인. sim에선 이를 **위치 격자 스윕**으로 정량화 가능.

## 6. 도구 · 모델 · 참조

- **평가 모델**: `gr00t_blocktask_v2_n16_8bit/checkpoint-20000` (sim-only, 현재 sim SR 80%). 5090 보관.
- **sim closed-loop 평가**: `setup/sim/t1_task/blocktask_sim_eval.sh <MODEL> <N> [eval|dr]`
  (real-robot 서버 + teleop-docker `lerobot_eval`, **성공률 자동 집계**). `-DR`은 조명·외형 랜덤화.
- **데이터 수집 환경 재현**: [deploy.md](../sim2real/08_T1_sim2real/assets/deploy.md) (Isaac Sim T1 blocktask).
- **씬 커스터마이즈 편집점**: [deploy.md §8](../sim2real/08_T1_sim2real/assets/deploy.md).
- **sim2real 계획(모델 비교)**: [../../model_md/sim2real/05_SimToReal.md](../../model_md/sim2real/05_SimToReal.md).
- **실기 파이프라인 선례(co-training)**: [../sim2real/08_T1_sim2real/report2.md](../sim2real/08_T1_sim2real/report2.md).

## 7. 진행 현황

| 단계 | 상태 | 비고 |
|---|---|---|
| 1. sim-only 추론 재실행 + 일반화 측정 | ⬜ 예정 | 학습분포 내 SR / OOD SR 각각 |
| 2-1/2-2. 원인 진단 → 데이터·학습 조정 | ⬜ | §5 기준으로 분기 |
| 3. 추론·일반화 모두 확보 | ⬜ | 목표 |
| 4. sim2real + co-training | ⬜ | 3 달성 후 |
