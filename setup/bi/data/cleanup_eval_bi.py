"""양팔(bi-manipulator) cleanup 실기 평가 — 계획 생성 · 결과 기록 · 분석.

setup/data/cleanup_eval.py 의 양팔판. 단일팔은 축이 둘(물체·목적지)이었지만
양팔은 **전달(handoff)이 끼어들어 셋**이다 — bi_manipulator_plan.md §2-2:

    오른팔 파지 → (그리퍼 대 그리퍼 전달) → 왼팔 배치
    picked(우완)  →  handoff(전달 성공?)   →  landed(좌완)

단일팔 cleanup_eval.py와 똑같은 이유로 셀 하나에 성공/실패를 뭉치지 않는다 —
"성공 40%"만 보면 그게 집기 문제인지 전달 문제인지 배치 문제인지 못 가린다.
**목적지 축의 분모는 '전달까지 성공한 시행 중'**이어야 공정하다(전달 실패를
목적지 분모에 넣으면 왼팔 배치 능력이 과소평가된다 — 애초에 왼팔이 받지도
못했으니까).

물체(8종)·칸(4색)·지시문 형식은 데이터 수집(setup/bi/data/gen_bi_plan.py)과
**그대로 맞춘다** — 평가가 수집과 다른 어휘·문형을 쓰면 측정하는 게
"지시문을 읽는가"가 아니라 "분포 밖 일반화"가 섞인다.

사용:
  python3 cleanup_eval_bi.py plan   --groups 12          # 평가 계획표 생성
  python3 cleanup_eval_bi.py log                          # 시행마다 결과 입력(로봇 자동 실행)
  python3 cleanup_eval_bi.py report                       # 분석
"""
import argparse
import csv
import subprocess
import os
import random
import sys
from collections import Counter
from math import comb, sqrt

PLAN = os.path.expanduser("~/manipulator_ws/manipulator_md/p6_real_bimanual/bi_cleanup_eval_plan.csv")
RESULT = os.path.expanduser("~/manipulator_ws/manipulator_md/p6_real_bimanual/bi_cleanup_eval_result.csv")
# ⚠️ 계획표와 결과는 **한 쌍**이다 — 칸 구성·물체 목록을 바꾸면 둘 다 새로 만들 것.

# setup/bi/data/gen_bi_plan.py 와 동일(2026-10-14 변경본) — 평가가 수집과 다른
# 물체 목록을 쓰면 분포 밖 일반화가 섞인다.
OBJECTS = ["red marker", "blue marker", "black marker", "yellow straw",
           "glue stick", "toothbrush", "eraser", "screwdriver"]
SLOTS = [(1, "black"), (2, "cyan"), (3, "pink"), (4, "white")]
CHANCE = 1.0 / len(SLOTS)
TEMPLATES = ["Put the {obj} into the {dst} bin"]

# gen_bi_plan.py 와 동일 — 아직 실측 근거가 없어 비워 둔다. 평가에서 특정
# 물체 쌍이 자주 혼동되는 게 보이면 그 실측을 근거로 추가할 것(짐작으로 미리
# 배제하지 않는다 — 단일팔 cleanup_eval.py 의 red/orange cube 교훈과 같다).
EXCLUSIVE = []

# gen_bi_plan.py 와 동일 — eraser 는 항상 세워서 배치(사용자 지정, 2026-10-14).
POSE_VARIANTS = {"eraser": "세워서"}


def partners_of(x):
    return {b for pr in EXCLUSIVE for a, b in (pr, pr[::-1]) if a == x}


FIELDS = ["trial", "group", "kind", "pos", "keep_layout",
          "objects", "target", "slot", "slot_color", "pose_hint", "instruction", "layout"]
# layout = 그 시행의 칸 배치("1번 black · 2번 cyan · 3번 pink · 4번 white"). 비어 있으면 SLOTS(평가 기본 배치).
# 평가 B(bi_cleanup_eval_plan_B.csv)처럼 시행 도중 배치가 바뀌는 계획표에서 쓴다 — 배치가 바뀌는
# 시행에서 log 가 안내를 띄우고, report 는 배치별 정확도와 "위치 기준" 착지 분포를 따로 낸다.


