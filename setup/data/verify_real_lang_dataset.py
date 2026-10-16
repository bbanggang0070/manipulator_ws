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
  REAL_LANG_PLAN=~/manipulator_ws/manipulator_md/p5_real_cleanup/real_lang_plan_s1.csv \\
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
    "~/manipulator_ws/manipulator_md/p5_real_cleanup/real_lang_plan_v3.csv"))
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

    # ── 파일 개수 ────────────────────────────────────────────────────
    #   메타·데이터·영상이 같은 수여야 한다. 하나라도 비면 학습이 조용히
    #   어긋난 프레임을 쓴다.
    vk = sorted(os.path.basename(p) for p in glob.glob(f"{root}/videos/*"))
    nd = len(glob.glob(f"{root}/data/**/*.parquet", recursive=True))
    counts = {k: len(glob.glob(f"{root}/videos/{k}/**/*.mp4", recursive=True)) for k in vk}
    print(f"  파일 수: data {nd} · " + " · ".join(f"{k.split('.')[-1]} {v}" for k, v in counts.items())
          + f" · info {n_ep}")
    if {nd, *counts.values()} != {n_ep}:
        print("  ❌ 개수가 어긋난다 — 영상이나 parquet 이 빠졌다")
        return 1

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
        # 파지 시도·놓은 위치는 **episode_events.py** 가 맡는다.
        #   이 측정을 네 번 틀렸고(그 내력은 그 파일 머리말에 있다), 지금은
        #   손으로 읽고 영상으로 확인한 정답 14개로 고정돼 있다:
        #       python3 episode_events.py --selftest
        #   지표를 건드리면 그 자가검사부터 통과시킬 것.
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from episode_events import analyze

        starts, attempts, bad_grip, rel = [], [], [], {}
        for e, sub in d.groupby("episode_index"):
            a = np.stack(sub.sort_values("frame_index")["observation.state"].values).astype(float)
            starts.append(a[0])
            ev = analyze(a, fps=fps)
            if ev["release_pan"] is not None:
                rel[int(e)] = ev["release_pan"]
            if ev["attempts"] is None:
                continue
            attempts.append(ev["attempts"])
            if ev["attempts"] > 1:
                bad_grip.append((int(e), ev["attempts"]))
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

        # ── 칸 분리도 ────────────────────────────────────────────────
        #   **목적지 축에서 가장 중요한 수치다.** 지시한 칸마다 놓은 위치가
        #   실제로 갈라져 있어야 모델이 배울 신호가 존재한다. 겹쳐 있으면
        #   아무리 많이 모아도 목적지를 배울 수 없다.
        # 에피소드 인덱스 → 계획표 행. collect_progress.txt 의 **실제 행 번호**를 쓴다
        # (지시문 문자열로 맞추면 같은 문장이 여러 행에 나와 틀린다 — 이미 겪었다).
        if rel and plan and prog_rows and len(prog_rows) >= len(rel):
            by = defaultdict(list)
            for e, v in rel.items():
                if e < len(prog_rows) and 1 <= prog_rows[e] <= len(plan):
                    by[plan[prog_rows[e] - 1]["slot_color"]].append(v)
            cols = [c for c in ("black", "cyan", "pink", "white") if len(by.get(c, [])) >= 5]
            if len(cols) >= 2:
                print("\n  놓은 위치 (shoulder_pan) — 칸이 실제로 갈라지는가")
                mu, sd = {}, {}
                for c in cols:
                    v = np.array(by[c]); mu[c], sd[c] = v.mean(), v.std()
                    print(f"    {c:<7} n={len(v):>3}  {v.mean():+7.1f}° ±{v.std():4.1f}"
                          f"   범위 {v.min():+.0f}~{v.max():+.0f}")
                zs = [(a, b, abs(mu[a] - mu[b]) / max(np.sqrt((sd[a]**2 + sd[b]**2) / 2), 1e-6))
                      for a, b in zip(cols, cols[1:])]
                a, b, z = min(zs, key=lambda t: t[2])
                if z < 2.0:
                    ok = False
                    print(f"  ❌ {a}↔{b} 가 {z:.1f}σ 밖에 안 갈라진다 — 목적지를 배울 수 없다")
                else:
                    print(f"  ✅ 가장 가까운 인접 쌍 {a}↔{b} = {z:.1f}σ")

        # ── 끝맺음 ───────────────────────────────────────────────────
        #   **모델에는 종료 신호가 없다.** "이제 멈춰라"를 오직 궤적으로만 배우므로
        #   에피소드가 rest 에서 **멈춘 채** 끝나야 한다. v2(250ep)는 복귀 도중
        #   녹화가 끝나 끝 정지가 중앙 3프레임(0.1초)뿐이었고, 그 모델은 평가에서
        #   42%가 칸 위에 머문 채 타임아웃했다.
        def tail_still(x, tol=1.0):
            v = np.abs(np.diff(x, axis=0)).max(axis=1)
            n = 0
            for q in v[::-1]:
                if q < tol:
                    n += 1
                else:
                    break
            return n

        end_dev, end_still = [], []
        for e, sub in d.groupby("episode_index"):
            a = np.stack(sub.sort_values("frame_index")["observation.state"].values).astype(float)
            end_dev.append(float(np.abs(a[-1] - a[0]).max()))
            end_still.append(tail_still(a))
        end_dev = np.array(end_dev); end_still = np.array(end_still)
        # ⚠️ **최근 구간을 따로 본다.** 수집 규칙을 도중에 바꾸면 전체 중앙값은
        #    옛 방식이 끌어내려, 지금 제대로 하고 있어도 경고가 뜬다(실제로 겪음:
        #    v3 120개는 10° 이내 99% 인데 전체는 75% 로 찍혔다).
        #    판정은 **최근 100개**로 한다 — 그게 지금 수집 방식을 말해 준다.
        RECENT = min(100, len(end_dev))
        rd, rs = end_dev[-RECENT:], end_still[-RECENT:]
        print(f"\n  끝맺음 — rest 로 돌아와 멈춘 채 끝났는가")
        print(f"    {'전체':<8}{len(end_dev):>4}ep  끝 자세 중앙 {np.median(end_dev):>5.1f}° · "
              f"10° 이내 {(end_dev < 10).mean() * 100:>3.0f}% · "
              f"끝 정지 중앙 {np.median(end_still) / fps:>4.1f}s")
        print(f"    {'최근':<8}{RECENT:>4}ep  끝 자세 중앙 {np.median(rd):>5.1f}° · "
              f"10° 이내 {(rd < 10).mean() * 100:>3.0f}% · "
              f"끝 정지 중앙 {np.median(rs) / fps:>4.1f}s   ← 판정 기준")
        print(f"    끝 정지 합계 {end_still.sum():,} 프레임 — 모델이 '멈춰라'를 배우는 유일한 신호")
        end_dev, end_still = rd, rs
        if np.median(end_still) < fps * 0.5:
            print(f"  ⚠️  끝 정지가 0.5초 미만이다 — 복귀 도중 녹화가 끝나고 있다."
                  f" 놓은 뒤 rest 에서 1~2초 멈춘 뒤 종료할 것")
        elif np.median(end_dev) > 10:
            print(f"  ⚠️  끝 자세가 시작에서 10° 넘게 벗어난다 — rest 까지 안 갔다")
        else:
            print(f"  ✅ rest 에서 멈춘 채 끝난다")

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
