"""추출값으로 보고서 데이터(섹션 I~VIII)를 만든다. 계산 규칙은 config(rules)에서 온다."""

from __future__ import annotations

from dataclasses import dataclass, field

from .extract import YearData
from .model import CONFIRMED, NEEDS_CHECK, Evidence, Value

# 출력 예시 Excel의 표준재무제표 행 (코드, 표시명)
BS_ROWS = [
    (1, "Ⅰ. 유동자산"), (2, "(1) 당좌자산"), (44, "(2) 재고자산"), (67, "(3) 기타유동자산"),
    (80, "Ⅱ. 비유동자산"), (81, "(1) 투자자산"), (110, "(2) 유형자산"), (169, "(3) 무형자산"), (194, "(4) 기타비유동자산"),
    (228, "자산총계(Ⅰ+Ⅱ)"), (229, "Ⅰ. 유동부채"), (284, "Ⅱ. 비유동부채"), (333, "부채총계(Ⅰ+Ⅱ)"),
    (334, "Ⅲ. 자본금"), (337, "Ⅳ. 자본잉여금"), (348, "Ⅴ. 자본조정"), (361, "Ⅵ. 기타포괄손익누계액"),
    (372, "Ⅶ. 이익잉여금"), (382, "자본총계(Ⅲ~Ⅶ)"), (383, "부채와자본총계"),
]
PL_ROWS = [
    (1, "Ⅰ. 매출액"), (35, "Ⅱ. 매출원가"), (66, "Ⅲ. 매출총손익"), (67, "Ⅳ. 판매비와관리비"),
    (129, "Ⅴ. 영업손익"), (130, "Ⅵ. 영업외수익"), (179, "Ⅶ. 영업외비용"),
    (217, "Ⅷ. 법인세비용차감전손익"), (218, "Ⅸ. 법인세비용"), (219, "Ⅹ. 당기순손익"),
]


def g(d: dict, code) -> int:
    v = d.get(code)
    return v.value if v is not None and isinstance(v.value, int) else 0


def change(prev: float | None, cur: float | None) -> dict:
    """증감액·증감률·표기 (D-022)."""
    if prev is None or cur is None:
        return {"diff": None, "rate": None, "label": "확인 필요"}
    diff = cur - prev
    if prev < 0 <= cur and cur > 0:
        return {"diff": diff, "rate": None, "label": "흑자전환"}
    if prev > 0 > cur:
        return {"diff": diff, "rate": None, "label": "적자전환"}
    if prev < 0 and cur < 0:
        return {"diff": diff, "rate": None, "label": "적자지속"}
    if prev == 0:
        return {"diff": diff, "rate": None, "label": "-" if cur == 0 else "-"}
    return {"diff": diff, "rate": diff / abs(prev) * 100, "label": None}


def debt_ratio(bs: dict) -> dict:
    liab, eq = g(bs, 333), g(bs, 382)
    if eq <= 0:
        return {"value": liab / eq * 100 if eq else None, "label": "자본잠식", "impaired": True}
    return {"value": liab / eq * 100, "label": None, "impaired": False}


@dataclass
class Report:
    prev: YearData
    cur: YearData
    rules: dict
    ev: Evidence = field(default_factory=Evidence)
    sections: dict = field(default_factory=dict)


def build(prev: YearData, cur: YearData, rules: dict) -> Report:
    rp = Report(prev, cur, rules)
    ev = rp.ev
    for y in (prev, cur):
        for d in (y.bs, y.pl):
            for v in d.values():
                ev.add(v)
        for v in y.tax.values():
            ev.add(v)
        ev.add(y.revenue)
        ev.add(y.local_tax)

    _checks(rp)
    S = rp.sections
    S["card"] = _card(rp)
    S["I"] = cur.info
    S["II"] = _section2(rp)
    S["III"] = _section3(rp)
    S["IV"] = _section4(rp)
    S["V"] = cur.adjustments
    S["VI"] = _section6(rp)
    S["VIII"] = _section8(rp)
    from .comments import build_comments

    S["VII"] = build_comments(rp)
    return rp


