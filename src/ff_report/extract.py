"""세무조정계산서 PDF에서 값 추출. 모든 값은 Value(근거 포함)로 돌려준다."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .model import CONFIRMED, NA, NEEDS_CHECK, Value, missing
from .pdfdoc import Page, PdfDoc, nospace, to_int

AMT = r"-?\(?[\d,]+\)?"


# ---------------------------------------------------------------- 기본정보
def basic_info(doc: PdfDoc) -> dict[str, Value]:
    out: dict[str, Value] = {}
    pages = doc.find("신고서")
    if not pages:
        return {"법인명": missing("법인명", 0, "신고서(별지1) 없음")}
    pg = pages[0]
    flat = pg.flat

    def grab(key, pattern, src=flat):
        m = re.search(pattern, src)
        out[key] = Value(key, 0, m.group(1).strip() if m else None, doc.name, "법인세과세표준및세액신고서", pg.no,
                         key, CONFIRMED if m else NEEDS_CHECK, "" if m else "원문에서 찾지 못함", unit="")

    grab("사업자등록번호", r"사업자등록번호(\d{3}-\d{2}-\d{5})")
    grab("법인등록번호", r"법인등록번호(\d{6}-\d{7})")
    grab("법인명", r"법인명(.+?)④")
    grab("대표자명", r"대표자성명(.+?)⑥")
    grab("사업장 소재지", r"소재지(.+?)⑧")
    grab("업태", r"업태(.+?)⑨")
    grab("종목", r"종목(.+?)⑩")
    grab("주업종코드", r"주업종코드(\d+)")
    grab("사업연도", r"사업연도(\d{4}\.\d{2}\.\d{2}~\d{4}\.\d{2}\.\d{2})")
    grab("법인유형", r"법인유형별구분(.+?)코드")
    grab("신고일", r"신고일(\d{4}\.\d{2}\.\d{2})")
    fy = out["사업연도"].value
    if fy:
        s, e = fy.split("~")
        out["시작일자"] = Value("시작일자", 0, s, doc.name, "법인세과세표준및세액신고서", pg.no, "⑪사업연도", unit="")
        out["종료일자"] = Value("종료일자", 0, e, doc.name, "법인세과세표준및세액신고서", pg.no, "⑪사업연도", unit="")
    # 중소기업 여부: 중소기업등기준검토표 제출 여부로 판단 (D-019 메모)
    sme = [p for p in doc.pages if "중소기업등기준검토표" in p.flat]
    out["중소기업여부"] = Value("중소기업여부", 0, "중소기업" if sme else "-", doc.name if sme else "",
                            "중소기업등기준검토표" if sme else "", sme[0].no if sme else None,
                            "기준검토표 제출", unit="")
    # 기수 (표지: 第2期)
    m = re.search(r"第(\d+)期", doc.pages[0].flat)
    out["기수"] = Value("기수", 0, f"제{m.group(1)}기" if m else "-", doc.name, "표지", 1, "第N期", unit="")
    return out


def fiscal_year(info: dict[str, Value]) -> int:
    v = info.get("종료일자")
    return int(v.value[:4]) if v and v.value else 0


# ---------------------------------------------------------------- 표준재무제표 (코드 → 금액)
STD_ROW = re.compile(r"^(?P<label>.*?)\s+(?P<code>\d{1,3})\s+(?P<amt>[:\d\s\-]*?)(?:\s*(?P<txt>[가-힣]+))?$")


def standard_statement(doc: PdfDoc, form: str) -> dict[int, Value]:
    """표준재무상태표/표준손익계산서: 좌우 2단 표를 x좌표로 나눠 '계정 코드 금액'을 읽는다.
    금액 칸이 회색으로 가려져 있으면 0이 아니라 «확인 필요»로 둔다 (2차 규칙 4)."""
    out: dict[int, Value] = {}
    year = 0
    for pg in doc.find(form):
        mid = pg.width / 2
        for row in pg.rows():
            for side, half in ((0, [w for w in row if w["x0"] < mid]), (1, [w for w in row if w["x0"] >= mid])):
                if not half:
                    continue
                text = " ".join(w["text"] for w in half)
                m = STD_ROW.match(text.strip())
                if not m or (":" not in m.group("amt") and m.group("amt").strip()):
                    continue
                if len(nospace(m.group("label")).lstrip(":")) < 2:
                    continue
                code = int(m.group("code"))
                if code in out:  # 같은 코드가 다시 나오면 첫 값 유지
                    continue
                amt = to_int(re.sub(r"^[\s:]+", "", m.group("amt")))
                label = m.group("label").strip().lstrip(": ").strip()
                if m.group("txt"):  # 금액 칸에 '확인중' 같은 글자가 적혀 있음 → 숫자가 아님
                    out[code] = Value(label, year, None, doc.name, form, pg.no, f"{label} (코드 {code})", NEEDS_CHECK,
                                      f"금액 칸에 '{m.group('txt')}'(으)로 적혀 있음 (숫자 아님)")
                    continue
                code_w = next((w for w in half if w["text"] == m.group("code")), half[0])
                x_end = mid if side == 0 else pg.width
                top = min(w["top"] for w in half)
                bottom = max(w["bottom"] for w in half)
                if amt is None and pg.masked(code_w["x1"], x_end, top, bottom):
                    out[code] = Value(label, year, None, doc.name, form, pg.no, f"{label} (코드 {code})",
                                      NEEDS_CHECK, "회색 처리된 칸 (금액 확인 필요, 0 아님)")
                    continue
                out[code] = Value(label, year, amt if amt is not None else 0, doc.name, form, pg.no,
                                  f"{label} (코드 {code})", note="" if amt is not None else "원문 빈칸")
    return out


# ---------------------------------------------------------------- 결산 재무제표 (계정명, 당기/전기)
NUM = re.compile(r"^-?\(?[\d,]+\)?$")


def _clean_label(s: str) -> str:
    s = nospace(s)
    s = re.sub(r"^[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+\.", "", s)
    s = re.sub(r"^<(.+)>$", r"\1", s)
    return s


def settlement_statement(doc: PdfDoc, form: str) -> list[dict]:
    """결산 재무상태표/손익계산서. 단어 좌표로 당기·전기 열을 나눠 읽는다.
    [{'label','cur','prev','page','cur_masked','prev_masked'}] — 값이 없으면 None."""
    rows = []
    for pg in doc.find(form):
        prs = pg.rows()
        cur_h = prev_h = None
        for r in prs[:14]:  # 당기·전기 머리글이 한 줄에 같이 있는 행
            c = next((w for w in r if re.search(r"\(당\)기$", w["text"])), None)
            p_ = next((w for w in r if re.search(r"\(전\)기$", w["text"])), None)
            if c and p_:
                cur_h, prev_h = c, p_
                break
        if cur_h and prev_h:
            bound = ((cur_h["x0"] + cur_h["x1"]) / 2 + (prev_h["x0"] + prev_h["x1"]) / 2) / 2
        else:
            bound = pg.width * 0.70
        for r in prs:
            nums = [w for w in r if NUM.match(w["text"]) and ("," in w["text"] or w["text"] in ("0", "-0"))]
            lab = [w for w in r if w not in nums]
            label = _clean_label("".join(w["text"] for w in lab))
            if not label or label.startswith("제") or "현재" in label or "회사명" in label or label in ("과목", "금액"):
                continue
            if "(당)기" in label or "단위" in label:
                continue
            lx = max((w["x1"] for w in lab), default=0)
            cur = [w for w in nums if (w["x0"] + w["x1"]) / 2 < bound]
            prev = [w for w in nums if (w["x0"] + w["x1"]) / 2 >= bound]
            top = min(w["top"] for w in r)
            bottom = max(w["bottom"] for w in r)
            cm = not cur and pg.masked(lx, bound, top, bottom)
            pm = not prev and pg.masked(bound, pg.width, top, bottom)
            if not nums and not (cm or pm):
                continue
            rows.append({"label": label, "cur": to_int(cur[-1]["text"]) if cur else None,
                         "prev": to_int(prev[-1]["text"]) if prev else None, "page": pg.no,
                         "cur_masked": cm, "prev_masked": pm})
    return rows


def sga_detail(doc: PdfDoc) -> list[dict]:
    """결산 손익계산서의 판매비와관리비 세부 계정."""
    rows = settlement_statement(doc, "결산손익계산서")
    out, inside = [], False
    for r in rows:
        if r["label"].startswith("판매비와관리비"):
            inside = True
            continue
        if inside and (r["label"].startswith("영업이익") or r["label"].startswith("영업손실") or r["label"].startswith("영업손익")):
            break
        if inside:
            out.append(r)
    return out


def settlement_value(doc: PdfDoc, form: str, *labels: str) -> dict | None:
    for r in settlement_statement(doc, form):
        if any(r["label"].startswith(l) for l in labels):
            return r
    return None


# ---------------------------------------------------------------- 별지3 세액조정계산서 (줄 코드 → 금액)
TAX_CODES = {
    "01": "결산서상당기순손익", "02": "익금산입", "03": "손금산입", "04": "차가감소득금액",
    "05": "기부금한도초과액", "54": "기부금한도초과이월액손금산입", "06": "각사업연도소득금액",
    "07": "이월결손금", "08": "비과세소득", "09": "소득공제", "10": "과세표준", "56": "과세표준(+선박)",
    "11": "세율", "12": "산출세액", "16": "산출세액합계", "17": "최저한세적용대상공제감면세액",
    "18": "차감세액", "19": "최저한세적용제외공제감면세액", "20": "가산세액", "21": "가감계",
    "22": "중간예납세액", "23": "수시부과세액", "24": "원천납부세액", "28": "기납부세액합계",
    "30": "차감납부할세액", "46": "차감납부할세액계",
}
TAX_PAIR = re.compile(r"(?<![\d.\-,])(\d{2})\s+(?=(-?[\d,]+)(?![\d.,]))")


def tax_adjustment(doc: PdfDoc, year: int) -> dict[str, Value]:
    out: dict[str, Value] = {}
    pages = doc.find("세액조정계산서")
    if not pages:
        return out
    pg = pages[0]
    for line in pg.lines():
        for code, amt in TAX_PAIR.findall(line):
            if code in TAX_CODES and code not in out:
                v = to_int(amt)
                # 금액은 쉼표가 있어야 한다 (빈칸 뒤 다음 줄 코드를 금액으로 읽지 않기 위해). 세율(11)만 예외.
                if v is None or ("," not in amt and code != "11"):
                    continue
                out[code] = Value(TAX_CODES[code], year, v, doc.name, "법인세과세표준및세액조정계산서(별지3)",
                                  pg.no, f"{TAX_CODES[code]} ({code})")
    for code, name in TAX_CODES.items():  # 빈 칸: 회색 처리면 확인 필요, 아니면 서식상 해당 없음(0)
        if code not in out:
            masked = False
            if pg.masks:
                for w in pg.words:
                    if w["text"] == code and pg.masked(w["x1"], w["x1"] + 130, w["top"], w["bottom"]):
                        masked = True
                        break
            if masked:
                out[code] = Value(name, year, None, doc.name, "법인세과세표준및세액조정계산서(별지3)", pg.no,
                                  f"{name} ({code})", NEEDS_CHECK, "회색 처리된 칸 (금액 확인 필요, 0 아님)")
            else:
                out[code] = Value(name, year, 0, doc.name, "법인세과세표준및세액조정계산서(별지3)", pg.no,
                                  f"{name} ({code})", note="원문 빈칸")
    return out


def revenue(doc: PdfDoc, year: int) -> Value:
    for pg in doc.find("신고서"):
        m = re.search(r"수입금액\(([\d,]+)\)", pg.flat)
        if m:
            return Value("수입금액", year, to_int(m.group(1)), doc.name, "법인세과세표준및세액신고서", pg.no, "수입금액")
        note = "회색 처리된 칸 (금액 확인 필요, 0 아님)" if pg.masks else "수입금액 칸이 비어 있음"
        return Value("수입금액", year, None, doc.name, "법인세과세표준및세액신고서", pg.no, "수입금액",
                     NEEDS_CHECK, note)
    return missing("수입금액", year, "신고서에서 수입금액을 찾지 못함")


def local_tax(doc: PdfDoc, year: int, corp_tax: int) -> Value:
    pages = doc.find("지방소득세조정계산서")
    if pages:
        pg = pages[0]
        m = (re.search(r"신고기간이내납부할세액([\d,]+)", pg.flat)
             or re.search(r"가감계\([-+]*\)([\d,]+)", pg.flat))
        if m:
            return Value("법인지방소득세", year, to_int(m.group(1)), doc.name, "법인지방소득세과세표준및세액조정계산서",
                         pg.no, "가감계(납부할 세액)")
        return missing("법인지방소득세", year, "지방소득세 서식에서 금액을 찾지 못함")
    if corp_tax == 0:
        return Value("법인지방소득세", year, 0, "", "", None, "", note="지방소득세 서식 없음, 법인세 산출세액 0원")
    return missing("법인지방소득세", year, "지방소득세 서식 없음")


# ---------------------------------------------------------------- 결손금 (별지50 갑 Ⅱ)
def loss_carryforward(doc: PdfDoc, year: int) -> list[Value]:
    out = []
    for pg in doc.find("자본금과적립금조정명세서(갑)"):
        for line in pg.lines():
            m = re.match(r"^\s*(\d{4}-\d{2}-\d{2})\s+(.*)$", line)
            if not m:
                continue
            nums = [to_int(x) for x in re.findall(AMT, m.group(2))]
            nums = [n for n in nums if n is not None]
            if nums:
                out.append(Value(f"결손금 발생({m.group(1)})", year, nums[0], doc.name,
                                 "자본금과적립금조정명세서(갑) Ⅱ.결손금", pg.no, f"{m.group(1)} ⑦계"))
    return out


# ---------------------------------------------------------------- 소득금액조정합계표 (별지15)
DISP = r"(기타사외유출|유보|상여|배당|기타소득|기타)"
ADJ = re.compile(r"(?P<name>[가-힣A-Za-z()·.]+(?:\s[가-힣A-Za-z()·.]+)*)\s+(?P<amt>[\d,]{2,})\s+(?P<disp>" + DISP[1:-1] + r")")


def income_adjustments(doc: PdfDoc, year: int) -> dict:
    pages = doc.find("소득금액조정합계표")
    res = {"present": bool(pages), "plus": [], "minus": [], "page": pages[0].no if pages else None}
    if not pages:
        return res
    pg = pages[0]
    lines = pg.lines()
    split = None
    for l in lines:
        i = l.find("손금산입")
        j = l.find("익금산입")
        if i > 0 and j >= 0 and i > j:
            split = i - 4
            break
    for l in lines:
        if "합계" in nospace(l):
            continue
        for m in ADJ.finditer(l):
            name = nospace(m.group("name"))
            if name in {"처분", "코드"}:
                continue
            side = "minus" if split is not None and m.start() >= split else "plus"
            res[side].append(Value(name, year, to_int(m.group("amt")), doc.name, "소득금액조정합계표", pg.no,
                                   f"{name} / {m.group('disp')}", note=m.group("disp")))
    return res


# ---------------------------------------------------------------- 공제·감면 (세액감면신청서)
REDUCE = re.compile(
    r"^\s*(?P<name>\S.*?)\s+(?P<law>(?:舊)?(?:영|법)제\S+)\s+(?P<code>[0-9A-Z]{3})\s+(?P<rate>[\d.]+%)\s+(?P<base>[\d,]+)\s+(?P<amt>[\d,]+)"
)


def reductions(doc: PdfDoc, year: int) -> list[Value]:
    out = []
    for pg in doc.find("세액감면신청서"):
        for line in pg.lines():
            m = REDUCE.match(line)
            if m:
                law = m.group("law")
                law_txt = ("「조세특례제한법 시행령」" if law.startswith("영") else "「조세특례제한법」") + law[1:].replace("제", " 제", 1).strip()
                out.append(Value(nospace(m.group("name")), year, to_int(m.group("amt")), doc.name, "세액감면(면제)신청서",
                                 pg.no, f"코드 {m.group('code')} · 감면율 {m.group('rate')}",
                                 note=law_txt))
    return out


# ---------------------------------------------------------------- 결산 부속명세서 (거래처별)
@dataclass
class LedgerRow:
    account: str
    partner_code: str
    partner: str
    opening: int | None
    increase: int | None
    decrease: int | None
    balance: object  # int 또는 NA(회색 처리·빈칸)
    page: int
    masked: bool = False


def ledger(doc: PdfDoc, title: str) -> list[LedgerRow]:
    """부속명세서 한 종류(예: '가수금명세서')의 거래처별 행. 숫자는 머리글 열 위치(오른쪽 끝)에 맞춰 배정."""
    out: list[LedgerRow] = []
    for pg in doc.find_title(title):
        rows = pg.rows()
        active = False
        cols: list[tuple[str, float]] = []
        for row in rows:
            text = "".join(w["text"] for w in row)
            if text.endswith("명세서"):
                active = text == title
                cols = []
                continue
            if not active:
                continue
            heads = [(w["text"], w["x1"]) for w in row if w["text"] in ("기초액", "당기증가", "당기감소", "금액")]
            if heads:
                cols = heads
                continue
            if text.startswith("합계"):
                active = False
                continue
            codes = [w for w in row if re.fullmatch(r"\d{5}", w["text"])]
            if not codes or not cols:
                continue
            pc = codes[0]
            nums = [w for w in row if to_int(w["text"]) is not None and "," in w["text"]]
            name_words = [w["text"] for w in row if w["x0"] > pc["x1"] and w not in nums]
            vals: dict[str, int] = {}
            for w in nums:
                col = min(cols, key=lambda c: abs(c[1] - w["x1"]))[0]
                vals[col] = to_int(w["text"])
            acc = next((w["text"] for w in row if not re.fullmatch(r"\d+", w["text"])), "")
            name_words = [w for w in name_words if not re.fullmatch(r"\d{3}-\d{2}-\d{5}", w)]
            gold = next((c for c in cols if c[0] == "금액"), None)
            top, bottom = min(w["top"] for w in row), max(w["bottom"] for w in row)
            masked = bool(pg.masks) and pg.masked(pc["x1"], (gold[1] + 5) if gold else pg.width, top, bottom)
            if not nums:
                bal = NA  # 금액이 비어 있거나 회색 처리 → 0으로 보지 않는다
            else:
                bal = vals.get("금액", 0)
            out.append(LedgerRow(acc, pc["text"], " ".join(name_words), vals.get("기초액"), vals.get("당기증가"),
                                 vals.get("당기감소"), bal, pg.no, masked or not nums))
    return out


# ---------------------------------------------------------------- 한 해 묶음
@dataclass
class YearData:
    doc: PdfDoc
    year: int
    info: dict[str, Value]
    bs: dict[int, Value]
    pl: dict[int, Value]
    tax: dict[str, Value]
    revenue: Value
    local_tax: Value
    losses: list[Value]
    adjustments: dict
    reductions: list[Value]
    sga: list[dict]
    ledgers: dict[str, list[LedgerRow]] = field(default_factory=dict)
    settle_bs_prev: dict[str, int] = field(default_factory=dict)  # 결산 재무상태표 전기 열
    settle_pl_prev: dict[str, int] = field(default_factory=dict)
    settle_bs: list[dict] = field(default_factory=list)
    settle_pl: list[dict] = field(default_factory=list)


LEDGERS = ["가수금명세서", "가지급금명세서", "외상매출금명세서", "주임종단기채권명세서"]


def load_year(path) -> YearData:
    doc = PdfDoc(path)
    info = basic_info(doc)
    year = fiscal_year(info)
    for v in info.values():
        v.year = year
    bs = standard_statement(doc, "표준재무상태표")
    pl = standard_statement(doc, "표준손익계산서")
    for d in (bs, pl):
        for v in d.values():
            v.year = year
    tax = tax_adjustment(doc, year)
    yd = YearData(
        doc=doc, year=year, info=info, bs=bs, pl=pl, tax=tax,
        revenue=revenue(doc, year),
        local_tax=local_tax(doc, year, tax.get("12").value if tax.get("12") else 0),
        losses=loss_carryforward(doc, year),
        adjustments=income_adjustments(doc, year),
        reductions=reductions(doc, year),
        sga=sga_detail(doc),
    )
    yd.ledgers = {t: ledger(doc, t) for t in LEDGERS}
    yd.settle_bs = settlement_statement(doc, "결산재무상태표")
    yd.settle_pl = settlement_statement(doc, "결산손익계산서")
    for r in yd.settle_bs:
        if r["prev"] is not None:
            yd.settle_bs_prev.setdefault(r["label"], r["prev"])
    for r in yd.settle_pl:
        if r["prev"] is not None:
            yd.settle_pl_prev.setdefault(r["label"], r["prev"])
    return yd
