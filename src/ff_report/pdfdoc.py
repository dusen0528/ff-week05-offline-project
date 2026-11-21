"""PDF 읽기: 페이지별 레이아웃 텍스트와 단어 좌표, 서식(form) 찾기."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

import pdfplumber

# 서식 이름 → 페이지 판별 규칙 (공백 제거한 텍스트 기준).
# 페이지 번호가 아니라 서식 제목으로 찾는다 (NFR-2).
FORMS: dict[str, dict] = {
    "신고서": {"any": ["법인세과세표준및세액신고서", "re:별지제1호서식[\\]】)]"], "not": ["지방소득세", "지방세법", "조세특례제한법"]},
    "세액조정계산서": {"any": ["법인세과세표준및세액조정계산서", "re:별지제3호서식[\\]】)]"], "not": ["지방소득세", "지방세법"]},
    "수입금액조정명세서": {"any": ["수입금액조정명세서"], "not": ["조정후"]},
    "표준재무상태표": {"any": ["표준재무상태표"], "not": ["합계표준재무상태표"]},
    "표준손익계산서": {"any": ["표준손익계산서"], "not": []},
    "자본금과적립금조정명세서(갑)": {"any": ["자본금과적립금조정명세서(갑)", "re:별지제50호서식\\(갑\\)"], "not": []},
    "소득금액조정합계표": {"any": ["소득금액조정합계표", "re:별지제15호서식[\\]】)]"], "not": ["과목별", "부표"]},
    "세액감면신청서": {"any": ["세액감면(면제)신청서"], "not": []},
    "공제감면세액계산서": {"any": ["공제감면세액계산서"], "not": []},
    "최저한세조정계산서": {"any": ["최저한세조정계산서", "re:별지제4호서식[\\]】)(]"], "not": ["지방세법"]},
    "세액공제조정명세서(3)": {"any": ["세액공제조정명세서(3)"], "not": []},
    "지방소득세조정계산서": {"any": ["법인지방소득세과세표준및세액조정계산서"], "not": []},
    "결산재무상태표": {"head": "재무상태표", "not": ["표준", "합계"]},
    "결산손익계산서": {"head": "손익계산서", "not": ["표준"]},
}


def nospace(s: str) -> str:
    return re.sub(r"\s+", "", s)


def to_int(s: str | None) -> int | None:
    """'1,234' / '-15:510:353' / '(1,234)' → int. 빈 값이면 None."""
    if s is None:
        return None
    t = s.strip().replace(" ", "")
    neg = t.startswith("(") and t.endswith(")")
    t = t.strip("()").replace(",", "").replace(":", "")
    if not t or t in {"-", "."}:
        return None
    if not re.fullmatch(r"-?\d+", t):
        return None
    v = int(t)
    return -v if neg else v


@dataclass
class Page:
    no: int
    text: str  # layout text
    _plumber_page: object = field(repr=False)

    @cached_property
    def flat(self) -> str:
        return nospace(self.text)

    @cached_property
    def head(self) -> str:
        """맨 앞 6줄(공백 제거). 결산서 제목 판별용."""
        lines = [l for l in self.text.splitlines() if l.strip() and "실습용" not in l and "회색" not in l][:6]
        return nospace("".join(lines))

    @cached_property
    def has_mask_notice(self) -> bool:
        """'회색 처리 금액은 확인 필요' 안내가 있는 페이지."""
        return "회색처리금액은확인필요" in self.flat or "회색처리" in nospace(self._plumber_page.extract_text() or "")

    @cached_property
    def masks(self) -> list[dict]:
        """회색으로 가린 금액 칸 (안내문이 있는 페이지만). 칸 안에 글자가 없는 회색(≈0.90) 도형."""
        if not self.has_mask_notice:
            return []
        p = self._plumber_page
        out = []
        for s in list(p.curves) + list(p.rects):
            c = s.get("non_stroking_color")
            if not s.get("fill") or not isinstance(c, (tuple, list)) or not c:
                continue
            if not all(abs(float(x) - 0.90) < 0.02 for x in c) or s["width"] > 300:
                continue
            inside = [w for w in self.words if w["x0"] >= s["x0"] - 1 and w["x1"] <= s["x1"] + 1
                      and w["top"] >= s["top"] - 1 and w["bottom"] <= s["bottom"] + 1]
            if not inside:
                out.append({"x0": s["x0"], "x1": s["x1"], "top": s["top"], "bottom": s["bottom"]})
        return out

    def masked(self, x0: float, x1: float, top: float, bottom: float) -> bool:
        cy = (top + bottom) / 2
        return any(m["x0"] < x1 and m["x1"] > x0 and m["top"] - 2 <= cy <= m["bottom"] + 2 for m in self.masks)

    @cached_property
    def words(self) -> list[dict]:
        # x_tolerance를 좁혀 '150,934,713II.비유동자산'처럼 붙은 두 칸을 나눈다 (3차 서식)
        return self._plumber_page.extract_words(keep_blank_chars=False, x_tolerance=1.5)

    @property
    def width(self) -> float:
        return float(self._plumber_page.width)

    def lines(self) -> list[str]:
        return [l.rstrip() for l in self.text.splitlines() if l.strip()]

    def rows(self, tol: float = 2.5) -> list[list[dict]]:
        """단어를 줄(top 좌표) 단위로 묶는다."""
        rows: list[list[dict]] = []
        for w in sorted(self.words, key=lambda w: (round(w["top"]), w["x0"])):
            if rows and abs(rows[-1][0]["top"] - w["top"]) <= tol:
                rows[-1].append(w)
            else:
                rows.append([w])
        return [sorted(r, key=lambda w: w["x0"]) for r in rows]


class PdfDoc:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._pdf = pdfplumber.open(self.path)
        self.pages: list[Page] = []
        for i, p in enumerate(self._pdf.pages, start=1):
            txt = p.extract_text(layout=True) or ""
            self.pages.append(Page(i, txt, p))

    @property
    def name(self) -> str:
        return self.path.name

    def find(self, form: str) -> list[Page]:
        rule = FORMS[form]
        out = []
        for pg in self.pages:
            if "head" in rule:
                hit = rule["head"] in pg.head and not any(n in pg.head for n in rule["not"])
                # 결산서 제목은 '재 무 상 태 표'처럼 띄어 써 있고 첫 줄에 온다
                hit = hit and pg.head.find(rule["head"]) < 15
            else:
                head = pg.flat[:400]  # 서식 번호는 머리에 있다
                hit = (any((re.search(a[3:], head) if a.startswith("re:") else a in pg.flat) for a in rule["any"])
                       and not any(n in head for n in rule["not"]) and "목차" not in pg.flat[:40])
            if hit:
                out.append(pg)
        return out

    def find_title(self, title: str) -> list[Page]:
        """부속명세서처럼 한 페이지에 여러 표가 있을 때, 제목이 들어 있는 페이지."""
        return [pg for pg in self.pages if title in pg.flat]

    def close(self):
        self._pdf.close()
