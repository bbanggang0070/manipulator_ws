# setup — 재현용 스크립트 단계별 지도

폴더 이름이 프로젝트 흐름 단계(루트 [README.md](../README.md) "프로젝트 흐름")와,
진행 기록 폴더 `manipulator_md/p*`와 짝을 이룬다. 각 스크립트 머리말에 사용법과 이유가 있다.

| 폴더 | 단계 | 내용 | 진행 기록 |
| --- | --- | --- | --- |
| `hardware/` | 공통 | udev rules · 장치 식별 · 카메라 점검 · teleop | — |
| `gr00t/` | 공통 | GR00T 서빙 · 실기 추론 클라이언트 · 카메라 정렬 (아래 표) | — |
| [`p1_p4_sim/`](p1_p4_sim/t1_task/README.md) | P1~P4 | Isaac Sim T1 — 8-bit 학습 레시피, 워크숍 패치, `t1_task/`(단계별 표) | `p1_p2_sim_t1/` · `p3_generalization/` · `p4_language_sim/` |
| `p5_real_cleanup/` | P5 | 실기 cleanup 단일팔 — 점검 → 계획표 → 수집 → 검증 → 5090 준비·학습 → 평가 | `p5_real_cleanup/` |
| `p6_real_bimanual/` | P6 | 실기 cleanup 양팔 — `data/`(계획표·수집·전달 검사·평가) · `gr00t/`(설정·학습·추론) | `p6_real_bimanual/` |

`train_*.sh` 와 `serve_blocktask_n16_5090.sh` 는 5090에서 실행한다(5090 작업 폴더에 복사).

## `gr00t/` — 단계별로 어디서 쓰나

| 파일 | 역할 | 쓰는 단계 |
| --- | --- | --- |
| `serve_local.sh` · `serve_blocktask_n16_5090.sh` · `serve_blocktask_realclient.py` | 정책 서버 (로컬 5070 Ti / 5090) | P2~P6 |
| `client/service.py` | 서버 통신 클라이언트 (양팔 클라이언트도 이것을 불러 씀) | P2~P6 |
| `client/eval_lerobot.py` | 단일팔 실기 추론 (앙상블·영상·csv 기록) | P2·P3·P5 |
| `fix_stats_for_gr00t.py` | v2.1 변환 뒤 stats 정리 | P1~P6 데이터 준비 |
| `edge_patch.py` | 입력 해상도 패치 | P4 학습 · P5 학습·계획 |
| `infer_gr00t_blocktask_remote.sh` · `goto_home_sim.py` · `record_blocktask_real.sh` | T1 실기 zero-shot 추론·실기 50ep 수집 | P2 |
| `real_pose_align.py` · `rerun_cam_align.py` · `extract_sim_pose.sh` · `extract_real_pose.sh` · `pose_ref*/` | 실기 카메라 구도를 학습 화면에 맞추기 | P2·P3 |
| `record_blocktask_real_v2.sh` · `gen_real_collect_schedule.py` · `goto_home_real.py` | 박스 다양화 실기 수집 (co-training v4) | P3 |
| `run_eval_real.sh` · `home_then_infer.sh` · `analyze_real_run.py` | 실기 평가 실행기(홈 이동 → 추론, 시행 기록) · 시행 분석 | P3 · P5 (`cleanup_eval.py` 가 호출) |
| `probe_language.py` · `run_probe_sweep.sh` | 언어 프로브 — 같은 관측·다른 지시문의 액션 발산 | P4 |
| `goto_home_cleanup.py` | 단일팔 cleanup 홈 자세 | P5 |
