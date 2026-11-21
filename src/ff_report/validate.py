"""입력값 검증 (2차): 회색 칸·필수 합계 빈칸·서식 간 차이·전기 열 대조를 경고로 남긴다.

규칙 (2차 과제 안내)
- 회색 처리·빈칸인 필수값은 0으로 넣지 않고 «확인 필요»로 둔다. 그 값에 의존하는 계산만 보류한다.
- 서식끼리 숫자가 다르면 같은 범위의 값인지 먼저 본다. 한쪽으로 덮어쓰지 않고 차이를 경고로 남긴다.
- 확인 필요 값을 다른 서식에서 임의로 가져오지 않는다. 다른 서식의 같은 범위 값은 '참고 후보'로만 기록한다.
- 고객이 값을 확인해 주면 config/answers.yaml 에 근거와 함께 넣고 재실행한다.
"""

from __future__ import annotations

import re

from .extract import YearData
from .model import CONFIRMED, NEEDS_CHECK, Evidence, Value

# 필수 합계 코드: 빈칸이면 하위 대분류 합으로 0이 맞는지 본다. 0이 아니면 «확인 필요» (0으로 넣지 않음)
PL_TOTALS = {1: range(2, 35), 67: list(range(68, 129)) + [220], 130: range(131, 179), 179: range(180, 217)}
PL_DERIVED = {66: (1, 35), 129: (66, 67), 217: (129,), 219: (217,)}
BS_TOTALS = {2: range(3, 44), 44: range(45, 67), 67: range(68, 80), 229: range(230, 284), 284: range(285, 333)}
BS_SUMS = {1: (2, 44, 67), 80: (81, 110, 169, 194), 382: (334, 337, 348, 361, 372)}
BS_DERIVED = {228: (1, 80), 333: (229, 284), 383: (228,)}
COGS = {37: 1, 38: 1, 39: -1, 40: -1, 41: -1, 43: 1, 44: 1, 45: -1, 46: -1, 47: -1, 49: 1, 50: 1, 51: -1, 52: -1,
        53: 1, 54: 1, 56: 1, 57: 1, 58: -1, 59: -1, 60: 1, 62: 1, 63: 1, 64: -1, 65: -1}


def _top(v: Value) -> bool:
    """대분류 행인지 (라벨이 '1.급여', '(1)당좌자산'처럼 시작)."""
    lab = v.label.split(" (코드")[0].strip()
    return bool(re.match(r"^(\d+\.|\(\d+\))", lab))


# 표준재무제표 코드 ↔ 결산서 계정명 (같은 범위로 보는 것만)
PL_PAIRS = {1: ["매출액"], 35: ["매출원가"], 66: ["매출총이익", "매출총손익"], 67: ["판매비와관리비"],
            129: ["영업이익", "영업손실", "영업손익"], 130: ["영업외수익"], 179: ["영업외비용"],
            217: ["법인세차감전이익", "법인세차감전손실", "법인세비용차감전"], 218: ["법인세등", "법인세비용"],
            219: ["당기순이익", "당기순손실", "당기순손익"]}
BS_PAIRS = {1: ["유동자산"], 44: ["(2)재고자산", "재고자산"], 80: ["비유동자산"], 228: ["자산총계"],
            229: ["유동부채"], 284: ["비유동부채"], 333: ["부채총계"], 334: ["자본금"],
            372: ["이익잉여금", "결손금"], 382: ["자본총계"], 383: ["부채및자본총계", "부채와자본총계"]}
# 범위가 다를 수 있는 쌍 (분류 차이) — 차이는 '범위 차이'로 기록하고 값은 그대로 둔다
BS_SCOPE = {2: ["(1)당좌자산", "당좌자산"]}


def _mark(ev: Evidence, v: Value, why: str):
    shown = v.value
    if v.status != NEEDS_CHECK:
        v.status = NEEDS_CHECK
        v.note = why
        v.value = None
    ev.warn("필수값 확인 필요", v, why)
    if shown not in (None, 0):  # PDF에 숫자가 보이는 경우 표시값을 남긴다
        ev.warnings[-1]["표시값"] = shown