# ------------------------------------------------------------------ 검산
def _checks(rp: Report):
    ev, prev, cur = rp.ev, rp.prev, rp.cur
    ok = ev.check("같은 회사", prev.info["사업자등록번호"].value == cur.info["사업자등록번호"].value,
                  f"{prev.info['사업자등록번호'].value} / {cur.info['사업자등록번호'].value}")
    if not ok:
        raise SystemExit("두 PDF의 사업자등록번호가 다릅니다. 같은 회사의 자료인지 확인하세요.")
    ev.check("연속 사업연도", cur.year - prev.year == 1, f"{prev.year} → {cur.year}")
    for y in (prev, cur):
        bs, pl = y.bs, y.pl
        ev.check(f"{y.year} 자산=부채+자본", g(bs, 228) == g(bs, 333) + g(bs, 382),
                 f"{g(bs,228):,} = {g(bs,333):,} + {g(bs,382):,}")
        ev.check(f"{y.year} 매출총손익", g(pl, 66) == g(pl, 1) - g(pl, 35), f"{g(pl,66):,} = {g(pl,1):,} − {g(pl,35):,}")
        ev.check(f"{y.year} 영업손익", g(pl, 129) == g(pl, 66) - g(pl, 67), f"{g(pl,129):,} = {g(pl,66):,} − {g(pl,67):,}")
        ev.check(f"{y.year} 세전손익", g(pl, 217) == g(pl, 129) + g(pl, 130) - g(pl, 179),
                 f"{g(pl,217):,} = {g(pl,129):,} + {g(pl,130):,} − {g(pl,179):,}")
        ev.check(f"{y.year} 당기순손익", g(pl, 219) == g(pl, 217) - g(pl, 218), f"{g(pl,219):,} = {g(pl,217):,} − {g(pl,218):,}")
        s = sum(r["cur"] for r in y.sga)
        ev.check(f"{y.year} 판관비 세부 합계(결산서)", s == g(pl, 67), f"{s:,} vs 표준 {g(pl,67):,}")
        ev.check(f"{y.year} 결산서 당기순손익 = 별지3 ①01", g(pl, 219) == g(y.tax, "01"), f"{g(pl,219):,} / {g(y.tax,'01'):,}")
        if g(pl, 218):
            ev.check(f"{y.year} 법인세비용 = 법인세 + 지방소득세", g(pl, 218) == g(y.tax, "30") + (y.local_tax.value or 0),
                     f"{g(pl,218):,} = {g(y.tax,'30'):,} + {y.local_tax.value or 0:,}")
    # 당기 PDF 전기 열 = 전기 PDF 당기 값 (D-004)
    pairs = [("자산총계", prev.bs, 228), ("부채총계", prev.bs, 333), ("자본총계", prev.bs, 382)]
    for label, d, code in pairs:
        pv = cur.settle_bs_prev.get(label)
        if pv is not None:
            ev.check(f"전기 열 대조: {label}", pv == g(d, code), f"당기 PDF 전기 열 {pv:,} / 전기 PDF {g(d,code):,}")
    for label, code in [("매출액", 1), ("판매비와관리비", 67), ("당기순이익", 219), ("당기순손실", 219)]:
        pv = next((v for k, v in cur.settle_pl_prev.items() if k.startswith(label)), None)
        if pv is not None:
            ev.check(f"전기 열 대조: {label}", pv == g(prev.pl, code), f"당기 PDF 전기 열 {pv:,} / 전기 PDF {g(prev.pl,code):,}")


# ------------------------------------------------------------------ 요약 카드
def _card(rp: Report) -> list[dict]:
    p, c = rp.prev.pl, rp.cur.pl
    rows = []
    for name, code in [("매출액", 1), ("영업이익", 129), ("당기순이익", 219)]:
        rows.append({"item": name, "prev": g(p, code), "cur": g(c, code), **change(g(p, code), g(c, code)), "kind": "amount"})
    dp, dc = debt_ratio(rp.prev.bs), debt_ratio(rp.cur.bs)
    lab = None
    if dp["impaired"] and not dc["impaired"]:
        lab = "자본잠식 해소"
    elif not dp["impaired"] and dc["impaired"]:
        lab = "자본잠식 발생"
    rows.append({"item": "부채비율", "prev": dp, "cur": dc, "kind": "ratio",
                 "diff": (dc["value"] - dp["value"]) if not (dp["impaired"] or dc["impaired"]) else None, "label": lab})
    return rows


