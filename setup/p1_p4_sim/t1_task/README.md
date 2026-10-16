# sim T1 블록 태스크 (빨간 큐브 → 상자) — 단계별 스크립트

Isaac Sim(coworker 포크 `~/blocktask_ws`의 블록 씬)에서 SO-101로 물체를 상자에 넣는 태스크를
만들고, 실기로 옮기고, 일반화와 언어 조건화까지 넓힌 과정의 스크립트다.
프로젝트 전체 흐름은 루트 [README.md](../../../README.md)의 "프로젝트 흐름", sim 수집 환경을
처음부터 꾸리는 방법은 [deploy.md](../../../manipulator_md/p1_p2_sim_t1/deploy.md)에 있다.

`train_*.sh`·`*_sim_eval.sh`는 5090에서 실행한다(5090 작업 폴더에 복사).

## P1 · P2 — 기본 태스크, 데이터 개선, co-training

| 파일 | 역할 |
| --- | --- |
| `blocktask_fork.patch` | coworker 포크에 적용하는 블록 씬 패치 |
| `blocktask_run.sh` | 씬 보기(`view`) · 리더암 teleop 수집(`record`) · 데이터셋 초기화(`clear`) |
| `diag_block.py` | 씬 배치 진단 (deploy.md 에서 사용) |
| `blocktask_modality.json` · `_blocktask_convert_inner.sh` · `prepare_blocktask_gr00t.sh` | sim 데이터 v3.0 → GR00T v2.1 변환·전송 |
| `../train_gr00t_sim_n16_8bit.sh` | N1.6 8-bit 학습 레시피 — 워크숍 데이터로 검증한 뒤 `--dataset-path` 만 바꿔 **P1 blocktask75** 학습 |
| `blocktask_sim_eval.sh` | sim 무인 평가 |
| `merge_blocktask_v2.py` | v2(mat 낮춤·교정 시연) 데이터 병합 |
| `blocktask_real_modality.json` · `_blocktask_real_convert_inner.sh` · `prepare_blocktask_real_gr00t.sh` | 실기 데이터 변환·전송 |
| `launch_cotrain.py` · `train_gr00t_blocktask_cotrain_n16_8bit.sh` | **P2 최종** — sim v2 + 실기 50ep co-training |

## P3 — 일반화 (위치·박스 DR, 근접 보강, 평가 B)

| 파일 | 역할 |
| --- | --- |
| `configure_scene.py` | 조건 프리셋 씬 설정 (축별 교란, full+X 조합) |
| `blocktask_gui_cond.sh` | 조건별 GUI 추론 — 무인 평가·언어 수집이 쓰는 기준 장면도 만든다 |
| `blocktask_headless_scenes.sh` · `analyze_eval_scenes.py` | 조건별 무인 추론(영상 + scenes.csv)과 분석 |
| `run_evalB.sh` | 평가 B — 고정 패널 15조건 |
| `blocktask_collect_near.sh` · `analyze_dataset_geometry.py` · `selected_35_near.txt` | 블록-박스 근접 배치 타깃 수집과 배치 분석 |
| `merge_blocktask_select.py` · `prepare_blocktask_v4_200.sh` | v4_200 데이터 병합·변환·검증 |
| `train_gr00t_blocktask_v4_200_n16_8bit.sh` | sim 단독 v4_200 학습 (평가 B 대상) |
| `train_gr00t_blocktask_cotrain_v4_n16_8bit.sh` | **P3 최종** — sim v4_200 + 실기 v2_57 co-training |
| `train_gr00t_blocktask_realonly_n16_8bit.sh` | 실기만 학습한 대조군 — 이후 실기 cleanup 을 실기 데이터만으로 하기로 한 근거 |

## P4 — 언어 조건화 (sim)

| 파일 | 역할 |
| --- | --- |
| `hex_prism.usda` · `reset_lang_scene_snippet.py` | 다물체·다상자 언어 씬 |
| `gen_lang_collect_plan.py` · `blocktask_collect_lang.sh` | 계획표(물체·상자·지시문) → 수집 |
| `verify_lang_scene.py` · `verify_lang_dataset.py` · `drop_last_episode.py` | 씬·데이터 검증, 잘못 저장된 마지막 에피소드 제거 |
| `prepare_blocktask_lang.sh` · `train_gr00t_blocktask_lang_n16_8bit.sh` · `ckpt_keep.sh` | **P4 최종** — 파운데이션에서 새로 학습, 언어 곡선용 체크포인트 보관 |
| `gen_lang_eval_plan.py` · `run_eval_lang.sh` | 대응쌍(같은 장면·다른 문장) 무인 평가 |

언어 프로브(같은 관측·다른 지시문의 액션 발산)는 `setup/gr00t/probe_language.py` · `run_probe_sweep.sh`.
