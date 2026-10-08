"""실기 cleanup 평가 — 계획 생성 · 결과 기록 · 분석.

**이 도구의 존재 이유는 하나다: 축을 분리해서 기록하는 것.**

  sim 1단계에서 측정 때문에 결론이 네 번 뒤집혔다. 그중 가장 비쌌던 것:
  조건 5·6의 28.3%를 보고 "목적지를 못 읽는다"고 **두 번** 결론 냈는데,
  분해해 보니 `물체+배치 45.0% × 목적지 63.0%` 였다. 목적지는 우연(50%)을
  넘고 있었고, 낮아 보인 원인은 조작이었다.

  성공/실패 한 칸으로 기록하면 그 곱에 영원히 갇힌다. 그래서 매 시행에
  **집은 물체**와 **들어간 칸**을 따로 적는다. 그러면 곱을 풀 수 있다:

      물체 축   = 지시한 물체를 집은 비율
      목적지 축 = 맞는 칸 / **어딘가에 넣은 횟수**   ← 조작 실패를 분모에서 뺀다

설계 — 대응쌍이 전부다:
  같은 배치에 **지시문만 바꿔** 두 번 돌린다. 관측이 같고 행동만 다르므로
  차이의 출처가 언어로 특정된다. sim에서 가장 강한 증거가 이 구조였다
  (색 단어 하나 빼면 63.3% → 30.0%).

    dest 쌍 : 같은 물체, 칸만 black ↔ white   → 목적지 축
    obj 쌍  : 같은 화면, 지시 물체만 바꿈      → 물체 축

사용:
  python3 cleanup_eval.py plan   --groups 12          # 평가 계획표 생성
  python3 cleanup_eval.py log                          # 시행마다 결과 입력
  python3 cleanup_eval.py report                       # 분석
"""
import argparse
import csv
import subprocess
import os
import random
import sys
from collections import Counter
from math import comb, sqrt

PLAN = os.path.expanduser("~/manipulator_ws/manipulator_md/real/cleanup_eval_plan.csv")
RESULT = os.path.expanduser("~/manipulator_ws/manipulator_md/real/cleanup_eval_result.csv")
# ⚠️ 계획표와 결과는 **한 쌍**이다. 칸 구성이나 문형을 바꾸면 둘 다 새로 만들 것 —
#    v1(2칸·문형 3종) 결과 파일을 v2(4칸·문형 1종) 계획표로 읽으면 조용히 어긋난다.

OBJECTS = ["red cube", "blue cube", "yellow cube", "green cube",
           "purple cube", "orange cube", "marker", "eraser",
           "glue stick", "screwdriver"]
# v2 수집과 동일하게 **4칸 전부**. 우연 25%.
SLOTS = [(1, "black"), (2, "cyan"), (3, "pink"), (4, "white")]
CHANCE = 1.0 / len(SLOTS)
# 문형도 **학습과 같은 1종**이어야 한다. 학습에 없던 문형으로 평가하면
# 측정한 것이 "목적지를 읽는가"가 아니라 "문형 일반화"가 섞인 값이 된다.
TEMPLATES = ["Put the {obj} into the {dst} bin"]

# ── 같은 화면에 두지 않을 쌍 (평가 전용) ────────────────────────────────
#   ⚠️ **학습에서는 같이 둔다.** 모델이 구별을 배울 기회를 없애면 안 된다.
#      여기서 거르는 건 측정 쪽이다.
#   red cube ↔ orange cube: v2 수집본 실측으로 색상환에서 **18° 차이**이고
#   (red 4° · orange 22°) 둘 다 채도가 낮다(33% · 42%, 초록 큐브는 75%).
#   사람이 봐도 구별이 어렵다. v2 평가에서 "orange" 지시의 40%(4/10)가 red 로 샜고,
#   그 4건이 전체 물체 오답 10건의 40% 였다 — **한 쌍이 물체 축 전체를 끌어내린다.**
#   측정하려는 것은 "지시문을 읽는가"이지 "18° 색차를 가르는가"가 아니므로 분리한다.
#   ⚠️ 보고서에서 물체 축의 범위를 이 결정에 맞춰 쓸 것 —
#      "red/orange 를 함께 두지 않은 조건에서 N%" 라고 적어야 한다.
EXCLUSIVE = [("red cube", "orange cube")]


