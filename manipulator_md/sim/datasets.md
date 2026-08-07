# 학습 데이터셋 카탈로그

> 실제로 **학습에 투입된 최종 데이터셋**(LeRobot v2.1)을 버전별로 정리한 목록.
> 수집 세션 원본(v3.0)과 구분한다.
>
> 최종 갱신 2026-08-07 · 관련: [보고서](README.md) · [v4 수집 계획](collection_plan_v4.md)

---

## 1. 저장 위치

| 종류 | 경로 | 포맷 |
|---|---|---|
| **학습용 최종본** | `~/blocktask_ws/Sim-to-Real-SO-101-Workshop/datasets/_train/<버전>/` | **v2.1** (GR00T) |
| 수집 세션 원본 | `~/blocktask_ws/.../datasets/sim_so101_blocktask_*` | v3.0 (LeRobot 수집) |
| 5090 학습 마운트 | `~/gr00tn16_ws/sim_data/heongyu/<원래 이름>` | v2.1 |

`datasets/`는 fork의 `.gitignore` 대상이라 저장소를 오염시키지 않는다.
로컬 사본은 **백업 겸 재현용**이고, 학습은 5090의 사본으로 돌아간다.

---

## 2. 목록

| 폴더 (`_train/`) | 5090 이름 | ep | frames | 용량 | 학습 모델 | 결과 |
|---|---|---|---|---|---|---|
| `v1_sim75` | `sim_so101_blocktask` | 75 | 25,549 | 202M | `gr00t_blocktask75_n16_8bit` 20k | 초기 검증 |
| `v2_sim100` | `..._v2` | 100 | 30,887 | 259M | `gr00t_blocktask_v2_n16_8bit` 20k | sim SR ~80%, **위치 OOD 10~30% 붕괴** |
| **`v3_sim100`** | `..._v3` | 100 | 38,906 | 351M | **`gr00t_blocktask_v3_n16_8bit` 40k** | loss 0.0054 · **OOD 82.5% / full 61~67%** |
| `v3_200_sim200` | `..._v3_200` | 200 | 83,222 | 765M | (미학습) | 대조군 후보 — 같은 200ep, 근접 보강 없음 |
| **`v4_200_sim200_near`** | `..._v4_200` | 200 | 82,951 | 750M | **`gr00t_blocktask_v4_200_n16_8bit` 86k** 🔄 | 진행 중 |
| `real50` | `so101_blocktask_real` | 50 | 21,175 | 179M | `gr00t_blocktask_cotrain_n16_8bit` 20k | 실기 **10% → 90%** |

합계 2.5GB. 전 항목 **parquet 수 = mp4/2 = 에피소드 수**, `modality.json` 존재 확인 완료.

---

## 3. 버전별 구성

### `v1_sim75` (75ep)
초기 블록 태스크. 박스 고정, DR 없음. 파이프라인 검증용.

### `v2_sim100` (100ep)
블록 스폰 r 0.20~0.32 / θ −0.5~0.70, 박스 **고정** (0.10, −0.22), 물리 DR 없음,
top 카메라 오프셋 **0**.

> 이 카메라 설정 때문에 **현재 씬으로 재측정하면 부당하게 낮게 나온다**(오프셋 0.03/0.02와 불일치).
> v2 재측정을 포기한 이유다.

### `v3_sim100` (100ep) — 현 기준 모델
수집 세션 `v3`(82) + `v3_2`(18). 씬을 대폭 개조한 첫 버전:
블록 r 0.16~0.34 / θ −0.7~1.25, 박스 arc 랜덤 + yaw ±180°, 물리 DR, 카메라 오프셋 고정.

**근접(블록-박스 <0.18m) 비율 19.2%** — 씬의 자연 분포 43.2%의 절반 미만.
수집 시 겹침 ep를 제외하면서 유효 근접까지 걸러진 결과이고, 이것이 v3의 병목이 됐다.

### `v3_200_sim200` (200ep) — 미학습
231ep에서 **품질** 기준 선별(길이 이상치 6개 + 시작 idle 큰 25개 제외).
분포는 v3와 동일하므로 **근접 보강이 없다.**

