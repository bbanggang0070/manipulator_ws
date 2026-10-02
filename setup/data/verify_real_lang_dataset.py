"""수집한 **실기** 언어 데이터셋을 학습 전에 검증한다.

sim 검증(verify_lang_dataset.py)과 같은 목적이지만, 실기에서만 생기는 위험이 더 있다.

  ① **에피소드당 지시문이 정확히 1개인가**
     sim 예행에서 6ep 중 4ep이 지시문을 2~3개씩 갖고 저장된 적이 있다(recorder 경쟁 상태).
     실기는 에피소드마다 프로세스를 새로 띄워 문장을 박제하므로 구조적으로 안 생겨야 한다.
     **안 생겨야 한다는 것과 안 생겼다는 것은 다르다** — 매번 확인한다.

  ② **계획표와 실제 저장본이 일치하는가** ← 실기 고유
     사람이 계획표를 보고 물체를 놓는다. 행을 건너뛰거나(s), 재녹화하거나, 순서가
     밀리면 **저장된 문장과 계획표 행이 어긋난다.** 이건 sim에는 없던 위험이다.

  ③ **대응쌍이 저장본에서도 살아 있는가** ← 4칸 선반 구성의 핵심
     계획표가 쌍(같은 배치, 목적지만 다름)을 지정해도, 수집 중 한쪽을 건너뛰거나
     재녹화 순서가 밀리면 **짝이 깨진다.** 짝이 깨진 쌍은 그냥 평범한 에피소드 2개라
     이 데이터셋의 가장 진한 언어 신호가 사라진다. 저장 순서로 짝을 복원해 확인한다.

  ④ **캘리브레이션이 수집 시작 때와 같은가** — 바뀌면 관절 공간이 달라져
     데이터셋이 서로 안 맞는 두 덩어리가 된다. 기록에 남지 않아 조용히 지나간다.

  ⑤ 타깃·칸 균형, 지시문 다양성, 에피소드 길이

사용(lerobot venv 필요 — pandas):
  cd ~/manipulator_ws/envs/lerobot
  uv run python ../../setup/data/verify_real_lang_dataset.py \\
      ~/.cache/huggingface/lerobot/heongyu/so101_real_lang

  # 1단계(80행 계획표)를 검증할 때는 계획표를 맞춰 준다
  REAL_LANG_PLAN=~/manipulator_ws/manipulator_md/real/real_lang_plan_s1.csv \\
  uv run python ../../setup/data/verify_real_lang_dataset.py
"""
import csv
import glob
import json
import os
import re
import sys
from collections import Counter, defaultdict

import pandas as pd

# 대조할 계획표. **1단계는 80행짜리를 쓰므로** 환경변수로 바꿔야 한다 —
# 250행 계획표로 대조하면 대응쌍 그룹 번호가 어긋나 멀쩡한 쌍이 깨진 것으로 나온다.
PLAN = os.environ.get("REAL_LANG_PLAN", os.path.expanduser(
    "~/manipulator_ws/manipulator_md/real/real_lang_plan.csv"))
OBJ_NOUNS = ("red cube", "blue cube", "yellow cube", "green cube",
             "purple cube", "orange cube", "marker", "eraser",
             "glue stick", "screwdriver")
# 4칸 선반. gen_real_lang_plan.py 의 SLOTS 와 같아야 한다.
SLOTS = {"black": 1, "cyan": 2, "pink": 3, "white": 4}
DEST_NOUN = "bin"


def parse_target(instr):
    for n in OBJ_NOUNS:
        if re.search(rf"\b{re.escape(n)}\b", instr):
            return n
    # "the red block" 처럼 cube 대신 block을 쓴 문형도 받는다
    for n in OBJ_NOUNS:
        head = n.split()[0]
        if head not in ("marker", "eraser") and re.search(rf"\b{head}\b", instr):
            return n
    return "?"


def parse_dest(instr):
    for c in SLOTS:
        if re.search(rf"\b{c}\s+{DEST_NOUN}\b", instr):
            return c
    return "(미지정)"


