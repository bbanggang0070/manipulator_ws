# 5090 원격 서버 스크립트 (π0 async inference)

공용 RTX 5090(32GB, `ssh 5090` = airlab@192.168.0.56)에서 π0를 GPU 추론 서버로 돌리기 위한
서버 측 스크립트. **이 디렉터리가 정본**이고, 5090의 `~/pi0_remote/`로 배포해서 사용한다.
(로컬은 16GB라 π0 추론이 빠듯 → 5090에서 추론, 로봇은 로컬 유지하는 원격 정책 서버 구조.)

## 구성

| 파일 | 역할 | 5090 실행 위치 |
|---|---|---|
| `install_docker.sh` | Docker CE + NVIDIA Container Toolkit 1회 설치 | `bash ~/pi0_remote/install_docker.sh` |
| `pi0-server.sh` | π0 정책 서버 컨테이너 start/logs/stop/status | `~/pi0_remote/pi0-server.sh start` |
| `lerobot-gpu.sh` | 임시 대화형/단발 컨테이너 실행 헬퍼 | `~/pi0_remote/lerobot-gpu.sh [명령]` |

## 배포 방법 (로컬에서)

```bash
scp setup/pi0/remote_5090/*.sh 5090:~/pi0_remote/
ssh 5090 "chmod +x ~/pi0_remote/*.sh"
```

## 이미지 빌드 (1회)

`lerobot-gpu:local` 이미지는 5090의 `~/lerobot`(공식 repo) 기준으로 빌드:

```bash
ssh 5090 "cd ~/lerobot && docker build -f docker/Dockerfile.internal -t lerobot-gpu:local ."
```

## 클라이언트 (로컬, 로봇 연결)

- `../infer_pi0_t1_remote.sh` — T1 zero-shot 원격 추론 (server_address=192.168.0.56:8080)
- `../_robot_client_launcher.py` — so101_follower config 등록 우회 런처

## 전제 조건 메모

- **방화벽**: 5090에서 `sudo ufw allow from 192.168.0.11 to any port 8080 proto tcp`
- **HF 캐시**: `~/.cache/huggingface` (호스트) 마운트. UID 불일치(컨테이너 1001 vs 호스트 1000)로
  `chmod 777 ~/.cache/huggingface` 필요.
- **gated PaliGemma**: π0는 `google/paligemma-3b-pt-224` 토크나이저 필요(gated). 개인 토큰을
  공용 5090에 올리지 않기 위해, 로컬(승인된 계정)에서 토크나이저 파일만 받아 5090 캐시에 복사 +
  서버 `HF_HUB_OFFLINE=1`로 운영.
