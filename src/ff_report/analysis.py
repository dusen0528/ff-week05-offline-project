"""추출값으로 보고서 데이터(섹션 I~VIII)를 만든다. 계산 규칙은 config(rules)에서 온다."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .extract import YearData
from .model import CONFIRMED, NA, NEEDS_CHECK, Evidence, Value, div, is_na

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


def g(d: dict, code):
    """코드 값. 서식에 그 코드가 없으면 0, 확인 필요(회색·빈 합계)면 NA."""
    v = d.get(code)
    if v is None:
        return 0
    if v.status == NEEDS_CHECK or v.value is None:
        return NA
    return v.value if isinstance(v.value, (int, float)) else 0


def change(prev: float | None, cur: float | None) -> dict:
    """증감액·증감률·표기 (D-022)."""
    if is_na(prev, cur):
        return {"diff": NA, "rate": None, "label": "확인 필요"}
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
    if is_na(liab, eq):
        return {"value": NA, "label": "확인 필요", "impaired": False}
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


def build(prev: YearData, cur: YearData, rules: dict, answers: dict | None = None) -> Report:
    from .validate import apply_answers, validate

    rp = Report(prev, cur, rules)
    ev = rp.ev
    apply_answers(ev, {prev.year: prev, cur.year: cur}, answers)
    validate(ev, prev, cur)
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
def _eq(ev, name, left, right, detail):
    """left == right 검산. 확인 필요 값이 섞이면 '보류'."""
    return ev.check(name, (left == right) if not is_na(left, right) else None, detail, left, right)


def _checks(rp: Report):
    ev, prev, cur = rp.ev, rp.prev, rp.cur
    ok = ev.check("같은 회사", prev.info["사업자등록번호"].value == cur.info["사업자등록번호"].value,
                  f"{prev.info['사업자등록번호'].value} / {cur.info['사업자등록번호'].value}")
    if not ok:
        raise SystemExit("두 PDF의 사업자등록번호가 다릅니다. 같은 회사의 자료인지 확인하세요.")
    ev.check("연속 사업연도", cur.year - prev.year == 1, f"{prev.year} → {cur.year}")
    for y in (prev, cur):
        bs, pl = y.bs, y.pl
        _eq(ev, f"{y.year} 자산=부채+자본", g(bs, 228), g(bs, 333) + g(bs, 382),
            f"{g(bs,228):,} = {g(bs,333):,} + {g(bs,382):,}")
        _eq(ev, f"{y.year} 매출총손익", g(pl, 66), g(pl, 1) - g(pl, 35), f"{g(pl,66):,} = {g(pl,1):,} − {g(pl,35):,}")
        _eq(ev, f"{y.year} 영업손익", g(pl, 129), g(pl, 66) - g(pl, 67), f"{g(pl,129):,} = {g(pl,66):,} − {g(pl,67):,}")
        _eq(ev, f"{y.year} 세전손익", g(pl, 217), g(pl, 129) + g(pl, 130) - g(pl, 179),
            f"{g(pl,217):,} = {g(pl,129):,} + {g(pl,130):,} − {g(pl,179):,}")
        _eq(ev, f"{y.year} 당기순손익", g(pl, 219), g(pl, 217) - g(pl, 218), f"{g(pl,219):,} = {g(pl,217):,} − {g(pl,218):,}")
        sga = sga_items(y)
        tot = sum(r["value"] for r in sga)
        _eq(ev, f"{y.year} 판관비 세부 합계", tot, g(pl, 67), f"세부 합 {tot:,} / 판관비 {g(pl,67):,}")
        _eq(ev, f"{y.year} 표준손익 당기순손익 = 별지3 ①01", g(pl, 219), g(y.tax, "01"), f"{g(pl,219):,} / {g(y.tax,'01'):,}")
        if g(pl, 218):
            lt = y.local_tax.value if y.local_tax.value is not None else NA
            _eq(ev, f"{y.year} 법인세비용 = 법인세 + 지방소득세", g(pl, 218), g(y.tax, "30") + lt,
                f"{g(pl,218):,} = {g(y.tax,'30'):,} + {lt:,}")


# ------------------------------------------------------------------ 판관비 (표준손익계산서 코드, D-030)
SGA_TOP_CODES = [68, 74, 78, 79, 80, 81, 85, 86, 87, 90, 91, 92, 93, 94, 95, 96, 97, 98, 101, 104, 107, 108, 109,
                 110, 111, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121, 220, 124]


def sga_items(y: YearData) -> list[dict]:
    """판관비 대분류 계정 (표준손익계산서). '기타(124)'는 결산서에서 같은 금액 계정을 찾아 이름을 붙인다."""
    out = []
    settle = {r["label"]: r["cur"] for r in y.sga if r.get("cur") is not None}
    for code in SGA_TOP_CODES:
        v = y.pl.get(code)
        if v is None:
            continue
        val = g(y.pl, code)
        if val == 0:
            continue
        name = re.sub(r"^\d+\.", "", v.label.split(" (코드")[0]).strip()
        name = re.sub(r"\(.*?\)$", "", name) or name
        if code == 124:
            match = [k for k, a in settle.items() if a == val]
            name = f"기타({match[0]})" if len(match) == 1 else "기타"
        out.append({"code": code, "name": name, "value": val, "src": v})
    return out


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
    res = {"부채비율": debt_ratio(bs)}
    cl = g(bs, 229)
    res["유동비율"] = {"value": _pct(g(bs, 1), cl)}
    res["당좌비율"] = {"value": _pct(g(bs, 2), cl)}
    res["총자산세전순이익률"] = {"value": _pct(g(pl, 217), g(bs, 228))}
    res["영업이익률"] = {"value": _pct(g(pl, 129), g(pl, 1))}
    if prev_bs is None:
        res["총자산회전율"] = {"value": None}
        res["자기자본회전율"] = {"value": None}
    else:
        avg_ta = (g(prev_bs, 228) + g(bs, 228)) / 2
        avg_eq = (g(prev_bs, 382) + g(bs, 382)) / 2
        res["총자산회전율"] = {"value": div(g(pl, 1), avg_ta) if not (avg_ta is not NA and avg_ta <= 0) else None}
        res["자기자본회전율"] = {"value": div(g(pl, 1), avg_eq) if not (avg_eq is not NA and avg_eq <= 0) else None}
    return res


RATIO_META = [("부채비율", "%", "200이하"), ("유동비율", "%", "130이상"), ("당좌비율", "%", "100이상"),
              ("총자산세전순이익률", "%", "10이상"), ("영업이익률", "%", "10이상"), ("총자산회전율", "회", "1.5회"),
              ("자기자본회전율", "회", "3회")]


def _section2(rp: Report) -> dict:
    prev, cur = rp.prev, rp.cur
    # 전기의 기초 = 전기 PDF 결산 재무상태표 전기 열 (첫 사업연도면 0)
    po = prev.settle_bs_prev
    prev_open = ({228: _V(po["자산총계"]), 382: _V(po["자본총계"])} if "자산총계" in po and "자본총계" in po else None)
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
    # 판관비 (표준손익계산서 대분류, D-030). 순서는 당기 금액 내림차순, 당기 확인 필요 값은 맨 뒤.
    pm = {r["code"]: r for r in sga_items(prev)}
    cm = {r["code"]: r for r in sga_items(cur)}
    sga = []
    for code in list(cm) + [c for c in pm if c not in cm]:
        c = cm.get(code)
        p = pm.get(code)
        pv = p["value"] if p else 0
        cv = c["value"] if c else 0
        name = (c or p)["name"]
        if c and p and c["name"] != p["name"] and code == 124:
            name = c["name"] if c["name"] != "기타" else p["name"]
        sga.append({"code": code, "name": name, "prev": pv, "cur": cv, **change(pv, cv),
                    "share_prev": _pct(pv, g(prev.pl, 1)), "share_cur": _pct(cv, g(cur.pl, 1)),
                    "comp_cur": _pct(cv, g(cur.pl, 67)), "page_cur": (c or p)["src"].page,
                    "page_prev": p["src"].page if p else "-",
                    "src": (c or p)["src"]})
    sga.sort(key=lambda r: (is_na(r["cur"]), -(r["cur"] if not is_na(r["cur"]) else 0)))
    top_n = rp.rules["sga_top_n"]
    top = [r for r in sga if not is_na(r["cur"])][:top_n]
    return {"bs": bs, "pl": pl, "ratios": ratios, "summary": summary, "sga_all": sga, "sga_top": top}


def _pct(a, b):
    r = div(a, b)
    return r * 100 if r not in (None, NA) else r


def _V(x):
    return Value("", 0, x)


# ------------------------------------------------------------------ III 법인세 신고상황
def _section3(rp: Report) -> list[dict]:
    rows = []

    def r(name, fp, fc, kind="amount"):
        rows.append({"item": name, "prev": fp(rp.prev), "cur": fc(rp.cur), "kind": kind})

    t = lambda code: (lambda y: g(y.tax, code))
    rev = lambda y: y.revenue.value if y.revenue.status == CONFIRMED and y.revenue.value is not None else NA
    r("매출액(수입금액)", lambda y: rev(y), lambda y: rev(y))
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
    lt = lambda y: y.local_tax.value if y.local_tax.value is not None else NA
    r("법인지방소득세", lt, lt)

    def ratio(num, den):
        def f(y):
            n, d = num(y), den(y)
            if is_na(n, d):
                return NA
            return n / d * 100 if d > 0 else None
        return f

    rev = lambda y: y.revenue.value if y.revenue.status == CONFIRMED and y.revenue.value is not None else NA
    r("소득률", ratio(t("06"), rev), ratio(t("06"), rev), "pct")
    r("매출총이익률", ratio(lambda y: g(y.pl, 66), lambda y: g(y.pl, 1)), ratio(lambda y: g(y.pl, 66), lambda y: g(y.pl, 1)), "pct")
    r("영업이익률", ratio(lambda y: g(y.pl, 129), lambda y: g(y.pl, 1)), ratio(lambda y: g(y.pl, 129), lambda y: g(y.pl, 1)), "pct")
    r("실효세율(과세표준 기준)", ratio(t("21"), t("10")), ratio(t("21"), t("10")), "pct")
    r("실효세율(소득금액 기준)", ratio(t("21"), t("06")), ratio(t("21"), t("06")), "pct")
    return rows


# ------------------------------------------------------------------ IV 이월결손금 (D-024)
def _section4(rp: Report) -> dict:
    cur, prev = rp.cur, rp.prev
    rows, notes = [], []
    for r in cur.losses:
        rows.append({"year": r["year"], "occur": r["발생액"], "prior": r["기공제액"], "decrease": r["당기공제액"],
                     "dec_total": r["감소계"], "balance": r["잔액"], "src": r["src"]})
        _eq(rp.ev, f"결손금 {r['year']} 발생 = 감소계 + 잔액", r["발생액"], r["감소계"] + r["잔액"],
            f"{r['발생액']:,} = {r['감소계']:,} + {r['잔액']:,}")
    if rows:
        _eq(rp.ev, "당기 결손금 공제 합계 = 별지3 ②07", sum(r["decrease"] for r in rows), g(cur.tax, "07"),
            f"{sum(r['decrease'] for r in rows):,} / {g(cur.tax,'07'):,}")
    # 발생액 vs 그 해 세무상 결손금 (FR-4.7)
    for row in rows:
        if row["year"][:4] == str(prev.year):
            tax_loss = -g(prev.tax, "06") if g(prev.tax, "06") < 0 else 0
            ok = _eq(rp.ev, "결손금 발생액 = 전기 각사업연도 결손금", row["occur"], tax_loss,
                     f"자본금과적립금조정명세서(갑) {row['occur']:,} / {prev.year} 세액조정계산서 ⑥ {tax_loss:,}")
            if ok is False:
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
    """공제·감면세액: 합계표(갑)와 세액감면신청서 중 별지3 ⑰+⑲와 합계가 맞는 쪽을 쓴다 (4차)."""
    cur = rp.cur
    form_total = g(cur.tax, "17") + g(cur.tax, "19")
    cands = [("세액감면신청서", cur.reductions), ("공제감면세액합계표(갑)", cur.reductions_sum)]
    chosen = next((rows for _, rows in cands if rows and sum(v.value for v in rows) == form_total), None)
    if chosen is None:
        chosen = max((rows for _, rows in cands), key=lambda r: sum(v.value for v in r))
    if chosen is not cur.reductions:
        cur.reductions = chosen
    total = sum(v.value for v in cur.reductions)
    _eq(rp.ev, "공제감면 합계 = 별지3 ⑰+⑲", total, form_total, f"신청서 {total:,} / 별지3 {form_total:,}")
    return {"rows": cur.reductions, "total": total, "form_total": form_total}


# ------------------------------------------------------------------ VIII 재무제표 주요 특이사항 (D-026)
def _section8(rp: Report) -> list[dict]:
    from .fmt import pct, won

    prev, cur, rules = rp.prev, rp.cur, rp.rules
    py, cy = prev.year, cur.year
    sales_p, sales_c = g(prev.pl, 1), g(cur.pl, 1)
    items = []
    # ① 가지급금·가수금 (거래처코드별)
    for title, acc in [("가지급금명세서", "가지급금"), ("가지급금(인정이자명세서)", "가지급금"),
                       ("주임종단기채권명세서", "주임종단기채권"), ("가수금명세서", "가수금")]:
        key = lambda r: r.partner_code if r.partner_code != "-" else r.partner
        pr = {key(r): r for r in prev.ledgers.get(title, [])}
        cr = {key(r): r for r in cur.ledgers.get(title, [])}
        if not pr and not cr:
            continue
        lines = []
        for code in sorted(set(pr) | set(cr)):
            p, c = pr.get(code), cr.get(code)
            pb = p.balance if p else (c.opening if c and c.opening is not None else 0)
            cb = c.balance if c else 0
            name = (c or p).partner
            detail = f" (당기 증가 {c.increase:,}원, 감소 {c.decrease:,}원)" if c and c.increase is not None and c.decrease is not None else ""
            ch = cb - pb
            word = "확인 필요" if is_na(ch) else ("감소" if ch < 0 else "증가")
            who = f"거래처코드 {code} {name}" if code.isdigit() else f"{name} (거래처코드 없음 · 인정이자 조정명세서 기준)"
            lines.append(f"{who}: {py}년 말 {won(pb)}원 → {cy}년 말 {won(cb)}원, {word} "
                         f"{won(abs(ch)) if not is_na(ch) else ''}{'원' if not is_na(ch) else ''}{detail}. "
                         f"{cy}년 말 잔액은 매출액의 {pct(_pct(cb, sales_c))}입니다.")
        page = cur.ledgers[title][0].page if cur.ledgers.get(title) else None
        src_name = "가지급금 등의 인정이자 조정명세서(을)" if "인정이자" in title else f"결산부속명세서 {title}"
        items.append({"title": f"{acc} 현황", "lines": lines, "src": f"{src_name} ({cur.doc.name} p{page})"})
    if not any(prev.ledgers.get(t) or cur.ledgers.get(t) for t in ("가지급금명세서", "가지급금(인정이자명세서)", "주임종단기채권명세서")):
        items.append({"title": "가지급금 현황", "lines": ["전기·당기 모두 결산부속명세서에 가지급금 명세가 없습니다."],
                      "src": "결산부속명세서"})
    # 대표자·임원 차입금 (가수금 성격) — 표준재무상태표 236(단기)·292(장기)
    for code, nm in [(236, "주주·임원·직원 단기차입금"), (292, "주주·임원·직원 장기차입금")]:
        a, b = g(prev.bs, code), g(cur.bs, code)
        if (not is_na(a) and a) or (not is_na(b) and b):
            items.append({"title": nm, "lines": [f"{py}년 말 {won(a)}원 → {cy}년 말 {won(b)}원 ({won(b - a) if not is_na(b - a) else '확인 필요'}원 변동), "
                                                 f"{cy}년 말 매출액 대비 {pct(_pct(b, sales_c))}."],
                          "src": f"표준재무상태표 코드 {code}"})
    # ② 인건비 = 직원급여 + 임원급여
    pe, pw, ce, cw = g(prev.pl, 69), g(prev.pl, 70), g(cur.pl, 69), g(cur.pl, 70)
    ch = change(pe + pw, ce + cw)
    rate = f", {pct(ch['rate'], 1, sign=True)}" if ch["rate"] is not None else (f", {ch['label']}" if ch["label"] else "")
    items.append({"title": "인건비 (직원급여 + 임원급여)", "lines": [
        f"직원급여 {won(pw)}원 → {won(cw)}원, 임원급여 {won(pe)}원 → {won(ce)}원.",
        f"인건비 합계 {won(pe + pw)}원 → {won(ce + cw)}원 ({won(ch['diff']) if is_na(ch['diff']) else format(ch['diff'], '+,')}원{rate}), "
        f"매출액 대비 {pct(_pct(pe + pw, sales_p))} → {pct(_pct(ce + cw, sales_c))}."],
        "src": "표준손익계산서 코드 69(임원급여)·70(직원급여)"})
    # ③ 부채비율 변화
    dp, dc = debt_ratio(prev.bs), debt_ratio(cur.bs)

    def dtxt(d, bs):
        if d["label"] == "확인 필요":
            return "확인 필요"
        return f"자본잠식 (자본총계 {g(bs,382):,}원)" if d["impaired"] else pct(d["value"])

    lines = [f"부채비율 {py}년 {dtxt(dp, prev.bs)} → {cy}년 {dtxt(dc, cur.bs)}."]
    if dp["label"] == "확인 필요" or dc["label"] == "확인 필요":
        lines.append("부채총계 또는 자본총계에 확인 필요 값이 있어 변화 분석을 보류합니다.")
    elif dp["impaired"] and not dc["impaired"]:
        lines.append(f"당기순이익 {g(cur.pl,219):,}원으로 자본총계가 {g(cur.bs,382):,}원이 되어 자본잠식이 해소되었습니다.")
        cap, need = g(prev.bs, 334), g(prev.bs, 334) - g(prev.bs, 382)
        ga = sum(r.balance for r in prev.ledgers.get("가수금명세서", []))
        if ga:
            lines.append(f"참고: {py}년 말 기준으로 자본금({cap:,}원)까지 회복하려면 {need:,}원이 필요했으며, 당시 대표자 가수금은 {ga:,}원이었습니다.")
    elif dc["impaired"]:
        cap = g(cur.bs, 334)
        lines.append(f"자본잠식 상태입니다. 자본금({cap:,}원)까지 회복하려면 {cap - g(cur.bs,382):,}원의 자본 확충(가수금 출자전환 등)이 필요합니다.")
    else:
        lines.append(f"부채비율이 {dc['value'] - dp['value']:+,.2f}%p 변동했습니다 (부채총계 {g(prev.bs,333):,}원 → {g(cur.bs,333):,}원, "
                     f"자본총계 {g(prev.bs,382):,}원 → {g(cur.bs,382):,}원).")
    items.append({"title": "부채비율 변화", "lines": lines, "src": "표준재무상태표 코드 333·382"})
    # ④ 전기 대비 5% 이상 증가한 비용 (D-027)
    th = rules["expense_increase_pct"]
    sga = rp.sections["II"]["sga_all"]
    inc = sorted([x for x in sga if x["rate"] is not None and x["rate"] >= th], key=lambda x: -x["rate"])
    pend = [x for x in sga if x["label"] == "확인 필요"]
    lines = [f"{x['name']}: {x['prev']:,}원 → {x['cur']:,}원 ({x['diff']:+,}원, {x['rate']:+.1f}%)" for x in inc] or ["해당 항목 없음"]
    if pend:
        lines.append("판단 보류(확인 필요 값): " + ", ".join(x["name"] for x in pend))
    items.append({"title": f"전기 대비 {th:g}% 이상 증가한 비용", "lines": lines, "src": "표준손익계산서 판매비와관리비 코드"})
    # ⑤ 없어진 항목 / 새로 생긴 항목
    gone, new = [], []
    for x in sga:
        if is_na(x["prev"]) or is_na(x["cur"]):
            continue
        if x["prev"] and not x["cur"]:
            gone.append(f"{x['name']} ({x['prev']:,}원 → 0원)")
        if not x["prev"] and x["cur"]:
            new.append(f"{x['name']} (0원 → {x['cur']:,}원)")
    for code, name in [(35, "매출원가"), (218, "법인세비용")]:
        a, b = g(prev.pl, code), g(cur.pl, code)
        if is_na(a, b):
            continue
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
        if is_na(a, b) or not nm[:1].isdigit() or "." not in nm[:4]:
            continue
        if a and not b:
            gone.append(f"{nm} ({a:,}원 → 0원)")
        if not a and b:
            new.append(f"{nm} (0원 → {b:,}원)")
    items.append({"title": "없어진 항목 / 새로 생긴 항목", "lines": [
        "없어진 항목: " + (", ".join(gone) if gone else "없음"),
        "새로 생긴 항목: " + (", ".join(new) if new else "없음")], "src": "표준재무상태표 · 표준손익계산서"})
    # 참고: 매출채권 · 매출처
    pr, cr = prev.ledgers.get("외상매출금명세서", []), cur.ledgers.get("외상매출금명세서", [])
    if pr or cr:
        pb, cb = sum(r.balance for r in pr), sum(r.balance for r in cr)
        lines = [f"외상매출금 잔액 {won(pb)}원 → {won(cb)}원, 매출액 대비 {pct(_pct(pb, sales_p))} → {pct(_pct(cb, sales_c))}.",
                 f"명세서 거래처 수 {len(pr)}곳 → {len(cr)}곳."]
        if any(r.masked for r in cr + pr):
            lines.append("거래처별 금액 일부가 회색 처리·빈칸이라 거래처별 잔액 분석은 보류합니다 "
                         f"(재무상태표 외상매출금 {won(g(prev.bs,10))}원 → {won(g(cur.bs,10))}원).")
        items.append({"title": "매출채권 · 매출처", "lines": lines, "src": "결산부속명세서 외상매출금명세서 · 표준재무상태표 코드 10"})
    return items