def _blank_totals(ev: Evidence, y: YearData):
    def val(d, k):
        v = d.get(k)
        if v is None:
            return 0
        return None if v.status == NEEDS_CHECK else (v.value or 0)

    def blank(v):
        return v is not None and v.status != NEEDS_CHECK and v.value == 0 and v.note == "원문 빈칸"

    for d, totals, sums, derived in ((y.pl, PL_TOTALS, {}, PL_DERIVED), (y.bs, BS_TOTALS, BS_SUMS, BS_DERIVED)):
        checks = []
        for code, kids in totals.items():
            ks = [k for k in kids if k in d and _top(d[k])]
            checks.append((code, ks, {k: 1 for k in ks}))
        for code, ks in sums.items():
            checks.append((code, list(ks), {k: 1 for k in ks}))
        if d is y.pl:
            checks.append((35, list(COGS), COGS))
        for code, ks, sign in checks:
            v = d.get(code)
            if not blank(v):
                continue
            parts = [val(d, k) for k in ks]
            if any(p is None for p in parts):
                _mark(ev, v, f"합계 칸이 빈칸이고 하위 코드에 회색 칸이 있음 → 0으로 보지 않음")
                continue
            tot = sum(sign[k] * (val(d, k) or 0) for k in ks)
            if tot != 0:
                _mark(ev, v, f"합계 칸이 빈칸인데 하위 코드 합이 {tot:,}원 → 0으로 보지 않음 (하위 합은 참고만)")
        for code, deps in derived.items():
            v = d.get(code)
            if blank(v) and any(val(d, k) is None or val(d, k) for k in deps):
                _mark(ev, v, f"빈칸이지만 관련 코드({', '.join(map(str, deps))})에 금액이 있음 → 0으로 보지 않음")
        for v in d.values():
            if v.status == NEEDS_CHECK and v.note.startswith("회색"):
                ev.warn("회색 처리 칸", v, "PDF에 금액이 회색으로 가려져 있음 (추출 문제 아님, 칸 안에 글자 없음)")
            elif v.status == NEEDS_CHECK and "적혀 있음" in v.note:
                ev.warn("숫자 아닌 표시", v, v.note)
                ev.warnings[-1]["표시값"] = v.note.split("'")[1]


def _settle_lookup(rows, names, col):
    """결산서 계정 찾기. '영업손실'·'결손금'처럼 손실 표기 계정은 부호를 음수로 맞춘다."""
    for r in rows:
        if any(r["label"] == n or r["label"].startswith(n) for n in names):
            v = r[col]
            if v is not None and v > 0 and ("손실" in r["label"] or "결손" in r["label"]):
                v = -v
            return r, v, r[f"{col}_masked"]
    return None, None, False


def _cross_forms(ev: Evidence, y: YearData):
    """같은 해 PDF 안: 표준재무제표 ↔ 결산서. 다르면 경고, 값은 덮어쓰지 않는다."""
    for d, rows, pairs, scope in ((y.pl, y.settle_pl, PL_PAIRS, {}), (y.bs, y.settle_bs, BS_PAIRS, BS_SCOPE)):
        for code, names in {**pairs, **scope}.items():
            v = d.get(code)
            r, sv, sm = _settle_lookup(rows, names, "cur")
            if v is None or r is None:
                continue
            if v.status == NEEDS_CHECK:
                if sv is not None:
                    ev.warn("다른 서식 참고 후보", v,
                            f"결산서 p{r['page']} '{r['label']}'에 {sv:,}원이 보임. 같은 범위인지 확인 전이라 쓰지 않음")
                continue
            if sv is None:
                continue
            if sv != v.value:
                kind = "범위 차이(분류)" if code in scope else "서식 간 차이"
                ev.warn(kind, v, f"표준 {v.value:,}원 / 결산서 p{r['page']} '{r['label']}' {sv:,}원 "
                                 f"(차이 {sv - v.value:+,}원). 표준 값을 쓰고 차이를 표시함")
                if code not in scope:
                    ev.flags.append({"섹션": "II", "연도": y.year, "코드": code,
                                     "내용": f"{y.year}년 {v.label.split(' (코드')[0]}: 표준재무제표 {v.value:,}원, "
                                             f"결산서 {sv:,}원 (차이 {sv - v.value:+,}원, 원인 확인 중)"})
    # 별지3 결산서상 당기순손익 ↔ 표준 219
    t, p = y.tax.get("01"), y.pl.get(219)
    if t and p and t.status == CONFIRMED and p.status == CONFIRMED and t.value != p.value:
        ev.warn("서식 간 차이", t, f"별지3 ①01 {t.value:,} / 표준손익계산서 219 {p.value:,}")


