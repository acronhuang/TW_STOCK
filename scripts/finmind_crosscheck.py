#!/usr/bin/env python3
"""以 FinMind（獨立來源）逐檔抽樣核對 DB 的價量、三大法人、融資融券。唯讀。

用法：python scripts/finmind_crosscheck.py --from 2026-09-10 --to 2026-10-08 [--sample 40]
FinMind 免費帳號只能逐檔查（每小時 600 次），所以只做抽樣：持倉 + 成交值前段班 + 隨機中小型股。
"""
import argparse
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import requests  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from src.config import get_db  # noqa: E402

URL = "https://api.finmindtrade.com/api/v4/data"


def num(value):
    if value is None:
        return None
    return float(value.to_decimal()) if hasattr(value, "to_decimal") else float(value)


def finmind(dataset: str, symbol: str, start: str, end: str, token: str) -> list[dict]:
    for attempt in range(3):
        response = requests.get(URL, params={"dataset": dataset, "data_id": symbol, "start_date": start, "end_date": end, "token": token}, timeout=40)
        if response.status_code == 200:
            return response.json().get("data") or []
        if response.status_code in (402, 429):
            raise SystemExit(f"FinMind 額度用盡或限流（HTTP {response.status_code}），稍後再跑")
        time.sleep(2 * (attempt + 1))
    return []


def pick_symbols(db, day: datetime, count: int) -> list[str]:
    held = {lot.get("symbol") or lot.get("stock_id") for lot in db["portfolio_lots"].find({}, {"symbol": 1, "stock_id": 1})}
    rows = list(db["stock_price"].find({"date": day, "amount": {"$exists": True}}, {"symbol": 1, "amount": 1}))
    rows = [r for r in rows if r.get("symbol") and len(r["symbol"]) == 4 and r["symbol"].isdigit()]
    rows.sort(key=lambda r: -(num(r["amount"]) or 0))
    top = [r["symbol"] for r in rows[:count // 2]]
    rest = [r["symbol"] for r in rows[count // 2:]]
    random.seed(20261012)
    chosen = [s for s in dict.fromkeys([*held, *top, *random.sample(rest, min(len(rest), count - len(top)))]) if s]
    return chosen


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from", dest="start", required=True)
    parser.add_argument("--to", dest="end", required=True)
    parser.add_argument("--sample", type=int, default=40)
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")
    token = os.getenv("FINMIND_API_TOKEN", "")
    db = get_db()
    day0, day1 = datetime.strptime(args.start, "%Y-%m-%d"), datetime.strptime(args.end, "%Y-%m-%d")
    symbols = pick_symbols(db, day1, args.sample)
    print(f"抽樣 {len(symbols)} 檔，期間 {args.start} ~ {args.end}")

    stats = {name: [0, 0] for name in ("price_close", "price_volume", "foreign_net", "trust_net", "dealer_net", "margin_balance", "short_balance")}
    missing = {"price": [], "inst": [], "margin": []}
    bad = []

    def compare(name, symbol, day, mine, theirs, tolerance=0.0):
        stats[name][0] += 1
        if mine is not None and theirs is not None and abs(mine - theirs) <= tolerance:
            return
        stats[name][1] += 1
        bad.append((name, symbol, day, mine, theirs))

    for symbol in symbols:
        price = {r["date"]: r for r in finmind("TaiwanStockPrice", symbol, args.start, args.end, token)}
        inst = {}
        for r in finmind("TaiwanStockInstitutionalInvestorsBuySell", symbol, args.start, args.end, token):
            inst.setdefault(r["date"], {})[r["name"]] = r["buy"] - r["sell"]
        margin = {r["date"]: r for r in finmind("TaiwanStockMarginPurchaseShortSale", symbol, args.start, args.end, token)}
        mine_price = {d["date"].strftime("%Y-%m-%d"): d for d in db["stock_price"].find({"symbol": symbol, "date": {"$gte": day0, "$lte": day1}})}
        mine_inst = {d["date"].strftime("%Y-%m-%d"): d for d in db["institutional_flow"].find({"stock_id": symbol, "date": {"$gte": day0, "$lte": day1}})}
        mine_margin = {d["date"].strftime("%Y-%m-%d"): d for d in db["margin_purchase_short_sale"].find({"code": symbol, "date": {"$gte": day0, "$lte": day1}})}

        for day, ref in price.items():
            mine = mine_price.get(day)
            if mine is None:
                missing["price"].append((symbol, day))
                continue
            compare("price_close", symbol, day, num(mine.get("close")), float(ref["close"]), 0.005)
            compare("price_volume", symbol, day, num(mine.get("volume")), float(ref["Trading_Volume"]))
        for day, ref in inst.items():
            mine = mine_inst.get(day)
            if mine is None:
                missing["inst"].append((symbol, day))
                continue
            foreign = ref.get("Foreign_Investor", 0) + ref.get("Foreign_Dealer_Self", 0)
            compare("foreign_net", symbol, day, num(mine.get("foreign_net")), foreign)
            compare("trust_net", symbol, day, num(mine.get("trust_net")), ref.get("Investment_Trust", 0))
            compare("dealer_net", symbol, day, num(mine.get("dealer_net")), ref.get("Dealer_self", 0) + ref.get("Dealer_Hedging", 0))
        for day, ref in margin.items():
            mine = mine_margin.get(day)
            if mine is None:
                missing["margin"].append((symbol, day))
                continue
            compare("margin_balance", symbol, day, num(mine.get("margin_balance")), float(ref["MarginPurchaseTodayBalance"]))
            compare("short_balance", symbol, day, num(mine.get("short_balance")), float(ref["ShortSaleTodayBalance"]))
        time.sleep(0.3)

    print("--- 逐欄位一致率（FinMind 為對照）")
    for name, (total, wrong) in stats.items():
        print(f"{name:16} 比對 {total:5d}  不一致 {wrong:4d}  一致率 {100 * (total - wrong) / total if total else 0:6.2f}%")
    for name, pairs in missing.items():
        by_day = {}
        for symbol, day in pairs:
            by_day.setdefault(day, []).append(symbol)
        print(f"--- FinMind 有、DB 缺（{name}）共 {len(pairs)} 筆；依日期：", {day: len(v) for day, v in sorted(by_day.items())})
        for day, symbols_ in sorted(by_day.items())[:3]:
            print("   ", day, symbols_[:12])
    for item in [b for b in bad if b[0] != "price_volume"][:15]:
        print("  不一致", item)
    volume_days = sorted({b[2] for b in bad if b[0] == "price_volume"})
    print("  price_volume 不一致的日期：", volume_days)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
