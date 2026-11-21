"""조정료청구서 초안 (채점 대상 아님, D-015). 요율표를 받기 전이라 보수 금액은 «확인 필요»."""

from __future__ import annotations

from pathlib import Path

from .analysis import g


def render(rp, out: Path, rules: dict, issuer: str):
    cur = rp.cur
    sales, assets = g(cur.pl, 1), g(cur.bs, 228)
    base = max(sales, assets // 2)
    basis = "매출액" if sales >= assets // 2 else "자산총계 × 1/2"
    fee = rules.get("fee_schedule")
    red = rp.sections["VI"]["rows"]
    lines = [
        f"# 조정료청구서 (초안)", "",
        f"- 발행: {issuer}",
        f"- 청구 대상: {cur.info['법인명'].value} ({cur.info['사업자등록번호'].value})",
        f"- 사업연도: {cur.info['사업연도'].value}", "",
        "## 기본보수 기준 금액",
        f"- 매출액 {sales:,}원 / 자산총계 × 1/2 = {assets // 2:,}원 → 큰 금액 **{base:,}원** ({basis})",
        f"- 기본보수: {'요율표 적용' if fee else '«확인 필요» — 요율표 미수령 (Q-09)'}", "",
        "## 공제·감면 가산",
        *[f"- {v.item} {v.value:,}원 → 가산율 «확인 필요»" for v in red],
        "" if red else "- 해당 없음", "",
        f"- CMS 출금일: {rules.get('cms_date') or '관리자 설정'} / 피드백 요청일: {rules.get('feedback_date') or '관리자 설정'}",
    ]
    out.write_text("\n".join(lines), encoding="utf-8")