def layout_slots(r):
    """시행의 칸 배치 → [(번호, 색)]. layout 이 비어 있으면 SLOTS."""
    lay = (r.get("layout") or "").strip()
    if not lay:
        return SLOTS
    out = []
    for part in lay.split("·"):
        num, col = part.strip().split("번")
        out.append((int(num), col.strip()))
    return sorted(out)
# picked  = 오른팔이 실제로 집은 물체 (지시와 무관하게 본 대로)
# handoff = 전달(그리퍼 대 그리퍼)이 성공했는가 — picked가 "(없음)"이면 자동 "(없음)"
# landed  = 왼팔이 넣은 칸 — handoff가 "성공"이 아니면 자동 "(없음)"
RFIELDS = FIELDS + ["picked", "handoff", "landed", "note"]


# ───────────────────────── plan ─────────────────────────
def cmd_plan(a):
    rng = random.Random(a.seed)
    rows, trial = [], 0
    tgt_count, slot_count = Counter(), Counter()
    for g in range(a.groups):
        kind = "dest" if g % 2 == 0 else "obj"
        n_obj = rng.choice([2, 3, 3, 4])
        tgt = min(OBJECTS, key=lambda o: (tgt_count[o], rng.random()))
        n_trials = len(SLOTS) if kind == "dest" else 1
        tgt_count[tgt] += n_trials
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
            picks = [(tgt, sl) for sl in SLOTS]
            rng.shuffle(picks)
        else:
            tgt2 = min([o for o in objs if o != tgt],
                       key=lambda o: (tgt_count[o], rng.random()))
            tgt_count[tgt2] += 1
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
                "pose_hint": " · ".join(f"{o} {POSE_VARIANTS[o]}"
                                        for o in objs if o in POSE_VARIANTS),
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
           for a_, b_ in EXCLUSIVE
           if a_ in r["objects"] and b_ in r["objects"]]
    print(f"  상호 배제: " + ("✅ (설정 없음)" if not EXCLUSIVE else
          (f"✅ 위반 0건" if not bad else f"❌ 위반 {len(bad)}건 {bad[:5]}")))
    # 전달 단계가 끼어 단일팔보다 시행당 시간이 길다(home_then_infer_bi.sh 기본
    # MAX_SEC 추정치 근거, §6/§7 수집 시간 추정과 같은 정신 — 실측 전 추정).
    print(f"  예상 시간: 약 {len(rows) * 3.0 / 60:.1f}시간 (시행당 3분 추정 — 전달 단계 포함, 실측 전)")

    NEED = 20
    for rate in (0.4, 0.6, 0.8):
        placed = int(len(rows) * rate)
        mark = "OK" if placed >= NEED else ("아슬" if placed >= 14 else "부족")
        print(f"    (조작+전달) 성공률 {rate*100:.0f}% 가정 -> 목적지 분모 {placed}건  [{mark}]")
    print(f"    (우연 25% 기준: 정확도 50%를 p<0.05 로 잡으려면 배치 {NEED}건)")
    if len(rows) * 0.4 < NEED:
        print(f"    !! 조작/전달이 안 풀리면 표본이 모자랍니다 — --groups 를 올리세요")
    print("""
  ── 시행 규칙 ──────────────────────────────────────────────────────
   · 물체는 **오른팔 집는 영역**에 놓는다(선반 4칸은 왼팔 쪽에 고정).
   · pos 2/N 이후(KEEP)는 **물체를 건드리지 않는다.** 지시문만 바꿔 다시 돌린다.
   · 로봇이 멈추면 **집은 물체(우완)·전달 성공 여부·들어간 칸(좌완)**을
     본 대로 적는다. 성공/실패로 뭉치지 말 것 — 뭉치면 세 능력을 못 가른다.
""")
    return 0


