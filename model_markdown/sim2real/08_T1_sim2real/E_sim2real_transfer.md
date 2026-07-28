# Phase E — sim→real zero-shot 전이 (실기 SO-101) 🔄

> 목표: sim 학습 N1.6 체크포인트를 실기 로봇에 서빙해 zero-shot 추론.
> 계획: [../08_custom_T1_sim2real.md](../08_custom_T1_sim2real.md) §6 · 상위 index: [README.md](README.md)

**상태**: 배포 파이프라인 완성·부드러운 실기 추론 확인 → **zero-shot 파지는 sim-real gap으로 실패** → 개선 2트랙 진행 중

---

## 1. 배포 구조 (완성)
```
[5090] Gr00tPolicy 서빙(포트 5555) ← 관측(front,wrist,state) → 액션청크
[로컬] eval_lerobot.py → 실기 SO-101(/dev/ttyFOLLOWER) + 카메라(front←cam_top, wrist←cam_wrist)
```
- 서버: `setup/gr00t/serve_blocktask_n16_5090.sh` (+ `serve_blocktask_realclient.py`)
- 클라이언트: `setup/gr00t/infer_gr00t_blocktask_remote.sh` (+ `client/eval_lerobot.py`)
- 카메라 정렬 도구: `setup/gr00t/rerun_cam_align.py` (실기 vs sim 기준 프레임 비교)
- sim 홈: `setup/gr00t/goto_home_sim.py` (사전 점검으로 sim rest 자세 정합)

## 2. 넘긴 함정 (배포 엔지니어링 — 여기가 대부분의 작업)

### 2.1 서버 프로토콜 불일치
- 컨테이너 `run_gr00t_server.py`(PolicyServer)는 obs를 `**kwargs`로 언팩 → 실기 클라이언트의
  평탄 키(`video.front`)와 불일치(`unexpected keyword argument 'video.front'`).
- **수정**: 실기 클라이언트 `service.py`와 동일한 `BaseInferenceServer`로 `Gr00tPolicy`를 감싸는
  전용 서버(`serve_blocktask_realclient.py`) 작성. 입력을 평탄→중첩(video/state/language, state float32,
  language list[list[str]]), 출력을 `single_arm(1,16,5)`→`action.single_arm(16,5)`로 변환. 로봇 없이 합성 테스트로 검증.

### 2.2 모션 끊김 (WiFi 병목 → 3단 대응)
구간별 계측(`obs/exec/wait`)으로 원인 격리:
- **원인**: 로컬↔5090이 **WiFi**(ping 8~185ms 지터, 1.84MB/요청) → get_action RTT 평균 583ms > 실행시간 → 매 청크 정지.
- **대응** (`client/eval_lerobot.py`, env로 on/off):
  1. **JPEG 압축**(`JPEG=1`): 이미지 1.84MB → 수십 KB (전송지연 제거)
  2. **비동기 추론**(`ASYNC=1`): 실행 중 다음 청크 미리 받기 → 정지(stall) 0
  3. **temporal ensembling**(`ENSEMBLE=1`): 매 스텝 관측 + 겹치는 청크 블렌딩 → 청크 경계 튐 제거
- 결과: `obs=1 exec=554 wait=0ms`, rate ~27Hz, rerun 카메라 실시간 → **부드러운 실기 추론 확인**

### 2.3 카메라 정합
- 실기 카메라를 sim 학습 구도에 맞춤(rerun 비교). wrist는 그리퍼 고정 마운트라 조정 폭 작음.

## 3. 결과 — zero-shot 파지 실패 (sim-real gap)
- 블록 **인식·접근은 정상**, 그러나 **그리퍼가 블록 위에서 멈춰 파지 실패**(depth gap).
- `ENSEMBLE_W`↑(2.0)로도 하강 안 됨 → 블렌딩 문제 아님, **깊이 인식 gap 확정**.
- wrist 카메라 고정 마운트라 정렬만으론 한계 → **근본 해법은 데이터**(Phase F 또는 sim 개선).

## 4. 개선 2트랙 (진행 중)

### 4-A. sim SR 자체 개선 (60% → 목표 80~90%)
sim 실패 영상 4개 분석 → **전부 파지 실패**(접근 후 "맴돎", 재시도 못 함). 근본 원인·처방:
| 원인 | 처방 (반영됨) |
|---|---|
| **mat이 로봇과 겹치고 높음**(top 0.035) → 그리퍼 하강 여유 부족 | mat·물체 **top 0.026으로 낮춤**(원본 vials 작동높이) |
| **top 카메라 너무 멂** → 큐브 위치 추정 부정확 | external_D455 **당김**(CAM_X=-0.05, CAM_Z=-0.05 기본값 고정) |
| **교정 시연 부재** → 파지 빗나가면 분포 밖(covariate shift)→맴돎 | **교정 시연 포함 재수집**(정상70+교정30) |
- 재수집: `blocktask_run.sh` (기본 DSNAME=`sim_so101_blocktask_v2`, record 시 폴더 자동 증분으로 append 에러 방지). 원본 75ep은 보존(5090 백업에서 로컬 복원).

### 4-B. 실기 co-training (Phase F) — 도구 준비 완료
기존 실기 50ep은 카메라 각도 달라 못 씀 → 현재 구도로 재수집 필요.
- `record_blocktask_real.sh`(실기 teleop) → `prepare_blocktask_real_gr00t.sh`(변환+전송) →
  `train_gr00t_blocktask_cotrain_n16_8bit.sh`+`launch_cotrain.py`(sim+실기 다중 데이터셋 학습) → 재배포·측정

## 5. 재현 자산
- 포크 전체 변경: `setup/sim/t1_task/blocktask_fork.patch`
- 배포/평가/co-train 스크립트: `setup/gr00t/`, `setup/sim/t1_task/`

> **다음**: sim v2 재수집(mat·카메라·교정 반영) 100ep → 재학습 → sim SR 재측정 → 개선 확인 후 실기 재전이.
