"""수집 데이터셋의 블록·박스 배치를 **미터 단위로** 복원해 분포를 재고, 학습셋을 선별한다.

배경(2026-08-06):
  v3@40k의 실패 원인이 '블록-박스 근접'으로 밝혀졌는데(근접 39% vs 원거리 83%),
  학습 데이터에 그 구성이 자연 분포의 절반뿐이었다. 어느 에피소드가 근접인지 알아야
  선별을 할 수 있는데, 수집 데이터셋에는 물체 좌표가 저장돼 있지 않다.

방법:
  평가(headless)에서는 `scenes.csv`에 실제 좌표가 남는다. **카메라가 고정**이고 물체가
  평면 위에 있으므로 픽셀↔테이블 평면은 **호모그래피** 하나로 대응된다.
  → 평가 45ep의 (픽셀 중심, 실제 좌표) 쌍으로 호모그래피를 맞추고, 그걸 수집 영상에 적용한다.

  단순 비례 환산(거리 ∝ 픽셀거리)은 원근을 무시해 평균오차 6.8cm였다. 호모그래피는
  원근을 처리하므로 훨씬 정확하다(아래 실행 시 잔차 출력으로 확인).

  블록과 박스는 시각 중심의 높이가 달라(박스는 벽이 있음) **각각 별도 호모그래피**를 맞춘다.

의존성: PIL만 사용(numpy 없이 순수 파이썬 최소제곱). ffmpeg로 첫 프레임 추출.
"""
import glob
import os
import subprocess
import sys
import tempfile
from math import atan2, hypot

from PIL import Image

BASE_XY = (-0.05, 0.0)   # BLOCK_REACH_BASE_XY — 로봇 base
FRAME_IDX = 3            # 리셋 직후 물체가 안정된 프레임
WIDTH = 300              # 축소 폭(원본 비율 유지)


# ── 검출 ────────────────────────────────────────────────────────────────
def _largest_blob(mask, w, h, min_px):
    """마스크의 **최대 연결성분** 중심. 전체 평균을 쓰면 반사광·그림자 같은 작은 덩어리가
    중심을 끌어당겨 검출이 크게 빗나간다(호모그래피 잔차 24cm의 주원인이었다)."""
    seen = bytearray(w * h)
    best = None
    for s in range(w * h):
        if not mask[s] or seen[s]:
            continue
        stack, comp = [s], []
        seen[s] = 1
        while stack:
            i = stack.pop()
            comp.append(i)
            x, y = i % w, i // w
            for nx, ny in ((x-1, y), (x+1, y), (x, y-1), (x, y+1)):
                if 0 <= nx < w and 0 <= ny < h:
                    j = ny * w + nx
                    if mask[j] and not seen[j]:
                        seen[j] = 1
                        stack.append(j)
        if best is None or len(comp) > len(best):
            best = comp
    if best is None or len(best) < min_px:
        return None
    return (sum(i % w for i in best) / len(best), sum(i // w for i in best) / len(best))


def centroids(png):
    """빨간 블록 / 검은 박스의 픽셀 중심(최대 연결성분). 검출 실패 시 None."""
    im = Image.open(png).convert("RGB")
    w, h = im.size
    px = im.load()
    mb = bytearray(w * h)
    mk = bytearray(w * h)
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            # 로봇은 자주색(R,B 동시에 큼)이라 B로 배제
            if r > 110 and r - g > 55 and r - b > 45:
                mb[y * w + x] = 1
            elif r < 55 and g < 55 and b < 55 and max(r, g, b) - min(r, g, b) < 18:
                mk[y * w + x] = 1
    cb = _largest_blob(mb, w, h, 10)
    ck = _largest_blob(mk, w, h, 60)
    if cb is None or ck is None:
        return None
    return cb, ck


def first_frame(mp4, out_png):
    subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-i", mp4,
         "-vf", f"select=eq(n\\,{FRAME_IDX}),scale={WIDTH}:-1",
         "-vsync", "0", "-frames:v", "1", "-y", out_png],
        check=False)
    return os.path.exists(out_png)


