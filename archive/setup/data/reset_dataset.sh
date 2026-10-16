#!/usr/bin/env bash
# 데이터셋 초기화: record 프로세스 종료 → 로컬 삭제 → HF Hub repo 재생성(빈 private)
# 사용법: ./setup/data/reset_dataset.sh t1     (heongyu/so101_t1_pickplace)
#         ./setup/data/reset_dataset.sh t2     (heongyu/so101_t2_cleanup)
#         ./setup/data/reset_dataset.sh <repo_id>   (임의 repo 직접 지정)
set -u
cd "$(dirname "$0")/../../envs/lerobot" || exit 1

case "${1:-}" in
  t1) REPO="heongyu/so101_t1_pickplace" ;;
  t2) REPO="heongyu/so101_t2_cleanup" ;;
  */*) REPO="$1" ;;
  *) echo "사용법: $0 {t1|t2|<user/repo>}"; exit 1 ;;
esac

echo "⚠️  초기화 대상: $REPO"
echo "   로컬 + HF Hub의 모든 에피소드가 삭제됩니다. 5초 안에 Ctrl+C로 취소 가능..."
sleep 5

# 1. 실행 중인 record 프로세스 종료 (카메라 점유 해제)
pkill -f lerobot-record 2>/dev/null && { echo "── record 프로세스 종료"; sleep 2; }
pkill -9 -f lerobot-record 2>/dev/null

# 2. 로컬 캐시 삭제
LOCAL=~/.cache/huggingface/lerobot/$REPO
if [ -d "$LOCAL" ]; then
  rm -rf "$LOCAL" && echo "── 로컬 삭제: $LOCAL"
else
  echo "── 로컬 없음 (스킵)"
fi

# 3. Hub repo 재생성 (빈 private)
uv run python - "$REPO" <<'EOF'
import sys
from huggingface_hub import HfApi, create_repo
from huggingface_hub.utils import RepositoryNotFoundError
repo = sys.argv[1]
api = HfApi()
try:
    api.delete_repo(repo, repo_type="dataset")
    print(f"── Hub 삭제: {repo}")
except RepositoryNotFoundError:
    print("── Hub에 repo 없음 (스킵)")
create_repo(repo, repo_type="dataset", private=True)
print(f"── Hub 재생성 완료 (빈 private): {repo}")
EOF

echo "✅ 초기화 완료 — 새로 수집을 시작할 수 있습니다."
