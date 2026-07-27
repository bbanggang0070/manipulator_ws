# 08 T1 Sim-to-Real — Phase별 진행 기록

[08_custom_T1_sim2real.md](../08_custom_T1_sim2real.md) 계획(6 Phase)의 **실제 실행 기록**을
Phase가 끝날 때마다 한 파일씩 정리한다. 계획서는 "무엇을 할지", 이 폴더는 "무엇을 했고 어떤
함정을 넘겼는지"를 담는다.

## 진행 현황

| Phase | 내용 | 상태 | 기록 |
|---|---|---|---|
| **A** | T1 씬·에셋 제작 (빨간 큐브 → 오픈박스) | ✅ 완료 | [A_scene_asset.md](A_scene_asset.md) |
| **B** | 리더암 teleop 데이터 수집 (75ep) | ✅ 완료 | [B_data_collection.md](B_data_collection.md) |
| **C** | GR00T N1.6 8-bit 학습 (loss 0.0073) | ✅ 완료 | [C_training.md](C_training.md) |
| **D** | sim 추론 확인 (Eval 60% / DR-Eval 50%) | ✅ 완료 | [report.md](report.md) E절 |
| **E** | sim-to-real 전이 (실기) | ⏳ 대기 | (D 후 작성) |
| **F** | (성능 부족 시) 실기 co-training | ⏳ 대기 | (E 판단 후) |

## 계획 대비 실행상의 주요 결정

- **환경 구현체**: 계획서의 `t1_cube_box_env_cfg.py`(메인 repo 신규 태스크) 대신,
  **coworker 포크의 블록 씬**(`Lerobot-So101-Teleop-Vials-To-Rack-DR` 등록을 블록 씬으로 덮어씀)을
  별도 클론(`~/blocktask_ws`)으로 사용. 태스크 개념(빨간 큐브→박스)은 동일. 기존 환경(`~/Sim-to-Real-SO-101-Workshop`)과 완전 분리 → 안전. 근거: 포크의 `MANAGING_MULTIPLE_ENVIRONMENTS.md` Method 1.
- **수집 규모**: 계획 50ep → 실제 **75ep** 수집.
- 상세는 각 Phase 파일 참조.
