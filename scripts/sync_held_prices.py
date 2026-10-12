#!/usr/bin/env python3
"""持倉代號的價格補抓（FinMind TaiwanStockPrice，每檔一次請求）。預設 dry-run，--apply 才寫。

日常管線只收 4 碼普通股與 OpenAPI 清單，債券 ETF（00679B 等）不在其中，持倉估值會停在舊價。
只補「最後一筆之後」的日子；還原價欄位只在新增時設定，不覆蓋既有的還原價回填。
"""
import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import requests  # noqa: E402
from bson.decimal128 import Decimal128  # noqa: E402
from pymongo import UpdateOne  # noqa: E402

URL = "https://api.finmindtrade.com/api/v4/data"
SOURCE = "FinMind:TaiwanStockPrice"


def _dec(value) -> Decimal128:
    return Decimal128(str(value))


def to_doc(symbol: str, row: dict) -> dict | None:
    if not row.get("close"):
        return None
    return {"stock_id": symbol, "symbol": symbol, "date": datetime.strptime(row["date"], "%Y-%m-%d"),
            "open": _dec(row["open"]), "high": _dec(row["max"]), "low": _dec(row["min"]), "close": _dec(row["close"]),
            "volume": _dec(row["Trading_Volume"]), "amount": str(row["Trading_money"]), "transaction": str(row["Trading_turnover"]),
            "change": str(row.get("spread", "")), "data_source": SOURCE}


def start_after(last: datetime, reference: datetime) -> str | None:
    return (last + timedelta(days=1)).strftime("%Y-%m-%d") if last < reference else None


def build_operation(doc: dict) -> UpdateOne:
    on_insert = {"adj_close": doc["close"], "adj_open": doc["open"], "adj_high": doc["high"], "adj_low": doc["low"],
                 "adjustment_factor": _dec("1.0")}
    return UpdateOne({"symbol": doc["symbol"], "date": doc["date"]},
                     {"$set": {**doc, "updated_at": datetime.now()}, "$setOnInsert": on_insert}, upsert=True)


def held_symbols(db) -> list[str]:
    return sorted({lot["symbol"] for lot in db["portfolio_lots"].find({"sell_date": None}, {"symbol": 1}) if lot.get("symbol")})


def main(argv: list[str] | None = None) -> int:
    from dotenv import load_dotenv

    from src.config import get_db

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    load_dotenv(PROJECT_ROOT / ".env")
    token = os.getenv("FINMIND_API_TOKEN", "")
    db = get_db()
    reference = db["stock_price"].find_one({"symbol": "2330"}, {"date": 1}, sort=[("date", -1)])["date"]
    failed = 0
    for symbol in held_symbols(db):
        last = db["stock_price"].find_one({"symbol": symbol}, {"date": 1}, sort=[("date", -1)])
        start = start_after(last["date"], reference) if last else "2020-01-01"
        if start is None:
            continue
        response = requests.get(URL, params={"dataset": "TaiwanStockPrice", "data_id": symbol, "start_date": start,
                                             "end_date": reference.strftime("%Y-%m-%d"), "token": token}, timeout=40)
        if response.status_code != 200:
            print(f"{symbol} FinMind HTTP {response.status_code}", flush=True)
            failed += 1
            continue
        docs = [d for d in (to_doc(symbol, r) for r in response.json().get("data") or []) if d]
        print(f"{symbol} {start}~{reference:%Y-%m-%d} rows={len(docs)} mode={'apply' if args.apply else 'dry-run'}", flush=True)
        if args.apply and docs:
            db["stock_price"].bulk_write([build_operation(d) for d in docs], ordered=False)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
