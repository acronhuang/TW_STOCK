#!/usr/bin/env python3
"""持倉分批(lot/tranche)資料層。

同股多次買進 → 每筆一個 doc 存 portfolio_lots(含買進日/價/股數)。
portfolio_positions(Phase2 風控在用的單一真相)由 lots **自動彙總**寫回,
所以 daily_alert_check / risk_deliberation 完全不用改。

集合 portfolio_lots 欄位:
  symbol, buy_date(datetime|None), shares(int), price(float),
  category, portfolio, note, created_at
"""
from datetime import datetime

from bson.decimal128 import Decimal128
from pymongo import MongoClient

CATS = ["波段", "債券ETF", "長期存股", "零成本", "零股"]
NO_STOP_CATS = {"債券ETF", "長期存股", "零成本", "零股"}


def db_conn():
    return MongoClient("localhost", 27017)["tw_stock_analysis"]


def _f(v):
    if isinstance(v, Decimal128):
        return float(v.to_decimal())
    return float(v) if isinstance(v, (int, float)) else None


# ---------- 彙總:lots → portfolio_positions ----------
def recompute_position(db, sym):
    """把某代號所有 lot 彙總,寫回 portfolio_positions(無 lot 則刪該部位)。"""
    lots = list(db.portfolio_lots.find({"symbol": sym}))
    if not lots:
        db.portfolio_positions.delete_one({"symbol": sym})
        return None
    tot_sh = sum(int(_f(l.get("shares")) or 0) for l in lots)
    tot_cost = sum((_f(l.get("shares")) or 0) * (_f(l.get("price")) or 0) for l in lots)
    avg = (tot_cost / tot_sh) if tot_sh else 0.0
    cats = [l.get("category") for l in lots if l.get("category")]
    cat = max(set(cats), key=cats.count) if cats else "波段"   # 取最常見分類
    doc = {
        "symbol": sym, "shares": int(tot_sh), "avg_cost": round(avg, 4),
        "total_cost": round(tot_cost, 2), "category": cat,
        "no_stop_loss": cat in NO_STOP_CATS, "long_hold": cat == "長期存股",
        "portfolio": "main", "updated_at": datetime.now(),
    }
    db.portfolio_positions.update_one({"symbol": sym}, {"$set": doc}, upsert=True)
    return doc


def recompute_all(db):
    syms = set(db.portfolio_lots.distinct("symbol"))
    for s in syms:
        recompute_position(db, s)
    # 刪掉已無 lot 的殘留部位
    for s in set(db.portfolio_positions.distinct("symbol")) - syms:
        db.portfolio_positions.delete_one({"symbol": s})
    return len(syms)


# ---------- migration:從既有 positions 種一批 lot ----------
def seed_lots_from_positions(db, force=False):
    """既有 portfolio_positions 每檔轉一個 lot(買進日未知,待使用者補)。"""
    if not force and db.portfolio_lots.count_documents({}) > 0:
        return 0
    n = 0
    for d in db.portfolio_positions.find({}):
        db.portfolio_lots.insert_one({
            "symbol": d["symbol"], "buy_date": None,
            "shares": int(_f(d.get("shares")) or 0),
            "price": _f(d.get("avg_cost")) or 0.0,
            "category": d.get("category") or "波段",
            "portfolio": d.get("portfolio", "main"),
            "note": "自既有持倉轉入(買進日未知,請補)",
            "created_at": datetime.now(),
        })
        n += 1
    return n


# ---------- 讀 lots 供編輯 ----------
def list_lots(db):
    out = []
    for l in db.portfolio_lots.find({}).sort([("symbol", 1), ("buy_date", 1)]):
        bd = l.get("buy_date")
        out.append({
            "id": str(l["_id"]),
            "symbol": l.get("symbol", ""),
            "buy_date": bd,
            "shares": int(_f(l.get("shares")) or 0),
            "price": _f(l.get("price")) or 0.0,
            "category": l.get("category") or "波段",
            "note": l.get("note") or "",
        })
    return out


