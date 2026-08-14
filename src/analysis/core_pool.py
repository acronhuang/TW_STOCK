"""核心池選股漏斗:數據品質 ∩ AI委員買進 ∩ 外資背書。

全市場 → 品質快篩(自由現金流>0·應收<60天·毛利>20%·獲利YoY>0)
       → ∩ 最新週跑合議「買進」
       → 排『絕對獲利能力(EPS+獲利+自由現金流) + 外資近10日淨買』綜合分。
純計算(pandas),dashboard 與每日追蹤 cron 共用。YoY 用 (今-去年)/|去年| 避免負基期翻轉。
"""
import os
from collections import defaultdict
from datetime import datetime, timedelta

import pandas as pd

# 買進反動能過濾:排除當批買進中事前 20 日漲幅最高的這一比例。
# 依據(verdict_detail 全樣本 2026-08-14,前瞻 20 日):買進判斷力隨事前動能單調遞減——
#   事前弱 命中 51.8%/超額 +1.04% ｜事前中 48.3%/+0.55% ｜事前強 40.6%/+0.75%
#   動能前 10% 為實質虧損(命中 33.0%、均超額 -1.54%)
#   排除前 30% 後:超額命中 68.6%→77.2%、均超額 +2.18%→+4.10%
# ⚠️ in-sample 切片,僅 34 個獨立分析日、單一空頭區間,尚未樣本外驗證。
#    設 CORE_POOL_MOM_FILTER_PCT=0 可完全關閉還原舊行為。
MOM_FILTER_PCT = float(os.getenv("CORE_POOL_MOM_FILTER_PCT", "0.30"))

YI = 1e8
INC = ["Revenue", "GrossProfit", "IncomeAfterTaxes", "EPS"]
CF = ["CashFlowsFromOperatingActivities", "PropertyAndPlantAndEquipment"]
_SEASON = {3: 1, 6: 2, 9: 3, 12: 4}
_PREVQ = {6: (3, 31), 9: (6, 30), 12: (9, 30)}


def _num(v):
    return float(v.to_decimal()) if hasattr(v, "to_decimal") else (float(v) if v is not None else None)


def _yoy(cu, ba):
    return None if (cu is None or ba is None or ba == 0) else (cu - ba) / abs(ba) * 100


def market_financials(db):
    """全市場最新廣覆蓋季的 EPS/獲利/營收/毛利率/自由現金流/應收週轉/獲利YoY。回 (季別, DataFrame)。"""
    fs = db.financial_statement_detail
    dates = sorted(fs.distinct("date", {"type": "Revenue"}), reverse=True)
    ref = next((d for d in dates if fs.count_documents({"date": d, "type": "Revenue"}) >= 500),
               dates[0] if dates else None)
    if ref is None:
        return None, pd.DataFrame()
    prev = datetime(ref.year - 1, ref.month, ref.day)
    season = _SEASON[ref.month]

    def load(coll, types, d):
        m = defaultdict(dict)
        for r in db[coll].find({"date": d, "type": {"$in": types}}, {"stock_id": 1, "type": 1, "value": 1}):
            m[r["stock_id"]][r["type"]] = _num(r["value"])
        return m
    cur = load("financial_statement_detail", INC, ref)
    ly = load("financial_statement_detail", INC, prev)
    cf_ref = load("cash_flows_detail", CF, ref)
    cf_prev = load("cash_flows_detail", CF, datetime(ref.year, *_PREVQ[ref.month])) if season != 1 else {}
    ar = {r["stock_id"]: _num(r["value"]) for r in db.balance_sheet_detail.find(
        {"date": ref, "type": "AccountsReceivableNet"}, {"stock_id": 1, "value": 1})}
    ids = [s for s in cur if len(s) == 4 and s.isdigit()]
    names = {}
    for r in db.stock_price.find({"stock_id": {"$in": ids}, "name": {"$nin": ["", None]}},
                                 {"_id": 0, "stock_id": 1, "name": 1}).sort("date", -1):
        names.setdefault(r["stock_id"], r["name"])
    rows = []
    for sid in ids:
        c = cur[sid]; l = ly.get(sid, {})
        rev = c.get("Revenue")
        if not rev:
            continue
        ni = c.get("IncomeAfterTaxes"); eps = c.get("EPS"); gp = c.get("GrossProfit")
        cf = cf_ref.get(sid, {})
        ocf = cf.get("CashFlowsFromOperatingActivities"); capex = cf.get("PropertyAndPlantAndEquipment")
        if season != 1:
            p = cf_prev.get(sid, {})
            po = p.get("CashFlowsFromOperatingActivities"); pc = p.get("PropertyAndPlantAndEquipment")
            ocf = (ocf - po) if (ocf is not None and po is not None) else None
            capex = (capex - pc) if (capex is not None and pc is not None) else None
        free_cf = (ocf + capex) if (ocf is not None and capex is not None) else None
        _ar = ar.get(sid); dso = (_ar / rev * 91.25) if (_ar and rev) else None
        gy = _yoy(ni, l.get("IncomeAfterTaxes"))
        rows.append({
            "代號": sid, "名稱": names.get(sid, ""), "營收(億)": round(rev / YI, 1),
            "獲利(億)": round(ni / YI, 1) if ni is not None else None, "EPS": eps,
            "毛利率%": round(gp / rev * 100, 1) if gp is not None else None,
            "自由現金流(億)": round(free_cf / YI, 1) if free_cf is not None else None,
            "應收週轉(天)": round(dso, 1) if dso is not None else None,
            "獲利YoY%": round(gy, 1) if gy is not None else None,
        })
    return f"{ref.year}Q{season}", pd.DataFrame(rows)


