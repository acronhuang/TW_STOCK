"""
止損觸發後檢查清單 + 投組 VaR
================================
解決「執行面」兩大障礙(非選股，是減壓/紀律)：
  • 僥倖心態：止損觸發時，系統常以「主力建倉中→暫抱」放行 → 變成凹單藉口。
    本清單把該藉口攤開，用客觀籌碼/型態/乖離數據「替使用者回答」是離場還是洗盤，
    四維皆❌時直接判「已無凹單理由」，壓縮自我合理化空間。
  • 心理帳戶混淆：帳戶類型(波段/存股/債券)分流，硬性止損只套用「波段」。

四維檢查(每項用現成資料自動填答)：
  ①邏輯：當初買入訊號(型態轉強/均線)是否還在
  ②籌碼：主力真離場 還是 洗盤(外資連賣+破MA60=離場；建倉+守MA=可能洗盤)
  ③情境：現價若是現金還會不會買進(乖離過大+型態破壞→不會)
  ④執行：一次出場 或 分段限價(依流動性)

VaR：此倉佔淨值%、未實現損益佔淨值%、後續1日95%風險(參數法)。
"""
from typing import Dict, List, Optional


def _f(v):
    try:
        return float(v.to_decimal()) if hasattr(v, 'to_decimal') else float(v)
    except (TypeError, ValueError, AttributeError):
        return None


def _factor(db, symbol, field):
    rec = db.stock_factors.find_one({'symbol': symbol, field: {'$ne': None}},
                                    {field: 1}, sort=[('date', -1)])
    return _f(rec.get(field)) if rec else None


def _daily_vol(db, symbol, days=30) -> Optional[float]:
    """近 days 日簡單報酬標準差(日波動)。"""
    closes = [_f(p.get('close')) for p in db.stock_price.find(
        {'symbol': symbol}, {'close': 1}).sort('date', -1).limit(days + 1)]
    closes = [c for c in closes if c]
    if len(closes) < 10:
        return None
    closes = closes[::-1]
    rets = [(closes[i] / closes[i - 1] - 1) for i in range(1, len(closes))]
    m = sum(rets) / len(rets)
    var = sum((r - m) ** 2 for r in rets) / (len(rets) - 1)
    return var ** 0.5


def portfolio_snapshot(db) -> Dict:
    """回 {nav, positions:{sym:{shares,cost,price,value,pnl_pct,weight}}}（合併所有 portfolio）。"""
    pos = {}
    for d in db.portfolio_positions.find():
        sym = d.get('symbol')
        sh = _f(d.get('shares')) or 0
        cost = _f(d.get('avg_cost'))
        p = db.stock_price.find_one({'symbol': sym}, sort=[('date', -1)])
        price = _f((p or {}).get('close'))
        if not (sym and sh and price):
            continue
        prev = pos.get(sym)
        if prev:                                   # 同代號跨 portfolio 合併(加權成本)
            tot_sh = prev['shares'] + sh
            prev['cost'] = (prev['cost'] * prev['shares'] + (cost or 0) * sh) / tot_sh if tot_sh else cost
            prev['shares'] = tot_sh
            prev['value'] = tot_sh * price
        else:
            pos[sym] = {'shares': sh, 'cost': cost, 'price': price, 'value': sh * price}
    nav = sum(v['value'] for v in pos.values())
    for v in pos.values():
        v['pnl_pct'] = (v['price'] / v['cost'] - 1) * 100 if v['cost'] else None
        v['weight'] = v['value'] / nav * 100 if nav else None
    return {'nav': nav, 'positions': pos}


def var_lines(db, symbol: str, snapshot: Optional[Dict] = None) -> List[str]:
    """此持倉的 VaR/淨值影響文字（無持倉資料則回空）。"""
    snap = snapshot or portfolio_snapshot(db)
    nav, pos = snap['nav'], snap['positions'].get(symbol)
    if not (nav and pos):
        return []
    weight = pos['weight'] or 0
    unreal = (pos['value'] - pos['shares'] * pos['cost']) if pos['cost'] else 0
    unreal_pct = unreal / nav * 100
    out = [f"💰 此倉佔淨值 {weight:.1f}%；未實現損益佔淨值 {unreal_pct:+.2f}%"]
    sd = _daily_vol(db, symbol)
    if sd:
        var95 = pos['value'] * 1.645 * sd            # 參數法 1日95% VaR(金額)
        out.append(f"   後續1日95%風險 約 -{var95/nav*100:.2f}% 淨值（-{var95:,.0f}元）")
    return out


