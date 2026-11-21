"""법인세 분석 보고서 생성기.

사용:
    uv run ff-report --prev 전기.pdf --curr 당기.pdf [--out output] [--config config/rules.yaml]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def main(argv=None):
    ap = argparse.ArgumentParser(prog="ff-report", description="세무조정계산서 PDF 2개 → 법인세 분석 보고서")
    ap.add_argument("--prev", required=True, help="전기 세무조정계산서 PDF")
    ap.add_argument("--curr", required=True, help="당기 세무조정계산서 PDF")
    ap.add_argument("--out", default=str(ROOT / "output"), help="출력 폴더")
    ap.add_argument("--config", default=str(ROOT / "config" / "rules.yaml"))
    ap.add_argument("--fonts", default=str(ROOT / "assets" / "fonts"))
    args = ap.parse_args(argv)

    from . import charts, invoice, render_pdf, render_xlsx
    from .analysis import build
    from .extract import load_year

    rules = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    a, b = load_year(args.prev), load_year(args.curr)
    prev, cur = (a, b) if a.year <= b.year else (b, a)  # 본문 사업연도로 전기/당기 판정 (D-002)
    rp = build(prev, cur, rules)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    name = cur.info["법인명"].value.replace("(주)", "").replace("㈜", "")
    stem = f"{name}_{prev.year}-{cur.year}"
    fonts = Path(args.fonts)
    ch = charts.make_all(rp, out / "charts", fonts)
    pdf = out / f"{stem}_법인세분석보고서.pdf"
    render_pdf.render(rp, pdf, fonts, ch, rules["issuer"])
    xlsx = out / f"{stem}_법인세분석보고서.xlsx"
    render_xlsx.render(rp, xlsx, rules["issuer"])
    inv = out / f"{stem}_조정료청구서_초안.md"
    invoice.render(rp, inv, rules, rules["issuer"])
    ev = out / f"{stem}_근거.json"
    ev.write_text(json.dumps({"values": [v.dict() for v in rp.ev.values], "checks": rp.ev.checks,
                              "flags": rp.ev.flags}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    bad = [c for c in rp.ev.checks if c["결과"] != "통과"]
    print(f"보고서: {pdf}\nExcel:  {xlsx}\n청구서: {inv}\n근거:   {ev}")
    print(f"검산 {len(rp.ev.checks)}건 중 불일치 {len(bad)}건")
    for c in bad:
        print(f"  - {c['검산']}: {c['내용']}")
    nc = rp.ev.needs_check
    print(f"«확인 필요» {len(nc)}건" + ("" if not nc else ": " + ", ".join(f"{v.item}({v.year})" for v in nc)))
    return 0