# ───────────────────────── log ─────────────────────────
def cmd_log(a):
    plan = list(csv.DictReader(open(a.plan)))
    done = {}
    if os.path.exists(a.out):
        done = {r["trial"]: r for r in csv.DictReader(open(a.out))}
    # 평가 A 결과(layout 열 없음)를 평가 B 결과로 가져와 이어 할 때 — 같은 trial 의 배치를 계획표에서 채운다
    lay_of = {r["trial"]: r.get("layout", "") for r in plan}
    for t, r in done.items():
        if not r.get("layout") and lay_of.get(t):
            r["layout"] = lay_of[t]
    print(f"\n  계획 {len(plan)}시행 · 기록됨 {len(done)}시행")
    if any(r.get("layout") for r in plan):
        print("  ⚠️ 물체는 오른팔 집는 영역에 놓으세요 — 칸 배치는 바뀔 때마다 안내가 뜹니다.\n")
    else:
        print("  ⚠️ 물체는 오른팔 집는 영역에 놓으세요 — 선반 4칸(black·cyan·pink·white)은 왼팔 쪽에 고정돼 있습니다.\n")

    objs_all = sorted(OBJECTS)
    prev_layout = None
    for r in plan:
        if r["trial"] in done and not a.redo:
            prev_layout = r.get("layout") or None
            continue
        lay = r.get("layout") or None
        if lay and lay != prev_layout:
            print("\n" + "#" * 64)
            print("  \033[1;43;30m  ████ 칸 배치를 바꾸세요 ████  \033[0m")
            print(f"  \033[1m{lay}\033[0m")
            print("#" * 64)
            input("  칸 배치를 바꿨으면 Enter ")
        prev_layout = lay
        print("=" * 64)
        if r["keep_layout"] == "KEEP":
            print("  \033[1;41m  ████ 물체를 건드리지 마세요 — 배치 그대로 ████  \033[0m")
        print(f"  시행 {r['trial']}/{len(plan)}   [{r['kind']} 쌍 {r['pos']}]")
        print("-" * 64)
        if r["keep_layout"] == "NEW":
            print(f"  놓을 물체(오른팔 영역) :  \033[1m{r['objects']}\033[0m")
        else:
            print(f"  물체      :  \033[2m{r['objects']}  (그대로)\033[0m")
        print(f"  지시문    :  \033[1;36m\"{r['instruction']}\"\033[0m")
        if r.get("pose_hint"):
            print(f"  놓는 자세 :  \033[1;35m{r['pose_hint']}\033[0m")
        if lay:
            print(f"  칸 배치   :  {lay}")
        print(f"  정답      :  {r['target']} → 전달 → {r['slot']}번({r['slot_color']})")
        print("=" * 64)

        if not a.no_run:
            input("  물체를 놓았으면 Enter (로봇이 출발합니다) ")
            cond = f"trial{int(r['trial']):02d}"
            env = dict(os.environ, LANG_INSTRUCTION=r["instruction"],
                       MAX_SEC=str(a.max_sec))
            # 작업이 끝나면(양팔 모두 rest 로 복귀해 머물면) 스스로 멈춘다.
            # eval_lerobot_bi.py 는 robot_state_keys 12개를 그대로 보고 판정하므로
            # "양팔 다 돌아와야 끝" 이 공짜로 보장된다(단일팔 로직 변경 없음).
            env.setdefault("STOP_ON_REST", "1")
            # cleanup_eval.py 와 같은 이유로 배치 실행 중 rerun 메모리 누적을 막는다
            # (2026-10-14 실측: 96시행 배치에서 rerun이 54GB까지 먹어 카메라 읽기가 멈춤).
            if a.rerun:
                env["RERUN"] = "1"
            else:
                env.setdefault("RERUN", "0")
            runner = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "..", "gr00t", "run_eval_real_bi.sh")
            if not os.path.exists(runner):
                print(f"  ⚠️  러너 없음: {runner} — 직접 돌린 뒤 결과만 입력하세요")
            else:
                print(f"\n  ▶ 실행: LANG_INSTRUCTION=\"{r['instruction']}\"")
                _lim = f"{a.max_sec:.0f}s 후 자동 종료" if a.max_sec else "Ctrl+C 로 멈추세요"
                print(f"     ({_lim} · 가망 없으면 \033[1;33mq\033[0m 한 번 → 결과 입력으로)\n")
                # Ctrl+C 를 눌러도 배치 전체가 끊기지 않고 이 시행의 결과 입력으로 넘어가게 한다
                # (SIGINT 는 자식과 이 프로세스에 같이 가므로 여기서 받아 넘긴다)
                # subprocess.call 은 KeyboardInterrupt 때 자식을 kill(-9)해 영상이 깨지므로 Popen 으로 기다린다
                proc = subprocess.Popen(["bash", runner, a.eval_name, cond],
                                        cwd=os.path.dirname(runner), env=env)
                while True:
                    try:
                        proc.wait()
                        break
                    except KeyboardInterrupt:
                        print("\n  (Ctrl+C — 이 시행 중단, 정리 후 결과 입력으로 넘어갑니다)")
                # eval_lerobot_bi.py 는 끝날 때 스스로 그 자리 정지 → rest 복귀(토크 유지)를 한다.
                # 종료 코드 3 = 그 복귀가 실패해 팔이 공중에서 버티는 중. 아래 goto_home_bi.py 는 연결할 때
                # 설정을 쓰느라 토크를 잠깐 끄므로(lerobot SOFollower.configure) 그 전에 사람이 받쳐야 한다.
                if proc.returncode == 3:
                    print("\n  \033[1;31m⚠️  rest 자동 복귀 실패 — 팔이 공중에서 토크로 버티는 중\033[0m")
                    input("  팔을 손으로 받치거나 안전한 자세로 옮긴 뒤 Enter (홈 이동 중 토크가 잠깐 꺼짐) ")
                home = os.path.join(os.path.dirname(runner), "goto_home_bi.py")
                lerobot = os.path.join(os.path.dirname(runner), "..", "..", "..", "envs", "lerobot")
                if os.path.exists(home) and not a.no_home:
                    print("  ▶ rest 자세로 복귀 중...", end=" ", flush=True)
                    rc = subprocess.call(["uv", "run", "python", os.path.abspath(home)],
                                         cwd=os.path.abspath(lerobot),
                                         stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL)
                    print("완료" if rc == 0 else f"⚠️ 실패(rc={rc}) — 팔을 손으로 치우고 판정하세요")
                print()
        else:
            print("  로봇을 직접 돌린 뒤 결과를 입력하세요.")

        print("  로봇이 멈췄으면 **본 대로** 입력하세요.\n")

        # ── 1) 집은 물체 — 오른팔, 지시와 무관하게 실제로 집은 것 ──
        print("  집은 물체(오른팔):")
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

        # ── 2) 전달 성공 여부 — 집지 못했으면 자동 '없음' ──
        if picked == "(없음)":
            handoff = "(없음)"
            print("  전달: (집지 못해 자동 '없음')")
        else:
            while True:
                s = input("  전달(그리퍼→그리퍼) 성공했나요?  1) 성공   0) 실패(떨어뜨림 등)\n  > ").strip()
                if s in ("1", "y", "yes", "성공"):
                    handoff = "성공"; break
                if s in ("0", "n", "no", "실패"):
                    handoff = "실패"; break
                print("    1 또는 0 을 입력하세요")

        # ── 3) 들어간 칸 — 전달 실패면 자동 '없음' ──
        if handoff != "성공":
            landed = "(없음)"
            print("  들어간 칸: (전달 실패로 자동 '없음')")
        else:
            slots_r = layout_slots(r)
            menu = "   ".join(f"{n}) {c}" for n, c in slots_r)
            print(f"  들어간 칸(왼팔):  {menu}   0) 어느 칸도 아님")
            by_num = {str(n): c for n, c in slots_r}
            by_name = {c: c for _, c in slots_r}
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
        row = dict(r); row.update(picked=picked, handoff=handoff, landed=landed, note=note)
        done[r["trial"]] = row

        os.makedirs(os.path.dirname(a.out), exist_ok=True)
        with open(a.out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=RFIELDS)
            w.writeheader()
            for t in sorted(done, key=int):
                w.writerow({k: done[t].get(k, "") for k in RFIELDS})
        ok_o = "✅" if picked == r["target"] else "❌"
        ok_h = "✅" if handoff == "성공" else ("—" if handoff == "(없음)" else "❌")
        ok_d = "✅" if landed == r["slot_color"] else ("—" if landed == "(없음)" else "❌")
        print(f"  기록됨 — 물체 {ok_o}  전달 {ok_h}  목적지 {ok_d}\n")
    print("  모든 시행 기록 완료.  분석: python3 cleanup_eval_bi.py report")
    return 0


