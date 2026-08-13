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
        # 2026-08-13 納管:先前不在 SPEC,停更 20 天無人知(見 EXEMPT 上方說明)
        # 2026-08-13 剛接上每日 cron(18:20),但歷史資料是一次性回填、間隔達 10 天,
        # 先給 weekly 門檻避免舊資料誤報;cron 穩定跑一週後可改回 daily。
        "securities_lending_detail": ("date", "weekly"),
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
        # 2026-08-13 納管。cadence 依「近 30 天實際有資料的天數」實測而定,
        # 不是看最新日期新不新 —— 這幾張是**事件型**:沒事件的日子本來就沒資料,
        # 標成 daily 會天天誤報。實測(對照組 stock_price 21 天):
        "margin_suspension": ("date", "daily"),      # 20 天,間隔 ≤3
        "major_news": ("date", "daily"),             # 18 天,間隔 ≤3
        "punished_stocks": ("date", "weekly"),       # 17 天但事件型,給寬鬆門檻
        "insider_transfer": ("date", "weekly"),      # 14 天,內部人申報非每日
        "noticed_stocks": ("date", "weekly"),        # 5 天,注意股本就少
    },
    "每日周邊": {
        # 2026-08-13 納管:皆由 twse_openapi_sync 每交易日更新
        "foreign_top20": ("date", "daily"),
        "total_institutional_investors": ("date", "daily"),
        "total_margin": ("date", "daily"),
        "etf_dca_rank": ("date", "daily"),
        "gold_price": ("date", "daily"),
    },
    "分析產出": {
        # 2026-08-13 納管:pipeline 產物,停更代表 pipeline 出事
        "team_analysis": ("date", "daily"),          # 24 天,每晚產出
        "risk_analysis": ("date", "weekly"),         # 15 天,有持倉才產出
    },
}
THRESH = {"daily": 4, "weekly": 9, "monthly": 45, "quarterly": 135, "event": None}
# per-table 門檻覆寫:shareholding(TDCC股權分散)資料日為週五,cron 週六13:00抓(2026-08-11 由週二09:00改),
# 改週六後最大落後~8天(週六抓上週五),12天門檻對週六更寬鬆仍安全;真漏一週會跳~15天+仍🔴。
TH_OVERRIDE = {"shareholding": 12}

