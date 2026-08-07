#!/usr/bin/env bash
# 실기 블록 시연 재수집 v2 — **박스 위치·회전 다양성 포함**. co-training용.
#
# 왜 재수집인가:
#   기존 so101_blocktask_real(50ep)은 **박스가 완전히 고정**이다
#   (실측: 50ep 전체에서 박스 픽셀 중심 편차 x 7px, y 4px).
#   실기 배포에서 박스를 옮길 것이므로, 그 데이터로 co-training하면
#   **박스 다양성이 0인 채로 실기 분포를 배우게 된다.**
#
#   또 sim에서 확인된 병목(블록이 박스에 가까우면 SR 39% vs 원거리 83%)이
#   실기에서 재현되지 않도록, 근접 배치를 **의도적으로 55%** 넣는다.
#
# 배치표: manipulator_md/sim/real_collect_schedule.md  (gen_real_collect_schedule.py로 생성)
#   → 박스 자세 10개 × 6ep = 60ep. **표를 띄워놓고 그대로 따라 놓을 것.**
#     사람이 감으로 놓으면 무의식적으로 비슷한 자리에 몰린다(기존 50ep가 그랬다).
#
# 사용법: ./setup/gr00t/record_blocktask_real_v2.sh [에피소드 수]   (기본 6 = 박스 자세 1개분)
#         ./setup/gr00t/record_blocktask_real_v2.sh 6 resume       (이어서 수집)
# 키보드: →(오른쪽) 조기 종료·저장 / ←(왼쪽) 재녹화 / ESC 세션 종료
#
# 규칙:
#   · **박스 벽에 닿는 배치만 제외**. "붙어 있어 어렵다"고 빼지 말 것 —
#     sim에서 그 판단 때문에 유효 근접 구간이 통째로 걸러졌고 그게 v3의 병목이었다.
#   · 파지 각도가 안 나오면 박스 벽을 피해 **비스듬히 접근**하는 시연을 일부러 보여줄 것.
#   · rerun 뷰만 보고 조작(cheating 방지), 성공 종결만 저장. 정상 ~70% + 교정 ~30%.
#   · ⚠️ **수집 전 카메라 정렬 필수**. 기존 데이터와 같은 구도여야 co-training에서 두 세트를
#     함께 쓸 수 있고, 배포 때도 같은 구도여야 한다.
#       cd ~/manipulator_ws/envs/lerobot
#       uv run python ../../setup/gr00t/rerun_cam_align.py          # 기준 era90
#     overlay/front 를 보며 맞추고, 콘솔의 '일치'가 최대가 되게 한다. 맞춘 뒤 나사 고정.
cd "$(dirname "$0")/../../envs/lerobot" || exit 1

NUM="${1:-6}"
RESUME=""
[ "${2:-}" = "resume" ] && RESUME="--resume=true"

DSNAME="${DSNAME:-so101_blocktask_real_v2}"
DS_ROOT="$HOME/.cache/huggingface/lerobot/heongyu/$DSNAME"

# lerobot-record는 대상 폴더가 이미 있으면 FileExistsError로 죽는다(--resume 없이는).
# 중단된 시도가 meta/info.json만 남기는 경우가 흔해 그때마다 손으로 지우게 되므로 여기서 처리한다.
if [ -d "$DS_ROOT" ] && [ -z "$RESUME" ]; then
  EP=$(python3 -c "import json;print(json.load(open('$DS_ROOT/meta/info.json'))['total_episodes'])" 2>/dev/null || echo 0)
  if [ "$EP" -gt 0 ]; then
    echo "❌ 이미 ${EP}ep 수집된 데이터셋이 있습니다: $DS_ROOT"
    echo "   이어서 수집: $0 $NUM resume"
    echo "   새로 시작(기존 삭제): rm -rf '$DS_ROOT' 후 다시 실행"
    exit 1
  fi
  echo "▶ 빈 폴더 정리(중단된 시도, 0ep): $DS_ROOT"
  rm -rf "$DS_ROOT"
fi

# 배포와 동일한 카메라 (front←top, wrist←wrist)
CAMS='{ top:   {type: opencv, index_or_path: /dev/cam_top,   width: 640, height: 480, fps: 30, fourcc: MJPG},
        wrist: {type: opencv, index_or_path: /dev/cam_wrist, width: 640, height: 480, fps: 30, fourcc: MJPG}}'

cat <<'INFO'

  ┌────────────────────────────────────────────────────────────────┐
  │  배치표를 먼저 띄우세요:                                       │
  │    manipulator_md/sim/real_collect_schedule.md                 │
  │                                                                │
  │  · 박스 자세 1개당 6ep → 다 찍으면 다음 자세로 박스를 옮긴다   │
  │  · 블록은 표의 '근접/보통 XXcm'대로. 방향은 골고루 바꿀 것     │
  │  · 벽에 닿는 배치만 제외. 붙어 있다고 빼지 말 것               │
  └────────────────────────────────────────────────────────────────┘

INFO

# 언어 지시문은 sim과 **완전히 동일**해야 한다 — co-training에서 태스크가 갈리면 안 된다.
# (2026-08-04에 sim 수집이 셸 따옴표 중첩으로 "Pick"만 저장된 사고가 있었다. 여기선 단일 인자라 안전)
exec uv run lerobot-record \
  --robot.type=so101_follower --robot.port=/dev/ttyFOLLOWER --robot.id=follower \
  --robot.cameras="$CAMS" \
  --teleop.type=so101_leader --teleop.port=/dev/ttyLEADER --teleop.id=leader \
  --display_data=true \
  --dataset.repo_id="heongyu/$DSNAME" \
  --dataset.num_episodes="$NUM" \
  --dataset.single_task="Pick up the block and place it in the box" \
  --dataset.episode_time_s=60 \
  --dataset.reset_time_s=25 \
  --dataset.private=true \
  --dataset.push_to_hub=false \
  $RESUME
