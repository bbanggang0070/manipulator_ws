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

OBJECTS = ["red cube", "blue cube", "yellow cube", "green cube",
           "purple cube", "orange cube", "marker", "eraser",
           "glue stick", "screwdriver"]
# 1단계는 칸 1·4만 쓴다(수집과 동일). 우연 50%.
SLOTS = [(1, "black"), (4, "white")]
TEMPLATES = ["Pick up the {obj} and put it in the {dst} bin",
             "Put the {obj} into the {dst} bin",
             "Grab the {obj} and place it in the {dst} bin"]

FIELDS = ["trial", "group", "kind", "pos", "keep_layout",
          "objects", "target", "slot", "slot_color", "instruction"]
RFIELDS = FIELDS + ["picked", "landed", "note"]


# ───────────────────────── plan ─────────────────────────
def cmd_plan(a):
    rng = random.Random(a.seed)
    rows, trial = [], 0
    tgt_count = Counter()
    for g in range(a.groups):
        # 쌍 종류를 번갈아 — 목적지 축과 물체 축을 같은 양으로 본다
        kind = "dest" if g % 2 == 0 else "obj"
        n_obj = rng.choice([2, 3, 3, 4])
        # 타깃을 **가장 적게 쓴 물체**부터 고른다. 무작위로 뽑으면 한쪽에 몰려
        # (실측: yellow 10회 vs marker 3회) 조작 난이도가 다른 물체가 과대표되고
        # 물체 축 추정이 그만큼 편향된다.
        tgt = min(OBJECTS, key=lambda o: (tgt_count[o], rng.random()))
        tgt_count[tgt] += 1
        others = [o for o in OBJECTS if o != tgt]
        objs = [tgt] + rng.sample(others, n_obj - 1)
        rng.shuffle(objs)
        if kind == "dest":
            # 같은 물체, 칸만 바꾼다
            picks = [(tgt, sl) for sl in SLOTS]
            rng.shuffle(picks)
        else:
            # 같은 칸, 지시 물체만 바꾼다 — 두 번째 타깃도 균형을 본다
            tgt2 = min([o for o in objs if o != tgt],
                       key=lambda o: (tgt_count[o], rng.random()))
            tgt_count[tgt2] += 1
            slot = rng.choice(SLOTS)
            picks = [(tgt, slot), (tgt2, slot)]
        for pos, (tgt, (snum, scol)) in enumerate(picks, start=1):
            trial += 1
            rows.append({
                "trial": trial, "group": g + 1, "kind": kind,
                "pos": f"{pos}/2", "keep_layout": "NEW" if pos == 1 else "KEEP",
                "objects": ", ".join(objs), "target": tgt,
                "slot": snum, "slot_color": scol,
                "instruction": rng.choice(TEMPLATES).format(obj=tgt, dst=scol),
            })
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader(); w.writerows(rows)

    kc = Counter(r["kind"] for r in rows)
    print(f"\n  {a.out}  —  {len(rows)}시행 ({a.groups}그룹 × 2)")
    print(f"    dest 쌍 {kc['dest']}시행 — 같은 물체, 칸만 black↔white  → 목적지 축")
    print(f"    obj  쌍 {kc['obj']}시행 — 같은 화면, 지시 물체만 변경    → 물체 축")
    print(f"\n  칸 분포: {dict(Counter(r['slot_color'] for r in rows))}")
    print(f"  예상 시간: 약 {len(rows) * 2.5 / 60:.1f}시간 (시행당 2.5분)")

    # ── 표본이 충분한가 — 돌리기 **전에** 따진다 ──────────────────────
    #   목적지 축의 분모는 '어딘가에 넣은 횟수'다. 조작 성공률이 60%쯤이면
    #   시행의 60%만 분모에 들어간다. sim 에서 68.3% 정확도를 p=0.025 로
    #   잡는 데 **배치 36건**이 필요했다. 그보다 적으면 효과가 있어도 못 잡는다.
    for rate in (0.5, 0.6, 0.7):
        placed = int(len(rows) * rate)
        mark = "OK" if placed >= 36 else ("아슬" if placed >= 24 else "부족")
        print(f"    조작 성공률 {rate*100:.0f}% 가정 -> 목적지 분모 {placed}건  [{mark}]")
    print("    (sim 기준: 정확도 68%를 p<0.05 로 잡으려면 배치 36건 필요)")
    if len(rows) * 0.6 < 36:
        need = int(36 / 0.6 / 2) + 1
        print(f"    !! --groups {need} 이상을 권합니다 — 지금 표본으로는 목적지 축이")
        print(f"       유의하게 안 나올 가능성이 큽니다")
    print("""
  ── 시행 규칙 ──────────────────────────────────────────────────────
   · pos 2/2(KEEP)는 **물체를 건드리지 않는다.** 지시문만 바꿔 다시 돌린다.
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
            env.setdefault("ENSEMBLE_W", "0.8")
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
            print("  들어간 칸:  1) black   4) white   0) 어느 칸도 아님")
            while True:
                s = input("  > ").strip()
                if s == "0":
                    landed = "(없음)"; break
                if s in ("1", "black"):
                    landed = "black"; break
                if s in ("4", "white"):
                    landed = "white"; break
                print("    1 / 4 / 0 중에서 고르세요")

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
    print(f"\n  목적지 축 — 맞는 칸으로 갔는가")
    print(f"    ⚠️ 분모는 '어딘가에 넣은 횟수'다. 조작 실패를 분모에 넣으면"
          f" 목적지 능력이 과소평가된다(sim 에서 두 번 그렇게 틀렸다).")
    cells = Counter((r["slot_color"], r["landed"]) for r in placed)
    bb, bw = cells[("black", "black")], cells[("black", "white")]
    wb, ww = cells[("white", "black")], cells[("white", "white")]
    print(f"\n    {'':<14}{'black에':>9}{'white에':>9}{'행합':>7}{'정확도':>9}")
    for lbl, (x, y), corr in (('"black" 지시', (bb, bw), bb), ('"white" 지시', (wb, ww), ww)):
        t = x + y
        print(f"    {lbl:<12}{x:>9}{y:>9}{t:>7}"
              + (f"{corr/t*100:>8.1f}%" if t else f"{'-':>9}"))
    tot = bb + bw + wb + ww
    if tot:
        acc = (bb + ww) / tot
        lo, hi = wilson(bb + ww, tot)
        p = fisher(bb, bw, wb, ww)
        a_ = bb / (bb + bw) if bb + bw else 0
        b_ = ww / (wb + ww) if wb + ww else 0
        print(f"\n    통합 {bb+ww}/{tot} = {acc*100:.1f}%   우연 50%   95% CI [{lo:.1f}, {hi:.1f}]")
        print(f"    a + b = {a_+b_:.3f}   (지시문 무시 = 1.000 · 완전히 읽음 = 2.000)")
        print(f"    Fisher 정확검정 p = {p:.4f}")
        print(f"    {'✅ 지시문이 목적지에 영향을 준다' if p < 0.05 else '⚠️  유의하지 않다 (표본 부족일 수 있다)'}")

    # ── 대응쌍 — 같은 배치, 지시문만 다름 ──
    print(f"\n  대응쌍 — 같은 배치에 지시문만 바꿨을 때")
    for kind, label in (("dest", "목적지"), ("obj", "물체")):
        gs = {}
        for r in rows:
            if r["kind"] == kind:
                gs.setdefault(r["group"], []).append(r)
        full = [v for v in gs.values() if len(v) == 2]
        if not full:
            print(f"    {label} 쌍: 완성된 그룹 없음")
            continue
        if kind == "dest":
            both = sum(1 for v in full if all(x["landed"] == x["slot_color"] for x in v))
            diff = sum(1 for v in full if v[0]["landed"] != v[1]["landed"])
            print(f"    {label} 쌍 {len(full)}그룹 — 둘 다 정답 {both} · "
                  f"**간 칸이 서로 다름 {diff}** ← 지시문을 따랐다는 직접 신호")
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
    l.add_argument("--max-sec", type=float, default=30,
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