# ── 未納管偵測(2026-08-13 加)────────────────────────────────────────────
#
# 為什麼:SPEC 是**明確列入才檢查**的清單,新增的 collection 預設不受監控,
# 而且不會有任何徵兆。實測抓到 securities_lending_detail(140 萬筆)自 2026-07-24
# 起停更 20 天無人知 —— 它由一次性搬移腳本 move_lending_detail.py 建立,
# 既無每日同步管道也不在 SPEC 裡。
#
# 改為「預設納管、豁免要寫理由」:凡 DB 裡有、SPEC 沒有、EXEMPT 也沒有的表,
# 一律列為未納管並進入告警。要豁免就得在下方寫一行理由 —— 讓「不監控」
# 變成一個需要明說的決定,而不是預設值。
EXEMPT = {
    # 執行狀態 / 續跑進度,非資料源
    "adj_close_backfill_state": "續跑進度表",
    "balance_equity_backfill_state": "續跑進度表",
    "dividend_2013_2014_backfill_state": "續跑進度表",
    "financial_detail_backfill_state": "續跑進度表",
    "fundamental_backfill_state": "續跑進度表",
    "financial_detail_empty": "空回應退避記錄(2026-08-13 加)",
    "financial_detail_runlog": "執行記錄,供告警判連續失敗",
    "dividend_sync_nodata": "查無資料的負向記錄",
    # 告警 / 系統自身
    "alert_history": "告警歷史",
    "alert_rules": "告警規則設定",
    "schedule_alerts": "排程告警佇列",
    "system_heartbeat": "心跳,由 watchdog 監控",
    "data_continuity_alerted": "去重用的告警記錄",
    "data_health_history": "健康快照歷史",
    "digest_history": "推播歷史",
    # 靜態 / 低頻參考資料
    "taiwan_stock_info": "股票清單,每日由 info sync 更新但非時序資料",
    "trading_dates": "交易日曆,年度更新",
    "corporate_actions": "公司行動事件表,event 型",
    "delisting": "下市清單,event 型",
    # ── 2026-08-13 分類:以下逐一判定過,非「懶得管」──────────────────
    # 續跑進度(同上分類)
    "institutional_rebuild_progress": "續跑進度表",
    "market_perdate_price_state": "續跑進度表",
    "twse_perdate_price_state": "續跑進度表",
    "monthly_revenue_backfill_state": "續跑進度表",
    "price_early_backfill_state": "續跑進度表",
    "price_history_backfill_state": "續跑進度表",
    # 使用者持倉:有交易才變動,無更新是正常狀態,不該報警
    "portfolio_positions": "使用者持倉,有交易才變動",
    "portfolio_lots": "使用者持倉批次,同上",
    "portfolio_trades": "使用者交易紀錄,同上",
    "portfolio_dividends": "使用者股利紀錄,同上(目前 0 筆)",
    "core_watchlist": "核心池設定,人工維護",
    "verdict_performance": "決策績效回顧,週期性產出",
    # 衍生/中繼資料:由主表推導,主表有監控即可
    "adjustment_factors": "除權息係數,由 corporate_actions 推導;主表已監控",
    "dividend_results": "股利計算結果,由 dividend_detail 推導;主表已監控",
    "major_shareholders": "大戶持股,shareholding 的衍生檢視;主表已監控",
    "media_news": "新聞語料,無固定節奏(事件驅動)",
    # 🔴 停更但**仍有活躍讀取端**,不可刪
    "financial_statements": ("🔴 停更範圍窄(192 檔,到 2025Q4)但 **hsieh_dividend 是主路徑**"
                             "(負債比/速動比/未分配盈餘三門檻),經 API server 使用;"
                             "刪掉會讓那三項靜默不加分。2026-08-13 六查後刻意保留"),
    "system.views": "MongoDB 系統表",
}


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
            th = TH_OVERRIDE.get(coll, THRESH[cad])
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
    # ── 未納管偵測 ──────────────────────────────────────────────────
    known = {t for grp in SPEC.values() for t in (grp if isinstance(grp, dict) else {})}
    if not known:
        # 對照:SPEC 是巢狀({分類:{表:...}}),當成扁平取鍵會得到分類名而非表名,
        # 交集為 0 卻看起來「都沒納管」。2026-08-13 我就這樣誤報過一次。
        print("🔴 SPEC 解析後為空 —— 結構可能已改變,未納管偵測不可信,跳過")
        unregistered = []
    else:
        assert "stock_price" in known, "對照失敗:stock_price 應在 SPEC 內 → SPEC 解析有誤"
        actual = set(db.list_collection_names())
        unregistered = sorted(actual - known - set(EXEMPT))

    if unregistered:
        print(f"\n⚠️  未納管的 collection({len(unregistered)} 個)"
              f" —— 既不在 SPEC 也不在 EXEMPT,等於沒有任何新鮮度監控:")
        for c in unregistered:
            try:
                n = db[c].estimated_document_count()
            except Exception:
                n = -1
            print(f"     {c:<38} {n:>10} 筆")
        print("   要監控 → 加進 SPEC;不需要 → 加進 EXEMPT 並寫明理由。")

    if args.alert:
        if unregistered:
            try:
                db.schedule_alerts.insert_one({
                    "ts": datetime.now(), "level": "warn", "source": "freshness_audit",
                    "message": (f"⚠️ {len(unregistered)} 個 collection 未納管新鮮度監控:"
                                + ", ".join(unregistered[:10])
                                + ("…" if len(unregistered) > 10 else "")),
                    "resolved": False})
                print(f"[alert] 未納管清單已寫入 schedule_alerts({len(unregistered)} 個)")
            except Exception as e:
                print(f"[alert] 未納管告警寫入失敗:{e!r}")
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
