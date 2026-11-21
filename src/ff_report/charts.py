"""그래프 4종 (요구사항 #2, D-025). 인쇄용 PDF에 넣는 정적 PNG.

색: 기준 팔레트 슬롯 1(파랑)=전기, 슬롯 2(주황)=당기. validate_palette.js로 검증함 (모두 통과).
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

PREV_C, CUR_C = "#2a78d6", "#eb6834"
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#ffffff"


def setup_font(font_dir: Path):
    for f in font_dir.glob("*.ttf"):
        font_manager.fontManager.addfont(str(f))
    plt.rcParams.update({
        "font.family": "NanumGothic", "axes.unicode_minus": False, "font.size": 9,
        "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
        "axes.spines.top": False, "axes.spines.right": False, "figure.facecolor": SURF, "axes.facecolor": SURF,
    })


def _mil(v):
    return v / 1_000_000


def _finish(fig, ax, path, title, unit):
    ax.set_title(title, loc="left", fontsize=11, color=INK, pad=22, fontweight="bold")
    if unit:
        ax.text(1.0, 1.02, unit, transform=ax.transAxes, ha="right", va="bottom", fontsize=8, color=INK2)
    ax.grid(axis="x" if ax.get_ylabel() == "h" else "y", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


def grouped(path, title, labels, prev, cur, py, cy, unit="(단위: 백만원)"):
    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    x = range(len(labels))
    w = 0.36
    b1 = ax.bar([i - w / 2 - 0.01 for i in x], [_mil(v) for v in prev], w, color=PREV_C, label=f"{py}년")
    b2 = ax.bar([i + w / 2 + 0.01 for i in x], [_mil(v) for v in cur], w, color=CUR_C, label=f"{cy}년")
    ax.set_xticks(list(x), labels)
    ax.axhline(0, color=INK2, linewidth=0.8)
    for bars in (b1, b2):
        for b in bars:
            h = b.get_height()
            ax.annotate(f"{h:,.1f}", (b.get_x() + b.get_width() / 2, h), ha="center",
                        va="bottom" if h >= 0 else "top", fontsize=7.5, color=INK, xytext=(0, 2 if h >= 0 else -2),
                        textcoords="offset points")
    ax.legend(frameon=False, loc="lower left", bbox_to_anchor=(0, 1.0), ncols=2, fontsize=8)
    ax.margins(y=0.15)
    _finish(fig, ax, path, title, unit)


def hbar_pair(path, title, labels, prev, cur, py, cy, unit="(단위: 백만원)"):
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    n = len(labels)
    y = list(range(n))[::-1]
    h = 0.36
    ax.barh([i + h / 2 + 0.01 for i in y], [_mil(v) for v in prev], h, color=PREV_C, label=f"{py}년")
    ax.barh([i - h / 2 - 0.01 for i in y], [_mil(v) for v in cur], h, color=CUR_C, label=f"{cy}년")
    for i, (a, b) in zip(y, zip(prev, cur)):
        ax.text(_mil(a), i + h / 2, f" {_mil(a):,.1f}", va="center", fontsize=7.5, color=INK)
        ax.text(_mil(b), i - h / 2, f" {_mil(b):,.1f}", va="center", fontsize=7.5, color=INK)
    ax.set_yticks(y, labels)
    ax.legend(frameon=False, loc="lower right", fontsize=8)
    ax.margins(x=0.15)
    ax.set_ylabel("h")
    ax.yaxis.label.set_visible(False)
    _finish(fig, ax, path, title, unit)


def composition(path, title, labels, shares):
    """판관비 구성비(%) — 한 계열이라 범례 없이 막대 끝에 % 표기."""
    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    y = list(range(len(labels)))[::-1]
    ax.barh(y, shares, 0.55, color=CUR_C)
    for i, s in zip(y, shares):
        ax.text(s, i, f" {s:.1f}%", va="center", fontsize=8, color=INK)
    ax.set_yticks(y, labels)
    ax.set_xlim(0, max(shares) * 1.2)
    ax.set_ylabel("h")
    ax.yaxis.label.set_visible(False)
    _finish(fig, ax, path, title, "(판관비 합계 대비 %)")


def make_all(rp, out_dir: Path, font_dir: Path) -> dict[str, Path]:
    from .analysis import g

    setup_font(font_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    py, cy = rp.prev.year, rp.cur.year
    p, c = rp.prev.pl, rp.cur.pl
    files = {}
    files["pl"] = out_dir / "chart1_주요손익.png"
    grouped(files["pl"], "1. 주요 손익 전기·당기 비교", ["매출액", "매출총이익", "영업손익", "당기순손익"],
            [g(p, 1), g(p, 66), g(p, 129), g(p, 219)], [g(c, 1), g(c, 66), g(c, 129), g(c, 219)], py, cy)
    II = rp.sections["II"]
    top = II["sga_top"]
    rest = sum(s["comp_cur"] for s in II["sga_all"][len(top):])
    files["comp"] = out_dir / "chart2_판관비구성비.png"
    composition(files["comp"], f"2. 판관비 구성비 ({cy}년)", [s["name"] for s in top] + ["기타"],
                [s["comp_cur"] for s in top] + [rest])
    files["sga"] = out_dir / "chart3_판관비주요5.png"
    hbar_pair(files["sga"], f"3. 판관비 주요 {len(top)}개 항목 전기·당기 비교", [s["name"] for s in top],
              [s["prev"] for s in top], [s["cur"] for s in top], py, cy)
    b0, b1 = rp.prev.bs, rp.cur.bs
    files["bs"] = out_dir / "chart4_재무상태.png"
    grouped(files["bs"], "4. 재무상태 비교", ["자산총계", "부채총계", "자본총계"],
            [g(b0, 228), g(b0, 333), g(b0, 382)], [g(b1, 228), g(b1, 333), g(b1, 382)], py, cy)
    return files
