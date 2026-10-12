#!/usr/bin/env python3
"""補算停機日的 fair_value / margin_of_safety（stock_factors）。預設 dry-run，--apply 才寫。

用與 backfill_valuation_factors 相同的 ValuationAnalyzer.analyze（DCF+DDM+PE Band 綜合價），只把股價換成該日收盤，
讓補出的值與前後日同口徑。財報、股利、股數沿用目前資料；停機日若沒有新財報公布，結果與當日重算相同。
只填目前沒有 fair_value 的文件，以及先前以 DCF+DDM 補的舊標記（會被重算覆蓋）。
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pymongo import UpdateOne  # noqa: E402

from src.analysis.valuation_models import ValuationAnalyzer, _to_float  # noqa: E402
from src.config import get_db  # noqa: E402
from src.data_gap import fair_value  # noqa: E402

URI = "mongodb://localhost:27017/"


class AsOfPriceValuation(ValuationAnalyzer):
    """只覆寫現價：取 as_of 當日（含）以前最近一筆收盤。"""

    def __init__(self, uri: str, as_of: datetime):
        super().__init__(uri)
        self.as_of = as_of

    def _get_current_price(self, symbol: str):
        rec = self.db["stock_price"].find_one({"symbol": symbol, "date": {"$lte": self.as_of}}, {"close": 1}, sort=[("date", -1)])
        return _to_float(rec["close"]) if rec else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, nargs="+", help="一個或多個 YYYY-MM-DD")
    parser.add_argument("--limit", type=int, default=0, help="只算前 N 檔（試跑用）")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    db = get_db()
    for text in args.date:
        day = datetime.strptime(text, "%Y-%m-%d")
        query = {"date": day, "$or": [{"fair_value": {"$exists": False}}, {"fair_value_source": {"$in": list(fair_value.REPLACEABLE)}}]}
        pending = sorted(d["symbol"] for d in db["stock_factors"].find(query, {"symbol": 1}))
        if args.limit:
            pending = pending[:args.limit]
        model = AsOfPriceValuation(URI, day)
        operations, filled, cleared = [], 0, 0
        for symbol in pending:
            try:
                result = model.analyze(symbol)
            except Exception:  # noqa: BLE001 - 個股資料不足時略過
                continue
            value = (result.get("composite") or {}).get("fair_value")
            fields = fair_value.fields(value, result.get("current_price"))
            if fields:
                operations.append(UpdateOne({"symbol": symbol, "date": day}, {"$set": fields}))
                filled += 1
            else:  # 與 backfill_valuation_factors 一致：算不出來就不留值（含先前舊標記補的）
                operations.append(UpdateOne({"symbol": symbol, "date": day, "fair_value_source": {"$in": list(fair_value.REPLACEABLE)}},
                                            {"$unset": {"fair_value": "", "margin_of_safety": "", "fair_value_source": ""}}))
                cleared += 1
        print(f"{text} pending={len(pending)} computed={filled} cleared_or_skipped={cleared} mode={'apply' if args.apply else 'dry-run'}", flush=True)
        if args.apply and operations:
            db["stock_factors"].bulk_write(operations, ordered=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
