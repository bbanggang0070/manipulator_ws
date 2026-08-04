# 커스텀 T1 sim 태스크 (빨간 큐브 → 검은 박스)

[03_custom_T1_sim2real.md](../../../manipulator_md/sim2real/03_custom_T1_sim2real.md) Phase A 산출물.
워크숍(`~/Sim-to-Real-SO-101-Workshop`)의 vials_to_rack 태스크를 T1으로 개조한 정본.

## 파일
- `t1_cube_box_env_cfg.py` — 태스크 env cfg 4종(base/DR/Eval/DR-Eval). **신규 파일**, 워크숍
  `source/sim_to_real_so101/tasks/`에 복사.
- `reset_cube_box_snippet.py` — `mdp/resets.py`에 **append**(큐브·박스 리셋; rack 슬롯 의존 없음).
- `gym_register_t1_snippet.py` — `tasks/__init__.py`에 **append**(T1 4종 gym.register).

## 5090 배포 (재현)
```bash
W=~/Sim-to-Real-SO-101-Workshop/source/sim_to_real_so101
# 1) 검은 박스 에셋: tray 복사 후 diffuse_color → (0.02,0.02,0.02)
cp $W/assets/usd/tray.usda $W/assets/usd/tray_black.usda   # 후 diffuse_color_constant 수정
# 2) env cfg 배치
cp t1_cube_box_env_cfg.py $W/tasks/
# 3) 스니펫 append (idempotent — 이미 있으면 skip)
#    reset_cube_box → $W/mdp/resets.py,  gym.register 4종 → $W/tasks/__init__.py
```

## 재사용 설계 (신규 코드 최소화)
- 파지/배치 판정은 vials 함수 재사용: `any_vial_grasped`, `vial_placed_on_rack[_termination]`을
  `vials=["cube"]`, `rack_name="box"`, `vertical_threshold=0.0`(큐브는 방향 무관)로 호출.
- 리셋만 신설(`reset_cube_box`): `reset_vials_rack`은 rack의 `top_*` 슬롯 prim에 의존해 박스 불가.
- 빨간 큐브 = 프리미티브 `CuboidCfg`(USD/mesh 제작 불필요). 검은 박스 = `tray_black.usda`(tray 0.6배).

## 검증 (Checkpoint A)
- **코드 게이트(headless, 2026-07-23 통과)**: `zero_agent --task Lerobot-So101-T1-CubeBox --headless`로
  씬 생성 → 내부 로그에 cube/box/robot/contact_grasp 엔티티 바인딩 + cube_grasped/cube_placed 배선
  확인, 에러 없음. (헤드리스 콘솔 stdout은 버퍼링으로 지연되니 내부 로그 `/tmp/isaaclab/logs/`로 확인)
- **육안 게이트(모니터)**: GUI로 빨간 큐브·검은 박스 위치·색 확인, 큐브를 박스에 옮겨 success=True 확인
  후 판정 경계(`BOX_LOCAL_*`, `cube_pose_range`) 튜닝.

## 튜닝 포인트 (env cfg 상단 상수)
- `CUBE_SPAWN_Z`, `cube_pose_range`(도달범위), `box` init pos/`BOX_SCALE`, `BOX_LOCAL_X/Y/Z_MAX`(성공 경계).
