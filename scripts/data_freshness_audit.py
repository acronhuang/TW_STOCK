#!/usr/bin/env python3
"""資料新鮮度盤點 —— 認得日頻/週頻/月頻/季頻/事件型的各種日期欄位,依 cadence 判斷是否落後。

背景:先前臨時盤點用「date 欄 vs 今天」一把尺,對週頻(集保/外資明細)、季頻(財報)、
月頻(月營收)、事件型(corporate_actions 用 event_date、月營收用 year_month、財報用 year+season)
一律誤報 🔴。本工具內建每表的(日期欄位種類, 更新頻率),按頻率給不同落後門檻。

用法: python3 scripts/data_freshness_audit.py [--all]   # --all 連未列在 SPEC 的表也掃(視為 date/daily)
"""
import sys
import argparse
from datetime import datetime, timedelta

from pymongo import MongoClient

# (日期欄位種類, 更新頻率)。種類: date | event_date | year_month | year_season | fiscal
# 頻率決定落後門檻(天): daily=4(含週末) weekly=9 monthly=45 quarterly=135 event=一律OK(可未來日)
SPEC = {
    "每日核心價量": {
        "stock_price": ("date", "daily"), "stock_factors": ("date", "daily"),
        "after_hours_trading": ("date", "daily"), "odd_lot_trading": ("date", "daily"),
        "day_trading_targets": ("date", "daily"), "securities_lending": ("date", "daily"),
    },
    "籌碼法人": {
        "margin_purchase_short_sale": ("date", "daily"), "institutional_flow": ("date", "daily"),
        "institutional_investors_wide": ("date", "weekly"), "foreign_holding": ("date", "daily"),
        "shareholding": ("date", "weekly"), "foreign_shareholding": ("date", "weekly"),
    },
    "財報基本面": {
        "fundamental_factors": ("year_season", "quarterly"),
        "quarterly_earnings": ("year_season", "quarterly"),
        "financial_statement_detail": ("date", "quarterly"),
        "balance_sheet_detail": ("date", "quarterly"),
        "cash_flows_detail": ("date", "quarterly"),
        "monthly_revenue": ("year_month", "monthly"),
        "month_revenue_detail": ("date", "monthly"),  # 此表用 date/revenue_month 而非 year_month
    },
    "總經國際": {
        "macro_indicators": ("date", "monthly"), "intl_index": ("date", "daily"),
    },
    "事件/公司行動": {
        "corporate_actions": ("event_date", "event"), "dividend_detail": ("date", "event"),
    },
}
THRESH = {"daily": 4, "weekly": 9, "monthly": 45, "quarterly": 135, "event": None}


def _season_end(year, season):
    m, d = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}.get(int(season), (12, 31))
    return datetime(int(year), m, d)


def _month_end(ym):  # "YYYY-MM" → 該月最後一天(概算用下月1號-1天)
    y, m = int(ym[:4]), int(ym[5:7])
    nxt = datetime(y + (m == 12), (m % 12) + 1, 1)
    return nxt - timedelta(days=1)


def latest_period(db, coll, kind):
    """回 (顯示字串, 代表 datetime, 當期涵蓋檔數 or None)。無資料回 (None,None,None)。"""
    c = db[coll]
    if kind == "date":
        d = (c.find_one({"date": {"$type": "date"}}, sort=[("date", -1)])
             or c.find_one({"date": {"$type": "string"}}, sort=[("date", -1)]))
        if not d:
            return None, None, None
        val = d["date"]
        dt = val if isinstance(val, datetime) else datetime.strptime(str(val)[:10], "%Y-%m-%d")
        n = c.count_documents({"date": val})
        return str(val)[:10], dt, n
    if kind == "event_date":
        d = c.find_one({"event_date": {"$exists": True}}, sort=[("event_date", -1)])
        if not d:
            return None, None, None
        s = str(d["event_date"])[:10]
        try:
            dt = datetime.strptime(s, "%Y-%m-%d")
        except ValueError:
            dt = None
        return s, dt, None
    if kind == "year_month":
        d = c.find_one({"year_month": {"$exists": True}}, sort=[("year_month", -1)])
        if not d:
            return None, None, None
        ym = str(d["year_month"])[:7]
        n = len(c.distinct("symbol", {"year_month": ym}))
        return ym, _month_end(ym), n
    if kind == "year_season":
        d = c.find_one({"year": {"$exists": True}}, sort=[("year", -1), ("season", -1)])
        if not d:
            return None, None, None
        y, s = d.get("year"), d.get("season")
        n = len(c.distinct("stock_id", {"year": y, "season": s})) or len(c.distinct("symbol", {"year": y, "season": s}))
        return f"{y}Q{s}", _season_end(y, s), n
    return None, None, None


