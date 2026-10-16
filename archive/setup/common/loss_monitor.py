"""lerobot-train loss 실시간 모니터 (모델 공용) — 로그 파싱 → PNG 갱신 (15초 주기).

실행:  cd ~/manipulator_ws/envs/lerobot && uv run python ../../setup/common/loss_monitor.py [로그경로] [총_step수]
보기:  eog ~/manipulator_ws/logs/loss_curve_<로그이름>.png   (파일 갱신 시 자동 리로드)
종료:  Ctrl+C

⚠️ 총_step수는 학습 스크립트의 --steps 값과 반드시 일치시킬 것 (ETA 계산 기준값).
   생략 시 100000(ACT 기본값) 가정 — 다른 step 수로 학습 중이면 반드시 명시.
"""
import re
import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

LOG = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "manipulator_ws/logs/act_t1.log"
OUT = Path.home() / f"manipulator_ws/logs/loss_curve_{LOG.stem}.png"
TOTAL_STEPS = int(sys.argv[2]) if len(sys.argv) > 2 else 100_000
LABEL = LOG.stem  # 예: smolvla_t1.log -> "smolvla_t1"

PAT = re.compile(
    r"step:(\d+(?:\.\d+)?)(K|M)?\s.*?loss:([\d.]+).*?updt_s:([\d.]+)\s+data_s:([\d.]+)"
)


LOG_FREQ = 200  # train_act_t1.sh --log_freq


def parse(text):
    # 로그의 step 표기는 "1K"처럼 반올림되므로, log_freq 간격으로 step을 복원한다.
    steps, losses, sec_per_step = [], [], 0.11
    for i, m in enumerate(PAT.finditer(text)):
        steps.append(LOG_FREQ * (i + 1))
        losses.append(float(m.group(3)))
        sec_per_step = float(m.group(4)) + float(m.group(5))
    return steps, losses, sec_per_step


def render(steps, losses, sec_per_step):
    remain = max(TOTAL_STEPS - steps[-1], 0)
    eta_h = remain * sec_per_step / 3600
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=110)
    fig.patch.set_facecolor("#FFFFFF")
    ax.set_facecolor("#FFFFFF")
    ax.plot(steps, losses, color="#2A5DB0", linewidth=2, solid_capstyle="round")
    # 최신값 직접 라벨 (마지막 점만)
    ax.plot(steps[-1], losses[-1], "o", color="#2A5DB0", markersize=6)
    ax.annotate(
        f"{losses[-1]:.3f}",
        (steps[-1], losses[-1]),
        textcoords="offset points",
        xytext=(8, 4),
        fontsize=10,
        color="#333333",
    )
    ax.set_yscale("log")
    ax.set_xlabel("step", color="#666666")
    ax.set_ylabel("total loss (log scale)", color="#666666")
    ax.set_title(
        f"{LABEL} training  ·  step {steps[-1]:,}/{TOTAL_STEPS:,}"
        f"  ·  ETA ≈ {eta_h:.1f}h",
        color="#333333", fontsize=11, loc="left",
    )
    ax.grid(True, color="#EEEEEE", linewidth=0.8)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#CCCCCC")
    ax.tick_params(colors="#888888", labelsize=9)
    fig.tight_layout()
    fig.savefig(OUT)
    plt.close(fig)


print(f"모니터 시작 — {LOG}\n그래프: {OUT}  (eog로 열면 자동 갱신)")
try:
    while True:
        steps, losses, sps = parse(LOG.read_text(errors="ignore"))
        if steps:
            render(steps, losses, sps)
            remain_h = (TOTAL_STEPS - steps[-1]) * sps / 3600
            print(f"step {steps[-1]:>7,}  loss {losses[-1]:.3f}  잔여 ≈ {remain_h:.1f}h")
        else:
            print("아직 loss 로그 없음...")
        time.sleep(15)
except KeyboardInterrupt:
    print("종료")
