"""수집한 **실기** 언어 데이터셋을 학습 전에 검증한다.

sim 검증(verify_lang_dataset.py)과 같은 목적이지만, 실기에서만 생기는 위험이 더 있다.

  ① **에피소드당 지시문이 정확히 1개인가**
     sim 예행에서 6ep 중 4ep이 지시문을 2~3개씩 갖고 저장된 적이 있다(recorder 경쟁 상태).
     실기는 에피소드마다 프로세스를 새로 띄워 문장을 박제하므로 구조적으로 안 생겨야 한다.
     **안 생겨야 한다는 것과 안 생겼다는 것은 다르다** — 매번 확인한다.

  ② **계획표와 실제 저장본이 일치하는가** ← 실기 고유
     사람이 계획표를 보고 물체를 놓는다. 행을 건너뛰거나(s), 재녹화하거나, 순서가
     밀리면 **저장된 문장과 계획표 행이 어긋난다.** 이건 sim에는 없던 위험이다.
     저장된 지시문 집합이 계획표에 실재하는지, 순서가 맞는지 본다.

  ③ 타깃·목적지 균형, 지시문 다양성, 에피소드 길이

사용(lerobot venv 필요 — pandas):
  cd ~/manipulator_ws/envs/lerobot
  uv run python ../../setup/data/verify_real_lang_dataset.py \\
      ~/.cache/huggingface/lerobot/heongyu/so101_real_lang
"""
import csv
import glob
import json
import os
import re
import sys
from collections import Counter

import pandas as pd

PLAN = os.path.expanduser("~/manipulator_ws/manipulator_md/real/real_lang_plan.csv")
OBJ_NOUNS = ("red cube", "blue cube", "yellow cube", "green cube",
             "purple cube", "orange cube", "marker", "eraser")
BOXES = ("black", "brown", "gray")
LEGACY = "Pick up the block and place it in the box"


def parse_target(instr):
    if instr.strip() == LEGACY:
        return "legacy"
    for n in OBJ_NOUNS:
        if re.search(rf"\b{re.escape(n)}\b", instr):
            return n
    # "the red block" 처럼 cube 대신 block을 쓴 문형도 받는다
    for n in OBJ_NOUNS:
        head = n.split()[0]
        if head != "marker" and head != "eraser" and re.search(rf"\b{head}\b", instr):
            return n
    return "?"


def parse_dest(instr):
    for b in BOXES:
        if re.search(rf"\b{b} box\b", instr):
            return b
    return "(미지정)"


def main(root):
    info = json.load(open(f"{root}/meta/info.json"))
    n_ep, n_fr, fps = info["total_episodes"], info.get("total_frames", 0), info["fps"]
    print(f"\n{'=' * 66}\n{os.path.basename(root)} — {n_ep}ep · {n_fr:,}frames · "
          f"{info['codebase_version']}\n{'=' * 66}")

    ef = sorted(glob.glob(f"{root}/meta/episodes/**/*.parquet", recursive=True))
    if not ef:
        sys.exit("❌ meta/episodes 없음 — 경로를 확인하세요")
    eps = pd.concat([pd.read_parquet(f) for f in ef]).sort_values("episode_index")
    ok = True

    # ── ① 에피소드당 지시문 1개 ──────────────────────────────────────
    multi = [(int(r.episode_index), list(r.tasks)) for r in eps.itertuples() if len(r.tasks) != 1]
    good = not multi
    ok &= good
    print(f"  {'✅' if good else '❌'} 에피소드당 지시문 1개        위반 {len(multi)}/{len(eps)}")
    for i, t in multi[:5]:
        print(f"       ep{i}: {len(t)}개 → {t}")

    tasks = [t[0] for t in eps.tasks if len(t) >= 1]

    # ── ② 계획표와 대조 ── 실기 고유 위험 ────────────────────────────
    if os.path.exists(PLAN):
        plan = list(csv.DictReader(open(PLAN)))
        plan_instr = [r["instruction"] for r in plan]
        pset = set(plan_instr)
        stray = [t for t in tasks if t not in pset]
        good = not stray
        ok &= good
        print(f"  {'✅' if good else '❌'} 계획표에 없는 지시문        {len(stray)}건")
        for t in stray[:3]:
            print(f'       "{t}"')
        # 순서 확인 — 저장 순서가 계획표 순서를 따르는가(건너뛰기는 허용, 역행은 아님)
        idx, back = [], 0
        for t in tasks:
            if t in plan_instr:
                idx.append(plan_instr.index(t))
        for a, b in zip(idx, idx[1:]):
            if b < a:
                back += 1
        print(f"  {'✅' if back == 0 else '⚠️ '} 계획표 순서 역행          {back}건 "
              f"{'' if back == 0 else '← 문장이 중복돼 추정이 거칠 수 있다. 재녹화가 있었다면 정상'}")
        if idx:
            span = max(idx) + 1
            print(f"     계획표 {span}행까지 진행해 {len(eps)}ep 저장 "
                  f"→ 건너뜀 약 {max(0, span - len(eps))}행")
    else:
        print(f"  ⏸ 계획표 없음({PLAN}) — 대조 건너뜀")

    # ── ③ 분포 ───────────────────────────────────────────────────────
    tgt = Counter(parse_target(t) for t in tasks)
    dst = Counter(parse_dest(t) for t in tasks)
    print(f"\n  타깃 분포")
    n_named = sum(tgt[o] for o in OBJ_NOUNS)
    exp = n_named / len(OBJ_NOUNS) if n_named else 0
    lo, hi = exp * 0.7, exp * 1.3
    bad = []
    for o in OBJ_NOUNS:
        mark = "" if (n_named < 80 or lo <= tgt[o] <= hi) else "  ⚠"
        if mark:
            bad.append(o)
        print(f"    {o:<13} {tgt[o]:>3}{mark}")
    if n_named >= 80:
        ok &= not bad
        print(f"  {'✅' if not bad else '❌'} 타깃 균형                 기대 {exp:.0f} ±30%")
    else:
        print(f"  ⏸ 표본 {n_named}ep — 균형 판정은 80ep 이상에서")

    print(f"\n  목적지 분포: {dict(dst)}")
    named = sum(v for k, v in dst.items() if k != "(미지정)")
    print(f"     목적지 명시 {named}/{len(tasks)} ({named/len(tasks)*100:.0f}%) "
          f"— 계획상 약 66%")
    print(f"  ℹ️  레거시 문장 {tgt.get('legacy', 0)}/{len(tasks)}  ·  "
          f"서로 다른 지시문 {len(set(tasks))}종")
    if tgt.get("?", 0):
        ok = False
        print(f"  ❌ 타깃을 못 읽은 문장 {tgt['?']}건 — 지시문 생성이 계획과 어긋났다")

    # ── ④ 길이 ───────────────────────────────────────────────────────
    L = eps.length
    print(f"\n  에피소드 길이: 중앙 {L.median()/fps:.1f}s · 범위 "
          f"{L.min()/fps:.1f}~{L.max()/fps:.1f}s (fps {fps})")
    short = int((L / fps < 5).sum())
    if short:
        print(f"  ⚠️  5초 미만 {short}건 — 시연이 중간에 끊겼을 수 있다. 영상 확인 권장")

    print(f"\n  {'✅ 통과' if ok else '❌ 실패 — 위 항목을 고칠 것'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else
                                     "~/.cache/huggingface/lerobot/heongyu/so101_real_lang")))