# ------------------------------------------------------------------ II
def _ratios(y: YearData, prev_bs: dict | None) -> dict:
    bs, pl = y.bs, y.pl
    res = {}
    dr = debt_ratio(bs)
    res["부채비율"] = dr
    cl = g(bs, 229)
    res["유동비율"] = {"value": g(bs, 1) / cl * 100 if cl else None}
    res["당좌비율"] = {"value": g(bs, 2) / cl * 100 if cl else None}
    ta = g(bs, 228)
    res["총자산세전순이익률"] = {"value": g(pl, 217) / ta * 100 if ta else None}
    res["영업이익률"] = {"value": g(pl, 129) / g(pl, 1) * 100 if g(pl, 1) else None}
    open_ta = g(prev_bs, 228) if prev_bs else None
    open_eq = g(prev_bs, 382) if prev_bs else None
    if open_ta is None:
        res["총자산회전율"] = {"value": None, "note": "기초 자료 없음"}
        res["자기자본회전율"] = {"value": None, "note": "기초 자료 없음"}
    else:
        avg_ta = (open_ta + ta) / 2
        avg_eq = (open_eq + g(bs, 382)) / 2
        res["총자산회전율"] = {"value": g(pl, 1) / avg_ta if avg_ta > 0 else None}
        res["자기자본회전율"] = {"value": g(pl, 1) / avg_eq if avg_eq > 0 else None,
                            "note": "평균 자기자본 0 이하" if avg_eq <= 0 else ""}
    return res


RATIO_META = [("부채비율", "%", "200이하"), ("유동비율", "%", "130이상"), ("당좌비율", "%", "100이상"),
              ("총자산세전순이익률", "%", "10이상"), ("영업이익률", "%", "10이상"), ("총자산회전율", "회", "1.5회"),
              ("자기자본회전율", "회", "3회")]


def _section2(rp: Report) -> dict:
    prev, cur = rp.prev, rp.cur
    # 전기의 기초 = 전기 PDF 결산 재무상태표 전기 열 (첫 사업연도면 0)
    prev_open = {228: _V(prev.settle_bs_prev.get("자산총계", 0)), 382: _V(prev.settle_bs_prev.get("자본총계", 0))}
    if "자산총계" not in prev.settle_bs_prev:  # 결산서 전기 열에 합계 줄이 없으면 구성 항목 합
        prev_open = {228: _V(0), 382: _V(0)}
    bs = [{"code": c, "name": n, "prev": g(prev.bs, c), "cur": g(cur.bs, c),
           "src_prev": prev.bs.get(c), "src_cur": cur.bs.get(c)} for c, n in BS_ROWS]
    pl = [{"code": c, "name": n, "prev": g(prev.pl, c), "cur": g(cur.pl, c),
           "src_prev": prev.pl.get(c), "src_cur": cur.pl.get(c)} for c, n in PL_ROWS]
    ratios = {"prev": _ratios(prev, prev_open), "cur": _ratios(cur, prev.bs)}
    # 요약 손익 비교 (요구사항 #4)
    def oi(pl):
        return g(pl, 130) - g(pl, 179)

    items = [("매출액", lambda p: g(p, 1)), ("매출총이익", lambda p: g(p, 66)), ("영업손익", lambda p: g(p, 129)),
             ("영업외손익", oi), ("법인세차감전손익", lambda p: g(p, 217)), ("법인세비용", lambda p: g(p, 218)),
             ("당기순이익", lambda p: g(p, 219))]
    summary = [{"item": n, "prev": f(prev.pl), "cur": f(cur.pl), **change(f(prev.pl), f(cur.pl))} for n, f in items]
    # 판관비 (결산서 계정명, D-025)
    prev_map = {r["label"]: r["cur"] for r in prev.sga}
    sga = []
    for r in cur.sga:
        pv = prev_map.get(r["label"], r["prev"] or 0)
        sga.append({"name": r["label"], "prev": pv, "cur": r["cur"], **change(pv, r["cur"]),
                    "share_prev": pv / g(prev.pl, 1) * 100 if g(prev.pl, 1) else None,
                    "share_cur": r["cur"] / g(cur.pl, 1) * 100 if g(cur.pl, 1) else None,
                    "comp_cur": r["cur"] / g(cur.pl, 67) * 100 if g(cur.pl, 67) else None,
                    "page_cur": r["page"]})
    for name, pv in prev_map.items():  # 전기에만 있는 계정
        if name not in {s["name"] for s in sga}:
            sga.append({"name": name, "prev": pv, "cur": 0, **change(pv, 0), "share_prev": pv / g(prev.pl, 1) * 100,
                        "share_cur": 0.0, "comp_cur": 0.0, "page_cur": None})
    sga.sort(key=lambda r: -r["cur"])
    top_n = rp.rules["sga_top_n"]
    return {"bs": bs, "pl": pl, "ratios": ratios, "summary": summary, "sga_all": sga, "sga_top": sga[:top_n]}