def partners_of(x):
    return {b for pr in EXCLUSIVE for a, b in (pr, pr[::-1]) if a == x}

FIELDS = ["trial", "group", "kind", "pos", "keep_layout",
          "objects", "target", "slot", "slot_color", "instruction"]
RFIELDS = FIELDS + ["picked", "landed", "note"]


# ───────────────────────── plan ─────────────────────────
def cmd_plan(a):
    rng = random.Random(a.seed)
    rows, trial = [], 0
    tgt_count, slot_count = Counter(), Counter()
    for g in range(a.groups):
        # 쌍 종류를 번갈아 — 목적지 축과 물체 축을 같은 양으로 본다
        kind = "dest" if g % 2 == 0 else "obj"
        n_obj = rng.choice([2, 3, 3, 4])
        # 타깃을 **가장 적게 쓴 물체**부터 고른다. 무작위로 뽑으면 한쪽에 몰려
        # (실측: yellow 10회 vs marker 3회) 조작 난이도가 다른 물체가 과대표되고
        # 물체 축 추정이 그만큼 편향된다.
        # ⚠️ 카운터를 **그룹당 1회**가 아니라 **시행 수만큼** 올려야 한다.
        #   dest 그룹은 한 타깃으로 4시행을 돌리므로, 그룹 단위로 세면
        #   dest 로 뽑힌 물체는 4시행, obj 로 뽑힌 물체는 1시행이 된다.
        #   실측(60시행): orange 10회 vs red 2회 — 물체별 정확도를 비교할 수 없었다.
        n_trials = len(SLOTS) if kind == "dest" else 1
        tgt = min(OBJECTS, key=lambda o: (tgt_count[o], rng.random()))
        tgt_count[tgt] += n_trials
        # 상호 배제 — 타깃만이 아니라 **방해물끼리도** 막아야 한다.
        # 타깃이 marker 여도 red 와 orange 가 둘 다 방해물로 뽑힐 수 있다.
        pool = [o for o in OBJECTS if o != tgt and o not in partners_of(tgt)]
        objs = [tgt]
        for _ in range(n_obj - 1):
            if not pool:
                break
            pick = rng.choice(pool)
            objs.append(pick)
            drop = partners_of(pick) | {pick}
            pool = [o for o in pool if o not in drop]
        n_obj = len(objs)
        rng.shuffle(objs)
        if kind == "dest":
            # 같은 배치·같은 물체로 **4칸 전부** 돌린다.
            #   칸이 4개가 되면서 쌍(2칸)보다 4연속이 훨씬 효율적이다 —
            #   물체를 한 번만 놓고 지시문만 네 번 바꾸므로 시행당 준비 시간이
            #   1/4 이고, 한 배치에서 '네 번 다 다른 칸으로 갔는가'라는
            #   가장 강한 신호가 직접 나온다.
            picks = [(tgt, sl) for sl in SLOTS]
            rng.shuffle(picks)
        else:
            # 같은 칸, 지시 물체만 바꾼다 — 두 번째 타깃도 균형을 본다
            tgt2 = min([o for o in objs if o != tgt],
                       key=lambda o: (tgt_count[o], rng.random()))
            tgt_count[tgt2] += 1
            # 칸도 **가장 적게 쓴 것**부터. 무작위로 고르면 4연속이 10씩 깔아 둔
            # 위에 obj 쌍 20시행이 쏠려 12~18 로 벌어진다(실측).
            slot = min(SLOTS, key=lambda sl: (slot_count[sl[1]], rng.random()))
            picks = [(tgt, slot), (tgt2, slot)]
        for pos, (tgt, (snum, scol)) in enumerate(picks, start=1):
            trial += 1
            slot_count[scol] += 1
            rows.append({
                "trial": trial, "group": g + 1, "kind": kind,
                "pos": f"{pos}/{len(picks)}", "keep_layout": "NEW" if pos == 1 else "KEEP",
                "objects": ", ".join(objs), "target": tgt,
                "slot": snum, "slot_color": scol,
                "instruction": rng.choice(TEMPLATES).format(obj=tgt, dst=scol),
            })
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader(); w.writerows(rows)

    kc = Counter(r["kind"] for r in rows)
    gq = len({r["group"] for r in rows if r["kind"] == "dest"})
    gp = len({r["group"] for r in rows if r["kind"] == "obj"})
    print(f"\n  {a.out}  —  {len(rows)}시행")
    print(f"    dest 4연속 {gq}그룹 = {kc['dest']}시행 — 같은 물체, 칸 4개 전부  → 목적지 축")
    print(f"    obj  쌍    {gp}그룹 = {kc['obj']}시행 — 같은 화면, 지시 물체만 변경 → 물체 축")
    print(f"\n  칸 분포: {dict(Counter(r['slot_color'] for r in rows))}")
    bad = [r["trial"] for r in rows
           for a, b in EXCLUSIVE
           if a in r["objects"] and b in r["objects"]]
    print(f"  상호 배제({', '.join(a + '↔' + b for a, b in EXCLUSIVE)}): "
          + (f"✅ 위반 0건" if not bad else f"❌ 위반 {len(bad)}건 {bad[:5]}"))
    print(f"  예상 시간: 약 {len(rows) * 2.5 / 60:.1f}시간 (시행당 2.5분)")

    # ── 표본이 충분한가 — 돌리기 **전에** 따진다 ──────────────────────
    #   목적지 축의 분모는 '어딘가에 넣은 횟수'다. 조작 성공률이 60%쯤이면
    #   시행의 60%만 분모에 들어간다. sim 에서 68.3% 정확도를 p=0.025 로
    #   잡는 데 **배치 36건**이 필요했다. 그보다 적으면 효과가 있어도 못 잡는다.
    #   ⚠️ 칸이 4개가 되어 **우연이 25%로 내려갔다.** 같은 표본으로 훨씬 잘 잡힌다.
    #      칸 2개(우연 50%) 때는 36건이 필요했지만, 우연 25%에서는 20건이면
    #      정확도 50%를 p<0.05 로 잡는다(이항검정).
    NEED = 20
    for rate in (0.4, 0.6, 0.8):
        placed = int(len(rows) * rate)
        mark = "OK" if placed >= NEED else ("아슬" if placed >= 14 else "부족")
        print(f"    조작 성공률 {rate*100:.0f}% 가정 -> 목적지 분모 {placed}건  [{mark}]")
    print(f"    (우연 25% 기준: 정확도 50%를 p<0.05 로 잡으려면 배치 {NEED}건)")
    if len(rows) * 0.4 < NEED:
        print(f"    !! 조작이 안 풀리면 표본이 모자랍니다 — --groups 를 올리세요")
    print("""
  ── 시행 규칙 ──────────────────────────────────────────────────────
   · pos 2/N 이후(KEEP)는 **물체를 건드리지 않는다.** 지시문만 바꿔 다시 돌린다.
     관측이 같아야 차이의 출처가 언어로 특정된다.
   · 로봇이 멈추면 **집은 물체**와 **들어간 칸**을 본 대로 적는다.
     성공/실패로 뭉치지 말 것 — 뭉치면 곱에 갇혀 목적지 축을 못 읽는다.
""")
    return 0