def main(root):
    info = json.load(open(f"{root}/meta/info.json"))
    n_ep, n_fr, fps = info["total_episodes"], info.get("total_frames", 0), info["fps"]
    print(f"\n{'=' * 66}\n{os.path.basename(root)} — {n_ep}ep · {n_fr:,}frames · "
          f"{info['codebase_version']}\n{'=' * 66}")

    # ── ⓪ 캘리브레이션 지문 ──────────────────────────────────────────
    #   수집 도중/후에 캘리브레이션이 바뀌면 관절 공간이 달라져 데이터셋이
    #   서로 안 맞는 두 덩어리가 된다. 학습 전에 반드시 확인한다.
    import subprocess
    fp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "calib_fingerprint.py")
    if os.path.exists(fp):
        r = subprocess.run([sys.executable, fp, "--check", root],
                           capture_output=True, text=True)
        for line in r.stdout.rstrip().split("\n"):
            print("  " + line.strip() if line.strip() else "")
        if r.returncode != 0:
            print("  ❌ 캘리브레이션 불일치 — 학습 전에 정리해야 한다")
            return 1
    else:
        print(f"  ⏸ calib_fingerprint.py 없음 — 캘리브레이션 대조 건너뜀")

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

    # ── ② 계획표 대조 + ③ 대응쌍 무결성 ── 실기 고유 위험 ─────────────
    plan = None
    if os.path.exists(PLAN):
        plan = list(csv.DictReader(open(PLAN)))
        if plan and "keep_layout" not in plan[0]:
            print(f"  ⚠️  계획표가 옛 구조다({PLAN}) — gen_real_lang_plan.py 로 다시 생성하세요")
            plan = None
    if plan:
        plan_instr = [r["instruction"] for r in plan]
        pset = set(plan_instr)
        stray = [t for t in tasks if t not in pset]
        ok &= not stray
        print(f"  {'✅' if not stray else '❌'} 계획표에 없는 지시문        {len(stray)}건")
        for t in stray[:3]:
            print(f'       "{t}"')

        # 저장 순서 ↔ 계획표 순서. 건너뛰기는 허용, 역행은 재녹화 신호
        idx = [plan_instr.index(t) for t in tasks if t in plan_instr]
        back = sum(1 for a, b in zip(idx, idx[1:]) if b < a)
        print(f"  {'✅' if back == 0 else '⚠️ '} 계획표 순서 역행          {back}건 "
              f"{'' if back == 0 else '← 문장 중복으로 추정이 거칠 수 있다. 재녹화면 정상'}")
        if idx:
            span = max(idx) + 1
            print(f"     계획표 {span}행까지 진행해 {len(eps)}ep 저장 "
                  f"→ 건너뜀 약 {max(0, span - len(eps))}행")

        # ── ③ 대응쌍이 저장본에서 살아 있는가 ──
        #   계획표 그룹별로 "저장된 지시문 집합"을 모아, 그룹 전원이 들어왔는지 본다.
        #   한쪽만 저장된 그룹은 **깨진 쌍**이다 — 언어 신호가 가장 진한 구간을 잃은 것.
        saved = Counter(tasks)
        groups = defaultdict(list)
        for r in plan:
            groups[r["group"]].append(r)
        intact = broken = 0
        broken_ex = []
        for g, items in groups.items():
            if len(items) < 2:
                continue
            got = sum(1 for r in items if saved.get(r["instruction"], 0) > 0)
            if got == 0:
                continue          # 아직 진행 안 한 그룹
            if got == len(items):
                intact += 1
            else:
                broken += 1
                if len(broken_ex) < 3:
                    broken_ex.append((g, got, len(items), items[0]["target"]))
        tot_pair = intact + broken
        if tot_pair:
            ok &= broken == 0
            print(f"  {'✅' if broken == 0 else '❌'} 대응쌍 무결성            "
                  f"온전 {intact} · 깨짐 {broken} / {tot_pair}그룹")
            for g, got, need, tgt in broken_ex:
                print(f"       그룹 {g}({tgt}): {got}/{need}만 저장됨 — 나머지를 마저 찍으세요")
            if broken:
                print("       ⚠️ 깨진 쌍은 평범한 에피소드 2개와 같다. 같은 배치에 지시문만")
                print("          다른 구간이 이 데이터셋에서 언어 신호가 가장 진한 곳이다.")
        else:
            print("  ⏸ 대응쌍 판정은 쌍 그룹이 저장된 뒤에")
    else:
        print(f"  ⏸ 계획표 없음/옛 구조 — 대조·쌍 검사 건너뜀")

    # ── ④ 분포 ───────────────────────────────────────────────────────
    tgt = Counter(parse_target(t) for t in tasks)
    dst = Counter(parse_dest(t) for t in tasks)
    print(f"\n  타깃 분포")
    n_named = sum(tgt[o] for o in OBJ_NOUNS)
    exp = n_named / len(OBJ_NOUNS) if n_named else 0
    bad = [o for o in OBJ_NOUNS if n_named >= 80 and not exp * 0.7 <= tgt[o] <= exp * 1.3]
    for o in OBJ_NOUNS:
        print(f"    {o:<13} {tgt[o]:>3}{'  ⚠' if o in bad else ''}")
    if n_named >= 80:
        ok &= not bad
        print(f"  {'✅' if not bad else '❌'} 타깃 균형                 기대 {exp:.0f} ±30%")
    else:
        print(f"  ⏸ 표본 {n_named}ep — 균형 판정은 80ep 이상에서")

    named = sum(v for k, v in dst.items() if k != "(미지정)")
    print(f"\n  칸 분포")
    for c, n in sorted(SLOTS.items(), key=lambda kv: kv[1]):
        print(f"    {n}번 {c:<7} {dst.get(c, 0):>3}")
    if named:
        e2 = named / len(SLOTS)
        badv = [c for c in SLOTS if named >= 60 and not e2 * 0.7 <= dst.get(c, 0) <= e2 * 1.3]
        if named >= 60:
            ok &= not badv
            print(f"  {'✅' if not badv else '❌'} 칸 균형                   기대 {e2:.0f} ±30%")
        else:
            print(f"  ⏸ 목적지 명시 {named}ep — 칸 균형 판정은 60ep 이상에서")
    print(f"  목적지 명시 {named}/{len(tasks)} ({named / len(tasks) * 100:.0f}%) — 계획 약 85%")
    print(f"  ℹ️  서로 다른 지시문 {len(set(tasks))}종")
    if tgt.get("?", 0):
        ok = False
        print(f"  ❌ 타깃을 못 읽은 문장 {tgt['?']}건 — 지시문 생성이 계획과 어긋났다")

    # ── ⑤ 길이 ───────────────────────────────────────────────────────
    L = eps.length
    print(f"\n  에피소드 길이: 중앙 {L.median() / fps:.1f}s · 범위 "
          f"{L.min() / fps:.1f}~{L.max() / fps:.1f}s (fps {fps})")
    short = int((L / fps < 5).sum())
    if short:
        print(f"  ⚠️  5초 미만 {short}건 — 시연이 중간에 끊겼을 수 있다. 영상 확인 권장")

    print(f"\n  {'✅ 통과' if ok else '❌ 실패 — 위 항목을 고칠 것'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else
                                     "~/.cache/huggingface/lerobot/heongyu/so101_real_lang")))