def _V(x):
    return Value("", 0, x)


# ------------------------------------------------------------------ III 법인세 신고상황
def _section3(rp: Report) -> list[dict]:
    rows = []

    def r(name, fp, fc, kind="amount"):
        rows.append({"item": name, "prev": fp(rp.prev), "cur": fc(rp.cur), "kind": kind})

    t = lambda code: (lambda y: g(y.tax, code))
    r("매출액(수입금액)", lambda y: y.revenue.value, lambda y: y.revenue.value)
    r("매출총이익", lambda y: g(y.pl, 66), lambda y: g(y.pl, 66))
    r("영업이익", lambda y: g(y.pl, 129), lambda y: g(y.pl, 129))
    r("당기순손익", t("01"), t("01"))
    r("(+)익금조정", t("02"), t("02"))
    r("(-)손금조정", t("03"), t("03"))
    r("각사업연도 소득금액", t("06"), t("06"))
    r("(-)이월결손금", t("07"), t("07"))
    r("(-)비과세소득", t("08"), t("08"))
    r("(-)소득공제", t("09"), t("09"))
    r("과세표준금액", t("10"), t("10"))
    r("세율(%)", t("11"), t("11"), "rate_int")
    r("산출세액", t("12"), t("12"))
    r("최저한세 적용대상 공제감면세액", t("17"), t("17"))
    r("최저한세 적용제외 공제감면세액", t("19"), t("19"))
    r("총부담세액", t("21"), t("21"))
    r("기납부세액", t("28"), t("28"))
    r("차감납부할세액", lambda y: g(y.tax, "46") or g(y.tax, "30"), lambda y: g(y.tax, "46") or g(y.tax, "30"))
    r("법인지방소득세", lambda y: y.local_tax.value, lambda y: y.local_tax.value)

    def ratio(num, den):
        return lambda y: (num(y) / den(y) * 100) if den(y) and den(y) > 0 and num(y) is not None else None

    rev = lambda y: y.revenue.value or 0
    r("소득률", ratio(t("06"), rev), ratio(t("06"), rev), "pct")
    r("매출총이익률", ratio(lambda y: g(y.pl, 66), lambda y: g(y.pl, 1)), ratio(lambda y: g(y.pl, 66), lambda y: g(y.pl, 1)), "pct")
    r("영업이익률", ratio(lambda y: g(y.pl, 129), lambda y: g(y.pl, 1)), ratio(lambda y: g(y.pl, 129), lambda y: g(y.pl, 1)), "pct")
    r("실효세율(과세표준 기준)", ratio(t("21"), t("10")), ratio(t("21"), t("10")), "pct")
    r("실효세율(소득금액 기준)", ratio(t("21"), t("06")), ratio(t("21"), t("06")), "pct")
    return rows


# ------------------------------------------------------------------ IV 이월결손금 (D-024)
def _section4(rp: Report) -> dict:
    cur, prev = rp.cur, rp.prev
    used = g(cur.tax, "07")
    rows, notes = [], []
    remaining = used
    for v in cur.losses:
        dec = min(v.value, remaining)
        remaining -= dec
        yymm = v.item[v.item.find("(") + 1:v.item.find(")")].replace("-", "")[:6]
        rows.append({"year": yymm, "occur": v.value, "decrease": dec, "balance": v.value - dec, "src": v})
    # 발생액 vs 그 해 세무상 결손금 (FR-4.7)
    for row in rows:
        if row["year"][:4] == str(prev.year):
            tax_loss = -g(prev.tax, "06") if g(prev.tax, "06") < 0 else 0
            ok = rp.ev.check("결손금 발생액 = 전기 각사업연도 결손금", row["occur"] == tax_loss,
                             f"자본금과적립금조정명세서(갑) {row['occur']:,} / {prev.year} 세액조정계산서 ⑥ {tax_loss:,}")
            if not ok:
                diff = row["occur"] - tax_loss
                note = (f"{prev.year}년 손익계산서·법인세 과세표준 및 세액조정계산서상 결손금은 {tax_loss:,}원으로, "
                        f"자본금과적립금조정명세서(갑) 발생액 {row['occur']:,}원과 {abs(diff):,}원 차이가 있습니다 "
                        f"(원인 확인 중). 근거: {cur.doc.name} p{row['src'].page}, {prev.doc.name} "
                        f"p{prev.tax['06'].page}.")
                notes.append(note)
                rp.ev.flags.append({"섹션": "IV", "내용": note})
    return {"rows": rows, "notes": notes, "used_src": cur.tax.get("07")}