# ───────────────────────── log ─────────────────────────
def cmd_log(a):
    plan = list(csv.DictReader(open(a.plan)))
    done = {}
    if os.path.exists(a.out):
        done = {r["trial"]: r for r in csv.DictReader(open(a.out))}
    print(f"\n  계획 {len(plan)}시행 · 기록됨 {len(done)}시행\n")

    objs_all = sorted(OBJECTS)
    for r in plan:
        if r["trial"] in done and not a.redo:
            continue
        print("=" * 64)
        if r["keep_layout"] == "KEEP":
            print("  \033[1;41m  ████ 물체를 건드리지 마세요 — 배치 그대로 ████  \033[0m")
        print(f"  시행 {r['trial']}/{len(plan)}   [{r['kind']} 쌍 {r['pos']}]")
        print("-" * 64)
        if r["keep_layout"] == "NEW":
            print(f"  놓을 물체 :  \033[1m{r['objects']}\033[0m")
        else:
            print(f"  물체      :  \033[2m{r['objects']}  (그대로)\033[0m")
        print(f"  지시문    :  \033[1;36m\"{r['instruction']}\"\033[0m")
        print(f"  정답      :  {r['target']} → {r['slot']}번({r['slot_color']})")
        print("=" * 64)

        # ── 로봇 실행 ────────────────────────────────────────────────
        #   log 는 원래 기록만 했는데, 그러면 매 시행마다 다른 터미널에서
        #   run_eval_real.sh 를 지시문까지 복사해 붙여야 한다. 오타 한 번이면
        #   엉뚱한 지시문으로 돌고 그 시행은 버린다. 여기서 바로 띄운다.
        if not a.no_run:
            input("  물체를 놓았으면 Enter (로봇이 출발합니다) ")
            cond = f"trial{int(r['trial']):02d}"
            # MAX_SEC: 실패 시행이 그냥 서 있으면 60시행이 끝나지 않는다.
            # 시간이 다 되면 러너가 스스로 빠져나와 다음 시행으로 넘어간다.
            env = dict(os.environ, LANG_INSTRUCTION=r["instruction"],
                       MAX_SEC=str(a.max_sec))
            # 아래 둘은 **이 모델에 맞는 값**이다. 사용자가 환경변수로 준 값이 이긴다.
            #   HOME_SCRIPT — goto_home_real.py 는 so101_blocktask_real 50ep 기준이라
            #     cleanup_real 의 시작 자세와 wrist_flex 가 18.3° 다르다. 그대로 쓰면
            #     정책이 학습 시작 분포 밖에서 출발한다.
            #   ENSEMBLE_W — run_eval_real.sh 기본값 0.6 은 그 스크립트 자신의 실측표에서
            #     **최악(1/5)**으로 적혀 있고 0.8 이 최적으로 적혀 있다. 0.8 로 둔다.
            #     (그 표는 co-train blocktask 모델 실측이므로 이 모델에서 재확인 필요)
            env.setdefault("HOME_SCRIPT", "goto_home_cleanup.py")
            # 작업이 끝나면(rest 로 복귀해 머물면) 스스로 멈춘다. 없으면 MAX_SEC
            # 까지 rest 를 유지하는 행동을 계속 내놓는다 — 모델에 종료 신호가 없다.
            env.setdefault("STOP_ON_REST", "1")
            env.setdefault("ENSEMBLE_W", "0.3")
            runner = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "..", "gr00t", "run_eval_real.sh")
            if not os.path.exists(runner):
                print(f"  ⚠️  러너 없음: {runner} — 직접 돌린 뒤 결과만 입력하세요")
            else:
                print(f"\n  ▶ 실행: LANG_INSTRUCTION=\"{r['instruction']}\"")
                _lim = f"{a.max_sec:.0f}s 후 자동 종료" if a.max_sec else "Ctrl+C 로 멈추세요"
                print(f"     ({_lim} · 먼저 끝내려면 Ctrl+C)\n")
                subprocess.call(["bash", runner, a.eval_name, cond],
                                cwd=os.path.dirname(runner), env=env)
                # 시행이 끝나면 **rest 로 돌려놓는다.** 추론 루프는 멈춘 자리에서
                # 그대로 끝나는데, 그 자리가 보통 칸 바로 위라 **어느 칸에 들어갔는지
                # 가린다.** 다음 시행의 홈 복귀는 물체를 다시 놓은 뒤에 일어나므로
                # 판정 시점에는 늦다. 여기서 먼저 비켜 준다.
                # env(러너에 넘긴 것)에서 읽는다 — os.environ 에는 setdefault 로
                # 넣은 HOME_SCRIPT 가 없어서 러너와 다른 홈을 쓸 뻔했다.
                home = os.path.join(os.path.dirname(runner), env["HOME_SCRIPT"])
                lerobot = os.path.join(os.path.dirname(runner), "..", "..", "envs", "lerobot")
                if os.path.exists(home) and not a.no_home:
                    print("  ▶ rest 자세로 복귀 중...", end=" ", flush=True)
                    # 실패를 삼키지 않는다. 복귀가 안 되면 팔이 칸을 가린 채로
                    # 판정하게 되고, 다음 시행의 출발 자세도 틀어진다.
                    rc = subprocess.call(["uv", "run", "python", os.path.abspath(home)],
                                         cwd=os.path.abspath(lerobot),
                                         stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL)
                    print("완료" if rc == 0 else f"⚠️ 실패(rc={rc}) — 팔을 손으로 치우고 판정하세요")
                print()
        else:
            print("  로봇을 직접 돌린 뒤 결과를 입력하세요.")

        print("  로봇이 멈췄으면 **본 대로** 입력하세요.\n")

        # 집은 물체 — 지시와 무관하게 실제로 집은 것
        print("  집은 물체:")
        on = [o.strip() for o in r["objects"].split(",")]
        for i, o in enumerate(on, 1):
            print(f"    {i}) {o}" + ("   ← 지시" if o == r["target"] else ""))
        print("    0) 아무것도 못 집음")
        while True:
            s = input("  > ").strip()
            if s == "0":
                picked = "(없음)"; break
            if s.isdigit() and 1 <= int(s) <= len(on):
                picked = on[int(s) - 1]; break
            if s in objs_all:
                picked = s; break
            print("    번호나 물체 이름을 입력하세요")

        # 들어간 칸 — 집기 실패면 자동으로 '없음'
        if picked == "(없음)":
            landed = "(없음)"
            print("  들어간 칸: (집지 못해 자동 '없음')")
        else:
            # ⚠️ 선택지는 **SLOTS 에서 만든다.** 예전에 black·white 를 박아 두었다가
            #    4칸으로 넓힌 뒤에도 두 칸만 입력할 수 있어 cyan·pink 를 기록할 수 없었다.
            menu = "   ".join(f"{n}) {c}" for n, c in SLOTS)
            print(f"  들어간 칸:  {menu}   0) 어느 칸도 아님")
            by_num = {str(n): c for n, c in SLOTS}
            by_name = {c: c for _, c in SLOTS}
            while True:
                s = input("  > ").strip().lower()
                if s == "0":
                    landed = "(없음)"; break
                if s in by_num:
                    landed = by_num[s]; break
                if s in by_name:
                    landed = by_name[s]; break
                print(f"    {'/'.join(by_num)} 또는 색 이름, 아니면 0")

        note = input("  메모(선택, Enter로 건너뜀): ").strip()
        row = dict(r); row.update(picked=picked, landed=landed, note=note)
        done[r["trial"]] = row

        os.makedirs(os.path.dirname(a.out), exist_ok=True)
        with open(a.out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=RFIELDS)
            w.writeheader()
            for t in sorted(done, key=int):
                w.writerow({k: done[t].get(k, "") for k in RFIELDS})
        ok_o = "✅" if picked == r["target"] else "❌"
        ok_d = "✅" if landed == r["slot_color"] else "❌"
        print(f"  기록됨 — 물체 {ok_o}  목적지 {ok_d}\n")
    print("  모든 시행 기록 완료.  분석: python3 cleanup_eval.py report")
    return 0