def _prior_20d(db, sym, dt):
    """dt(含)往前 20 個交易日的還原報酬。資料不足 21 根或價格無效回 None。"""
    rows = list(db.stock_price.find(
        {"symbol": sym, "date": {"$lte": dt}, "adj_close": {"$ne": None}},
        {"date": 1, "adj_close": 1}).sort("date", -1).limit(21))
    if len(rows) < 21:
        return None
    p0, pp = _num(rows[0].get("adj_close")), _num(rows[20].get("adj_close"))
    return (p0 / pp - 1.0) if (p0 and pp) else None


def latest_buys(db, min_universe=500, mom_filter_pct=None):
    """最新一批『全市場』週跑合議『買進』的股票集合 + 該分析日。
    用 doc 數 >= min_universe 判斷是全市場週跑(排除小universe的每日dailypicks,那只分析數十檔)。

    mom_filter_pct: 反動能過濾比例(見檔頭 MOM_FILTER_PCT)。None 用預設,0 關閉。
    取不到事前動能的標的**保留**(不因缺資料而誤殺),並會回報有幾檔算不出來。
    """
    from collections import Counter
    cnt = Counter()
    for d in db.team_analysis.find({}, {"date": 1}).sort("date", -1).limit(9000):
        cnt[d["date"]] += 1
    full = sorted((dt for dt, c in cnt.items() if c >= min_universe), reverse=True)
    if not full:
        return None, set()
    dt = full[0]
    d0 = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    d1 = d0 + timedelta(days=1)
    buys = set(x["symbol"] for x in db.team_analysis.find(
        {"date": {"$gte": d0, "$lt": d1}, "final_verdict": "買進"}))

    pct = MOM_FILTER_PCT if mom_filter_pct is None else mom_filter_pct
    if pct and buys:
        mom = {s: _prior_20d(db, s, d0) for s in buys}
        scored = sorted(((s, m) for s, m in mom.items() if m is not None),
                        key=lambda x: -x[1])
        n_drop = int(len(scored) * pct)
        dropped = {s for s, _ in scored[:n_drop]}
        n_nomom = len(buys) - len(scored)
        buys = buys - dropped
        # 不靜默截斷:被排除幾檔、因缺資料而豁免幾檔,都要講出來
        print(f"  [反動能過濾] 買進 {len(scored) + n_nomom} 檔 → 排除事前20日漲幅前"
              f"{pct*100:.0f}% 共 {len(dropped)} 檔,缺動能資料保留 {n_nomom} 檔,"
              f"餘 {len(buys)} 檔"
              + (f"(排除門檻 {scored[n_drop-1][1]*100:+.1f}%)" if n_drop else ""))
    return d0, buys


def _foreign_10d(db, sym):
    def g(v):
        return float(v.to_decimal()) if hasattr(v, "to_decimal") else (float(v) if v is not None else 0)
    return round(sum(g(x.get("foreign_net")) for x in db.institutional_flow.find(
        {"stock_id": sym}, {"foreign_net": 1}).sort("date", -1).limit(10)) / 1000)


def build_core_pool(db, min_rev=1.0):
    """回 (meta dict, core DataFrame 已排綜合分)。"""
    quarter, df = market_financials(db)
    if df is None or df.empty:
        return {"error": "無財報資料"}, pd.DataFrame()
    q = df[(df["營收(億)"].fillna(0) >= min_rev) & (df["自由現金流(億)"] > 0) & (df["應收週轉(天)"] < 60)
           & (df["毛利率%"] > 20) & (df["獲利YoY%"] > 0)].copy()
    buy_date, buys = latest_buys(db)
    core = q[q["代號"].isin(buys)].copy()
    if not core.empty:
        core["外資10日淨買(張)"] = core["代號"].map(lambda s: _foreign_10d(db, s))
        core["綜合分"] = ((core["EPS"].rank(pct=True) + core["獲利(億)"].rank(pct=True)
                        + core["自由現金流(億)"].rank(pct=True)) + core["外資10日淨買(張)"].rank(pct=True) * 2).round(2)
        core = core.sort_values("綜合分", ascending=False).reset_index(drop=True)
    meta = {"quarter": quarter, "buy_date": str(buy_date)[:10] if buy_date else None,
            "n_all": len(df), "n_quality": len(q), "n_buy": len(buys), "n_core": len(core)}
    return meta, core
