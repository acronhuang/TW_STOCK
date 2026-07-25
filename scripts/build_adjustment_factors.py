#!/usr/bin/env python3
"""從 dividend_detail 推算除權息調整係數,寫入 adjustment_factors 集合。

參考價公式(台灣證交所):
    參考價 = (前一交易日收盤 − 現金股利 + 現增認購價 × 現增率) / (1 + 配股率 + 現增率)
    配股率 = 股票股利(元) / 10        現增率 = 認股率 / 1000

    factor = 參考價 / 前一日收盤   (< 1)
    還原:把除權息日「之前」的價格乘上 factor,即為後復權基準

驗證邏輯:除權息當日實際收盤應該貼近參考價(漲跌幅以參考價為基準,限 ±10%)。
若改用前一日收盤當分母,誤差會系統性偏負一個股利的量 —— 兩者比較即可證明公式對錯。
"""
import argparse
import statistics
from datetime import datetime, timedelta

from pymongo import MongoClient, UpdateOne


def f(x):
    if x is None:
        return 0.0
    try:
        return float(x.to_decimal()) if hasattr(x, "to_decimal") else float(x)
    except (TypeError, ValueError):
        return 0.0


def parse_date(s):
    if not s or not isinstance(s, str):
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d")
    except ValueError:
        return None


def build_events(db, sub_divisor):
    """把 dividend_detail 攤平成 (stock_id, ex_date, cash, stock_ratio, sub_rate, sub_price)"""
    events = []
    for r in db.dividend_detail.find({}, {
            "_id": 0, "stock_id": 1, "cash_ex_dividend_date": 1, "stock_ex_dividend_date": 1,
            "cash_earnings_distribution": 1, "cash_statutory_surplus": 1,
            "stock_earnings_distribution": 1, "stock_statutory_surplus": 1,
            "cash_increase_subscription_rate": 1, "cash_increase_subscription_price": 1}):
        cd = parse_date(r.get("cash_ex_dividend_date"))
        sd = parse_date(r.get("stock_ex_dividend_date"))
        ex = min([d for d in (cd, sd) if d], default=None)
        if not ex:
            continue  # 兩個除權息日都沒有 → 無法定位,跳過
        cash = f(r.get("cash_earnings_distribution")) + f(r.get("cash_statutory_surplus"))
        stock = f(r.get("stock_earnings_distribution")) + f(r.get("stock_statutory_surplus"))
        sub_rate = f(r.get("cash_increase_subscription_rate")) / sub_divisor
        sub_price = f(r.get("cash_increase_subscription_price"))
        if cash <= 0 and stock <= 0 and sub_rate <= 0:
            continue  # 空事件
        events.append({"stock_id": r["stock_id"], "ex_date": ex, "cash": cash,
                       "stock_ratio": stock / 10.0, "sub_rate": sub_rate, "sub_price": sub_price})
    return events


def price_lookup(db, events):
    """取每檔在事件前後的收盤價序列(只抓需要的股票,一次拉完)"""
    ids = sorted({e["stock_id"] for e in events})
    lo = min(e["ex_date"] for e in events) - timedelta(days=15)
    series = {}
    for r in db.stock_price.find(
            {"stock_id": {"$in": ids}, "date": {"$gte": lo}},
            {"_id": 0, "stock_id": 1, "date": 1, "close": 1}).sort([("stock_id", 1), ("date", 1)]):
        c = f(r.get("close"))
        if c > 0:
            series.setdefault(r["stock_id"], []).append((r["date"], c))
    return series


# 「前一交易日」離除權息日最多幾個日曆天才算數。
# 2026-07-20 實測:656 筆異常事件中有 638 筆的間隔 >30 天 ——
# 那些股票的股價歷史有數年空洞(例:3037/2492/2603 只有一筆 2016 孤兒資料,2022 才恢復),
# bisect 會抓到跨年的錯誤鄰居,算出 +1400% 的假參考價。
# 15 天可容納農曆年封關(最長約 9 天)與短期停牌,同時擋掉跨年錯配。
MAX_PREV_GAP_DAYS = 15


