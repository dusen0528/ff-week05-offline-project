"""보고서 Excel (수기 수정용, 채점 대상 아님, D-014). 증감·비율은 수식으로 넣어 고치면 다시 계산된다."""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .analysis import g

HEAD = PatternFill("solid", fgColor="F2F1EE")
BOLD = Font(bold=True)


def _sheet(wb, title, header, rows, widths):
    ws = wb.create_sheet(title)
    ws.append(header)
    for c in ws[1]:
        c.fill, c.font = HEAD, BOLD
    for r in rows:
        ws.append(r)
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    for row in ws.iter_rows(min_row=2):
        for c in row:
            if isinstance(c.value, (int, float)) or (isinstance(c.value, str) and c.value.startswith("=")):
                c.number_format = "#,##0;-#,##0"
                c.alignment = Alignment(horizontal="right")
    return ws


def _cmp_rows(items, start_row=2):
    rows = []
    for i, (name, a, b) in enumerate(items):
        r = start_row + i
        rows.append([name, a, b, f"=C{r}-B{r}", f'=IF(B{r}>0,(C{r}-B{r})/B{r},IF(AND(B{r}<0,C{r}>0),"흑자전환","-"))'])
    return rows


def render(rp, out: Path, issuer: str):
    wb = Workbook()
    wb.remove(wb.active)
    prev, cur = rp.prev, rp.cur
    py, cy = prev.year, cur.year
    S = rp.sections
    info = wb.create_sheet("I.기본정보")
    info.append(["항목", "값"])
    for k, v in S["I"].items():
        info.append([k, v.value])
    info.append(["발행", issuer])
    info.column_dimensions["A"].width, info.column_dimensions["B"].width = 18, 48
    hdr = ["구분", f"{py}년", f"{cy}년", "증감액", "증감률"]
    ws = _sheet(wb, "II-1.재무상태표", hdr, _cmp_rows([(r["name"], r["prev"], r["cur"]) for r in S["II"]["bs"]]), [28, 16, 16, 16, 12])
    ws = _sheet(wb, "II-2.손익계산서", hdr, _cmp_rows([(r["name"], r["prev"], r["cur"]) for r in S["II"]["pl"]]), [28, 16, 16, 16, 12])
    ws = _sheet(wb, "II-4.요약손익", hdr, _cmp_rows([(r["item"], r["prev"], r["cur"]) for r in S["II"]["summary"]]), [22, 16, 16, 16, 12])
    rows = []
    for i, s in enumerate(S["II"]["sga_top"], start=2):
        rows.append([s["name"], s["prev"], s["cur"], f"=C{i}-B{i}", f"=IF(B{i}>0,(C{i}-B{i})/B{i},\"-\")",
                     f"=B{i}/{g(prev.pl,1)}", f"=C{i}/{g(cur.pl,1)}"])
    ws = _sheet(wb, "II-5.판관비주요", hdr + [f"매출대비 {py}", f"매출대비 {cy}"], rows, [18, 16, 16, 16, 12, 12, 12])
    for sh in wb.worksheets:
        for row in sh.iter_rows(min_row=2):
            for c in row[4:]:
                if isinstance(c.value, str) and c.value.startswith("="):
                    c.number_format = "0.00%"
    _sheet(wb, "III.신고상황", ["구분", f"{py}", f"{cy}"],
           [[r["item"], r["prev"], r["cur"]] for r in S["III"]], [30, 18, 18])
    _sheet(wb, "IV.이월결손금", ["발생 사업연도", "발생액", "감소액", "잔액"],
           [[r["year"], r["occur"], r["decrease"], f"=B{i}-C{i}"] for i, r in enumerate(S["IV"]["rows"], start=2)]
           + [[n] for n in S["IV"]["notes"]], [16, 16, 16, 16])
    _sheet(wb, "V.소득금액조정", ["구분", "과목", "금액", "소득처분"],
           [["익금산입", v.item, v.value, v.note] for v in S["V"]["plus"]]
           + [["손금산입", v.item, v.value, v.note] for v in S["V"]["minus"]], [12, 24, 16, 14])
    _sheet(wb, "VI.공제감면", ["구분", "근거", "세액"], [[v.item, v.note, v.value] for v in S["VI"]["rows"]], [34, 34, 16])
    c = wb.create_sheet("VII.요약코멘트")
    for x in S["VII"]:
        c.append([x["title"]])
        c.append([x["text"]])
    c.column_dimensions["A"].width = 120
    e = wb.create_sheet("VIII.특이사항")
    for x in S["VIII"]:
        e.append([x["title"]])
        for l in x["lines"]:
            e.append(["· " + l])
    e.column_dimensions["A"].width = 120
    _sheet(wb, "근거", ["항목", "연도", "값", "출처", "원문 라벨", "상태", "비고"],
           [[v.item, v.year, v.value, v.src(), v.label, v.status, v.note] for v in rp.ev.values], [24, 8, 16, 60, 30, 10, 20])
    _sheet(wb, "검산", ["검산", "결과", "내용"], [[x["검산"], x["결과"], x["내용"]] for x in rp.ev.checks], [36, 10, 70])
    wb.save(out)