def replace_lots(db, lots):
    """整批取代 portfolio_lots(小資料集,全刪重寫最單純),再彙總 positions。
    lots: list of dict(symbol, buy_date(datetime|None), shares, price, category, note)。"""
    clean = []
    for l in lots:
        sym = str(l.get("symbol") or "").strip()
        sh = int(_f(l.get("shares")) or 0)
        if not sym or sh <= 0:
            continue
        clean.append({
            "symbol": sym,
            "buy_date": l.get("buy_date"),
            "shares": sh,
            "price": _f(l.get("price")) or 0.0,
            "category": l.get("category") or "波段",
            "portfolio": "main",
            "note": str(l.get("note") or ""),
            "created_at": datetime.now(),
        })
    db.portfolio_lots.delete_many({})
    if clean:
        db.portfolio_lots.insert_many(clean)
    recompute_all(db)
    return len(clean)


# ---------- 實倉回放:用 adj_close 畫組合報酬 vs 大盤 ----------
def _fix_splits(s):
    """即時修正『未還原的分割/減資跳空』。

    後復權價本該連續(除權息已由 adjustment_factor 處理)。若相鄰交易日出現
    腰斬級跳空(比例 <0.55 或 >1.8,遠超台股 ±10% 日限),代表分割/減資未被
    係數處理(資料源需付費,見 build_adjustment_factors 只讀 dividend_detail)。
    以最新值為基準,把跳空之前的值乘上比例使其連續(後復權語意)。
    """
    v = list(s.values)
    n = len(v)
    if n < 2:
        return s
    factor = [1.0] * n
    cum = 1.0
    for i in range(n - 1, 0, -1):
        factor[i] = cum
        prev = v[i - 1]
        r = (v[i] / prev) if prev else 1.0
        if r < 0.55 or r > 1.8:          # 未還原的分割/減資跳空
            cum *= r
    factor[0] = cum
    import pandas as pd
    return pd.Series([v[i] * factor[i] for i in range(n)], index=s.index)


def _adj_series(db, sym, start):
    import pandas as pd
    cur = db.stock_price.find(
        {"symbol": sym, "date": {"$gte": start}},
        {"_id": 0, "date": 1, "adj_close": 1, "close": 1}
    ).sort("date", 1)
    data = {}
    for r in cur:
        p = _f(r.get("adj_close")) or _f(r.get("close"))
        if p:
            data[r["date"]] = p
    if not data:
        return None
    return _fix_splits(pd.Series(data).sort_index())


def equity_replay(db, benchmark="0050"):
    """從各批實際進場日,用還原價畫『持倉市值 vs 同資金買0050 vs 投入成本』。
    回傳 DataFrame(index=日期),或 None(無可用 lot)。"""
    import pandas as pd
    lots = [l for l in db.portfolio_lots.find({}) if l.get("buy_date")]
    if not lots:
        return None
    start = min(l["buy_date"] for l in lots)
    bench = _adj_series(db, benchmark, start)
    if bench is None or bench.empty:
        return None
    idx = bench.index                       # 以 0050 交易日為共用日曆
    port = pd.Series(0.0, index=idx)
    bnch = pd.Series(0.0, index=idx)
    cost = pd.Series(0.0, index=idx)
    used = 0
    for l in lots:
        bd = l["buy_date"]
        sh = _f(l.get("shares")) or 0
        pr = _f(l.get("price")) or 0
        invested = sh * pr
        if invested <= 0:
            continue
        s = _adj_series(db, l["symbol"], bd)
        if s is None or s.empty:
            continue
        s = s.reindex(idx).ffill()
        after = s[s.index >= bd].dropna()
        b_after = bench[bench.index >= bd].dropna()
        if after.empty or b_after.empty:
            continue
        base, bbase = after.iloc[0], b_after.iloc[0]
        mask = idx >= bd
        port.loc[mask] = port.loc[mask] + invested * (s[mask] / base).fillna(1.0)
        bnch.loc[mask] = bnch.loc[mask] + invested * (bench[mask] / bbase).fillna(1.0)
        cost.loc[mask] = cost.loc[mask] + invested
        used += 1
    if used == 0:
        return None
    df = pd.DataFrame({"持倉市值": port, "同資金買0050": bnch, "投入成本": cost})
    return df[df["投入成本"] > 0]