def compute(events, series, max_gap=MAX_PREV_GAP_DAYS):
    """回傳 (可算出的事件 list, 診斷資料, 跳過原因統計)"""
    out, diag = [], []
    skip = {"無價格序列": 0, "事件在序列範圍外": 0,
            "前一交易日過遠": 0, "參考價非正": 0}
    import bisect
    for e in events:
        s = series.get(e["stock_id"])
        if not s:
            skip["無價格序列"] += 1
            continue
        dates = [d for d, _ in s]
        i = bisect.bisect_left(dates, e["ex_date"])
        if i == 0 or i >= len(dates):
            skip["事件在序列範圍外"] += 1
            continue
        gap = (e["ex_date"] - dates[i - 1]).days
        if gap > max_gap:
            # 股價歷史有洞 → 這筆算出來的 factor 會是錯的,寧可不產生
            skip["前一交易日過遠"] += 1
            continue
        prev_close = s[i - 1][1]
        actual = s[i][1]            # 除權息當日實際收盤
        denom = 1.0 + e["stock_ratio"] + e["sub_rate"]
        ref = (prev_close - e["cash"] + e["sub_price"] * e["sub_rate"]) / denom
        if ref <= 0:
            skip["參考價非正"] += 1
            continue
        # 合理性檢查:除權息當日實際收盤若偏離參考價超過漲跌幅(±10%)+緩衝,
        # 代表這筆事件的來源資料有問題(實測主因是 cash_increase_subscription_rate
        # 的單位在不同年份/來源不一致:有的該除 100、有的該除 1000),
        # 與其猜單位,不如直接不產生這種會汙染還原價的 factor。
        day_move = actual / ref - 1 if ref > 0 else 999
        if abs(day_move) > 0.115:
            skip["參考價與實際嚴重偏離"] = skip.get("參考價與實際嚴重偏離", 0) + 1
            continue
        factor = ref / prev_close
        out.append({**e, "prev_close": prev_close, "ref_price": ref,
                    "factor": factor, "prev_gap_days": gap})
        diag.append({
            "has_sub": e["sub_rate"] > 0,
            "err_ref": actual / ref - 1,           # 用參考價當基準的當日漲跌
            "err_raw": actual / prev_close - 1,    # 用前收當基準(未調整)
        })
    return out, diag, skip


def report(diag, label):
    if not diag:
        print(f"  {label}: 無樣本")
        return
    er = [d["err_ref"] for d in diag]
    ew = [d["err_raw"] for d in diag]
    over = sum(1 for x in er if abs(x) > 0.105)
    print(f"  {label}: n={len(diag)}")
    print(f"    以參考價為基準 中位數 {statistics.median(er):+.4%}  |超出±10.5%| {over} ({over/len(er):.1%})")
    print(f"    以前收為基準   中位數 {statistics.median(ew):+.4%}   ← 未調整,應系統性偏負")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="寫入 adjustment_factors(預設只驗證)")
    args = ap.parse_args()

    db = MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]

    # ---- 先定現增率單位:試 /1000 與 /100,看哪個讓參考價更貼近實際 ----
    print("=== 現增率單位驗證 ===")
    best, best_med = None, None
    for div in (1000.0, 100.0):
        ev = [e for e in build_events(db, div) if e["sub_rate"] > 0]
        if not ev:
            continue
        srs = price_lookup(db, ev)
        _, dg, _sk = compute(ev, srs)
        if not dg:
            continue
        med = abs(statistics.median([d["err_ref"] for d in dg]))
        print(f"  除以 {div:.0f}: n={len(dg)} 參考價誤差中位數 {med:.4%}")
        if best_med is None or med < best_med:
            best, best_med = div, med
    div = best or 1000.0
    print(f"  → 採用 /{div:.0f}\n")

    # ---- 全量計算 ----
    events = build_events(db, div)
    print(f"=== 事件展開:{len(events)} 筆(來自 {db.dividend_detail.count_documents({})} 筆明細)===")
    series = price_lookup(db, events)
    rows, diag, skip = compute(events, series)
    print("跳過統計:" + ", ".join(f"{k} {v}" for k, v in skip.items() if v))
    print(f"對得到前後價格、可計算係數:{len(rows)} 筆\n")

    print("=== 公式驗證(除權息當日實際收盤 vs 推算參考價)===")
    report([d for d in diag if not d["has_sub"]], "純除權息")
    report([d for d in diag if d["has_sub"]], "含現金增資")

    if not args.write:
        print("\n(未加 --write,不寫入)")
        return

    # 只寫「新增或係數真的變了」的 —— updated_at 必須代表「最後一次真正異動」,
    # 否則每日 cron 會把全部標成異動,backfill_adj_close --changed-only 就退化成全量。
    existing = {(r["stock_id"], r["ex_date"]): f(r.get("factor"))
                for r in db.adjustment_factors.find(
                    {}, {"_id": 0, "stock_id": 1, "ex_date": 1, "factor": 1})}
    ops, skipped = [], 0
    for r in rows:
        old = existing.get((r["stock_id"], r["ex_date"]))
        if old is not None and abs(old - r["factor"]) < 1e-12:
            skipped += 1
            continue
        ops.append(UpdateOne(
            {"stock_id": r["stock_id"], "ex_date": r["ex_date"]},
            {"$set": {**r, "source": "computed:dividend_detail", "updated_at": datetime.now()}},
            upsert=True))

    print(f"\n未變動、跳過:{skipped}")
    if not ops:
        print("無新增或異動,不寫入。")
    else:
        res = db.adjustment_factors.bulk_write(ops, ordered=False)
        print(f"寫入 adjustment_factors:新增 {res.upserted_count} / 更新 {res.modified_count}")
    db.adjustment_factors.create_index([("stock_id", 1), ("ex_date", 1)], unique=True)
    print(f"涵蓋股票數:{len(db.adjustment_factors.distinct('stock_id'))}")


if __name__ == "__main__":
    main()
