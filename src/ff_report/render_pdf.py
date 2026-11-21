"""보고서 PDF (채점 대상). 섹션 순서는 D-019."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

from .analysis import RATIO_META, change, g
from .fmt import card_amount, change_text, pct, signed, won

INK = colors.HexColor("#0b0b0b")
INK2 = colors.HexColor("#52514e")
LINE = colors.HexColor("#d9d8d4")
HEAD_BG = colors.HexColor("#f2f1ee")
ACCENT = colors.HexColor("#2a78d6")


def _fonts(font_dir: Path):
    pdfmetrics.registerFont(TTFont("NG", str(font_dir / "NanumGothic-Regular.ttf")))
    pdfmetrics.registerFont(TTFont("NGB", str(font_dir / "NanumGothic-Bold.ttf")))
    pdfmetrics.registerFontFamily("NG", normal="NG", bold="NGB")


ST = {}


def _styles():
    ST["title"] = ParagraphStyle("t", fontName="NGB", fontSize=20, leading=26, textColor=INK)
    ST["sub"] = ParagraphStyle("s", fontName="NG", fontSize=10, leading=15, textColor=INK2)
    ST["h1"] = ParagraphStyle("h1", fontName="NGB", fontSize=13, leading=18, textColor=INK, spaceBefore=10, spaceAfter=6, keepWithNext=1)
    ST["h2"] = ParagraphStyle("h2", fontName="NGB", fontSize=10.5, leading=15, textColor=INK, spaceBefore=8, spaceAfter=4, keepWithNext=1)
    ST["body"] = ParagraphStyle("b", fontName="NG", fontSize=9.5, leading=15, textColor=INK)
    ST["note"] = ParagraphStyle("n", fontName="NG", fontSize=7.8, leading=11, textColor=INK2)
    ST["cell"] = ParagraphStyle("c", fontName="NG", fontSize=8.3, leading=11, textColor=INK)
    ST["cellr"] = ParagraphStyle("cr", parent=ST["cell"], alignment=TA_RIGHT)
    ST["cellb"] = ParagraphStyle("cb", parent=ST["cell"], fontName="NGB")
    ST["flag"] = ParagraphStyle("f", fontName="NG", fontSize=8.5, leading=12.5, textColor=colors.HexColor("#8a3b12"),
                                backColor=colors.HexColor("#fdf1ea"), borderPadding=5, spaceBefore=4, spaceAfter=6)


# 나눔고딕에 없는 글리프를 바꾼다 (로마 숫자, 원 숫자, 수학 기호)
_GLYPH = {**{c: r for c, r in zip("ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ", ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"])},
          **{chr(0x2460 + i): f"({i + 1})" for i in range(20)}, "−": "-", "±": "+/-", "≥": ">=", "≤": "<="}


def clean(t) -> str:
    t = str(t)
    for a, b in _GLYPH.items():
        t = t.replace(a, b)
    return t


def P(t, s="cell"):
    return Paragraph(clean(t), ST[s])


def table(header, rows, widths, num_cols=(), bold_rows=()):
    data = [[P(h, "cellb") for h in header]]
    for r in rows:
        data.append([P(v, "cellr" if i in num_cols else "cell") for i, v in enumerate(r)])
    t = Table(data, colWidths=widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), HEAD_BG),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, INK2),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    for r in bold_rows:
        style.append(("BACKGROUND", (0, r + 1), (-1, r + 1), colors.HexColor("#f8f7f5")))
    for ri, r in enumerate(rows, start=1):  # 확인 필요 칸 강조
        for ci, v in enumerate(r):
            if "확인 필요" in str(v):
                style.append(("BACKGROUND", (ci, ri), (ci, ri), colors.HexColor("#fdf1ea")))
    t.setStyle(TableStyle(style))
    return t


def src_note(*vals) -> Paragraph:
    seen = []
    for v in vals:
        if v is None:
            continue
        s = v if isinstance(v, str) else v.src()
        if s not in seen:
            seen.append(s)
    return P("출처: " + " / ".join(seen), "note")


def render(rp, out: Path, font_dir: Path, charts: dict[str, Path], issuer: str):
    _fonts(font_dir)
    _styles()
    prev, cur = rp.prev, rp.cur
    py, cy = prev.year, cur.year
    S = rp.sections
    name = cur.info["법인명"].value
    W = A4[0] - 36 * mm

    def on_page(canvas, doc):
        canvas.saveState()
        canvas.setFont("NG", 7.5)
        canvas.setFillColor(INK2)
        canvas.drawString(18 * mm, 10 * mm, f"{name} 법인세 분석 보고서 ({py}·{cy} 사업연도)  |  발행: {issuer}")
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"{doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(str(out), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                            bottomMargin=18 * mm, title=f"{name} 법인세 분석 보고서", author=issuer)
    E = []
    # ---- 표지 머리
    E.append(P(f"{name}", "sub"))
    E.append(P("법인세 분석 보고서", "title"))
    E.append(Spacer(1, 4))
    E.append(P(f"비교 사업연도: {py}년({prev.info['기수'].value}, 전기) · {cy}년({cur.info['기수'].value}, 당기)"
               f" &nbsp;|&nbsp; 사업자등록번호 {cur.info['사업자등록번호'].value}", "sub"))
    E.append(P(f"본 보고서는 <b>{issuer}</b>에서 발행하였습니다. &nbsp;발행일 {date.today():%Y.%m.%d}", "sub"))
    E.append(Spacer(1, 10))

    # ---- 요약 카드
    E.append(P("주요 지표 요약", "h1"))
    cells = []
    for r in S["card"]:
        if r["kind"] == "amount":
            v_prev, v_cur = card_amount(r["prev"]), card_amount(r["cur"])
            ch = r["label"] or (pct(r["rate"], sign=True) if r["rate"] is not None else "-")
            diff = card_amount(r["diff"])
            delta = f"증감액 {('+' if r['diff'] > 0 else '')}{diff} · {ch}"
        else:
            dp, dc = r["prev"], r["cur"]
            v_prev = "자본잠식" if dp["impaired"] else pct(dp["value"])
            v_cur = "자본잠식" if dc["impaired"] else pct(dc["value"])
            delta = r["label"] or (f"증감 {r['diff']:+.2f}%p" if r["diff"] is not None else "-")
        cells.append([P(r["item"], "cellb"), P(f"{py}년 {v_prev}", "cell"), P(f"<b>{cy}년 {v_cur}</b>", "cell"),
                      P(delta, "note")])
    card = Table([[c[0] for c in cells], [c[1] for c in cells], [c[2] for c in cells], [c[3] for c in cells]],
                 colWidths=[W / 4] * 4)
    card.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, LINE), ("INNERGRID", (0, 0), (-1, -1), 0, colors.white),
                              ("LINEAFTER", (0, 0), (-2, -1), 0.6, LINE), ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fafaf8")),
                              ("TOPPADDING", (0, 0), (-1, -1), 4), ("LEFTPADDING", (0, 0), (-1, -1), 8)]))
    E.append(card)
    E.append(P("요약 카드 금액은 0.01억원 단위 반올림, 1억원 이상은 억원·미만은 만원으로 표기합니다. "
               "부채비율 = 부채총계 ÷ 자본총계 × 100 (자본총계가 0 이하이면 «자본잠식»).", "note"))
    E.append(src_note(prev.pl.get(1), cur.pl.get(1), prev.bs.get(333), cur.bs.get(333)))

    # ---- I. 기본정보
    E.append(P("I. 기본정보", "h1"))
    I = S["I"]
    rows = [
        ["법인명", I["법인명"].value, "사업자등록번호", I["사업자등록번호"].value],
        ["대표자명", I["대표자명"].value, "법인등록번호", I["법인등록번호"].value],
        ["사업장 소재지", I["사업장 소재지"].value, "주업종코드", I["주업종코드"].value],
        ["업태", I["업태"].value, "종목", I["종목"].value],
        ["법인유형", I["법인유형"].value, "중소기업여부", I["중소기업여부"].value],
        ["사업연도", f"{cy}년 ({I['기수'].value})", "시작일자 ~ 종료일자", f"{I['시작일자'].value} ~ {I['종료일자'].value}"],
        ["신고일", I["신고일"].value, "비교 연도(전기)", f"{prev.info['시작일자'].value} ~ {prev.info['종료일자'].value}"],
    ]
    t = Table([[P(a, "cellb"), P(b), P(c, "cellb"), P(d)] for a, b, c, d in rows],
              colWidths=[W * 0.16, W * 0.34, W * 0.18, W * 0.32])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, LINE), ("BACKGROUND", (0, 0), (0, -1), HEAD_BG),
                           ("BACKGROUND", (2, 0), (2, -1), HEAD_BG)]))
    E.append(t)
    E.append(src_note(I["법인명"], I["중소기업여부"]))

    # ---- II. 표준재무제표
    E.append(PageBreak())
    II = S["II"]
    E.append(P("II. 표준재무제표", "h1"))
    hdr = ["구분", "코드", f"{py}년", f"{cy}년", "증감액", "증감률"]
    wid = [W * 0.30, W * 0.08, W * 0.17, W * 0.17, W * 0.16, W * 0.12]

    def fs_rows(rows):
        out = []
        for r in rows:
            ch = change(r["prev"], r["cur"])
            out.append([r["name"], r["code"], won(r["prev"]), won(r["cur"]), signed(ch["diff"]), change_text(ch)])
        return out

    E.append(P("(1) 표준재무상태표 <font size=8 color='#52514e'>(단위: 원)</font>", "h2"))
    E.append(table(hdr, fs_rows(II["bs"]), wid, num_cols=(2, 3, 4, 5), bold_rows=(9, 12, 18, 19)))
    E.append(src_note(prev.bs.get(228), cur.bs.get(228)))
    E.append(P("(2) 표준손익계산서 <font size=8 color='#52514e'>(단위: 원)</font>", "h2"))
    E.append(table(hdr, fs_rows(II["pl"]), wid, num_cols=(2, 3, 4, 5), bold_rows=(0, 4, 9)))
    E.append(src_note(prev.pl.get(1), cur.pl.get(1)))

    for fl in rp.ev.flags:
        if fl["섹션"] == "II":
            E.append(P("※ 차이 표시: " + fl["내용"], "flag"))
    E.append(P("(3) 재무비율", "h2"))
    rr = []
    for k, unit, std in RATIO_META:
        a, b = II["ratios"]["prev"][k], II["ratios"]["cur"][k]

        def f(x):
            if x.get("label"):
                return x["label"]
            if x["value"] is None:
                return "-"
            return f"{x['value']:.2f}" if unit == "%" else f"{x['value']:.4f}"
        rr.append([k, unit, std, f(a), f(b)])
    E.append(table(["구분", "단위", "표준비율", f"{py}년", f"{cy}년"], rr, [W * 0.32, W * 0.1, W * 0.18, W * 0.2, W * 0.2],
                   num_cols=(3, 4)))
    E.append(P("부채비율 = 부채/자기자본×100, 유동비율 = 유동자산/유동부채×100, 당좌비율 = 당좌자산/유동부채×100, "
               "총자산세전순이익률 = 세전이익/총자산×100, 영업이익률 = 영업이익/매출액×100, 총자산회전율 = 매출액/평균총자산, "
               "자기자본회전율 = 매출액/평균자기자본. 평균 = (기초+기말)/2, 전기 기초는 전기 결산서 전기 열 값. "
               "「표준비율」은 업종 특성을 고려하지 않은 일반 기준입니다.", "note"))

    E.append(P("(4) 요약 손익 비교 <font size=8 color='#52514e'>(단위: 원)</font>", "h2"))
    E.append(table(["항목", f"{py}년", f"{cy}년", "증감액", "증감률"],
                   [[r["item"], won(r["prev"]), won(r["cur"]), signed(r["diff"]), change_text(r)] for r in II["summary"]],
                   [W * 0.28, W * 0.2, W * 0.2, W * 0.18, W * 0.14], num_cols=(1, 2, 3, 4)))
    E.append(P("영업외손익 = 영업외수익 − 영업외비용. 전기 손실에서 당기 이익으로 바뀐 항목은 «흑자전환»으로 표기합니다.", "note"))

    E.append(P(f"(5) 판매비와관리비 주요 항목 (당기 상위 {len(II['sga_top'])}개) <font size=8 color='#52514e'>(단위: 원)</font>", "h2"))
    srows = [[s["name"], won(s["prev"]), won(s["cur"]), signed(s["diff"]), change_text(s),
              pct(s["share_prev"]), pct(s["share_cur"])] for s in II["sga_top"]]
    srows.append(["판매비와관리비 합계", won(g(prev.pl, 67)), won(g(cur.pl, 67)), signed(g(cur.pl, 67) - g(prev.pl, 67)),
                  change_text(change(g(prev.pl, 67), g(cur.pl, 67))), pct(g(prev.pl, 67) / g(prev.pl, 1) * 100),
                  pct(g(cur.pl, 67) / g(cur.pl, 1) * 100)])
    E.append(table(["계정", f"{py}년", f"{cy}년", "증감액", "증감률", f"매출 대비 {py}", f"매출 대비 {cy}"], srows,
                   [W * 0.2, W * 0.15, W * 0.15, W * 0.15, W * 0.11, W * 0.12, W * 0.12], num_cols=(1, 2, 3, 4, 5, 6),
                   bold_rows=(len(srows) - 1,)))
    E.append(P("계정명은 결산서 손익계산서 기준입니다 (표준손익계산서 「37.기타」 = 결산서 「외주용역비」). "
               f"매출 대비 비중 = 해당 계정 ÷ 같은 연도 매출액 × 100.", "note"))
    E.append(src_note(f"{cur.doc.name} · 결산 손익계산서 · p{II['sga_top'][0]['page_cur']}" if II["sga_top"] else None))

    E.append(P("(6) 그래프", "h2"))
    for k in ("pl", "comp", "sga", "bs"):
        E.append(KeepTogether([Image(str(charts[k]), width=W, height=W * (3.4 if k == "sga" else 3.2) / 7.2), Spacer(1, 6)]))

    # ---- III. 법인세 신고상황
    E.append(PageBreak())
    E.append(P("III. 법인세 신고상황 <font size=8 color='#52514e'>(단위: 원)</font>", "h1"))
    rows = []
    for r in S["III"]:
        if r["kind"] == "pct":
            a, b = pct(r["prev"]), pct(r["cur"])
        elif r["kind"] == "rate_int":
            a, b = (f"{r['prev']}" if r["prev"] else "-"), (f"{r['cur']}" if r["cur"] else "-")
        else:
            a, b = won(r["prev"]), won(r["cur"])
        rows.append([r["item"], a, b])
    E.append(table(["구분", f"{py} 사업연도", f"{cy} 사업연도"], rows, [W * 0.44, W * 0.28, W * 0.28], num_cols=(1, 2),
                   bold_rows=(6, 10, 15, 17)))
    E.append(P("소득률 = 각사업연도소득금액/수입금액×100, 매출총이익률 = 매출총이익/매출액×100, 영업이익률 = 영업이익/매출액×100, "
               "실효세율(과세표준 기준) = 총부담세액/과세표준×100, 실효세율(소득금액 기준) = 총부담세액/각사업연도소득금액×100. "
               "기준 금액이 0 이하이면 «-».", "note"))
    E.append(src_note(prev.tax.get("01"), cur.tax.get("01"), prev.revenue, cur.revenue, cur.local_tax))

    # ---- IV. 이월결손금
    E.append(P(f"IV. 이월결손금 ({cy} 사업연도) <font size=8 color='#52514e'>(단위: 원)</font>", "h1"))
    IV = S["IV"]
    if IV["rows"]:
        rows = [[r["year"], won(r["occur"]), won(r["prior"]), won(r["decrease"]), won(r["balance"])] for r in IV["rows"]]
        rows.append(["합계"] + [won(sum(r[k] for r in IV["rows"])) for k in ("occur", "prior", "decrease", "balance")])
        E.append(table(["발생 사업연도", "발생액", "기공제액(전기까지)", f"감소액({cy} 공제)", "잔액"], rows, [W * 0.2] * 5,
                       num_cols=(1, 2, 3, 4), bold_rows=(len(rows) - 1,)))
        E.append(P("잔액 = 발생액 − 기공제액 − 당기 공제액 (자본금과적립금조정명세서(갑) Ⅱ 기준).", "note"))
        for n in IV["notes"]:
            E.append(P("※ 차이 표시: " + n, "flag"))
        E.append(src_note(IV["rows"][0]["src"], IV["used_src"]))
    else:
        E.append(P("이월결손금 내역이 없습니다.", "body"))

    # ---- V. 소득금액조정
    E.append(P(f"V. 소득금액조정 ({cy} 사업연도) <font size=8 color='#52514e'>(단위: 원)</font>", "h1"))
    V = S["V"]
    if not V["present"] or not (V["plus"] or V["minus"]):
        E.append(P("세무조정 사항이 없습니다 (소득금액조정합계표 없음).", "body"))
    else:
        n = max(len(V["plus"]), len(V["minus"]))
        rows = []
        for i in range(n):
            a = V["plus"][i] if i < len(V["plus"]) else None
            b = V["minus"][i] if i < len(V["minus"]) else None
            rows.append([a.item if a else "", won(a.value) if a else "", a.note if a else "",
                         b.item if b else "", won(b.value) if b else "", b.note if b else ""])
        rows.append(["합계", won(sum(v.value for v in V["plus"])), "", "합계", won(sum(v.value for v in V["minus"])), ""])
        E.append(table(["익금산입·손금불산입 과목", "금액", "소득처분", "손금산입·익금불산입 과목", "금액", "소득처분"], rows,
                       [W * 0.2, W * 0.15, W * 0.15, W * 0.2, W * 0.15, W * 0.15], num_cols=(1, 4), bold_rows=(len(rows) - 1,)))
        E.append(src_note(*(V["plus"] + V["minus"])))
    if not prev.adjustments["present"]:
        E.append(P(f"참고: {py} 사업연도는 소득금액조정합계표가 없으며 익금·손금 조정액이 0원입니다.", "note"))

    # ---- VI. 공제·감면세액
    E.append(P(f"VI. 공제·감면세액 ({cy} 사업연도) <font size=8 color='#52514e'>(단위: 원)</font>", "h1"))
    VI = S["VI"]
    if VI["rows"]:
        rows = [[v.item.replace("에대한", "에 대한 "), v.note, v.label, won(v.value)] for v in VI["rows"]]
        rows.append(["합계", "", "", won(VI["total"])])
        E.append(table(["공제·감면 구분", "근거 법조항", "코드·감면율", "공제·감면세액"], rows,
                       [W * 0.32, W * 0.3, W * 0.18, W * 0.2], num_cols=(3,), bold_rows=(len(rows) - 1,)))
        E.append(src_note(*VI["rows"]))
    else:
        E.append(P(f"{cy} 사업연도에 적용된 공제·감면세액이 없습니다 (세액조정계산서 ⑰·⑲ 0원).", "body"))
    if cur.credits:  # 세액공제조정명세서(3)에 적힌 그대로 (고객 답변 Q-21: 서식에 나와 있는 그대로)
        rows = [[c["name"], f"{c['year'][:4]}.{c['year'][4:]}", won(c["amount"]), won(VI["form_total"])] for c in cur.credits]
        E.append(P("세액공제 (세액공제조정명세서(3) 「2. 당기공제세액 및 이월액계산」)", "h2"))
        E.append(table(["공제 구분", "발생 사업연도", "요공제세액", f"{cy} 공제세액"], rows,
                       [W * 0.34, W * 0.18, W * 0.24, W * 0.24], num_cols=(2, 3)))
        E.append(P(f"{cy} 공제세액은 법인세 과세표준 및 세액조정계산서의 공제감면세액(⑰·⑲) 기준입니다. "
                   "산출세액이 0원이라 공제된 세액이 없습니다.", "note"))
        E.append(src_note(*[c["src"] for c in cur.credits], cur.tax.get("17")))

    # ---- VII. 요약 코멘트
    E.append(PageBreak())
    E.append(P("VII. 요약 코멘트", "h1"))
    for c in S["VII"]:
        E.append(P(c["title"], "h2"))
        E.append(P(c["text"], "body"))

    # ---- VIII. 재무제표 주요 특이사항
    E.append(P("VIII. 재무제표 주요 특이사항", "h1"))
    for i, it in enumerate(S["VIII"], start=1):
        E.append(P(f"{i}. {it['title']}", "h2"))
        for line in it["lines"]:
            E.append(P("· " + line, "body"))
        E.append(P("출처: " + it["src"], "note"))
    for fl in rp.ev.flags:
        if fl["섹션"] != "IV":
            E.append(P("※ " + fl["내용"], "flag"))

    # ---- 부록: 검산
    E.append(PageBreak())
    E.append(P("부록. 검산 결과", "h1"))
    E.append(table(["검산", "결과", "내용"], [[c["검산"], c["결과"], c["내용"]] for c in rp.ev.checks],
                   [W * 0.34, W * 0.1, W * 0.56]))
    E.append(P("불일치 항목은 숫자를 고치지 않고 원문 값을 그대로 쓰며, 해당 섹션에 차이를 표시합니다. "
               "«보류»는 확인 필요 값이 섞여 검산하지 않은 항목입니다.", "note"))
    if rp.ev.warnings:
        E.append(P("부록. 확인 필요 · 경고 목록", "h1"))
        E.append(P("PDF에 회색으로 가려진 칸, 합계가 빈칸인 필수값, 서식 간 숫자 차이를 기록했습니다. 확인 필요 값은 0으로 넣거나 "
                   "다른 서식에서 가져오지 않았고, 그 값에 의존하는 계산만 보류했습니다.", "note"))
        rows = [[w["구분"], f"{w['연도']}", f"{w['서식']} p{w['페이지']}", w["항목"],
                 f"{w['표시값']:,}" if isinstance(w["표시값"], int) else str(w["표시값"]), w["내용"]] for w in rp.ev.warnings]
        E.append(table(["구분", "연도", "서식·페이지", "항목", "표시값", "내용"], rows,
                       [W * 0.12, W * 0.06, W * 0.17, W * 0.16, W * 0.11, W * 0.38]))
    doc.build(E, onFirstPage=on_page, onLaterPages=on_page)
