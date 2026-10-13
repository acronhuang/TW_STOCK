"""公告事件回看：只讀報表。事件取自 major_news，股價取自 stock_price，大盤用 TAIEX。

用法：python scripts/event_study_report.py [--start 2026-04-01] [--end 2026-09-11] [--min-clause-events 30]
只印出結果，不寫入資料庫、不發通知。事件窗口需要事件後 20 個交易日，所以預設結束日要早於今天一個月。
"""
import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.analysis import event_study as es  # noqa: E402
from src.config import get_db  # noqa: E402


def to_float(value):
    if value is None:
        return None
    try:
        return float(value.to_decimal()) if hasattr(value, "to_decimal") else float(value)
    except (TypeError, ValueError):
        return None


def price_series(db, stock_ids, since, field="adj_close"):
    series = {sid: {} for sid in stock_ids}
    cursor = db["stock_price"].find({"stock_id": {"$in": list(stock_ids)}, "date": {"$gte": since}},
                                    {"stock_id": 1, "date": 1, field: 1, "close": 1})
    for doc in cursor:
        value = to_float(doc.get(field)) or to_float(doc.get("close"))
        if value:
            series[doc["stock_id"]][doc["date"]] = value
    return series


def pct(value):
    return "  —  " if value is None else f"{value * 100:+.2f}%"


def render(result, min_clause_events, samples):
    lines = []
    for clause, item in sorted(result.items(), key=lambda kv: -kv[1]["counts"]["kept"]):
        counts = item["counts"]
        if counts["kept"] < min_clause_events:
            continue
        lines.append(f"\n{clause}  共 {counts['total']} 則；有效 {counts['kept']}；"
                     f"盤中略過 {counts['intraday']}、重複 {counts['overlap']}、缺價 {counts['no_price']}、窗口未滿 {counts['out_of_range']}")
        lines.append("  例：" + "｜".join(samples.get(clause, [])))
        lines.append(f"  {'窗口':6} {'n':>5} {'平均':>9} {'中位數':>9} {'上漲占比':>8}   {'對照平均':>9} {'對照n':>5} {'事件減對照':>9}")
        for name in es.WINDOWS:
            real, fake = item["windows"][name], item["placebo"][name]
            if "mean" not in real:
                lines.append(f"  {name:6} {real['n']:>5}  樣本不足（少於 {es.MIN_EVENTS}），不給平均")
                continue
            gap = real["mean"] - fake["mean"] if "mean" in fake else None
            lines.append(f"  {name:6} {real['n']:>5} {pct(real['mean']):>9} {pct(real['median']):>9} "
                         f"{real['share_up'] * 100:>7.0f}%   {pct(fake.get('mean')):>9} {fake['n']:>5} {pct(gap):>9}")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2026-04-01")
    parser.add_argument("--end", default=(datetime.now() - timedelta(days=32)).strftime("%Y-%m-%d"))
    parser.add_argument("--min-clause-events", type=int, default=30)
    parser.add_argument("--seed", type=int, default=20261013)
    parser.add_argument("--benchmark", choices=("ew", "taiex"), default="ew", help="ew=全市場等權（預設）、taiex=市值加權大盤")
    args = parser.parse_args(argv)
    start = datetime.strptime(args.start, "%Y-%m-%d")
    end = datetime.strptime(args.end, "%Y-%m-%d")

    db = get_db()
    docs = [d for d in db["major_news"].find({"date": {"$gte": start, "$lte": end}},
                                              {"stock_id": 1, "date": 1, "time": 1, "clause": 1, "subject": 1})
            if str(d.get("stock_id", "")).isdigit() and len(str(d["stock_id"])) == 4 and d.get("clause")]
    events = [{"stock_id": d["stock_id"], "day": d["date"], "time": d.get("time"), "clause": d["clause"]} for d in docs]
    samples = {}
    for d in docs:
        bucket = samples.setdefault(d["clause"], [])
        if len(bucket) < 2:
            bucket.append(" ".join(str(d["subject"]).split())[:24])

    since = start - timedelta(days=15)
    taiex = price_series(db, ["TAIEX"], since, field="close")["TAIEX"]
    calendar = sorted(taiex)
    event_ids = {e["stock_id"] for e in events}
    if args.benchmark == "ew":
        every = [sid for sid in db["stock_price"].distinct("stock_id", {"date": {"$gte": end}})
                 if str(sid).isdigit() and len(str(sid)) == 4]
        all_series = price_series(db, set(every) | event_ids, since)
        market = es.equal_weight_index(all_series, calendar)
        stock_series = {sid: all_series[sid] for sid in event_ids if all_series.get(sid)}
    else:
        market = taiex
        stock_series = {sid: s for sid, s in price_series(db, event_ids, since).items() if s}
    excess = {sid: es.daily_excess(series, market, calendar) for sid, series in stock_series.items()}
    result = es.study(events, excess, calendar, seed=args.seed)

    print(f"事件回看（相對 {'全市場等權指數' if args.benchmark == 'ew' else 'TAIEX'} 的累積超額報酬）  "
          f"事件日 {args.start} ~ {args.end}；共 {len(events)} 則重大訊息，"
          f"交易日曆 {calendar[0]:%Y-%m-%d} ~ {calendar[-1]:%Y-%m-%d}")
    print("只描述過去。同一天大量公司同時公告（如財報前預告）會彼此相關，平均不等於因果。")
    if args.benchmark == "taiex":
        print("大盤是市值加權的 TAIEX，平均個股常輸給它，所以『平均』欄整體偏負；請看『事件減對照』（對照＝同批公司在其他時間的相同窗口）。")
    print(render(result, args.min_clause_events, samples))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
