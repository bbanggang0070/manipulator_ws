# Phase A — T1 씬·에셋 제작 ✅

> 목표: Isaac Sim에 T1 태스크(빨간 큐브 → 오픈박스) 씬을 만들고 육안 검증.
> 계획: [../08_custom_T1_sim2real.md](../08_custom_T1_sim2real.md) §2 · 상위 index: [README.md](README.md)

**상태**: 완료 (2026-07-25) · **실행 위치**: 로컬 5070 Ti (GUI 육안 검증)

---

## 1. 구현 방식 — coworker 포크 블록 씬 (기존 환경과 분리)

계획서는 메인 repo에 `t1_cube_box_env_cfg.py`를 신설하는 안이었으나, coworker가 만든 블록 씬을
**별도 클론**으로 가져와 사용했다. 태스크 개념은 동일(빨간 큐브를 박스에 넣기).

- 클론 위치: `~/blocktask_ws/Sim-to-Real-SO-101-Workshop` (기존 `~/Sim-to-Real-SO-101-Workshop`과 별개)
- 근거: 포크의 `MANAGING_MULTIPLE_ENVIRONMENTS.md` **Method 1(독립 클론)** — 기존 vials 환경을
  건드리지 않아 안전. 두 이미지 모두 `teleop-docker:latest`(Isaac Lab 2.3.2) 동일.
- 태스크 ID: `Lerobot-So101-Teleop-Vials-To-Rack-DR` (coworker가 이 등록을 **블록 씬으로 덮어씀**)
- 런처: `setup/sim/t1_task/blocktask_run.sh` (`view` / `record` / `clear` 모드)

## 2. 씬 커스터마이즈 (`source/sim_to_real_so101/tasks/vials_to_rack_env_cfg.py`)

| 요소 | 최종 설정 | 비고 |
|---|---|---|
| **빨간 큐브** | `CuboidCfg` 20mm, mass 5g, `diffuse_color=(0.9,0.1,0.1)`, spawn `(0.23, 0.0, 0.045)` | 실기 큐브(~2cm)와 크기 일치. mesh 불필요 |
| **오픈박스** | `basket_box.usda`(손수 제작 open box, 바닥+4벽), 100×200×75mm, spawn `(0.10, -0.22, 0.045)` | 큐브가 담기는 컨테이너. root 원점이 박스 바닥 |
| **매트(바닥)** | `mat.usda` 제거 → **kinematic RigidObject 평면** `size=(0.8,1.0,0.005)`, 회색빛 흰색 `(0.85,0.85,0.85)`, pos `(0.20,-0.05,0.0325)` (top=0.035) | 넓게(전 영역 커버)+얇게(5mm) |
| **로봇 색** | 보라색 고정 — base·DR 이벤트 모두 `color_names=["purple"]` | DR에서도 랜덤화 안 함(언어·색 일관) |
| **매트 회전 DR** | `reset_mat_rotation = None` | kinematic 평면은 prim_paths 미보유 → 회전 DR 비활성 |

## 3. 넘긴 함정 (물리 관련)

- **물체가 바닥을 통과·낙하** → GPU 물리(fabric/DIRECT_GPU_API)에서 정적 `AssetBaseCfg`+`CuboidCfg`
  collision이 **미등록**됨. base 씬에 ground plane도 없음. → 매트를 **kinematic RigidObject**로 만들어
  확실한 collision 면 확보.
- **큐브·박스가 바닥 아래로 보임** → 실제로는 LightStudio lightbox 바닥(z≈0.026)이 보이던 것.
  매트 top=0.035에 물체 spawn z(0.045)를 맞춰 해결.
- **`randomize_mat_rotation` 크래시** → kinematic RigidObject는 prim_paths 없음. base·DR 양쪽
  이벤트에서 `reset_mat_rotation` 비활성화(DR cfg가 재추가하던 것도 제거).
- **뷰포트에서 매트 deactivate 시 "Simulation view object is invalidated"** → GPU 물리에선
  런타임 프림 토글 불가. 처음부터 cfg에서 매트를 평면으로 교체하는 방식으로 우회.

## 4. 검증 (게이트 통과)

- `blocktask_run.sh view` (GUI zero_agent)로 씬 렌더링 육안 확인:
  빨간 큐브·오픈박스·**보라색** SO-101·밝은 평면 바닥 정상. 물체 낙하/통과 없음.
- import/cfg 에러 없음, 엔티티 바인딩 정상.

→ **Phase B(데이터 수집)로 진행.** 상세: [B_data_collection.md](B_data_collection.md)
