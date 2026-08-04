# 워크숍 저장소 로컬 패치

`~/Sim-to-Real-SO-101-Workshop`은 이 repo 밖(NVIDIA 공식 저장소)이라 수정이
버전관리되지 않는다. 여기에 패치를 보관해 **재클론/재설치 시 재적용**할 수 있게 한다.

적용: `cd ~/Sim-to-Real-SO-101-Workshop && git apply <이 디렉터리>/workshop_local_changes.patch`

## workshop_local_changes.patch (2026-07-21)

2개 파일 수정 (recorder VRAM 버그 + 참고용 reset 함수):

### 1. `utils/lerobot_recorder.py` — VRAM 버그 2건
- **버퍼 해제 오타**: `save_episode`/`cancel_recording`이 `self.rgb_buffer_tensor`(단수)를
  비우는데 실제 GPU 버퍼는 `rgb_buffer_tensors`(복수) → 에피소드마다 6.2GiB 누수.
  다음 에피소드가 해제 전에 새로 할당해 순간 12.4GiB 필요 → 16GB GPU에서 2번째
  에피소드에 OOM. 복수형으로 수정 + `torch.cuda.empty_cache()` 추가.
- **버퍼 용량**: 120초 고정(3600프레임/캠=3.09GiB, 2캠 6.2GiB)을 `SIM_RECORD_SECONDS`
  (기본 60)로 조정 가능하게 — 6.18→3.09GiB.

### 2. `mdp/resets.py` — 관절별 시작자세 무작위화 함수 (참고용, 미사용)
- `reset_joints_by_offset_per_joint()`: 관절별로 다른 오프셋 범위 적용.
- ⚠️ **teleop 수집에는 무효**: teleop이 절대 위치 추종이라 리셋 오프셋이 첫 스텝에
  리더암 자세로 덮어써짐(2026-07-21 실측 확인). `tasks/so101_env_cfg.py`의 토글 시도는
  **원복**했다(패치에 미포함). 교정 데이터는 사람이 리더암으로 수동 생성한다.
  이 함수는 RL/autonomous rollout에서 재사용 가능성이 있어 남겨둠.

근거: 실기 GR00T 실패의 근본 원인이 covariate shift(교정 시연 부재)였음
— report/GR00T_report.md §3.2, model_md/sim2real/05_SimToReal.md §0.1.1.

## dockerfile_blackwell_flashattn.patch (2026-07-21)

`docker/real/Dockerfile.blackwell` (real-robot 추론 컨테이너) 빌드 실패 수정.

**증상**: flash-attn 소스 컴파일 중 `#error C++20 or later compatible compiler is
required to use ATen` → 빌드 실패.

**원인**: Dockerfile이 torch를 **버전 고정 없이** `--pre ... nightly/cu130`으로 설치하는데,
그 사이 nightly가 `2.14.0.dev`(C++20 요구)로 드리프트. flash-attn 2.7.4 소스 빌드는
`-std=c++17`이라 충돌. (Isaac-GR00T 자체는 torch==2.7.1+cu128을 핀하지만 Dockerfile이 덮어씀)

**수정**: n1d5에서 검증한 조합으로 교체 —
- torch를 `2.8.0+cu128`로 (Blackwell sm_120 지원, cu130 nightly 불필요)
- flash-attn을 **소스 컴파일 대신 사전빌드 휠**(v2.8.3 cp310/torch2.8/cu12)로

적용: `cd ~/Sim-to-Real-SO-101-Workshop && patch -p0 docker/real/Dockerfile.blackwell < dockerfile_blackwell_flashattn.patch`
(원본은 Dockerfile.blackwell.orig로 백업됨)

## n1d5_client_adapter.patch (2026-07-22)

`source/sim_to_real_so101/utils/lerobot_interface.py` (`GR00TRemotePolicy`) — 워크숍 sim 평가
클라이언트를 **n1d5(N1.5) 서버 프로토콜**에 맞춤. 우리 학습본(gr00t_n1_5)을 n1d5
`inference_service.py` 서버로 서빙하고 워크숍 `lerobot_eval`로 closed-loop 평가하기 위함.

**배경**: 워크숍 클라이언트는 N1.6 워크숍 서버(run_gr00t_server.py) 전용 프로토콜.
n1d5 서버와 3가지 불일치(전송 계층 msgpack numpy는 동일해서 호환):
1. 관측 감싸기: 워크숍 `{"observation":obs,"options":..}` → n1d5는 obs 직접
2. 관측 구조: 워크숍 중첩(`video:{front}`)+(1,1)차원 → n1d5 평면(`video.front`)+(1)차원
3. 액션 응답: 워크숍 `single_arm`(B,T,5) 튜플 → n1d5 `action.single_arm`(T,5) dict
4. reset 엔드포인트: n1d5 서버엔 없음 → 선택적 처리

**적용**: `cd ~/Sim-to-Real-SO-101-Workshop && patch -p0 source/sim_to_real_so101/utils/lerobot_interface.py < n1d5_client_adapter.patch`
(원본 백업: lerobot_interface.py.bak_preadapter)

**검증**: 3ep headless closed-loop 정상 작동(씬 1.5s, 서버 연결·롤아웃·랙배치 확인).
전송 계층은 두 MsgSerializer의 numpy 직렬화(`np.save`→`__ndarray_class__`)가 동일해 호환.