# ───────────────────────── report ─────────────────────────
def binom_p(k, n, p0):
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
    print(f"\n{'=' * 66}\n양팔 실기 cleanup 평가 — {len(rows)}시행\n{'=' * 66}")

    # ── 조작/전달 (언어와 무관 — 모터 신뢰도) ──
    picked_any = [r for r in rows if r["picked"] != "(없음)"]
    handoff_ok = [r for r in picked_any if r["handoff"] == "성공"]
    placed = [r for r in handoff_ok if r["landed"] != "(없음)"]
    print(f"\n  조작/전달 — 언어 성능과 섞이면 안 되는 항")
    print(f"    무언가 집음(오른팔)   {len(picked_any)}/{len(rows)} = {len(picked_any)/len(rows)*100:.1f}%")
    if picked_any:
        print(f"    전달 성공            {len(handoff_ok)}/{len(picked_any)} = "
              f"{len(handoff_ok)/len(picked_any)*100:.1f}%  (분모: 집은 시행)")
    if handoff_ok:
        print(f"    칸에 넣음(왼팔)       {len(placed)}/{len(handoff_ok)} = "
              f"{len(placed)/len(handoff_ok)*100:.1f}%  (분모: 전달 성공한 시행)")

    # ── 물체 축 ──
    n_obj = [len(r["objects"].split(",")) for r in rows]
    chance_o = sum(1 / n for n in n_obj) / len(rows) * 100
    hit_o = sum(1 for r in rows if r["picked"] == r["target"])
    lo, hi = wilson(hit_o, len(rows))
    print(f"\n  물체 축 — 지시한 물체를 집었는가(오른팔)")
    print(f"    {hit_o}/{len(rows)} = {hit_o/len(rows)*100:.1f}%   "
          f"우연 {chance_o:.1f}% (화면당 물체 수 가변)   95% CI [{lo:.1f}, {hi:.1f}]")
    print(f"    {'✅ 우연 초과' if lo > chance_o else '⚠️  우연과 구별 안 됨'}")

    # ── 목적지 축 — 분모는 '전달까지 성공한 시행 중' ──
    COLS = [c for _, c in SLOTS]
    print(f"\n  목적지 축 — 맞는 칸으로 넣었는가(왼팔)")
    print(f"    ⚠️ 분모는 '전달까지 성공한 시행 중 어딘가에 넣은 횟수'다 — 집기·전달"
          f" 실패를 분모에 넣으면 왼팔 배치 능력이 과소평가된다.")
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
        if sum(land_tot):
            worst = max(land_tot) / sum(land_tot)
            print(f"    착지 쏠림: 가장 많이 간 칸이 전체의 {worst * 100:.0f}%"
                  f" (균등이면 {CHANCE * 100:.0f}%)"
                  + ("  ← 특정 칸으로 도망가는 경향" if worst > 0.45 else ""))

    # ── 배치별 (layout 열이 있는 계획표만) ──
    if any(r.get("layout") for r in rows):
        print(f"\n  배치별 — 학습에 있던 배치 vs 없던 배치")
        print(f"    {'배치':<40}{'물체':>9}{'목적지':>10}")
        lays = []
        for r in rows:
            if r.get("layout") not in lays:
                lays.append(r.get("layout"))
        for lay in lays:
            rs = [r for r in rows if r.get("layout") == lay]
            ho = sum(r["picked"] == r["target"] for r in rs)
            pl = [r for r in rs if r["handoff"] == "성공" and r["landed"] != "(없음)"]
            hd = sum(r["landed"] == r["slot_color"] for r in pl)
            print(f"    {lay or '(기본)':<40}{f'{ho}/{len(rs)}':>9}{f'{hd}/{len(pl)}':>10}")
        # 색이 아니라 자리로 간다면 "위치 기준" 분포가 한쪽에 쏠린다
        pos = Counter()
        for r in placed:
            m = {c: n for n, c in layout_slots(r)}
            if r["landed"] in m:
                pos[m[r["landed"]]] += 1
        if pos:
            tot_p = sum(pos.values())
            print(f"    착지 위치(칸 번호 기준): " + " · ".join(
                f"{n}번 {pos[n]}" for n in sorted(pos)) +
                f"   — 가장 많은 자리 {max(pos.values()) / tot_p * 100:.0f}% (균등 {CHANCE * 100:.0f}%)")

    # ── 대응쌍 ──
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
            ok = spread = 0
            for v in full:
                got = [x["landed"] for x in v if x["landed"] not in ("", "(없음)", "-")]
                if len(got) >= 2:
                    spread += 1
                    if len(set(got)) == len(got):
                        ok += 1
            print(f"    {label} {want}연속 {len(full)}그룹")
            if spread:
                print(f"      2회 이상 넣은 그룹 {spread}개 중 **넣은 칸이 전부 서로 다름"
                      f" {ok}개 ({ok / spread * 100:.0f}%)** ← 지시문을 따랐다는 직접 신호")
            else:
                print(f"      2회 이상 넣은 그룹이 없다 — 조작/전달이 먼저다")
        else:
            diff = sum(1 for v in full if v[0]["picked"] != v[1]["picked"])
            print(f"    {label} 쌍 {len(full)}그룹 — **집은 물체가 서로 다름 {diff}** ← 지시문을 따랐다는 직접 신호")

    print(f"\n  ※ 세 축(물체·전달·목적지)을 따로 적었기에 곱이 풀린다. 한 칸에 뭉쳤다면"
          f"\n     '{len(placed)/len(rows)*100:.0f}% 성공'으로만 보여 어느 단계가 약한지 못 가린다.")
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan"); p.add_argument("--groups", type=int, default=12)
    p.add_argument("--seed", type=int, default=20261015); p.add_argument("--out", default=PLAN)
    p.set_defaults(fn=cmd_plan)
    l = sub.add_parser("log"); l.add_argument("--plan", default=PLAN)
    l.add_argument("--out", default=RESULT); l.add_argument("--redo", action="store_true")
    l.add_argument("--no-run", action="store_true",
                   help="로봇을 띄우지 않고 기록만 한다(다른 터미널에서 돌릴 때)")
    l.add_argument("--no-home", action="store_true",
                   help="시행이 끝나도 rest 로 복귀시키지 않는다(팔이 그 자리에 선다)")
    # 전달 단계가 끼어 단일팔(60s)보다 여유를 둔다 — 실측 전 추정치(§plan 출력과 같은 근거).
    l.add_argument("--max-sec", type=float, default=150,
                   help="시행 1회 제한 시간(초, 실측 전 추정). 지나면 다음 시행으로. 0=무제한")
    l.add_argument("--rerun", action="store_true",
                   help="rerun 실시간 시각화를 켠다(기본 꺼짐). 시행마다 같은 뷰어에 계속 쌓이므로 "
                        "긴 배치에서는 중간에 rerun 창을 닫아 메모리를 비울 것")
    l.add_argument("--eval-name", default="bi_cleanup",
                   help="run_eval_real_bi.sh 의 평가 이름 — 영상 저장 폴더가 된다")
    l.set_defaults(fn=cmd_log)
    r = sub.add_parser("report"); r.add_argument("--out", default=RESULT)
    r.set_defaults(fn=cmd_report)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
