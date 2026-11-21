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
    ap.add_argument("--answers", default=str(ROOT / "config" / "answers.yaml"), help="고객 확인값 (없으면 생략)")
    args = ap.parse_args(argv)

    from . import charts, invoice, render_pdf, render_xlsx
    from .analysis import build
    from .extract import load_year

    rules = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    a, b = load_year(args.prev), load_year(args.curr)
    prev, cur = (a, b) if a.year <= b.year else (b, a)  # 본문 사업연도로 전기/당기 판정 (D-002)
    ans_path = Path(args.answers)
    answers = yaml.safe_load(ans_path.read_text(encoding="utf-8")) if ans_path.exists() else None
    rp = build(prev, cur, rules, answers)

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
                              "flags": rp.ev.flags, "warnings": rp.ev.warnings}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    bad = [c for c in rp.ev.checks if c["결과"] == "불일치"]
    hold = [c for c in rp.ev.checks if c["결과"] == "보류"]
    print(f"보고서: {pdf}\nExcel:  {xlsx}\n청구서: {inv}\n근거:   {ev}")
    print(f"검산 {len(rp.ev.checks)}건 중 불일치 {len(bad)}건, 보류 {len(hold)}건")
    for c in bad:
        print(f"  - 불일치 {c['검산']}: {c['내용']}")
    for c in hold:
        print(f"  - 보류 {c['검산']}")
    print(f"경고 {len(rp.ev.warnings)}건")
    for w in rp.ev.warnings:
        print(f"  - [{w['구분']}] {w['파일']} {w['연도']} {w['서식']} p{w['페이지']} {w['항목']} = {w['표시값']} :: {w['내용']}")
    nc = [v for v in rp.ev.values if v.status != "확정"]
    print(f"«확인 필요» {len(nc)}건" + ("" if not nc else ": " + ", ".join(f"{v.item}({v.year})" for v in nc)))
    return 0
