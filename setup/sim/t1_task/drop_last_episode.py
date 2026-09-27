"""LeRobot v3.0 데이터셋에서 **마지막 에피소드 1개**를 정합성을 지키며 제거한다.

왜 마지막만인가:
  각 에피소드 메타에는 전역 프레임 구간(`dataset_from_index`/`dataset_to_index`)이 박혀 있다.
  중간 것을 지우면 그 뒤 전부를 다시 매겨야 하지만, **마지막은 뒤가 없어 그대로 끝난다.**
  그래서 이 도구는 마지막 1개만 다룬다. 중간 에피소드를 빼야 하면 재변환이 맞다.

무엇을 지우나 (4개 + 메타 2개):
  data/<chunk>/file-N.parquet
  videos/observation.images.ego/<chunk>/file-N.mp4
  videos/observation.images.external_D455/<chunk>/file-N.mp4
  meta/episodes/<chunk>/file-N.parquet
  meta/info.json          total_episodes -1, total_frames -길이
  (stats.json은 건드리지 않는다 — 아래 주의 참고)

⚠️ stats.json: 전체 프레임 집계라 1 에피소드를 빼면 아주 조금 어긋난다(281ep 기준 0.35%).
   평균·표준편차가 그만큼 움직이지 않으므로 그대로 둔다. 학습용 v2.1 변환 단계에서
   어차피 후처리(fix_stats_for_gr00t.py)를 거친다.

사용:
  python drop_last_episode.py <데이터셋경로>            # 미리보기만(기본)
  sudo python drop_last_episode.py <데이터셋경로> --apply   # 실제 삭제
"""
import argparse
import glob
import json
import os
import re
import sys

import pandas as pd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--apply", action="store_true", help="실제로 지운다(기본은 미리보기)")
    a = ap.parse_args()
    R = os.path.expanduser(a.root)

    ep_files = sorted(glob.glob(f"{R}/meta/episodes/**/*.parquet", recursive=True))
    if not ep_files:
        sys.exit(f"❌ meta/episodes 없음: {R}")
    eps = pd.concat([pd.read_parquet(f) for f in ep_files]).sort_values("episode_index")
    last = eps.iloc[-1]
    n = int(last.episode_index)
    length = int(last.length)

    info = json.load(open(f"{R}/meta/info.json"))
    if int(info["total_episodes"]) != len(eps):
        sys.exit(f"❌ info.json({info['total_episodes']})과 meta/episodes({len(eps)})가 불일치 — 먼저 정합성부터")
    if n != len(eps) - 1:
        sys.exit(f"❌ 마지막 episode_index({n})가 개수-1({len(eps)-1})과 다르다 — 결번이 있다")

    # 지울 파일 모으기. 경로는 meta에 박힌 chunk/file 인덱스가 아니라 실제 파일명으로 찾는다.
    targets = []
    for pat in (f"{R}/data/**/*.parquet",
                f"{R}/videos/observation.images.ego/**/*.mp4",
                f"{R}/videos/observation.images.external_D455/**/*.mp4",
                f"{R}/meta/episodes/**/*.parquet"):
        hit = [p for p in glob.glob(pat, recursive=True)
               if int(re.search(r"(\d+)", os.path.basename(p)).group(1)) == n]
        if len(hit) != 1:
            sys.exit(f"❌ ep{n}에 해당하는 파일이 {len(hit)}개 — {pat}")
        targets.append(hit[0])

    print(f"\n대상: ep{n}  ({length}프레임)")
    print(f'  지시문: "{list(last.tasks)[0]}"')
    print("\n지울 파일:")
    for t in targets:
        print(f"  - {os.path.relpath(t, R)}  ({os.path.getsize(t):,}B)")
    print("\ninfo.json:")
    print(f"  total_episodes  {info['total_episodes']} → {info['total_episodes'] - 1}")
    print(f"  total_frames    {info['total_frames']} → {info['total_frames'] - length}")
    print(f"  total_tasks     {info.get('total_tasks')} (변경 없음 — 지시문은 다른 ep에도 쓰인다)")

    if not a.apply:
        print("\n미리보기다. 실제로 지우려면 --apply 를 붙일 것 (root 소유라 sudo 필요).")
        return 0

    for t in targets:
        os.remove(t)
    info["total_episodes"] -= 1
    info["total_frames"] -= length
    with open(f"{R}/meta/info.json", "w") as f:
        json.dump(info, f, indent=4)
    print(f"\n✅ ep{n} 제거 완료 → {info['total_episodes']}ep · {info['total_frames']}frames")
    print("   확인: verify_lang_dataset.py 를 다시 돌릴 것")
    return 0


if __name__ == "__main__":
    sys.exit(main())