def strategy_replay(db, stop_loss=None, take_profit=None, trailing=None,
                    max_days=None, benchmark="0050"):
    """以各批**真實進場點**為基礎,套用可調出場規則做互動式回測。

    規則(擇最早觸發者出場,出場後該筆轉現金、報酬凍結):
      stop_loss   現價 <= 進場價×(1-sl)      例 0.08
      take_profit 現價 >= 進場價×(1+tp)
      trailing    現價 <= 進場後最高×(1-tr)   移動停損
      max_days    持有天數 >= N

    回傳 (equity_df, trades):
      equity_df: index=日期, 欄=[策略市值, 買抱市值, 同資金買0050, 投入成本]
      trades:    每筆 dict(symbol,name?,buy_date,buy_price,shares,exit_date,exit_price,reason,ret_pct)
    """
    import pandas as pd
    rows = [l for l in db.portfolio_lots.find({}) if l.get("buy_date")]
    if not rows:
        return None, []
    start = min(l["buy_date"] for l in rows)
    bench = _adj_series(db, benchmark, start)
    if bench is None or bench.empty:
        return None, []
    idx = bench.index
    strat = pd.Series(0.0, index=idx)
    hold = pd.Series(0.0, index=idx)
    bnch = pd.Series(0.0, index=idx)
    cost = pd.Series(0.0, index=idx)
    trades = []
    used = 0
    for l in rows:
        bd = l["buy_date"]
        sh = _f(l.get("shares")) or 0
        pr = _f(l.get("price")) or 0
        invested = sh * pr
        if invested <= 0:
            continue
        s = _adj_series(db, l["symbol"], bd)
        if s is None or s.empty:
            continue
        s = s.reindex(idx).ffill()
        after = s[s.index >= bd].dropna()
        b_after = bench[bench.index >= bd].dropna()
        if after.empty or b_after.empty:
            continue
        entry = after.iloc[0]
        bbase = b_after.iloc[0]
        # 逐日套用出場規則
        peak = entry
        ex_dt, ex_px, reason = after.index[-1], after.iloc[-1], "續持"
        for dt, px in after.items():
            peak = max(peak, px)
            if stop_loss and px <= entry * (1 - stop_loss):
                ex_dt, ex_px, reason = dt, entry * (1 - stop_loss), "停損"
                break
            if take_profit and px >= entry * (1 + take_profit):
                ex_dt, ex_px, reason = dt, entry * (1 + take_profit), "停利"
                break
            if trailing and px <= peak * (1 - trailing):
                ex_dt, ex_px, reason = dt, px, "移動停損"
                break
            if max_days and (dt - bd).days >= max_days:
                ex_dt, ex_px, reason = dt, px, "到期"
                break
        ret = (ex_px / entry - 1)
        # 曲線:進場~出場走市值,出場後凍結為現金(=進場資金×(1+報酬))
        mask_hold = idx >= bd
        held_val = invested * (s / entry)                    # 買抱:全程持有
        strat_val = pd.Series(0.0, index=idx)
        live = (idx >= bd) & (idx <= ex_dt)
        after_ex = idx > ex_dt
        strat_val[live] = invested * (s[live] / entry)
        strat_val[after_ex] = invested * (1 + ret)           # 出場後凍結
        strat = strat.add(strat_val.where(mask_hold, 0.0), fill_value=0)
        hold = hold.add(held_val.where(mask_hold, 0.0).fillna(0.0), fill_value=0)
        bnch.loc[mask_hold] = bnch.loc[mask_hold] + invested * (bench[mask_hold] / bbase).fillna(1.0)
        cost.loc[mask_hold] = cost.loc[mask_hold] + invested
        trades.append({
            "symbol": l["symbol"], "buy_date": bd, "buy_price": round(pr, 2),
            "shares": int(sh), "exit_date": ex_dt, "exit_price": round(float(ex_px), 2),
            "reason": reason, "ret_pct": round(ret * 100, 1),
        })
        used += 1
    if used == 0:
        return None, []
    eq = pd.DataFrame({"策略市值": strat, "買抱市值": hold,
                       "同資金買0050": bnch, "投入成本": cost})
    eq = eq[eq["投入成本"] > 0]
    return eq, trades
