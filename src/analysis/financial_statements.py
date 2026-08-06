"""財報深度:從明細三表(FinMind long格式)算逐季 三率/現金流/負債結構/YoY。

單位換算與陷阱:
- 損益表(financial_statement_detail)= **單季**值(實測 2330 各季營收非累計)。
- 現金流量表(cash_flows_detail)= **累計**(年內 Q1→Q4 遞增,隔年重置)→ 本模組差分成單季。
- 資產負債表(balance_sheet_detail)= 時點值,不差分。
- 值單位=元;顯示時 /1e8 = 億。

台灣報別:Q1 第一季報 / Q2 半年報 / Q3 第三季報 / Q4 年報。
"""
from datetime import datetime

IS = {"revenue": "Revenue", "gross": "GrossProfit", "op_income": "OperatingIncome",
      "net_income": "IncomeAfterTaxes", "eps": "EPS"}
CF = {"ocf": "CashFlowsFromOperatingActivities", "icf": "CashProvidedByInvestingActivities",
      "fcf": "CashFlowsProvidedFromFinancingActivities", "capex": "PropertyAndPlantAndEquipment"}
BS = {"assets": "TotalAssets", "equity": "Equity", "cur_assets": "CurrentAssets",
      "cur_liab": "CurrentLiabilities", "inventory": "Inventories",
      "recv": "AccountsReceivableNet", "cash": "CashAndCashEquivalents"}
REPORT = {1: "Q1 第一季報", 2: "Q2 半年報", 3: "Q3 第三季報", 4: "Q4 年報"}
_SEASON = {3: 1, 6: 2, 9: 3, 12: 4}


def _num(v):
    return float(v.to_decimal()) if hasattr(v, "to_decimal") else (float(v) if v is not None else None)


def yoy_pct(cur, base):
    """YoY 成長%,用 abs(基期) 當分母 → 去年為負(虧轉盈)時符號正確:改善=正、惡化=負。
    去年基期為 0 或缺 → None(成長率無意義,看絕對值)。"""
    if cur is None or base is None or base == 0:
        return None
    return (cur - base) / abs(base) * 100


def _load(db, coll, symbol, fields):
    """回 {(year,season): {key: value}}。"""
    want = {v: k for k, v in fields.items()}
    out = {}
    for d in db[coll].find({"stock_id": symbol, "type": {"$in": list(want)}},
                           {"date": 1, "type": 1, "value": 1}):
        dt = d["date"]
        if not isinstance(dt, datetime) or dt.month not in _SEASON:
            continue
        ys = (dt.year, _SEASON[dt.month])
        out.setdefault(ys, {})[want[d["type"]]] = _num(d.get("value"))
    return out


def quarterly_financials(db, symbol, n=13):
    """回逐季 dict(舊→新),含三率/EPS/三大現金流(單季)/YoY/負債比/流動比。"""
    inc = _load(db, "financial_statement_detail", symbol, IS)
    cf = _load(db, "cash_flows_detail", symbol, CF)
    bs = _load(db, "balance_sheet_detail", symbol, BS)
    quarters = sorted(set(inc) | set(cf) | set(bs))
    if not quarters:
        return []

    def prevq(ys):
        y, s = ys
        return (y, s - 1) if s > 1 else (y - 1, 4)

    rows = []
    for ys in quarters:
        y, s = ys
        i = inc.get(ys, {}); c = cf.get(ys, {}); b = bs.get(ys, {})
        rev = i.get("revenue")
        gm = (i["gross"] / rev * 100) if (i.get("gross") and rev) else None
        om = (i["op_income"] / rev * 100) if (i.get("op_income") and rev) else None
        nm = (i["net_income"] / rev * 100) if (i.get("net_income") and rev) else None
        # 現金流:累計→單季(Q1即單季;Q2-4 = 本季累計 - 上一季累計,同年)
        def cf_single(key):
            v = c.get(key)
            if v is None:
                return None
            if s == 1:
                return v
            pv = cf.get((y, s - 1), {}).get(key)
            return (v - pv) if pv is not None else None
        ocf = cf_single("ocf"); icf = cf_single("icf"); fcf = cf_single("fcf")
        capex = cf_single("capex")  # 取得PP&E,存負值(流出)
        free_cf = (ocf + capex) if (ocf is not None and capex is not None) else None  # 自由現金流=營運CF-資本支出

        ni = i.get("net_income")
        ocf_ni = (ocf / ni) if (ocf is not None and ni) else None   # 營運現金流/淨利 = 現金含金量
        assets = b.get("assets"); equity = b.get("equity")
        debt_ratio = ((assets - equity) / assets * 100) if (assets and equity is not None) else None
        cur_ratio = (b["cur_assets"] / b["cur_liab"] * 100) if (b.get("cur_assets") and b.get("cur_liab")) else None
        dso = (b.get("recv") / rev * 91.25) if (b.get("recv") and rev) else None  # 應收帳款週轉天數(單季)

        # YoY(同季去年);用 yoy_pct 處理去年為負(虧轉盈)的符號
        ly = inc.get((y - 1, s), {})
        rev_yoy = yoy_pct(rev, ly.get("revenue"))
        ni_yoy = yoy_pct(ni, ly.get("net_income"))
        eps_yoy = yoy_pct(i.get("eps"), ly.get("eps"))
        rows.append({
            "year": y, "season": s, "report": REPORT[s], "label": f"{y}Q{s}",
            "revenue": rev, "gross_margin": gm, "op_margin": om, "net_margin": nm,
            "eps": i.get("eps"), "net_income": ni,
            "ocf": ocf, "icf": icf, "fcf": fcf, "ocf_to_ni": ocf_ni,
            "capex": capex, "free_cf": free_cf, "dso": dso,
            "total_assets": assets, "equity": equity, "debt_ratio": debt_ratio,
            "current_ratio": cur_ratio, "inventory": b.get("inventory"), "recv": b.get("recv"),
            "revenue_yoy": rev_yoy, "net_yoy": ni_yoy, "eps_yoy": eps_yoy,
        })
    return rows[-n:]


def committee_summary(db, symbol):
    """給基本面委員的精簡字串:最新季三率+趨勢、現金含金量、負債比、流動比。"""
    rows = quarterly_financials(db, symbol, n=5)
    if not rows:
        return ""
    cur = rows[-1]
    def trend(key):
        vals = [r[key] for r in rows if r.get(key) is not None]
        if len(vals) < 2:
            return ""
        return "↑" if vals[-1] > vals[0] else ("↓" if vals[-1] < vals[0] else "→")
    def f(v, suf="%"):
        return f"{v:.1f}{suf}" if v is not None else "—"
    return (f"{cur['label']}({cur['report']}) "
            f"毛利率{f(cur['gross_margin'])}{trend('gross_margin')} "
            f"營益率{f(cur['op_margin'])}{trend('op_margin')} "
            f"淨利率{f(cur['net_margin'])}{trend('net_margin')} "
            f"EPS{f(cur['eps'],'元')}(YoY{f(cur['eps_yoy'])}) "
            f"營運現金流/淨利{f(cur['ocf_to_ni']*100) if cur['ocf_to_ni'] is not None else '—'}(>100%=獲利含金量高) "
            f"負債比{f(cur['debt_ratio'])} 流動比{f(cur['current_ratio'])} "
            f"自由現金流{(str(round(cur['free_cf']/1e8))+'億') if cur.get('free_cf') is not None else '—'} "
            f"應收週轉{f(cur['dso'],'天')}")
