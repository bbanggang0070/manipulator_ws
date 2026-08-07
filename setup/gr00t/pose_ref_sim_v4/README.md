# 카메라 정렬 기준 프레임

| 폴더 | 내용 | 용도 |
|---|---|---|
| `pose_ref_sim_v4/` | **현재 sim(v3/v4) 구도** — v4 수집 영상 40개 프레임3의 **중앙값 합성**(블록·박스 제거, 고정 구조만) | **정렬 기준** |
| `pose_ref_v4_aligned/` | 위 기준에 맞춘 **실기 카메라 실제 상태** (2026-08-07) | **드리프트 복구용** |
| `pose_ref_era90/` | 실기 SR 90% 시점 구도 — **v2 시절 sim 기준** | 이력 |

## 왜 era90이 기준일 수 없나

v3에서 sim top 카메라 오프셋이 **(0, 0) → (0.03, 0.02)** 로 바뀌었다.
`era90`은 그 이전 sim에 맞춰 정렬한 실기 구도라 현재 sim과 어긋난다.
실측(08-07): 정렬 후 카메라는 era90 대비 **세로 약 114px** 이동했다.

> **결과**: 기존 실기 데이터 `so101_blocktask_real`(50ep)은 **era90 구도**에서 수집됐다.
> 정렬 후 수집하는 `so101_blocktask_real_v2`와 **카메라 구도가 다르다** —
> co-training에 둘을 섞으면 배포 때 쓰지 않을 구도를 함께 배우게 된다.

## 사용

```bash
cd ~/manipulator_ws/envs/lerobot
uv run python ../../setup/gr00t/rerun_cam_align.py                    # 기준 sim_v4
uv run python ../../setup/gr00t/rerun_cam_align.py --ref era90        # 옛 구도와 비교
uv run python ../../setup/gr00t/rerun_cam_align.py --save-ref <DIR>   # 현재 상태 저장
```

sim은 렌더, 실기는 사진이라 **일치도 상한이 낮다**(1.00 안 나옴).
overlay에서 **벽 모서리·바닥 경계·로봇 베이스가 겹치는지**를 보고, dx·dy는 방향 지시로 쓴다.

## 정렬 기록

| 일시 | 기준 | front 일치 | wrist 일치 | 비고 |
|---|---|---|---|---|
| 2026-08-07 | sim_v4 | 0.24 (dx +6, dy −7) | 0.10 (dx −2, dy −7) | 오버레이에서 팔·그리퍼 일치 확인 |