> **대조군으로서의 가치**: `v4_200`과 ep 수가 같아, 같은 86k로 돌리면
> 변수가 **'근접 비율' 하나**로 깨끗하게 남는다. v4의 효과를 데이터 양과 분리하려면 이것을 쓴다.

### `v4_200_sim200_near` (200ep) — 현재 학습 중
**근접 구성을 의도적으로 보강**한 재구성본.

| 출처 | ep | 근접(<0.18m) |
|---|---|---|
| `v3` 기존 학습셋 전체 | 100 | 19 |
| 잔여(v3_3 6 + v3_4 29)에서 **근접 우선 선별** | 35 | 35 |
| **v4 신규 타깃 수집**(`v4_near_3`) | 65 | 55 |
| **합계** | **200** | **109 = 54.5%** |

- v3의 19.2% → **2.8배**, 자연 분포 43.2% 대비 **1.26배 오버샘플**(의도적)
- 원거리 91ep로 v3의 80ep보다 **많아** 퇴행 위험 통제
- 선별 목록: `setup/sim/t1_task/selected_35_near.txt`
- **231ep 전부를 쓰지 않았다** — 오래된 원거리가 분모만 키워 근접 비율을 39%로 희석시킨다

### `real50` (50ep)
실기 SO-ARM101 수집. sim 데이터와 함께 co-training에 사용.
[report2 §5](../sim2real/08_T1_sim2real/report2.md): sim-only 10% → co-training **90%**.

---

## 4. 수집 세션 원본 (v3.0)

병합 전 원본. 재구성이 필요할 때의 소재다.

| 세션 | ep | 사용처 |
|---|---|---|
| `sim_so101_blocktask` | 75 | v1 |
| `..._v2` / `_v2_2` / `_v2_3` | 100 / — / — | v2 |
| `..._v3` / `_v3_2` | 82 / 18 | **v3 (100ep)** |
| `..._v3_3` / `_v3_4` | 31 / 100 | v3_200, **v4_200에 35ep 선별 투입** |
| `..._v4_near` / `_v4_near_2` / `_v4_near_3` | — / — / **65** | **v4_200** |

`v4_near`·`v4_near_2`는 시행착오 폴더로 실사용분은 **`v4_near_3` 65ep**이다.

---

## 5. v3.0 → v2.1 변환

수집은 LeRobot v3.0, 학습은 v2.1이라 변환이 필요하다.

```bash
python /gr00t/scripts/lerobot_conversion/convert_v3_to_v2.py --repo-id heongyu/<이름> --root /data
cp blocktask_modality.json <DS>/meta/modality.json      # external_D455→front, ego→wrist
python fix_stats_for_gr00t.py <DS>                       # stats.json의 count 제거
```

> ⚠️ **병합본에는 이 후처리가 자동으로 따라오지 않는다.** `merge_blocktask_v2.py`는
> `modality.json`을 넣지 않고 `stats.count`도 남긴다(세션별 변환 때 한 것은 세션 파일에만 적용).
> 그대로 학습을 걸면 GR00T가 modality를 못 찾아 **한참 뒤에 실패한다.**
> → `prepare_blocktask_v4_200.sh`가 병합 후 자동 적용하고, 학습 스크립트에도 선확인 게이트가 있다.

---

## 6. 검증 방법

```bash
# 개수·메타 정합
python3 -c "import json;j=json.load(open('<DS>/meta/info.json'));print(j['codebase_version'],j['total_episodes'],j['total_frames'])"
ls <DS>/data/chunk-000/*.parquet | wc -l        # = total_episodes
find <DS>/videos -name '*.mp4' | wc -l          # = total_episodes × 카메라 수(2)

# 언어 지시문 절단 확인 (2026-08-04 버그)
cat <DS>/meta/tasks.jsonl        # "Pick up the block and place it in the box" 전문이어야 함

# 배치 분포 (근접 비율)
python3 setup/sim/t1_task/analyze_dataset_geometry.py <datasets_root> <tmp> <보정소스...>
```

**언어 지시문 절단**은 실제로 발생했던 버그다 — 셸 따옴표 중첩으로 `"Pick"`만 저장돼
원본 75ep·v2·v3가 모두 영향받았다. 수집 후 **메타 검증은 필수**다.