# ── 순수 파이썬 최소제곱 (정규방정식 + 가우스 소거) ──────────────────────
def solve(A, b):
    n = len(A[0])
    M = [[sum(A[k][i] * A[k][j] for k in range(len(A))) for j in range(n)]
         + [sum(A[k][i] * b[k] for k in range(len(A)))] for i in range(n)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        if abs(M[p][c]) < 1e-12:
            raise ValueError("특이 행렬 — 대응점이 부족하거나 한 줄에 몰려 있음")
        M[c], M[p] = M[p], M[c]
        for r in range(n):
            if r == c:
                continue
            f = M[r][c] / M[c][c]
            for j in range(c, n + 1):
                M[r][j] -= f * M[c][j]
    return [M[i][n] / M[i][i] for i in range(n)]


# 사영(호모그래피, 8파라미터)은 분모 (h6·u + h7·v + 1)가 0 근처를 지나면 발산한다.
# 실측: 검출 이상치가 섞이자 잔차 최대 1496cm까지 폭발했다. 카메라가 거의 top-down이고
# 대상 영역이 좁아 **아핀(6파라미터)로 충분**하며, 분모가 없어 수치적으로 안전하다.
# 2차항(u², v², uv)을 넣으면 잔여 원근 왜곡까지 흡수한다.
QUADRATIC = True


def _basis(u, v):
    b = [u, v, 1.0]
    if QUADRATIC:
        b += [u * u, v * v, u * v]
    return b


def _fit_once(pairs):
    n = len(_basis(0, 0))
    A, b = [], []
    for u, v, x, y in pairs:
        f = _basis(u, v)
        A.append(f + [0.0] * n); b.append(x)
        A.append([0.0] * n + f); b.append(y)
    return solve(A, b)


def fit_homography(pairs, trim=0.2, iters=6):
    """[(u,v,x,y)] → 계수. x = Σ c_i·basis_i(u,v), y도 동일.

    **강건 추정**: 색 분할 검출은 로봇 팔이 물체를 가리거나 그림자를 잡으면 완전히
    빗나간 중심을 낸다. 최소제곱은 그런 이상치 하나에도 해가 무너지므로(실측: 잔차
    평균 24cm, 최대 176cm) 잔차 상위 `trim`을 버리고 다시 맞추기를 반복한다.
    """
    keep = list(pairs)
    h = _fit_once(keep)
    for _ in range(iters):
        res = [(hypot(*(a - b for a, b in zip(apply_h(h, u, v), (x, y)))), (u, v, x, y))
               for u, v, x, y in pairs]
        res.sort(key=lambda t: t[0])
        n = max(len(_basis(0, 0)) + 2, int(len(res) * (1 - trim)))
        keep = [p for _, p in res[:n]]
        h = _fit_once(keep)
    return h, keep


def apply_h(h, u, v):
    f = _basis(u, v)
    n = len(f)
    return (sum(f[i] * h[i] for i in range(n)),
            sum(f[i] * h[n + i] for i in range(n)))


# ── 데이터셋 스캔 ────────────────────────────────────────────────────────
def scan(video_dir, tmp, tag):
    """에피소드별 (이름, 블록픽셀, 박스픽셀). 파일명 순서 = 에피소드 순서."""
    out = []
    for mp4 in sorted(glob.glob(os.path.join(video_dir, "file-*.mp4"))):
        name = f"{tag}/{os.path.basename(mp4)[:-4]}"
        png = os.path.join(tmp, name.replace("/", "_") + ".png")
        if not first_frame(mp4, png):
            continue
        c = centroids(png)
        if c:
            out.append((name, c[0], c[1]))
    return out


def main():
    """인자: <데이터셋루트> <임시디렉터리> <보정소스1> [<보정소스2> ...]
    보정소스 = `scenes.csv가_있는_폴더` (그 안의 epNN_*.mp4와 scenes.csv를 짝짓는다)

    보정 대응점은 **많을수록 안정적**이다. 40쌍(=헤드리스 1배치)에서는 홀드아웃 오차가
    분할에 따라 5cm~37cm로 요동쳤다. 시드가 다른 배치를 모두 넣을 것.
    """
    datasets_root, tmp = sys.argv[1:3]
    sources = sys.argv[3:]
    import csv

    # 1) 평가 프레임에서 대응점 수집 (여러 배치 합산)
    pb, pk = [], []
    for si, src in enumerate(sources):
        truth = {int(r["ep"]): r for r in csv.DictReader(open(os.path.join(src, "scenes.csv")))}
        got = 0
        for mp4 in sorted(glob.glob(os.path.join(src, "ep*.mp4"))):
            ep = int(os.path.basename(mp4)[2:4])
            png = os.path.join(tmp, f"cal{si}_{ep:02d}.png")
            if not first_frame(mp4, png):
                continue
            c = centroids(png)
            if not c or ep not in truth:
                continue
            (bu, bv), (ku, kv) = c
            t = truth[ep]
            pb.append((bu, bv, float(t["block_x"]), float(t["block_y"])))
            pk.append((ku, kv, float(t["box_x"]), float(t["box_y"])))
            got += 1
        print(f"[보정] {os.path.basename(src)}: {got}쌍")
    print(f"[보정] 합계 {len(pb)}쌍")
    (Hb, kb), (Hk, kk) = fit_homography(pb), fit_homography(pk)
    for nm, H, P, K in (("블록", Hb, pb, kb), ("박스", Hk, pk, kk)):
        e = sorted(hypot(*(a - b for a, b in zip(apply_h(H, u, v), (x, y))))
                   for u, v, x, y in K)
        print(f"  {nm}: 채택 {len(K)}/{len(P)}쌍 · 잔차 평균 {sum(e)/len(e)*100:.2f}cm "
              f"중앙값 {e[len(e)//2]*100:.2f}cm 최대 {e[-1]*100:.2f}cm")
    # 홀드아웃 검증. ⚠ keep은 **잔차 오름차순**이므로 앞/뒤로 가르면 "잘 맞는 것으로 학습해
    # 안 맞는 것을 예측"하는 편향된 검증이 된다(실측 85cm). 짝/홀로 교차 분할할 것.
    for name, idx in (("짝→홀", 0), ("홀→짝", 1)):
        tr = [p for i, p in enumerate(kb) if i % 2 == idx]
        te = [p for i, p in enumerate(kb) if i % 2 != idx]
        Hh, _ = fit_homography(tr, trim=0.1)
        ho = [hypot(*(a - b for a, b in zip(apply_h(Hh, u, v), (x, y)))) for u, v, x, y in te]
        ho.sort()
        print(f"  블록 홀드아웃 {name}({len(ho)}쌍): 평균 {sum(ho)/len(ho)*100:.2f}cm "
              f"중앙값 {ho[len(ho)//2]*100:.2f}cm")

    # 2) 수집 데이터셋에 적용
    groups = {"v3": ["sim_so101_blocktask_v3", "sim_so101_blocktask_v3_2"],
              "잔여": ["sim_so101_blocktask_v3_3", "sim_so101_blocktask_v3_4"]}
    result = {}
    for g, dss in groups.items():
        rows = []
        for ds in dss:
            vd = os.path.join(datasets_root, ds, "videos/observation.images.external_D455/chunk-000")
            if not os.path.isdir(vd):
                print(f"  ⚠ 없음: {ds}")
                continue
            for name, (bu, bv), (ku, kv) in scan(vd, tmp, ds.replace("sim_so101_blocktask_", "")):
                bxy, kxy = apply_h(Hb, bu, bv), apply_h(Hk, ku, kv)
                rows.append({
                    "ep": name,
                    "d": hypot(bxy[0] - kxy[0], bxy[1] - kxy[1]),
                    "r": hypot(bxy[0] - BASE_XY[0], bxy[1] - BASE_XY[1]),
                    "th": atan2(bxy[1] - BASE_XY[1], bxy[0] - BASE_XY[0]),
                })
        result[g] = rows
        print(f"\n[{g}] {len(rows)}ep")
        for a, b in ((0, .08), (.08, .12), (.12, .18), (.18, .25), (.25, 9)):
            n = sum(1 for x in rows if a <= x["d"] < b)
            print(f"   {a:.2f}~{b if b < 9 else 9:.2f}m  {n:>3} ({n/len(rows)*100:>4.1f}%)")
        near = sum(1 for x in rows if x["d"] < 0.18)
        print(f"   근접(<0.18) {near}/{len(rows)} = {near/len(rows)*100:.1f}%")
    return result, tmp


if __name__ == "__main__":
    res, tmp = main()
    # 3) 잔여에서 근접 우선 35개 선별
    N_SEL = int(os.environ.get("N_SEL", "35"))
    sel = sorted(res["잔여"], key=lambda x: x["d"])[:N_SEL]
    print(f"\n[선별] 잔여에서 근접 우선 {N_SEL}개 — 거리 {sel[0]['d']:.3f} ~ {sel[-1]['d']:.3f}m")
    neg = sum(1 for x in sel if x["th"] < 0)
    print(f"   θ<0(오른쪽) {neg}/{N_SEL} = {neg/N_SEL*100:.0f}%")
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "selected_35_near.txt")
    with open(out, "w") as f:
        f.write("# 잔여 131ep 중 블록-박스 근접 우선 선별 (호모그래피 복원 좌표 기준)\n")
        f.write("# ep_name  dist_m  block_r  block_theta\n")
        for x in sel:
            f.write(f"{x['ep']}  {x['d']:.4f}  {x['r']:.4f}  {x['th']:+.4f}\n")
    print(f"   → {out}")
