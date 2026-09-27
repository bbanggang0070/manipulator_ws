"""P5 무인 평가용 계획표를 만든다 — **배치를 고정하고 문장만 바꾸기 위해서**.

설계 (language_conditioning_sim_plan.md §7-2):
  평가의 핵심은 **대응쌍**이다. 조건 1↔2↔3↔4는 같은 화면에서 문장만 다르고,
  5↔6은 같은 배치에서 목적지만 다르다. 그래야 차이의 출처가 오직 언어로 특정된다.
  배치가 조건마다 새로 뽑히면 "위치 난이도"가 섞여 해석이 불가능해진다 —
  평가 B에서 실측된 적이 있다(같은 모델인데 시드만 바꿔 70% ↔ 30%).

배치를 어떻게 고정하나:
  고정 패널(reset_fixed_panel)은 언어 씬에서 꺼져 있다(configure_scene.py ⑦).
  대신 **같은 계획표 + 같은 seed**를 쓴다 — 물체·박스 조합이 같으면 거부 표집의
  난수 소비 순서가 같아 배치가 그대로 재현된다.
  따라서 한 패널군(= 같은 물체·박스 조합)에 CSV 하나를 만들고, 그 CSV를 공유하는
  조건들은 같은 seed로 돌린다.

CSV의 target/dest는 기록용이다. **실제 성공 판정은 EVAL_TARGET/EVAL_DEST 환경변수**가
정한다(configure_scene.py ④). 러너가 조건별로 그것을 바꾼다.

사용:
  python gen_lang_eval_plan.py --out-dir ~/manipulator_ws/manipulator_md/sim --episodes 30
"""
import argparse
import csv
import os

# 패널군 — 같은 물체·박스 조합을 공유하는 조건들의 묶음
#   P1: 조건 1·2·3·4·8·10 — 색 2종(red/blue) + 이름 2종(eraser/marker), 박스는 흑 하나
#       큐브 2개를 둔 것은 조건 10(모호 지시 "the cube")이 성립하게 하기 위함이다.
#   P2: 조건 5·6 — 목적지 축. 같은 물체, 박스 2색(흑·갈)
#   P3: 조건 7 — 합성(물체 + 목적지 동시)
PANELS = {
    "P1": {"objects": ["red_cube", "blue_cube", "eraser", "marker"],
           "boxes": ["black"],
           "note": "조건 1·2·3·4·8·10 공유 — 색 2 + 이름 2, 박스 1"},
    "P2": {"objects": ["yellow_cube", "purple_cube", "eraser", "marker"],
           "boxes": ["black", "brown"],
           "note": "조건 5·6 공유 — 목적지 축"},
    "P3": {"objects": ["green_cube", "cyan_cube", "eraser", "marker"],
           "boxes": ["black", "gray"],
           "note": "조건 7 — 물체 + 목적지 동시"},
}

# 조건 정의 — (번호, 패널, 지시문, EVAL_TARGET, EVAL_DEST, 무엇을 보나)
#   조건 9(레거시)는 언어 씬이 아니라 **기존 패널**에서 돈다. 러너가 따로 처리한다.
CONDITIONS = [
    (1,  "P1", "Pick up the red block and place it in the box",          "red_cube",    "black", "색 A"),
    (2,  "P1", "Pick up the blue block and place it in the box",         "blue_cube",   "black", "색 B ← 1과 대응쌍"),
    (3,  "P1", "Pick up the eraser and place it in the box",             "eraser",      "black", "이름 A"),
    (4,  "P1", "Pick up the marker and place it in the box",             "marker",      "black", "이름 B ← 3과 대응쌍"),
    (5,  "P2", "Pick up the yellow block and place it in the black box", "yellow_cube", "black", "목적지 A"),
    (6,  "P2", "Pick up the yellow block and place it in the brown box", "yellow_cube", "brown", "목적지 B ← 5와 대응쌍"),
    (7,  "P3", "Put the green block into the gray box",                  "green_cube",  "gray",  "합성 — 두 축 동시"),
    (8,  "P1", "Grab the blue cube and put it in the container",         "blue_cube",   "black", "동의어 — 형식 견고성"),
    (10, "P1", "Pick up the cube and place it in the box",               "red_cube",    "black", "모호(큐브 2개) — 우연 수준 대조"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=os.path.expanduser("~/manipulator_ws/manipulator_md/sim"))
    ap.add_argument("--episodes", type=int, default=30, help="조건당 에피소드 수")
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)

    for name, p in PANELS.items():
        path = os.path.join(a.out_dir, f"lang_eval_{name}.csv")
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["ep", "objects", "boxes", "target", "dest", "instruction"])
            for i in range(a.episodes):
                # 모든 행이 같다 — 배치는 seed가 정하고, 문장·판정은 러너가 환경변수로 덮는다
                w.writerow([i + 1, ",".join(p["objects"]), ",".join(p["boxes"]),
                            p["objects"][0], p["boxes"][0], ""])
        print(f"  {os.path.basename(path)}  {a.episodes}행  "
              f"물체[{', '.join(p['objects'])}]  박스[{', '.join(p['boxes'])}]")
        print(f"      {p['note']}")

    print(f"\n  조건 {len(CONDITIONS) + 1}개 (레거시 조건 9 포함)")
    print(f"  {'#':>3} {'패널':>4}  {'판정':<22} 지시문")
    for n, pan, lang, tgt, dst, why in CONDITIONS:
        print(f"  {n:>3} {pan:>4}  {tgt + ' → ' + dst:<22} \"{lang}\"")
    print(f"  {9:>3} {'—':>4}  {'red_cube → black':<22} "
          f"\"Pick up the block and place it in the box\"  (기존 패널, 성능 보존 확인)")
    print("\n  같은 패널을 쓰는 조건들은 **같은 seed**로 돌려야 배치가 일치한다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
