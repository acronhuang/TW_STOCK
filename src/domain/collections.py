"""MongoDB 集合名稱 —— 單一真相源 (Phase 2 資料層收斂)。

背景：全樹以裸字串散寫 ~65 個集合名（`db.stock_price`、`db['institutional_flow']`…），
打錯字不會報錯、改名要全樹搜尋、schema 無單一真相源。本模組把集合名收斂為常數，
供 repository 與各模組逐步採用（`db[COLL_STOCK_PRICE]`）。

命名慣例：`COLL_<UPPER_SNAKE>`，值 = 實際集合名（不改動既有集合）。
"""
from __future__ import annotations

# ── 價格 / 因子 ────────────────────────────────────────────────────────
COLL_STOCK_PRICE = "stock_price"
COLL_STOCK_FACTORS = "stock_factors"
COLL_FUNDAMENTAL_FACTORS = "fundamental_factors"
COLL_TECHNICAL_INDICATORS = "technical_indicators"
COLL_ADJUSTMENT_FACTORS = "adjustment_factors"
COLL_YAHOO_PRICES = "yahoo_prices"

# ── 財報 / 財務 ────────────────────────────────────────────────────────
COLL_FINANCIAL_REPORTS = "financial_reports"
COLL_FINANCIAL_STATEMENTS = "financial_statements"
COLL_FINANCIAL_STATEMENT_DETAIL = "financial_statement_detail"
COLL_BALANCE_SHEET_DETAIL = "balance_sheet_detail"
COLL_QUARTERLY_EARNINGS = "quarterly_earnings"
COLL_MONTHLY_REVENUE = "monthly_revenue"
COLL_FINMIND_FINANCIALS = "finmind_financials"
COLL_YAHOO_FINANCIALS = "yahoo_financials"

# ── 股利 / 公司行動 ────────────────────────────────────────────────────
COLL_DIVIDEND_DETAIL = "dividend_detail"
COLL_DIVIDEND_RESULTS = "dividend_results"
COLL_DIVIDENDS = "dividends"
COLL_CORPORATE_ACTIONS = "corporate_actions"
COLL_STOCK_SPLIT_EVENTS = "stock_split_events"

# ── 標的資訊 / 中繼 ────────────────────────────────────────────────────
COLL_TAIWAN_STOCK_INFO = "taiwan_stock_info"
COLL_TICKERS = "tickers"
COLL_STOCKS = "stocks"
COLL_STOCK_LIST = "stock_list"
COLL_COMPANY_BASIC_INFO = "company_basic_info"
COLL_TRADING_DATES = "trading_dates"

# ── 估值 ───────────────────────────────────────────────────────────────
COLL_TAIWAN_STOCK_PER = "taiwan_stock_per"
COLL_STOCK_PER_PBR = "stock_per_pbr"
COLL_RIVER_CHARTS = "river_charts"

# ── 籌碼 ───────────────────────────────────────────────────────────────
COLL_INSTITUTIONAL_FLOW = "institutional_flow"
COLL_INSTITUTIONAL_INVESTORS = "institutional_investors"
COLL_INSTITUTIONAL_INVESTORS_LONG = "institutional_investors_long"
COLL_INSTITUTIONAL_INVESTORS_WIDE = "institutional_investors_wide"
COLL_SHAREHOLDING = "shareholding"
COLL_FOREIGN_HOLDING = "foreign_holding"
COLL_MAJOR_SHAREHOLDERS = "major_shareholders"
COLL_MARGIN_PURCHASE_SHORT_SALE = "margin_purchase_short_sale"
COLL_MARGIN_TRADING = "margin_trading"
COLL_MARGIN_SUSPENSION = "margin_suspension"
COLL_SECURITIES_LENDING = "securities_lending"
COLL_INSIDER_TRANSFER = "insider_transfer"
COLL_AFTER_HOURS_TRADING = "after_hours_trading"
COLL_ODD_LOT_TRADING = "odd_lot_trading"
COLL_DAY_TRADING_TARGETS = "day_trading_targets"

# ── 總經 / 情緒 / 新聞 ─────────────────────────────────────────────────
COLL_MACRO_INDICATORS = "macro_indicators"
COLL_BULL_BEAR_INDICATORS = "bull_bear_indicators"
COLL_MAJOR_NEWS = "major_news"
COLL_MEDIA_NEWS = "media_news"

# ── 投組 ───────────────────────────────────────────────────────────────
COLL_PORTFOLIO_LOTS = "portfolio_lots"
COLL_PORTFOLIO_POSITIONS = "portfolio_positions"

# ── 告警 / 系統 / 健康 ─────────────────────────────────────────────────
COLL_SCHEDULE_ALERTS = "schedule_alerts"
COLL_ALERT_RULES = "alert_rules"
COLL_ALERT_HISTORY = "alert_history"
COLL_SYSTEM_HEARTBEAT = "system_heartbeat"
COLL_DATA_HEALTH_HISTORY = "data_health_history"
COLL_DATA_CONTINUITY_ALERTED = "data_continuity_alerted"
COLL_INSTITUTIONAL_REBUILD_PROGRESS = "institutional_rebuild_progress"

# ── 分析 / 名單 ────────────────────────────────────────────────────────
COLL_TEAM_ANALYSIS = "team_analysis"
COLL_VERDICT_METRICS = "verdict_metrics"
COLL_PEER_COMPARISON = "peer_comparison"
COLL_NOTICED_STOCKS = "noticed_stocks"
COLL_PUNISHED_STOCKS = "punished_stocks"
COLL_ETF_DCA_RANK = "etf_dca_rank"


def all_collections() -> dict[str, str]:
    """回傳 {常數名: 集合名}，供稽核/測試使用。"""
    return {k: v for k, v in globals().items()
            if k.startswith("COLL_") and isinstance(v, str)}
