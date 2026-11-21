"""VII. 요약 코멘트 (요구사항 #3). 숫자는 추출·계산값만 쓴다."""

from __future__ import annotations

from .fmt import card_amount, pct


def build_comments(rp) -> list[dict]:
    from .analysis import change, debt_ratio, g

    prev, cur = rp.prev, rp.cur
    py, cy = prev.year, cur.year
    p, c = prev.pl, cur.pl
    S = rp.sections
    out = []

    # 1. 매출 및 수익성
    rev = change(g(p, 1), g(c, 1))
    op = change(g(p, 129), g(c, 129))
    ni = change(g(p, 219), g(c, 219))
    t = [f"{cy}년 매출액은 {card_amount(g(c,1))}으로 전년({card_amount(g(p,1))}) 대비 "
         f"{card_amount(abs(rev['diff']))} {'증가' if rev['diff'] >= 0 else '감소'}"
         + (f"({pct(rev['rate'], sign=True)})" if rev["rate"] is not None else "") + "하였습니다."]
    def phr(name, ch, prv, cr):
        if ch["label"] == "흑자전환":
            return f"{name}은 전년 {card_amount(prv)}에서 {card_amount(cr)}으로 흑자전환하였습니다."
        if ch["label"] == "적자전환":
            return f"{name}은 전년 {card_amount(prv)}에서 {card_amount(cr)}으로 적자전환하였습니다."
        return f"{name}은 {card_amount(cr)}으로 전년 대비 {card_amount(abs(ch['diff']))} {'증가' if ch['diff'] >= 0 else '감소'}하였습니다."
    t.append(phr("영업이익", op, g(p, 129), g(c, 129)) + f" 영업이익률은 {pct(g(c,129)/g(c,1)*100)}입니다.")
    t.append(phr("당기순이익", ni, g(p, 219), g(c, 219)))
    out.append({"title": "1. 매출 및 수익성 요약", "text": " ".join(t)})

    # 2. 판관비 주요 항목
    sga = S["II"]["sga_all"]
    top = S["II"]["sga_top"]
    tot = change(g(p, 67), g(c, 67))
    t = [f"판매비와관리비는 {g(c,67):,}원으로 전년 대비 {tot['diff']:+,}원"
         + (f"({pct(tot['rate'], sign=True)})" if tot["rate"] is not None else "")
         + f" 변동했고, 매출액 대비 비율은 {pct(g(p,67)/g(p,1)*100)}에서 {pct(g(c,67)/g(c,1)*100)}로 바뀌었습니다."]
    t.append("주요 항목은 " + ", ".join(f"{s['name']}({pct(s['comp_cur'])})" for s in top) + " 순으로, 판관비의 "
             f"{pct(sum(s['comp_cur'] for s in top))}를 차지합니다.")
    ups = sorted([s for s in sga if s["diff"] and s["diff"] > 0], key=lambda s: -s["diff"])[:3]
    downs = sorted([s for s in sga if s["diff"] and s["diff"] < 0], key=lambda s: s["diff"])[:2]
    if ups:
        t.append("크게 늘어난 항목은 " + ", ".join(f"{s['name']}({s['diff']:+,}원)" for s in ups) + "입니다.")
    if downs:
        t.append("줄어든 항목은 " + ", ".join(f"{s['name']}({s['diff']:+,}원)" for s in downs) + "입니다.")
    out.append({"title": "2. 판관비 주요 항목", "text": " ".join(t)})

    # 3. 영업외손익
    det = [(v.label.split(" (코드")[0], v.value) for code, v in sorted(c.items()) if 131 <= code <= 174 and v.value]
    det_e = [(v.label.split(" (코드")[0], v.value) for code, v in sorted(c.items()) if 180 <= code <= 216 and v.value]
    t = [f"영업외수익은 {g(c,130):,}원" + (f"({', '.join(f'{n} {a:,}원' for n, a in det)})" if det else "")
         + f", 영업외비용은 {g(c,179):,}원" + (f"({', '.join(f'{n} {a:,}원' for n, a in det_e)})" if det_e else "")
         + f"으로 영업외손익은 {g(c,130)-g(c,179):+,}원입니다."]
    keys = {"유가증권처분이익": range(134, 138), "외환차익": [140], "외화환산이익": [141]}
    none = [k for k, codes in keys.items() if not any(g(c, x) for x in codes)]
    if none:
        t.append(f"{'·'.join(none)} 등 투자·외환 관련 영업외수익은 발생하지 않았습니다.")
    out.append({"title": "3. 영업외손익 발생 사유", "text": " ".join(t)})

    # 4. 전년 대비 주요 변동 + 부채비율 + 공제감면
    dp, dc = debt_ratio(prev.bs), debt_ratio(cur.bs)
    t = []
    if dp["impaired"] and not dc["impaired"]:
        t.append(f"부채비율은 {py}년 자본잠식에서 {cy}년 {pct(dc['value'])}로 개선되어 자본잠식이 해소되었습니다.")
    elif dc["impaired"]:
        t.append(f"{cy}년 말 자본총계가 {g(cur.bs,382):,}원으로 자본잠식 상태입니다.")
    else:
        t.append(f"부채비율은 {pct(dp['value'])}에서 {pct(dc['value'])}로 변동했습니다.")
    t.append(f"자산총계는 {g(prev.bs,228):,}원에서 {g(cur.bs,228):,}원으로, 부채총계는 {g(prev.bs,333):,}원에서 "
             f"{g(cur.bs,333):,}원으로 변동했습니다.")
    red = S["VI"]["rows"]
    if red:
        t.append("공제·감면은 " + ", ".join(f"{v.item.replace('에대한', '에 대한 ')} {v.value:,}원" for v in red)
                 + "이 반영되었습니다.")
    else:
        t.append("반영된 공제·감면세액은 없습니다.")
    if g(cur.tax, "07"):
        t.append(f"이월결손금 {g(cur.tax,'07'):,}원을 공제하여 과세표준은 {g(cur.tax,'10'):,}원, "
                 f"차감납부할 법인세는 {(g(cur.tax,'46') or g(cur.tax,'30')):,}원입니다.")
    out.append({"title": "4. 전년 대비 주요 변동사항", "text": " ".join(t)})
    return out
