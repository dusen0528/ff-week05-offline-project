"""숫자 표기 규칙 (D-021, D-022)."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal


def won(v) -> str:
    if v is None:
        return "확인 필요"
    return f"{int(v):,}"


def signed(v) -> str:
    if v is None:
        return "-"
    return "0" if int(v) == 0 else f"{int(v):+,}"


def pct(v, digits: int = 2, sign: bool = False) -> str:
    if v is None:
        return "-"
    return f"{v:+.{digits}f}%" if sign else f"{v:.{digits}f}%"


def card_amount(v) -> str:
    """요약 카드 금액: 0.01억 단위 반올림. |값| ≥ 1억 → '1.93억원', 미만 → '4,900만원' (D-021)."""
    if v is None:
        return "확인 필요"
    eok = (Decimal(int(v)) / Decimal(100_000_000)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if abs(eok) >= 1:
        return f"{eok}억원"
    man = int(eok * 10000)
    return f"{man:,}만원"


def change_text(ch: dict, kind: str = "amount") -> str:
    if ch.get("label"):
        return ch["label"]
    if ch.get("rate") is None:
        return "-"
    return pct(ch["rate"], sign=True)