def main():
    ap = argparse.ArgumentParser(description="資料新鮮度盤點(cadence-aware)")
    ap.add_argument("--all", action="store_true", help="連未列 SPEC 的 collection 也掃(視為 date/daily)")
    ap.add_argument("--alert", action="store_true",
                    help="有表超出頻率門檻(🔴)才寫一筆 schedule_alerts 進網頁;無則靜默")
    ap.add_argument("--uri", default="mongodb://localhost:27017")
    ap.add_argument("--strict", action="store_true", help="有 🔴 則以非零結束(供 deploy 硬閘 G5)")
    args = ap.parse_args()
    db = MongoClient(args.uri)["tw_stock_analysis"]
    now = datetime.now()

    spec = {g: dict(t) for g, t in SPEC.items()}
    if args.all:
        listed = {c for t in SPEC.values() for c in t}
        extra = {c: ("date", "daily") for c in db.list_collection_names()
                 if not c.startswith("system.") and c not in listed}
        if extra:
            spec["其他(未分類→date/daily)"] = extra

    print(f"資料新鮮度盤點  @ {now:%Y-%m-%d %H:%M}")
    print("門檻(落後天): 日頻≤4 週頻≤9 月頻≤45 季頻≤135 事件=不判\n")
    worst = []
    for group, tables in spec.items():
        print(f"=== {group} ===")
        for coll, (kind, cad) in sorted(tables.items()):
            try:
                disp, dt, n = latest_period(db, coll, kind)
            except Exception as e:
                print(f"  ⚠️ {coll:30} 讀取錯 {e!r}"); continue
            tot = db[coll].estimated_document_count()
            if dt is None:
                print(f"  ⚪ {coll:30} 無資料/無{kind}欄  總{tot:>12,}")
                continue
            lag = (now.replace(hour=0, minute=0, second=0, microsecond=0) - dt).days
            th = THRESH[cad]
            if th is None:
                flag = "✅"  # 事件型:未來日/事件排入,不判落後
            elif lag <= 1 or lag <= th * 0.5:
                flag = "✅"
            elif lag <= th:
                flag = "🟡"
            else:
                flag = "🔴"; worst.append((coll, disp, lag, cad))
            ahead = "(未來/超前)" if lag < 0 else f"落後{lag}天"
            covs = f" 當期{n:>5}" if n is not None else ""
            print(f"  {flag} {coll:30} 最新 {disp:>10} [{cad}] {ahead}{covs} 總{tot:>12,}")
        print()
    if worst:
        print("🔴 真正超出該頻率門檻(需查):")
        for coll, disp, lag, cad in worst:
            print(f"   - {coll} 最新 {disp} 落後 {lag} 天(>{THRESH[cad]}天 {cad}門檻)")
    else:
        print("✅ 無任何表超出其更新頻率的落後門檻。")

    # 只有真 🔴 才寫 schedule_alerts 進網頁(無則靜默),不發 LINE
    if args.alert:
        if worst:
            detail = chr(10).join(
                f"- {coll} 最新 {disp} 落後 {lag} 天(>{THRESH[cad]}天 {cad}門檻)"
                for coll, disp, lag, cad in worst)
            msg = f"⚠️ 資料新鮮度:{len(worst)} 個表超出更新頻率門檻{chr(10)}{detail}"
            try:
                db.schedule_alerts.create_index([("ts", -1)])
                db.schedule_alerts.insert_one({
                    "ts": datetime.now(), "level": "error", "source": "freshness_audit",
                    "message": msg, "resolved": False})
                print(f"[alert] 已寫入 schedule_alerts({len(worst)} 個表)")
            except Exception as e:
                print(f"[alert] schedule_alerts 寫入失敗:{e!r}")
        else:
            print("[alert] 無 🔴,不寫警報(靜默)")

    if args.strict and worst:
        sys.exit(1)


if __name__ == "__main__":
    main()