# ------------------------------------------------------------------ VI 공제·감면
def _section6(rp: Report) -> dict:
    cur = rp.cur
    total = sum(v.value for v in cur.reductions)
    form_total = g(cur.tax, "17") + g(cur.tax, "19")
    rp.ev.check("공제감면 합계 = 별지3 ⑰+⑲", total == form_total, f"신청서 {total:,} / 별지3 {form_total:,}")
    return {"rows": cur.reductions, "total": total, "form_total": form_total}


# ------------------------------------------------------------------ VIII 재무제표 주요 특이사항 (D-026)
def _section8(rp: Report) -> list[dict]:
    prev, cur, rules = rp.prev, rp.cur, rp.rules
    items = []
    # ① 가지급금·가수금 (거래처코드별)
    for title, acc in [("가지급금명세서", "가지급금"), ("주임종단기채권명세서", "주임종단기채권"), ("가수금명세서", "가수금")]:
        pr = {r.partner_code: r for r in prev.ledgers.get(title, [])}
        cr = {r.partner_code: r for r in cur.ledgers.get(title, [])}
        if not pr and not cr:
            continue
        lines = []
        for code in sorted(set(pr) | set(cr)):
            p = pr.get(code)
            c = cr.get(code)
            pb = p.balance if p else (c.opening or 0 if c else 0)
            cb = c.balance if c else 0
            name = (c or p).partner
            detail = ""
            if c and c.increase is not None and c.decrease is not None:
                detail = f" (당기 증가 {c.increase:,}원, 감소 {c.decrease:,}원)"
            lines.append(f"거래처코드 {code} {name}: {prev.year}년 말 {pb:,}원 → {cur.year}년 말 {cb:,}원, "
                         f"{'감소' if cb < pb else '증가'} {abs(cb - pb):,}원{detail}. "
                         f"{cur.year}년 말 잔액은 매출액의 {cb / g(cur.pl, 1) * 100:.2f}%입니다.")
        page = (cur.ledgers[title][0].page if cur.ledgers.get(title) else None)
        items.append({"title": f"{acc} 현황", "lines": lines, "src": f"결산부속명세서 {title} ({cur.doc.name} p{page})"})
    if not any(prev.ledgers.get(t) or cur.ledgers.get(t) for t in ("가지급금명세서", "주임종단기채권명세서")):
        items.append({"title": "가지급금 현황", "lines": ["전기·당기 모두 결산부속명세서에 가지급금 명세가 없습니다."],
                      "src": "결산부속명세서"})
    # ② 인건비 = 직원급여 + 임원급여 (표준손익계산서 69·70, 상여 71·72·73 별도 표시)
    def labor(pl):
        return g(pl, 69), g(pl, 70)

    pe, pw = labor(prev.pl)
    ce, cw = labor(cur.pl)
    ch = change(pe + pw, ce + cw)
    rate = f", {ch['rate']:+.1f}%" if ch["rate"] is not None else ""
    items.append({"title": "인건비 (직원급여 + 임원급여)", "lines": [
        f"직원급여 {pw:,}원 → {cw:,}원 ({cw - pw:+,}원), 임원급여 {pe:,}원 → {ce:,}원.",
        f"인건비 합계 {pe + pw:,}원 → {ce + cw:,}원 ({ch['diff']:+,}원{rate}), 매출액 대비 "
        f"{(pe + pw) / g(prev.pl, 1) * 100:.2f}% → {(ce + cw) / g(cur.pl, 1) * 100:.2f}%."],
        "src": f"표준손익계산서 코드 69·70 ({prev.doc.name} p{prev.pl[70].page if 70 in prev.pl else '-'}, "
               f"{cur.doc.name} p{cur.pl[70].page if 70 in cur.pl else '-'})"})
    # ③ 부채비율 변화
    dp, dc = debt_ratio(prev.bs), debt_ratio(cur.bs)

    def dtxt(d, bs):
        return (f"자본잠식 (자본총계 {g(bs,382):,}원)" if d["impaired"] else f"{d['value']:.2f}%")

    lines = [f"부채비율 {prev.year}년 {dtxt(dp, prev.bs)} → {cur.year}년 {dtxt(dc, cur.bs)}."]
    if dp["impaired"] and not dc["impaired"]:
        lines.append(f"당기순이익 {g(cur.pl,219):,}원으로 자본총계가 {g(cur.bs,382):,}원이 되어 자본잠식이 해소되었습니다.")
        cap = g(prev.bs, 334)
        need = cap - g(prev.bs, 382)
        ga = sum(r.balance for r in prev.ledgers.get("가수금명세서", []))
        if ga:
            lines.append(f"참고: {prev.year}년 말 기준으로 자본금({cap:,}원)까지 회복하려면 {need:,}원이 필요했으며, "
                         f"당시 대표자 가수금은 {ga:,}원이었습니다.")
    elif dc["impaired"]:
        cap = g(cur.bs, 334)
        need = cap - g(cur.bs, 382)
        lines.append(f"자본잠식 상태입니다. 자본금({cap:,}원)까지 회복하려면 {need:,}원의 자본 확충(가수금 출자전환 등)이 필요합니다.")
    else:
        lines.append(f"부채비율이 {dc['value'] - dp['value']:+.2f}%p 변동했습니다.")
    items.append({"title": "부채비율 변화", "lines": lines, "src": "표준재무상태표 코드 333·382"})
    # ④ 전기 대비 5% 이상 증가한 비용 (D-027)
    th = rules["expense_increase_pct"]
    sga = rp.sections.get("II", {}).get("sga_all") or _section2(rp)["sga_all"]
    inc = [s for s in sga if s["rate"] is not None and s["rate"] >= th]
    inc.sort(key=lambda s: -s["rate"])
    items.append({"title": f"전기 대비 {th:g}% 이상 증가한 비용", "lines": [
        f"{s['name']}: {s['prev']:,}원 → {s['cur']:,}원 ({s['diff']:+,}원, {s['rate']:+.1f}%)" for s in inc
    ] or ["해당 항목 없음"], "src": f"결산 손익계산서 판매비와관리비 ({cur.doc.name})"})
    # ⑤ 없어진 항목 / 새로 생긴 항목 (손익계산서 + 재무상태표 계정)
    gone, new = [], []
    for s in sga:
        if s["prev"] and not s["cur"]:
            gone.append(f"{s['name']} ({s['prev']:,}원 → 0원)")
        if not s["prev"] and s["cur"]:
            new.append(f"{s['name']} (0원 → {s['cur']:,}원)")
    for code, name in [(35, "매출원가"), (218, "법인세비용")]:
        a, b = g(prev.pl, code), g(cur.pl, code)
        if a and not b:
            gone.append(f"{name} ({a:,}원 → 0원)")
        if not a and b:
            new.append(f"{name} (0원 → {b:,}원)")
    skip = {1, 2, 80, 194, 228, 229, 333, 334, 372, 382, 383}
    names = {c: v.label.split(" (코드")[0] for c, v in {**prev.bs, **cur.bs}.items()}
    for code in sorted(set(prev.bs) | set(cur.bs)):
        if code in skip:
            continue
        a, b = g(prev.bs, code), g(cur.bs, code)
        nm = names[code]
        if not nm[:1].isdigit() or "." not in nm[:4]:  # 대분류만 (예: 2. 재고자산 → '(2) 재고자산'은 제외)
            continue
        if a and not b:
            gone.append(f"{nm} ({a:,}원 → 0원)")
        if not a and b:
            new.append(f"{nm} (0원 → {b:,}원)")
    items.append({"title": "없어진 항목 / 새로 생긴 항목", "lines": [
        "없어진 항목: " + (", ".join(gone) if gone else "없음"),
        "새로 생긴 항목: " + (", ".join(new) if new else "없음")], "src": "표준재무상태표 · 결산 손익계산서"})
    # 참고: 매출채권 · 거래처 (요구사항 #7 예시)
    pr, cr = prev.ledgers.get("외상매출금명세서", []), cur.ledgers.get("외상매출금명세서", [])
    if pr or cr:
        pb, cb = sum(r.balance for r in pr), sum(r.balance for r in cr)
        lines = [f"외상매출금 잔액 {pb:,}원 → {cb:,}원, 매출액 대비 {pb / g(prev.pl,1) * 100:.2f}% → {cb / g(cur.pl,1) * 100:.2f}%.",
                 f"거래 거래처 수 {len(pr)}곳 → {len(cr)}곳 (기말 잔액 보유 {sum(1 for r in pr if r.balance)}곳 → "
                 f"{sum(1 for r in cr if r.balance)}곳)."]
        items.append({"title": "매출채권 · 매출처", "lines": lines, "src": f"결산부속명세서 외상매출금명세서"})
    return items
