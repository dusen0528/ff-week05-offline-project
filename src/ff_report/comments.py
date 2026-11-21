"""VII. 요약 코멘트 (요구사항 #3). 숫자는 추출·계산값만 쓰고, 확인 필요 값이 들어가는 문장은 보류로 바꾼다."""

from __future__ import annotations

from .fmt import card_amount, pct
from .model import is_na

HOLD = "확인 필요 값({})이 있어 이 부분의 분석은 자료 확인 후 작성합니다."


def build_comments(rp) -> list[dict]:
    from .analysis import _pct, change, debt_ratio, g

    prev, cur = rp.prev, rp.cur
    py, cy = prev.year, cur.year
    p, c = prev.pl, cur.pl
    S = rp.sections
    out = []

    def amt_move(name, ch, prv, cr):
        if ch["label"] == "확인 필요":
            return HOLD.format(name)
        if ch["label"] in ("흑자전환", "적자전환"):
            return f"{name}은 전년 {card_amount(prv)}에서 {card_amount(cr)}으로 {ch['label']}하였습니다."
        if ch["label"] == "적자지속":
            return f"{name}은 {card_amount(cr)}으로 적자가 이어졌습니다(전년 {card_amount(prv)})."
        rate = f"({pct(ch['rate'], sign=True)})" if ch["rate"] is not None else ""
        return (f"{name}은 {card_amount(cr)}으로 전년({card_amount(prv)}) 대비 {card_amount(abs(ch['diff']))} "
                f"{'증가' if ch['diff'] >= 0 else '감소'}{rate}하였습니다.")

    # 1. 매출 및 수익성
    t = [amt_move(f"{cy}년 매출액", change(g(p, 1), g(c, 1)), g(p, 1), g(c, 1)),
         amt_move("영업이익", change(g(p, 129), g(c, 129)), g(p, 129), g(c, 129))]
    om = _pct(g(c, 129), g(c, 1))
    t.append(f"영업이익률은 {pct(om)}입니다." if not is_na(om) and om is not None else HOLD.format("매출액"))
    t.append(amt_move("당기순이익", change(g(p, 219), g(c, 219)), g(p, 219), g(c, 219)))
    out.append({"title": "1. 매출 및 수익성 요약", "text": " ".join(dict.fromkeys(t))})

    # 2. 판관비 주요 항목
    II = S["II"]
    sga, top = II["sga_all"], II["sga_top"]
    tot = change(g(p, 67), g(c, 67))
    t = []
    if tot["label"] == "확인 필요":
        t.append(HOLD.format("판매비와관리비 합계"))
    else:
        t.append(f"판매비와관리비는 {g(c,67):,}원으로 전년 대비 {tot['diff']:+,}원"
                 + (f"({pct(tot['rate'], sign=True)})" if tot["rate"] is not None else "") + " 변동했습니다.")
        ra, rb = _pct(g(p, 67), g(p, 1)), _pct(g(c, 67), g(c, 1))
        if not is_na(ra, rb) and ra is not None and rb is not None:
            t.append(f"매출액 대비 판관비 비율은 {pct(ra)}에서 {pct(rb)}로 바뀌었습니다.")
    if top and not any(is_na(s["comp_cur"]) or s["comp_cur"] is None for s in top):
        t.append("주요 항목은 " + ", ".join(f"{s['name']}({pct(s['comp_cur'])})" for s in top) + " 순입니다.")
    elif top:
        t.append("주요 항목(당기 금액 순): " + ", ".join(f"{s['name']} {s['cur']:,}원" for s in top) + ".")
    ok = [s for s in sga if not is_na(s["diff"]) and s["diff"]]
    ups = sorted([s for s in ok if s["diff"] > 0], key=lambda s: -s["diff"])[:3]
    downs = sorted([s for s in ok if s["diff"] < 0], key=lambda s: s["diff"])[:2]
    if ups:
        t.append("크게 늘어난 항목은 " + ", ".join(f"{s['name']}({s['diff']:+,}원)" for s in ups) + "입니다.")
    if downs:
        t.append("줄어든 항목은 " + ", ".join(f"{s['name']}({s['diff']:+,}원)" for s in downs) + "입니다.")
    pend = [s["name"] for s in sga if is_na(s["diff"])]
    if pend:
        t.append(HOLD.format(", ".join(pend)))
    out.append({"title": "2. 판관비 주요 항목", "text": " ".join(t)})

    # 3. 영업외손익
    def det(lo, hi):
        return [(v.label.split(" (코드")[0], g(c, code)) for code, v in sorted(c.items())
                if lo <= code <= hi and not is_na(g(c, code)) and g(c, code)]
    if is_na(g(c, 130), g(c, 179)):
        t = [HOLD.format("영업외수익·비용")]
    else:
        d1, d2 = det(131, 174), det(180, 216)
        t = [f"영업외수익은 {g(c,130):,}원" + (f"({', '.join(f'{n} {a:,}원' for n, a in d1)})" if d1 else "")
             + f", 영업외비용은 {g(c,179):,}원" + (f"({', '.join(f'{n} {a:,}원' for n, a in d2)})" if d2 else "")
             + f"으로 영업외손익은 {g(c,130)-g(c,179):+,}원입니다."]
        keys = {"유가증권처분이익": range(134, 138), "외환차익": [140], "외화환산이익": [141]}
        none = [k for k, codes in keys.items() if not any(g(c, x) for x in codes)]
        if none:
            t.append(f"{'·'.join(none)}은 발생하지 않았습니다.")
    out.append({"title": "3. 영업외손익 발생 사유", "text": " ".join(t)})

    # 4. 전년 대비 주요 변동 + 부채비율 + 공제감면
    dp, dc = debt_ratio(prev.bs), debt_ratio(cur.bs)
    t = []
    if "확인 필요" in (dp["label"], dc["label"]):
        t.append(HOLD.format("부채비율"))
    elif dp["impaired"] and not dc["impaired"]:
        t.append(f"부채비율은 {py}년 자본잠식에서 {cy}년 {pct(dc['value'])}로 개선되어 자본잠식이 해소되었습니다.")
    elif dc["impaired"]:
        t.append(f"{cy}년 말 자본총계가 {g(cur.bs,382):,}원으로 자본잠식 상태입니다.")
    else:
        t.append(f"부채비율은 {pct(dp['value'])}에서 {pct(dc['value'])}로 변동했습니다.")
    if not is_na(g(prev.bs, 228), g(cur.bs, 228), g(prev.bs, 333), g(cur.bs, 333)):
        t.append(f"자산총계는 {g(prev.bs,228):,}원에서 {g(cur.bs,228):,}원으로, 부채총계는 {g(prev.bs,333):,}원에서 "
                 f"{g(cur.bs,333):,}원으로 변동했습니다.")
    red = S["VI"]["rows"]
    if red:
        t.append("공제·감면은 " + ", ".join(f"{v.item.replace('에대한', '에 대한 ')} {v.value:,}원" for v in red) + "이 반영되었습니다.")
    else:
        t.append("반영된 공제·감면세액은 없습니다.")
    if g(cur.tax, "07"):
        t.append(f"이월결손금 {g(cur.tax,'07'):,}원을 공제하여 과세표준은 {g(cur.tax,'10'):,}원입니다.")
    t.append(f"차감납부할 법인세는 {(g(cur.tax,'46') or g(cur.tax,'30')):,}원입니다.")
    out.append({"title": "4. 전년 대비 주요 변동사항", "text": " ".join(t)})
    return out
