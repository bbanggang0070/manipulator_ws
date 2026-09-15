"""수집한 언어 데이터셋을 **학습 전에** 검증한다 (language_conditioning_sim_plan.md §5).

여기서 통과하지 못한 데이터로 학습하면 19~45시간을 버린다.

가장 중요한 검사는 ①이다:

  ① **에피소드당 지시문이 정확히 1개인가**
     2026-09-14 예행에서 6ep 중 4ep이 지시문을 2~3개씩 갖고 저장됐다. 원인은
     `lerobot_recorder.async_episode_processor`가 별도 스레드에서 프레임을 쓰는 동안
     메인 루프가 리셋하며 `self.task_name`을 바꾸는 **경쟁 상태**였다.
     지시문이 상수였던 기존 수집에서는 드러나지 않던 결함이고, 언어 수집에서는
     **라벨이 통째로 무의미해진다.** 고쳤지만(저장 시점에 문장을 박제), 조용히 재발하면
     수집 5시간이 그대로 날아가므로 매번 이 검사를 먼저 돌린다.

  ② 물체·박스 균형, 미학습 색 유출, 계획표 소화율

사용(lerobot venv 필요 — pandas):
  cd ~/manipulator_ws/envs/lerobot
  uv run python ../../setup/sim/t1_task/verify_lang_dataset.py \\
      ~/blocktask_ws/Sim-to-Real-SO-101-Workshop/datasets/sim_so101_blocktask_lang
"""
import glob
import json
import os
import re
import sys
from collections import Counter

import pandas as pd

PLAN = os.path.expanduser("~/manipulator_ws/manipulator_md/sim/lang_collect_plan.csv")
HELDOUT_WORDS = ("white", "pink")
BOX_COLORS = ("black", "brown", "gray")
OBJ_NOUNS = ("red", "blue", "yellow", "green", "cyan", "purple", "eraser", "marker")


def parse_target(instr):
    """지시문에서 타깃 명사를 뽑는다. 레거시 문장은 'legacy'로 표시."""
    if instr.strip() == "Pick up the block and place it in the box":
        return "legacy"
    for n in OBJ_NOUNS:
        if re.search(rf"\b{n}\b", instr):
            return n
    return "?"


def parse_dest(instr):
    for c in BOX_COLORS:
        if re.search(rf"\b{c} box\b", instr):
            return c
    return "box"      # 색 미지정(단일 박스 씬)


def main(root):
    info = json.load(open(f"{root}/meta/info.json"))
    print(f"\n{'=' * 64}\n{os.path.basename(root)} — {info['total_episodes']}ep · "
          f"{info.get('total_frames', '?')}frames · {info['codebase_version']}\n{'=' * 64}")

    ef = sorted(glob.glob(f"{root}/meta/episodes/**/*.parquet", recursive=True))
    eps = pd.concat([pd.read_parquet(f) for f in ef]).sort_values("episode_index")

    ok = True

    # ── ① 에피소드당 지시문 1개 ────────────────────────────────────────
    multi = [(int(r.episode_index), list(r.tasks)) for r in eps.itertuples()
             if len(r.tasks) != 1]
    good = not multi
    ok &= good
    print(f"  {'✅' if good else '❌'} 에피소드당 지시문 1개        위반 {len(multi)}/{len(eps)}")
    for i, t in multi[:5]:
        print(f"       ep{i}: {len(t)}개 → {t}")
    if multi:
        print("       ↑ recorder의 task 박제 패치가 빠졌다. 이 데이터는 **라벨이 무의미하다.**")

    # ── ② 타깃·목적지 분포 ────────────────────────────────────────────
    tasks = [t[0] for t in eps.tasks if len(t) >= 1]
    tgt = Counter(parse_target(t) for t in tasks)
    dst = Counter(parse_dest(t) for t in tasks)
    print(f"\n  타깃 명사: {dict(tgt)}")
    print(f"  목적지   : {dict(dst)}")

    n = len(tasks)
    if n >= 50:   # 표본이 적으면 균형을 논할 수 없다
        exp = n / len(OBJ_NOUNS)
        vals = [tgt[o] for o in OBJ_NOUNS]
        good = min(vals) >= exp * 0.7 and max(vals) <= exp * 1.3
        ok &= good
        print(f"  {'✅' if good else '❌'} 물체별 타깃 균형            {min(vals)}~{max(vals)} "
              f"(기대 {exp:.0f} ±30%)")
    else:
        print(f"  ⏸ 표본 {n}ep — 균형 판정은 50ep 이상에서")

    # ── ③ 미학습 색 유출 ──────────────────────────────────────────────
    leak = [t for t in tasks if any(re.search(rf"\b{w}\b", t) for w in HELDOUT_WORDS)]
    good = not leak
    ok &= good
    print(f"  {'✅' if good else '❌'} 미학습 색 유출              {len(leak)}건 "
          f"← 하나라도 있으면 일반화 평가가 무효다")

    # ── ④ 모호한 지칭 ─────────────────────────────────────────────────
    #   레거시 문장은 1물체 씬에만 허용된다. 여기서는 문장만 보므로 개수만 센다.
    legacy = tgt.get("legacy", 0)
    print(f"  ℹ️  레거시 문장 {legacy}/{n} (계획상 약 6%)")
    unk = tgt.get("?", 0)
    if unk:
        ok = False
        print(f"  ❌ 타깃을 못 읽은 문장 {unk}건 — 지시문 생성이 계획과 어긋났다")

    # ── ⑤ 계획표 소화율(스킵 추정) ────────────────────────────────────
    if os.path.exists(PLAN):
        plan = list(pd.read_csv(PLAN).instruction)
        idx = [plan.index(t) for t in tasks if t in plan]
        if idx:
            span = max(idx) + 1
            print(f"\n  계획표 소화: {span}행까지 진행해 {len(eps)}ep 저장 "
                  f"→ 스킵률 약 {(1 - len(eps) / span) * 100:.0f}%")
            print("       (레거시 문장은 여러 행에 중복돼 추정이 거칠다 — 참고용)")

    # ── ⑥ 길이 ───────────────────────────────────────────────────────
    L = eps.length
    print(f"\n  에피소드 길이: 중앙 {L.median() / 30:.1f}s · 범위 "
          f"{L.min() / 30:.1f}~{L.max() / 30:.1f}s (fps {info['fps']})")

    print(f"\n  {'✅ 통과' if ok else '❌ 실패 — 위 항목을 고칠 것'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(os.path.expanduser(sys.argv[1])))
