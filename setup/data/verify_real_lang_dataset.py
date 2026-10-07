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

        # 저장 순서 ↔ 계획표 순서.
        #   ⚠️ 지시문 **문자열**로 순서를 추정하면 안 된다. 같은 문장이 여러 행에
        #      나와서 멀쩡한 수집이 "역행 22건"으로 잡힌다(80ep에서 실제로 겪음).
        #      러너가 남기는 collect_progress.txt 의 **실제 행 번호**를 쓴다.
        prog_rows = []
        prog_f = os.path.join(root, "collect_progress.txt")
        if os.path.exists(prog_f):
            prog_rows = [int(l.split(",")[0]) for l in open(prog_f)
                         if l.split(",")[0].strip().isdigit()]
        if prog_rows:
            back = sum(1 for a, b in zip(prog_rows, prog_rows[1:]) if b < a)
            dup = sorted({r for r in prog_rows if prog_rows.count(r) > 1})
            span = max(prog_rows)
            missing = sorted(set(range(1, span + 1)) - set(prog_rows))
            ok &= back == 0 and not dup
            print(f"  {'✅' if back == 0 else '❌'} 계획표 순서 역행          {back}건")
            print(f"  {'✅' if not dup else '❌'} 행 중복                  "
                  f"{len(dup)}건{(' ' + str(dup[:5])) if dup else ''}")
            print(f"     계획표 {span}행까지 진행해 {len(eps)}ep 저장 "
                  f"→ 건너뛴 행 {len(missing)}개{(' ' + str(missing[:8])) if missing else ''}")
        else:
            print("  ⏸ collect_progress.txt 없음 — 순서 검사 건너뜀")

        # ── ③ 대응쌍이 저장본에서 살아 있는가 ──
        #   ⚠️ 지시문 **문자열**로 짝을 찾으면 안 된다. 80행에 지시문이 57종뿐이라
        #      같은 문장이 여러 행에 나온다. ep2를 저장했을 뿐인데 같은 문장을 가진
        #      행 50이 "절반 저장됨"으로 잡혀 수집 내내 거짓 경보가 난다(실제로 겪음).
        #   수집 러너가 남기는 collect_progress.txt 에 **실제 행 번호**가 있으므로
        #   그것으로 판정한다. 없으면(옛 수집본) 판정을 건너뛴다 — 틀린 경보보다 낫다.
        prog = os.path.join(root, "collect_progress.txt")
        done_rows = set()
        if os.path.exists(prog):
            for line in open(prog):
                part = line.split(",")[0].strip()
                if part.isdigit():
                    done_rows.add(part)
        groups = defaultdict(list)
        for r in plan:
            groups[r["group"]].append(r)
        intact = broken = 0
        broken_ex = []
        if not done_rows:
            print("  ⏸ collect_progress.txt 없음 — 대응쌍 판정 건너뜀")
            groups = {}
        last_row = max((int(x) for x in done_rows), default=0)
        for g, items in groups.items():
            if len(items) < 2:
                continue
            rows_ = [r["ep"] for r in items]
            got = sum(1 for e in rows_ if e in done_rows)
            if got == 0:
                continue          # 아직 시작 안 한 그룹
            if got == len(items):
                intact += 1
            elif max(int(e) for e in rows_) > last_row:
                continue          # **아직 진행 중인 그룹** — 뒷 행에 아직 도달 못 했다
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
    # ⚠️ 기대값은 **계획표가 실제로 쓰는 칸** 기준이어야 한다. 1단계는 칸 1·4만
    #    쓰는데 4칸 전부로 나누면 멀쩡한 33/35 가 "불균형"으로 잡힌다(실제로 겪음).
    used = {c for c in SLOTS}
    if plan:
        used = {r["slot_color"] for r in plan if r.get("dest_named")}
    print(f"\n  칸 분포  (계획표가 쓰는 칸: {', '.join(sorted(used)) or '?'})")
    for c, n in sorted(SLOTS.items(), key=lambda kv: kv[1]):
        tag = "" if c in used else "   (이 단계에서 미사용)"
        print(f"    {n}번 {c:<7} {dst.get(c, 0):>3}{tag}")
    if named and used:
        e2 = named / len(used)
        badv = [c for c in used if named >= 60 and not e2 * 0.7 <= dst.get(c, 0) <= e2 * 1.3]
        if named >= 60:
            ok &= not badv
            print(f"  {'✅' if not badv else '❌'} 칸 균형                   기대 {e2:.0f} ±30%"
                  f" ({len(used)}칸 기준)")
            for c in badv:
                print(f"       {c}: {dst.get(c, 0)}")
        else:
            print(f"  ⏸ 표본 {named}ep — 칸 균형 판정은 60ep 이상에서")
    # 기대 비율은 **계획표에서 직접 센다.** 85%로 박아 두었다가 설계가 100% 명시로
    # 바뀐 뒤에도 "계획 약 85%"라고 찍어 멀쩡한 데이터가 어긋나 보였다.
    exp = (sum(1 for r in plan if r.get("dest_named")) / len(plan) * 100) if plan else None
    print(f"  목적지 색 명시 {named}/{len(tasks)} ({named / len(tasks) * 100:.0f}%)"
          + (f" — 계획 {exp:.0f}%" if exp is not None else ""))
    if exp is not None and abs(named / len(tasks) * 100 - exp) > 10:
        ok = False
        print(f"  ❌ 계획({exp:.0f}%)과 10%p 넘게 다르다 — 계획표를 잘못 쓰고 있는지 확인")
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

    # ── ⑥ 시연 품질 ──────────────────────────────────────────────────
    #   1차 수집(2026-10-06, 80ep)에서 **이 검사가 없어서** 놓친 것들이다.
    #   계획표 대조·쌍 무결성·길이는 전부 통과했는데도 모델이 물체를 못 집었다.
    #   원인은 시연 자체의 품질이었고, 그건 메타가 아니라 **궤적**에만 들어 있다.
    import numpy as np
    df = sorted(glob.glob(f"{root}/data/**/*.parquet", recursive=True))
    if not df:
        print("\n  ⏸ data parquet 없음 — 시연 품질 검사 건너뜀")
    else:
        d = pd.concat([pd.read_parquet(f, columns=["episode_index", "frame_index",
                                                   "observation.state"]) for f in df])
        # 파지 **시도** 횟수를 센다. 이 지표는 두 번 틀렸으니 정의를 박아 둔다:
        #   ① 중점 임계로 개폐 전이를 세면 평균 3.9회가 나오는데, 이건 정상이다.
        #      rest 에서 그리퍼가 닫혀 있다가 **접근하려고 열고** → 집고 → 놓고 →
        #      복귀하며 닫는다. 즉 4회 전이가 올바른 시연이다. 99% 가 "재파지"로
        #      찍혔던 건 지표가 정상 동작을 센 것이었다.
        #   ② 첫 1초를 빼지 않으면, 에피소드가 그리퍼 열린 채 시작했다가 닫히는
        #      것(시작 자세 문제)이 파지 시도로 잘못 잡힌다 — 56% 로 부풀었다.
        # 올바른 정의: **첫 1초를 제외**하고, '크게 벌림 → 닫힘' 전이의 수.
        # 마지막 닫힘이 rest 복귀면 빼고 센다. 2회 이상이면 한 번에 못 집은 것이다.
        def grasp_attempts(g, dwell=3):
            g = g[fps:]
            lo, hi = g.min(), g.max()
            if hi - lo < 5:
                return None
            o_th, c_th = lo + 0.6 * (hi - lo), lo + 0.35 * (hi - lo)
            st, cand, run, seq = None, None, 0, []
            for v in g:
                t = "O" if v > o_th else ("C" if v < c_th else None)
                if t is None or t == st:
                    cand, run = None, 0
                    continue
                if t == cand:
                    run += 1
                else:
                    cand, run = t, 1
                if run >= dwell:
                    seq.append(t); st = t; cand, run = None, 0
            att = [i for i in range(1, len(seq)) if seq[i] == "C" and seq[i - 1] == "O"]
            if att and att[-1] == len(seq) - 1 and len(att) > 1:
                att = att[:-1]
            return len(att)

        starts, attempts, bad_grip = [], [], []
        for e, sub in d.groupby("episode_index"):
            a = np.stack(sub.sort_values("frame_index")["observation.state"].values).astype(float)
            starts.append(a[0])
            n = grasp_attempts(a[:, 5])
            if n is None:
                continue
            attempts.append(n)
            if n > 1:
                bad_grip.append((int(e), n))
        starts = np.array(starts)

        if attempts:
            rate = len(bad_grip) / len(attempts)
            print(f"\n  파지 시도: 1회 {attempts.count(1)}건 · 2회 이상 {len(bad_grip)}건 "
                  f"({rate:.0%}) · 미검출 {n_ep - len(attempts)}건")
            if bad_grip:
                print("     재파지 ep: " + ", ".join(
                    f"{e}({n}회)" for e, n in sorted(bad_grip, key=lambda x: -x[1])[:10])
                    + (" ..." if len(bad_grip) > 10 else ""))
            if rate > 0.15:
                ok = False
                print(f"  ❌ 재파지가 15% 를 넘는다 — drop_episode.sh 로 지우고 다시 찍을 것")
            else:
                print(f"  ✅ 재파지 15% 이하")

        J = ["pan", "lift", "elbow", "w_flex", "w_roll", "grip"]
        sd = starts.std(axis=0)
        print(f"\n  시작 자세 표준편차: " + " · ".join(f"{j} ±{v:.1f}°" for j, v in zip(J, sd)))
        loose = [j for j, v in zip(J, sd) if v > 8.0]
        if loose:
            # rest 가 흔들리면 **배포 시 goto_home 목표를 정할 수 없다.**
            # 1차 수집에서 wrist_flex ±14.3° 였고, 옛 홈 자세와 18.3° 어긋난 채
            # 평가를 돌렸다.
            print(f"  ⚠️  {', '.join(loose)} 의 편차가 8° 를 넘는다 — rest 가 느슨하다. "
                  f"배포 홈 자세(goto_home_*.py)를 이 평균으로 갱신할 것")
        print(f"  배포용 홈 자세(이 데이터셋 기준): " +
              ", ".join(f"{j} {v:+.1f}" for j, v in zip(J, starts.mean(axis=0))))

    print(f"\n  {'✅ 통과' if ok else '❌ 실패 — 위 항목을 고칠 것'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else
                                     "~/blocktask_ws/Sim-to-Real-SO-101-Workshop/datasets/_train/cleanup_real")))