def _prior_column(ev: Evidence, prev: YearData, cur: YearData):
    """당기 PDF의 전기 열 ↔ 전기 PDF 값."""
    for d, rows, pairs, scope in ((prev.pl, cur.settle_pl, PL_PAIRS, {}), (prev.bs, cur.settle_bs, BS_PAIRS, BS_SCOPE)):
        for code, names in {**pairs, **scope}.items():
            v = d.get(code)
            r, pv, pm = _settle_lookup(rows, names, "prev")
            if v is None or r is None:
                continue
            if v.status == NEEDS_CHECK:
                if pv is not None:
                    ev.warn("다른 서식 참고 후보", v,
                            f"{cur.doc.name} 결산서 p{r['page']} 전기 열 '{r['label']}'에 {pv:,}원이 보임. 쓰지 않음")
                continue
            if pv is not None and pv != v.value:
                kind = "범위 차이(분류)" if code in scope else "전기 열 불일치"
                ev.warn(kind, v, f"{prev.doc.name} 표준 {v.value:,}원 / {cur.doc.name} 결산서 p{r['page']} 전기 열 "
                                 f"{pv:,}원 (차이 {pv - v.value:+,}원)")


def _sanity(ev: Evidence, y: YearData):
    """PDF에 그렇게 적혀 있지만 다른 숫자와 맞지 않는 값."""
    pl = y.pl
    s, c, op = pl.get(1), pl.get(35), pl.get(129)
    if s and c and op and all(x.status == CONFIRMED for x in (s, c, op)) and s.value and s.value == c.value and op.value:
        _mark(ev, c, f"매출원가가 매출액과 같아 매출총이익이 0이 되는데, 영업손익은 {op.value:,}원 — PDF 표시값이 의심됨")


def _ledgers(ev: Evidence, y: YearData):
    for title, rows in y.ledgers.items():
        bad = [r for r in rows if r.masked]
        if bad:
            ev.warn("부속명세서 금액 확인 필요", None,
                    f"{title} {len(bad)}개 거래처의 금액이 비어 있거나 회색 처리됨 (예: {bad[0].partner_code} {bad[0].partner})",
                    file=y.doc.name, year=y.year, form=title, page=bad[0].page, item=title, shown="(빈칸/회색)")


def validate(ev: Evidence, prev: YearData, cur: YearData):
    for y in (prev, cur):
        if y.revenue.status == NEEDS_CHECK:
            ev.warn("필수값 확인 필요", y.revenue, y.revenue.note)
        else:
            s1 = y.pl.get(1)
            if s1 and s1.status == CONFIRMED and s1.value and y.revenue.value != s1.value:
                ev.warn("범위 차이(수입금액)", y.revenue,
                        f"신고서 수입금액 {y.revenue.value:,}원 / 표준손익계산서 매출액 {s1.value:,}원 "
                        f"(차이 {y.revenue.value - s1.value:+,}원). 세법상 수입금액은 매출액과 범위가 다를 수 있어 각각 그대로 씀")
        for v in y.tax.values():
            if v.status == NEEDS_CHECK:
                ev.warn("회색 처리 칸", v, v.note)
        _blank_totals(ev, y)
        _sanity(ev, y)
        _cross_forms(ev, y)
        _ledgers(ev, y)
    _prior_column(ev, prev, cur)


def apply_answers(ev: Evidence, years: dict[int, YearData], answers: dict | None):
    """고객이 확인해 준 값 (config/answers.yaml). 근거 문구가 없으면 적용하지 않는다."""
    for item in (answers or {}).get("overrides", []) or []:
        y = years.get(int(item["year"]))
        if not y or not item.get("source"):
            continue
        form = item["form"]
        d = {"표준손익계산서": y.pl, "표준재무상태표": y.bs}.get(form)
        if d is not None:
            v = d.get(int(item["code"]))
            if v is None:
                v = d[int(item["code"])] = Value(item.get("label", ""), y.year, None, form=form)
        elif form == "수입금액":
            v = y.revenue
        else:
            continue
        old = v.value
        v.value, v.status = int(item["value"]), CONFIRMED
        v.note = f"고객 확인값 ({item['source']})"
        ev.warn("고객 확인값 적용", v, f"PDF 표시값 {old if old is not None else '(회색/빈칸)'} → {v.value:,}원. 근거: {item['source']}")
