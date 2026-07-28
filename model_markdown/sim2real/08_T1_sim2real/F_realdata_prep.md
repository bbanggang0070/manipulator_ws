# Phase F 준비 — 실기 데이터 사전 제작 주의사항 (co-training용)

> real gap 대비 실기 시연 데이터를 미리 수집해두기 위한 체크리스트. sim v2 재학습과 병행 준비.
> 배경: [report2.md](report2.md) · 전이 시도: [E_sim2real_transfer.md](E_sim2real_transfer.md) · 상위: [README.md](README.md)

작성: 2026-07-28

**왜 지금**: v2 sim 모델이 sim SR은 개선돼도 real gap(카메라 구도·물리·노이즈)은 남을 확률이 높다.
실기 데이터를 미리 두면 전이 부족 시 **즉시 co-training** 가능.

**핵심 한 줄**: *카메라를 sim v2 뷰에 맞춰 **고정** → 그 상태로 수집·배포 모두 → **파지 쉬운 높이** + **교정 시연** 포함.*

---

## ⭐ A. 카메라 (가장 중요 — 지난 실패의 직접 원인)
- **지난 실기 50ep(`so101_t1_pickplace`)이 폐기된 이유 = 카메라 각도 불일치.** co-training은 실기 카메라
  뷰로 학습되므로, 실기 카메라는 **①sim 뷰와 최대한 유사 + ②배포 때와 동일**이어야 한다.
- **top(front)**: sim external_D455를 원래 위치로 원복했으니, 실기 top도 그 원래 sim 구도(각도·거리·높이)에
  맞춘다. `setup/gr00t/rerun_cam_align.py`로 `sim_ref_front`와 비교하며 **큐브 크기·위치를 일치**.
- **wrist**: 그리퍼 고정 마운트 — sim ego 뷰(집게 아래, 대상 상단중앙)와 방향 일치 확인.
- ⚠️ **수집 후 카메라를 절대 움직이지 말 것.** 수집 카메라 위치 = 배포 카메라 위치. 움직이면 데이터가 또
  못 쓰게 됨. → **먼저 카메라 확정 → 그 뒤 수집.**
- 해상도·fps: **640×480, 30fps** (sim과 동일, record 스크립트에 설정됨).

## B. 물리 씬 (sim과 매칭)
- **물체**: 빨간 큐브 ~2cm(sim 20mm), 어두운 박스(sim basket 크기 유사) — 색·크기 최대한 일치.
- **파지 높이** ⚠️: sim에서 mat 낮춰 그리퍼 하강 여유를 준 것처럼, 실기도 **그리퍼가 큐브까지 끝까지
  내려가 잡히는** 테이블/물체 높이 확보 (물리적으로 파지가 쉬워야 깔끔한 시연이 나옴).
- **배치**: 5지점 그리드(작은 마킹) 순환, 박스 위치 고정. **배경·조명 일정하게.**

## C. 로봇 상태·캘리브레이션 정합
- 실기 팔로워 **캘리브레이션을 바꾸지 말 것** (재캘리브 시 좌표 어긋남 → sim과 프레임 불일치).
- 정합 유지: wrist_roll rest sim(0.6)≈실기(1.0), state/action 6-dim, 단위 `.pos`(도).

## D. 데이터 품질·구성 (sim v2와 동일 교훈)
- **깔끔·결단력 있는 파지**(한 번에), 일관된 접근각. 머뭇/다회시도 시연은 넣지 않기.
- **교정(recovery) 시연 ~30% 필수** — 살짝 빗나감→재접근→성공. **실기는 노이즈가 커서 재시도 학습이 특히 중요.**
- **성공 종결만 저장**, idle 최소화(녹화 즉시 동작 개시).
- ⚠️ **rerun 카메라 뷰만 보고 teleop** — 실기 로봇을 눈으로 직접 보며 조작하면 정책이 못 쓰는 정보를
  쓰는 셈(cheating). 반드시 카메라 피드만 보고 조작.

## E. 수집 규모·혼합
- co-training은 **소량 실기로도 효과** (문헌: sim 70~100 + real 5~10, 또는 sim50+real50).
- 권장 **20~50ep**, 5지점 균등 커버(편중 금지). 부족하면 학습 시 실기 `mix_ratio`↑로 보완.

## F. 파이프라인 (도구 준비됨)
| 단계 | 도구 |
|---|---|
| 수집 | `setup/gr00t/record_blocktask_real.sh` (top/wrist, 언어=sim 일치 "Pick up the block and place it in the box", repo_id `heongyu/so101_blocktask_real`) |
| 변환 | `setup/sim/t1_task/prepare_blocktask_real_gr00t.sh` (v3→v2.1 + modality top→front/wrist→wrist) |
| co-train | `setup/sim/t1_task/train_gr00t_blocktask_cotrain_n16_8bit.sh` + `launch_cotrain.py` (sim_v2 + 실기 다중 데이터셋) |
- co-train 스크립트의 sim 데이터는 **`sim_so101_blocktask_v2`**(새 것)를 사용하도록 반영됨.

## G. 타이밍 주의
- ⚠️ **카메라를 확정한 뒤** 수집. 카메라가 또 바뀌면 실기 데이터를 다시 만들어야 함.
- 지금 sim 카메라를 원복했으니, **실기 카메라를 그 구도로 맞춰 고정** 후 수집 시작.

---

## 실행 순서 (요약)
1. 실기 카메라(top/wrist)를 sim v2 뷰에 맞춰 **고정** (`rerun_cam_align.py`로 큐브 크기·위치 일치)
2. 파지 쉬운 높이로 씬 세팅 → `record_blocktask_real.sh`로 **20~50ep**(정상 ~70% + 교정 ~30%) 수집
3. `prepare_blocktask_real_gr00t.sh`로 v2.1 변환·전송
4. (v2 sim 전이 부족 시) `train_gr00t_blocktask_cotrain_n16_8bit.sh`로 **sim_v2 + 실기 co-training**
5. 실기 재측정 → §10 결과표 채움
