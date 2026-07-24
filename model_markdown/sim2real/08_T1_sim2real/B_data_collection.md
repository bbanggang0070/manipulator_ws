# Phase B — 리더암 teleop 데이터 수집 ✅

> 목표: 리더암(`/dev/ttyLEADER`)으로 T1 블록 씬을 조종해 학습 데이터 수집.
> 계획: [../08_custom_T1_sim2real.md](../08_custom_T1_sim2real.md) §3 · 상위 index: [README.md](README.md)

**상태**: 완료 (2026-07-25) · **실행 위치**: 로컬 5070 Ti (리더암·GUI 로컬 필수)

---

## 1. 결과 데이터셋

| 항목 | 값 |
|---|---|
| repo_id | `heongyu/sim_so101_blocktask` |
| 위치(로컬) | `~/blocktask_ws/Sim-to-Real-SO-101-Workshop/datasets/sim_so101_blocktask` |
| 포맷 | LeRobot **v3.0** (recorder 기본, lerobot 0.4.3) |
| 에피소드 | **75ep** (계획 50 → 75로 상향) |
| 프레임 | 25,549 @ 30fps |
| 카메라 키 | `observation.images.ego`(wrist) · `observation.images.external_D455`(front) |

- 수집 도구: `setup/sim/t1_task/blocktask_run.sh record`
  (`Lerobot-So101-Teleop-Vials-To-Rack-DR` + `--rerun` + `/dev/ttyLEADER`)
- 태스크 언어: 블록 pick&place (빨간 큐브 → 오픈박스)

## 2. 수집 중 실시간 카메라 뷰 (rerun)

가상 카메라(ego/external_D455) 시점을 보며 녹화하도록 **rerun** 연동.
- `scripts/lerobot_agent.py`에 `--rerun` 인자 + `init_rerun` + 루프에서 `obs["visual"]` rgb 로깅 추가.

## 3. 넘긴 함정

### 3.1 2번째 에피소드 녹화 시 CUDA OOM
- 원인: `lerobot_recorder.py`에서 프레임 버퍼 해제 **오타** — `rgb_buffer_tensor`(단수)만 비우고
  실제 축적되는 `rgb_buffer_tensors`(복수)는 안 비워 GPU 메모리 누적.
- 조치: `save_episode`/`cancel_recording`에서 `self.rgb_buffer_tensors = {}` + `torch.cuda.empty_cache()`,
  버퍼 용량 `self.capcity = 60 * self.fps`(기존 2분→60초)로 축소.

### 3.2 키 매핑 (직관적 저장/취소)
`utils/keyboard.py` 재매핑:
| 키 | 동작 |
|---|---|
| `S` | 녹화 시작 |
| `→` (RIGHT) | 녹화 중지 **+ 저장** |
| `←` (LEFT) | 녹화 중지 **+ 삭제**(discard) |
| `R` | 리셋 + 진행 중 녹화 취소 |

### 3.3 wrist(ego) 카메라 90° 반시계 회전
- 증상: 실기 학습 데이터는 wrist 카메라가 gripper 정면(위)을 봤는데, sim에선 leader-rest 상태에서
  joint5(Wrist_Roll)가 로봇 기준 반시계 90°로 돌아가 있어 rerun wrist 뷰가 기울어짐.
- 근본 원인: `init_state`의 Wrist_Roll = **-1.6034 rad**인데 leader-rest 매핑은 midpoint **0°** →
  약 91.9° 불일치.
- 조치: **관절 매핑에 오프셋** (`utils/lerobot_interface.py`)
  - forward(`get_mapped_actions_vectorized`): `rad[...,4] -= 1.6034` (sim follower wrist를 카메라-위 방향으로)
  - reverse(`get_raw_actions_from_radians`): `raw_values[...,4] += 1.6034` (되돌려 **기록 데이터는 leader/실기 프레임 유지**)
  - 카메라 offset(euler[-45,0,0])은 **원복** — 매핑으로만 해결.
- 검증: rest에서 wrist state[4] ≈ -0.322(≈0), action[4]≈state[4]. rerun에서 gripper 정면 뷰 확인.

## 4. co-training 안전성 확인 (Phase F 대비)

관절 매핑·이미지 롤 수정이 나중에 **sim+실기 혼합 학습**에 문제되지 않음을 확인:
- reverse-undo(+1.6034)가 forward 오프셋을 정확히 상쇄 → **기록된 action/state는 leader/실기 프레임**.
- **바뀐 것은 sim 렌더링 시점뿐**, 저장 데이터의 좌표계는 실기와 동일.
- 추후 sim·실기 두 데이터셋 확보 시 wrist_roll rest 값을 비교·정렬할 것(§Phase F).

## 5. 게이트 통과

- 75ep 성공 종결 저장, `info.json` total_episodes=75.
- 무작위 ep 재생: ego 카메라 upright, wrist rest≈0, 큐브 빨강 고정 확인.
- (참고) AV1 코덱 mp4는 하이브리드 그래픽에서 VLC 검은화면 → **mpv** 권장.

→ **Phase C(GR00T N1.6 학습)로 진행.** 상세: [C_training.md](C_training.md)