def checklist(db, symbol: str, cost: float, name: str = '',
              snapshot: Optional[Dict] = None) -> str:
    """止損觸發後四維檢查清單（每項用客觀資料自動填答 + 結論）。"""
    from src.strategy.trading_rules import TradingRules
    tr = TradingRules()
    stop = tr.check_stop_loss(symbol, cost)
    if stop.get('error'):
        return ''
    phase = tr.detect_institution_phase(symbol)
    pnl = stop.get('pnl_pct')
    below60 = bool(stop.get('below_ma60'))
    mat = stop.get('ma_trend', '?')
    fs = _factor(db, symbol, 'foreign_streak') or 0
    ts = _factor(db, symbol, 'trust_streak') or 0
    bias_y = _factor(db, symbol, 'ma_bias_240')
    above_long = _factor(db, symbol, 'ma_above_long')
    ind = phase.get('indicators') or {}
    vol_ratio = _f(ind.get('vol_ratio'))

    fails = 0

    # ① 邏輯：型態/均線是否還支持當初買入
    logic_bad = below60 or mat in ('糾結', '空頭排列') or (above_long is not None and above_long == 0)
    fails += logic_bad
    d1 = (f"①邏輯: 型態{mat}" + ("·破MA60" if below60 else "")
          + ("·年線下" if above_long == 0 else "")
          + (" → 買入理由已消失 ❌" if logic_bad else " → 結構尚存 ✅"))

    # ② 籌碼：離場 vs 洗盤
    leaving = (fs < 0 or ts < 0) and below60
    washing = phase.get('phase') in ('建倉', '拉升') and not below60
    chip_bad = leaving or (not washing and (fs < 0 or ts < 0))
    fails += chip_bad
    chip_tag = ("主力離場(非洗盤)" if leaving else
                "可能洗盤(建倉/守MA60)" if washing else
                "籌碼鬆動" if chip_bad else "籌碼仍穩")
    d2 = (f"②籌碼: 外資連{'賣' if fs<0 else '買'}{abs(int(fs))} "
          f"投信連{'賣' if ts<0 else '買'}{abs(int(ts))} "
          f"主力{phase.get('phase','?')} → {chip_tag} "
          + ("❌" if chip_bad else "✅"))

    # ③ 情境：現價若是現金還會買嗎
    overbought = bias_y is not None and bias_y >= 40
    wont_buy = logic_bad or overbought
    fails += wont_buy
    d3 = ("③情境: " + (f"乖離年{bias_y:+.0f}%超買·" if overbought else "")
          + ("型態破壞·" if logic_bad else "")
          + ("若是現金「不會買進」 ❌" if wont_buy else "現價仍具吸引力 ✅"))

    # ④ 執行：一次 vs 分段（依流動性）
    from src.strategy.screen_liquidity import avg_volume_lots
    lots = avg_volume_lots(db, symbol)
    if lots < 300:
        d4 = f"④執行: 均量{lots:.0f}張(冷門) → 分2批限價,掛跌破點上緣避滑價"
    else:
        d4 = f"④執行: 均量{lots:.0f}張(流動足) → 型態已破可一次出場(或先出50%)"

    verdict = ("　→ 三項皆❌：已無凹單理由，執行止損" if fails >= 3 else
               "　→ 部分成立：先出50%降曝險，剩餘設最後防線" if fails == 2 else
               "　→ 訊號未全破：可暫抱，但設硬性防線勿凹單")

    L = [f"📋 止損檢查清單 {symbol} {name} 損{pnl:+.1f}%", d1, d2, d3, d4]
    L += var_lines(db, symbol, snapshot=snapshot)
    L.append(verdict)
    return '\n'.join(L)
