# Phase C — GR00T N1.6 8-bit 학습 ✅

> 목표: 75ep 블록 데이터로 GR00T N1.6를 단일 5090에서 8-bit Adam 학습.
> 계획: [../08_custom_T1_sim2real.md](../08_custom_T1_sim2real.md) §4 · 상위 index: [README.md](README.md)

**상태**: 완료 (2026-07-25, ~15시간) · **실행 위치**: 원격 5090 (32GB 필요, 로컬 16GB 부족)

---

## 1. 데이터 준비 — v3.0 → v2.1 변환 ✅

`setup/sim/t1_task/prepare_blocktask_gr00t.sh` (vials 80% 모델과 동일 파이프라인):
1. 로컬 v3.0 → 5090 전송 (rsync, 임시 `images/` 제외, 녹화 중 vanished code 24 무시)
2. 컨테이너(`real-robot-train8`) 안에서 `convert_v3_to_v2.py`로 v2.1 변환 (`_v3.0` 백업)
3. `meta/modality.json` 배치: **front ← external_D455**, **wrist ← ego**
4. `stats.json`의 count 제거(GR00T 호환)

**변환 결과 검증**: `codebase_version: v2.1 | episodes: 75 | modality.json: True | stats count: False(정상)`
- 데이터 위치(5090): `~/gr00tn16_ws/sim_data/heongyu/sim_so101_blocktask`

### 넘긴 함정
- rsync "file vanished"(녹화 중 임시 PNG) → `--exclude='images/'` + code 24 허용.
- "Permission denied"(이전 변환의 root 소유 잔여물) → rsync 전 컨테이너로 이전 출력 삭제 단계 추가.

## 2. 학습 설정

스크립트: `5090:~/gr00tn16_ws/train_gr00t_blocktask_n16_8bit.sh`
(검증된 `train_gr00t_sim_n16_8bit.sh`에서 dataset-path·OUT_NAME만 교체)

| 항목 | 값 |
|---|---|
| base-model | `nvidia/GR00T-N1.6-3B` |
| dataset-path | `/data/heongyu/sim_so101_blocktask` (DATA_ROOT=`~/gr00tn16_ws/sim_data`) |
| optimizer | `paged_adamw_8bit` (bitsandbytes, 단일 5090) |
| modality-config | `examples/SO100/so100_config.py` (front/wrist) |
| embodiment-tag | `NEW_EMBODIMENT` |
| max-steps | 20,000 |
| learning-rate | 1e-4 |
| global-batch-size | 2 × gradient-accumulation 32 (유효 배치 64) |
| num-gpus | 1 |
| 컨테이너 | `gr00t-train8` (detached) |
| 출력 | `~/gr00tn16_ws/checkpoints/gr00t_blocktask75_n16_8bit` |

## 3. 학습 추이 (최종)

| 시점 | step | loss | grad_norm | 비고 |
|---|---|---|---|---|
| 시작 직후 | 10 | 1.14 | 0.35 | 샤드 캐싱 완료, 루프 진입 정상 |
| +13분 | ~진행 | 0.15 | ~2.0 | 정상 수렴 |
| **완주** | **20,000** | **0.0073** | ~0.06 | epoch 1.0, 최저 0.0048 |

- 손실 곡선: [report.md D.1](report.md#d-학습-지표--2026-07-25-완주) (`assets/loss_curve.svg`)
- 최종 모델: `~/gr00tn16_ws/checkpoints/gr00t_blocktask75_n16_8bit/checkpoint-20000`

## 4. 게이트 (완주 — 전부 통과 ✅)

- [x] 20k step 완주, OOM 없음 (동일 구성 vials ~22.7GB < 32GB)
- [x] 최종 loss 0.0073 (목표 ~0.005 수준)
- [x] `checkpoint-20000/` 무결성 — optimizer/scheduler/trainer_state/statistics/experiment_cfg 존재

→ **Phase D(sim 추론 확인)로 진행.**
