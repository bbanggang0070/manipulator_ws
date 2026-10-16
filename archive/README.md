# archive — 지금 파이프라인에서 쓰지 않는 과거 자료

저장소를 배포용으로 정리하면서, 최종 결과물(언어 지시 cleanup — 단일팔·양팔, GR00T N1.6)과
sim2real 과정(Isaac Sim T1 → 실기)에 쓰이지 않는 파일을 이곳으로 옮겼다.
**원래 경로 구조를 그대로 유지**한다 — `archive/setup/gr00t/goto_home.py`는 원래 `setup/gr00t/goto_home.py`였다.

| 경로 | 내용 | 옮긴 이유 |
| --- | --- | --- |
| `model_md/` | Phase 1-0 모델 비교 보고서 (ACT · SmolVLA · π0 · GR00T N1.5) | 모델 선정 단계 기록 — 이후 GR00T N1.6으로 확정 |
| `setup/act/` · `setup/smolvla/` · `setup/pi0/` | 모델별 학습·추론 스크립트 (T1 pick-and-place / T2 cleanup) | 같은 이유 |
| `setup/data/record_t1.sh` · `record_t2.sh` · `reset_dataset.sh` | 모델 비교용 T1/T2 수집 | 같은 이유 |
| `setup/gr00t/` (README · modality.json · goto_home.py · `*_t1_*` · `probe_*.py` · trim_idle_v2.py · `remote_5090/`) | GR00T N1.5 초기 셋업과 일회성 진단 스크립트 | N1.6 전환 후 쓰지 않음 |
| `setup/sim/*_n1d5.sh` | sim GR00T N1.5 학습·평가 | N1.6 스크립트로 대체 |
| `setup/sim/t1_task/` 일부 | zero/diag/GUI 평가 도구, 적용하지 않은 패치 2개 | 어디에서도 참조되지 않음 |
| `setup/common/` · `setup/hardware/wrist_cam_tune.py` · `envs/gr00t/` | 학습 손실 모니터, 손목 카메라 초점 도구, 빈 uv 프로젝트 | 어디에서도 참조되지 않음 (GR00T는 도커 이미지에서 실행) |
| `manipulator_md/sim2real/08_T1_sim2real/assets/eval_run10/` · `eval_v2/` | 보고서에서 링크하지 않은 평가 영상 | 보고서에 쓰인 영상만 원래 자리에 남김 |
| `setup/gr00t/show_safe_region.py` · `infer_save.sh` | 일회성 실기 도구 | 어디에서도 참조되지 않음 |
| `setup/sim/t1_task/` (orchestrate_sweeps.sh · verify_sweep_conditions.py · capture_presets_local.sh · train_..._v3_200_...) | sim 일반화 실험 자동화와 중간 버전 학습 | 어디에서도 참조되지 않거나, 위 자동화 스크립트만 참조 |
| `docs/figures/` (real_rollout_strip.png · lang_scene_catalog.png · evalB_conditions.png · dest_bias_ep17.mp4 · dest_ok_ep11.mp4 · lang_pair4_B6k.mp4) | 9월 sim 일반화·언어 조건화 그림·영상 | 문서에서 쓰이지 않음 (lang_pair4_B6k 는 gif 판을 사용 중) |
| `manipulator_md/real/real_lang_plan_v2_pre_rebalance.csv` | 실기 언어 수집 v2 계획의 균형 조정 전 중간본 | 조정 후 v2·최종 v3 가 원래 자리에 있음 |
| `setup/data/gen_swap6_plan.py` | 색지 교체 검증 1차 설계 생성기 | 2차 설계(gen_swap6_dest_plan.py)로 대체 |
| `manipulator_md/real/archive/` | 단일팔 v2(checkpoint-21000) 평가 결과 | 하위 archive 폴더를 이곳으로 통일 |
| `manipulator_md/real/notion_bi_cleanup_progress.md` | 양팔 151ep 진행 보고 Notion 원고 | Notion 페이지(Capstone ›「양팔 cleanup — 151ep 추론 결과와 300ep 학습 계획」)가 최신본 |

archive 안 문서끼리의 상대 링크는 구조를 그대로 옮겼기 때문에 대부분 유지되지만,
archive 밖(원래 자리에 남은 파일)을 가리키는 상대 링크는 한 단계 어긋날 수 있다.