# ───────────────────────── report ─────────────────────────
def fisher(a_, b_, c_, d_):
    n = a_ + b_ + c_ + d_
    r1, r2, c1 = a_ + b_, c_ + d_, a_ + c_
    if min(r1, r2, c1, n - c1) < 0 or n == 0:
        return 1.0
    p = lambda x: comb(r1, x) * comb(r2, c1 - x) / comb(n, c1)
    p0 = p(a_)
    return sum(p(x) for x in range(max(0, c1 - r2), min(r1, c1) + 1) if p(x) <= p0 * (1 + 1e-12))


def binom_p(k, n, p0):
    """관측 k/n 이 우연 p0 보다 **높을** 확률(단측 정확검정).

    scipy 없이 쓰려고 직접 센다. 칸이 4개가 되며 우연이 25%로 내려가,
    2×2 Fisher 보다 이쪽이 바로 답을 준다.
    """
    from math import comb
    return sum(comb(n, i) * p0 ** i * (1 - p0) ** (n - i) for i in range(k, n + 1))


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    ph = k / n; den = 1 + z * z / n
    c = (ph + z * z / (2 * n)) / den
    hw = z * sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / den
    return ((c - hw) * 100, (c + hw) * 100)


def cmd_report(a):
    if not os.path.exists(a.out):
        sys.exit(f"❌ 결과 없음: {a.out}  (먼저 log 를 돌리세요)")
    rows = list(csv.DictReader(open(a.out)))
    print(f"\n{'=' * 66}\n실기 cleanup 평가 — {len(rows)}시행\n{'=' * 66}")

    # ── 조작 (언어와 무관) ──
    picked_any = [r for r in rows if r["picked"] != "(없음)"]
    placed = [r for r in picked_any if r["landed"] != "(없음)"]
    print(f"\n  조작 — 언어 성능과 섞이면 안 되는 항")
    print(f"    무언가 집음        {len(picked_any)}/{len(rows)} = {len(picked_any)/len(rows)*100:.1f}%")
    print(f"    칸에 넣음          {len(placed)}/{len(rows)} = {len(placed)/len(rows)*100:.1f}%")

    # ── 물체 축 ──
    n_obj = [len(r["objects"].split(",")) for r in rows]
    chance_o = sum(1 / n for n in n_obj) / len(rows) * 100
    hit_o = sum(1 for r in rows if r["picked"] == r["target"])
    lo, hi = wilson(hit_o, len(rows))
    print(f"\n  물체 축 — 지시한 물체를 집었는가")
    print(f"    {hit_o}/{len(rows)} = {hit_o/len(rows)*100:.1f}%   "
          f"우연 {chance_o:.1f}% (화면당 물체 수 가변)   95% CI [{lo:.1f}, {hi:.1f}]")
    print(f"    {'✅ 우연 초과' if lo > chance_o else '⚠️  우연과 구별 안 됨'}")

    # ── 목적지 축 — **분모가 핵심** ──
    COLS = [c for _, c in SLOTS]
    print(f"\n  목적지 축 — 맞는 칸으로 갔는가")
    print(f"    ⚠️ 분모는 '어딘가에 넣은 횟수'다. 조작 실패를 분모에 넣으면"
          f" 목적지 능력이 과소평가된다(sim 에서 두 번 그렇게 틀렸다).")
    cells = Counter((r["slot_color"], r["landed"]) for r in placed)
    hdr = "".join(f"{c:>8}" for c in COLS)
    print(f"\n    {'지시 \\ 착지':<14}{hdr}{'행합':>7}{'정확도':>9}")
    corr = tot = 0
    for ins in COLS:
        row = [cells[(ins, land)] for land in COLS]
        t = sum(row)
        c = cells[(ins, ins)]
        corr += c; tot += t
        print(f"    {'\"' + ins + '\" 지시':<14}" + "".join(f"{v:>8}" for v in row)
              + f"{t:>7}" + (f"{c / t * 100:>8.1f}%" if t else f"{'-':>9}"))
    # 착지 쏠림 — 지시와 무관하게 특정 칸으로 도망가는지 본다
    land_tot = [sum(cells[(ins, land)] for ins in COLS) for land in COLS]
    print(f"    {'(착지 합계)':<14}" + "".join(f"{v:>8}" for v in land_tot))

    if tot:
        acc = corr / tot
        lo, hi = wilson(corr, tot)
        p = binom_p(corr, tot, CHANCE)
        print(f"\n    통합 {corr}/{tot} = {acc * 100:.1f}%   우연 {CHANCE * 100:.0f}%"
              f"   95% CI [{lo:.1f}, {hi:.1f}]")
        print(f"    이항검정 p = {p:.5f}  (우연보다 높을 확률)")
        print(f"    {'✅ 지시문이 목적지를 정한다' if p < 0.05 else '⚠️  유의하지 않다 (표본 부족일 수 있다)'}")
        # 쏠림: 착지 분포가 균등에서 얼마나 벗어났나
        if sum(land_tot):
            worst = max(land_tot) / sum(land_tot)
            print(f"    착지 쏠림: 가장 많이 간 칸이 전체의 {worst * 100:.0f}%"
                  f" (균등이면 {CHANCE * 100:.0f}%)"
                  + ("  ← 특정 칸으로 도망가는 경향" if worst > 0.45 else ""))

    # ── 대응쌍 — 같은 배치, 지시문만 다름 ──
    print(f"\n  대응쌍 — 같은 배치에 지시문만 바꿨을 때")
    for kind, label in (("dest", "목적지"), ("obj", "물체")):
        gs = {}
        for r in rows:
            if r["kind"] == kind:
                gs.setdefault(r["group"], []).append(r)
        want = len(SLOTS) if kind == "dest" else 2
        full = [v for v in gs.values() if len(v) == want]
        if not full:
            print(f"    {label} 그룹: 완성된 것 없음")
            continue
        if kind == "dest":
            both = sum(1 for v in full if all(x["landed"] == x["slot_color"] for x in v))
            # ⚠️ '네 번 다 다른 칸으로 갔는가'를 **전체 4시행**에 요구하면,
            #    하나만 조작에 실패해도 0 이 되어 신호가 늘 0 으로 찍힌다.
            #    조작 실패를 분모에서 빼는 목적지 축의 원칙을 여기에도 적용한다:
            #    **놓은 시행만** 보고, 그것들이 서로 다른 칸으로 갔는지 센다.
            ok = spread = 0
            for v in full:
                got = [x["landed"] for x in v if x["landed"] not in ("", "(없음)", "-")]
                if len(got) >= 2:
                    spread += 1
                    if len(set(got)) == len(got):
                        ok += 1
            print(f"    {label} {want}연속 {len(full)}그룹 — 전부 정답 {both}")
            if spread:
                print(f"      2회 이상 놓은 그룹 {spread}개 중 **놓은 칸이 전부 서로 다름"
                      f" {ok}개 ({ok / spread * 100:.0f}%)** ← 지시문을 따랐다는 직접 신호")
                print(f"      (지시문을 무시하면 같은 칸으로 반복해 이 값이 0 에 가깝다)")
            else:
                print(f"      2회 이상 놓은 그룹이 없다 — 조작이 먼저다")
        else:
            both = sum(1 for v in full if all(x["picked"] == x["target"] for x in v))
            diff = sum(1 for v in full if v[0]["picked"] != v[1]["picked"])
            print(f"    {label} 쌍 {len(full)}그룹 — 둘 다 정답 {both} · "
                  f"**집은 물체가 서로 다름 {diff}** ← 지시문을 따랐다는 직접 신호")

    print(f"\n  ※ 축을 따로 적었기에 곱이 풀린다. 성공/실패 한 칸만 적었다면"
          f"\n     '{len(placed)/len(rows)*100:.0f}% 성공'으로 뭉뚱그려져 목적지 축을 못 읽는다.")
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan"); p.add_argument("--groups", type=int, default=30)
    p.add_argument("--seed", type=int, default=7); p.add_argument("--out", default=PLAN)
    p.set_defaults(fn=cmd_plan)
    l = sub.add_parser("log"); l.add_argument("--plan", default=PLAN)
    l.add_argument("--out", default=RESULT); l.add_argument("--redo", action="store_true")
    l.add_argument("--no-run", action="store_true",
                   help="로봇을 띄우지 않고 기록만 한다(다른 터미널에서 돌릴 때)")
    l.add_argument("--no-home", action="store_true",
                   help="시행이 끝나도 rest 로 복귀시키지 않는다(팔이 그 자리에 선다)")
    # 30초로 시작했는데 모자랐다 — 4칸이 되며 cyan·pink 같은 중간 칸까지 가야 하고,
    # 수집 시연의 중앙값이 21.8초(최대 48.9초)다. 추론은 시연보다 느리므로 1분을 준다.
    l.add_argument("--max-sec", type=float, default=60,
                   help="시행 1회 제한 시간(초). 지나면 다음 시행으로 넘어간다. 0=무제한")
    l.add_argument("--eval-name", default="cleanup",
                   help="run_eval_real.sh 의 평가 이름 — 영상 저장 폴더가 된다")
    l.set_defaults(fn=cmd_log)
    r = sub.add_parser("report"); r.add_argument("--out", default=RESULT)
    r.set_defaults(fn=cmd_report)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
