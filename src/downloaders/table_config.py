"""
資料表配置
定義所有 43 個 FinMind 資料表的下載配置
"""

from datetime import datetime, timedelta
from pymongo import ASCENDING, DESCENDING


# 完整的 43 個資料表配置
DATA_TABLES = {
    "技術面": [
        {
            "name": "台股總覽",
            "dataset": "TaiwanStockInfo",
            "collection": "taiwan_stock_info",
            "params": {},
            "indexes": [("stock_id", ASCENDING)],
            "unique_keys": ["stock_id"],
            "needs_symbols": False,
            "description": "台股所有上市櫃股票基本資訊"
        },
        {
            "name": "台灣股價資料表",
            "dataset": "TaiwanStockPrice",
            "collection": "stock_price",
            "params": {"start_date": "2020-01-01"},
            "indexes": [("stock_id", ASCENDING), ("date", DESCENDING)],
            "unique_keys": ["stock_id", "date"],
            "needs_symbols": True,
            "batch_size": 50,
            "description": "個股每日開高低收量價資料"
        },
        {
            "name": "個股 PER、PBR",
            "dataset": "TaiwanStockPER",
            "collection": "taiwan_stock_per",
            "params": {"start_date": "2020-01-01"},
            "indexes": [("stock_id", ASCENDING), ("date", DESCENDING)],
            "unique_keys": ["stock_id", "date"],
            "needs_symbols": True,
            "batch_size": 50,
            "disabled": True,
            "disabled_reason": "已由 twse_daily_update.py 直接寫入 stock_factors（pe_ratio/pb_ratio/dividend_yield）取代",
            "description": "個股本益比、股價淨值比（舊集合，已廢棄）"
        },
        {
            "name": "台股加權指數",
            "dataset": "TaiwanVariousIndicators5Seconds",
            "collection": "market_statistics",
            "params": {"start_date": "2025-01-01"},
            "indexes": [("date", DESCENDING)],
            "unique_keys": ["date"],
            "needs_symbols": False,
            "description": "大盤指數及市場統計"
        },
        {
            "name": "台股交易日",
            "dataset": "TaiwanStockTradingDate",
            "collection": "trading_dates",
            "params": {},
            "indexes": [("date", DESCENDING)],
            "unique_keys": ["date"],
            "needs_symbols": False,
            "description": "台股開市交易日曆"
        },
        {
            "name": "台灣類股股價表",
            "dataset": "TaiwanStockIndustryPrice",
            "collection": "industry_price",
            "disabled": True,
            "disabled_reason": "從未成功下載，可用 stock_price 按產業分類替代",
            "params": {"start_date": "2020-01-01"},
            "indexes": [("industry", ASCENDING), ("date", DESCENDING)],
            "unique_keys": ["industry", "date"],
            "needs_symbols": False,
            "description": "產業分類指數價格"
        },
        {
            "name": "每 5 秒委託成交統計",
            "dataset": "TaiwanStockStatisticsOfOrderBookAndTrade",
            "collection": "order_statistics_5s",
            "disabled": True,
            "disabled_reason": "從未成功下載，盤中即時數據非必要",
            "params": {"start_date": (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")},
            "indexes": [("stock_id", ASCENDING), ("date", DESCENDING)],
            "unique_keys": ["stock_id", "date", "time"],
            "needs_symbols": True,
            "batch_size": 20,
            "description": "盤中 5 秒委買賣統計（近一週）"
        },
        {
            "name": "當日沖銷交易標的",
            "dataset": "TaiwanStockDayTrading",
            "collection": "day_trading_targets",
            "disabled": True,
            "disabled_reason": "從未成功下載，非核心分析需求",
            "params": {},
            "indexes": [("date", DESCENDING), ("stock_id", ASCENDING)],
            "unique_keys": ["stock_id", "date"],
            "needs_symbols": False,
            "description": "可當沖股票名單"
        },
        {
            "name": "加權、櫃買報酬指數",
            "dataset": "TaiwanStockTotalReturnIndex",
            "collection": "total_return_index",
            "disabled": True,
            "disabled_reason": "從未成功下載，可用 stock_price 自行計算報酬指數",
            "params": {"start_date": "2020-01-01"},
            "indexes": [("date", DESCENDING)],
            "unique_keys": ["date", "type"],
            "needs_symbols": False,
            "description": "含息報酬指數"
        }
    ],
    
    "籌碼面": [
        {
            "name": "個股融資融劵表",
            "dataset": "TaiwanStockMarginPurchaseShortSale",
            "collection": "margin_purchase_short_sale",
            "params": {"start_date": "2020-01-01"},
            "indexes": [("stock_id", ASCENDING), ("date", DESCENDING)],
            "unique_keys": ["stock_id", "date"],
            "needs_symbols": True,
            "batch_size": 50,
            "description": "個股融資融券餘額變化"
        },
        {
            "name": "整體市場融資融劵表",
            "dataset": "TaiwanStockTotalMarginPurchaseShortSale",
            "collection": "total_margin",
            "params": {"start_date": "2020-01-01"},
            "indexes": [("date", DESCENDING)],
            "unique_keys": ["date"],
            "needs_symbols": False,
            "description": "全市場融資融券統計"
        },
        {
            "name": "個股三大法人買賣表",
            "dataset": "TaiwanStockInstitutionalInvestors",
            "collection": "institutional_investors_detail",
            "disabled": True,
            "disabled_reason": "從未成功下載，已由 institutional_flow (TWSE T86) 取代",
            "params": {"start_date": "2020-01-01"},
            "indexes": [("stock_id", ASCENDING), ("date", DESCENDING)],
            "unique_keys": ["stock_id", "date"],
            "needs_symbols": True,
            "batch_size": 50,
            "description": "外資、投信、自營商買賣超"
        },
        {
            "name": "整體三大市場法人買賣表",
            "dataset": "TaiwanStockTotalInstitutionalInvestors",
            "collection": "total_institutional_investors",
            "params": {"start_date": "2020-01-01"},
            "indexes": [("date", DESCENDING)],
            "unique_keys": ["date"],
            "needs_symbols": False,
            "description": "三大法人市場總買賣"
        },
        {
            "name": "外資持股表",
            "dataset": "TaiwanStockShareholding",
            "collection": "shareholding",
            "disabled": True,
            "disabled_reason": "從未成功下載，已由 foreign_shareholding 取代",
            "params": {"start_date": "2020-01-01"},
            "indexes": [("stock_id", ASCENDING), ("date", DESCENDING)],
            "unique_keys": ["stock_id", "date"],
            "needs_symbols": True,
            "batch_size": 50,
            "description": "外資持股比例"
        },
        {
            "name": "借券成交明細",
            "dataset": "TaiwanStockSecuritiesLending",
            "collection": "securities_lending",
            "params": {"start_date": "2020-01-01"},
            "indexes": [("stock_id", ASCENDING), ("date", DESCENDING)],
            "unique_keys": ["stock_id", "date"],
            "needs_symbols": True,
            "batch_size": 50,
            "description": "借券交易資料"
        },
        {
            "name": "暫停融券賣出表",
            "dataset": "TaiwanStockShortSalingSuspensionAndReturnDate",
            "collection": "short_sale_suspension",
            "disabled": True,
            "disabled_reason": "從未成功下載，非核心分析需求",
            "params": {},
            "indexes": [("stock_id", ASCENDING), ("date", DESCENDING)],
            "unique_keys": ["stock_id", "suspend_date"],
            "needs_symbols": False,
            "description": "禁止融券股票名單"
        },
        {
            "name": "信用額度總量管制餘額表",
            "dataset": "TaiwanStockTotalCreditLimit",
            "collection": "total_credit_limit",
            "disabled": True,
            "disabled_reason": "從未成功下載，非核心分析需求",
            "params": {"start_date": "2020-01-01"},
            "indexes": [("date", DESCENDING)],
            "unique_keys": ["date"],
            "needs_symbols": False,
            "description": "信用交易額度管制"
        },
        {
            "name": "證券商資訊表",
            "dataset": "TaiwanSecuritiesTradersInfo",
            "collection": "securities_traders_info",
            "disabled": True,
            "disabled_reason": "從未成功下載，非核心分析需求",
            "params": {},
            "indexes": [("trader_id", ASCENDING)],
            "unique_keys": ["trader_id"],
            "needs_symbols": False,
            "description": "券商基本資料"
        }
    ],
    
    "基本面": [
        {
            "name": "綜合損益表",
            "dataset": "TaiwanStockFinancialStatement",
            "collection": "financial_statement_detail",
            "disabled": True,
            "disabled_reason": "從未成功下載，已由 financial_statements + financial_reports 取代",
            "params": {"start_date": "2020-01-01"},
            "indexes": [("stock_id", ASCENDING), ("date", DESCENDING)],
            "unique_keys": ["stock_id", "date", "type"],
            "needs_symbols": True,
            "batch_size": 50,
            "description": "損益表財報科目明細"
        },
        {
            "name": "資產負債表",
            "dataset": "TaiwanStockBalanceSheet",
            "collection": "balance_sheet_detail",
            "disabled": True,
            "disabled_reason": "從未成功下載，已由 financial_reports.balanceSheet 取代",
            "params": {"start_date": "2020-01-01"},
            "indexes": [("stock_id", ASCENDING), ("date", DESCENDING)],
            "unique_keys": ["stock_id", "date", "type"],
            "needs_symbols": True,
            "batch_size": 50,
            "description": "資產負債表財報科目明細"
        },
        {
            "name": "現金流量表",
            "dataset": "TaiwanStockCashFlowsStatement",
            "collection": "cash_flows_detail",
            "disabled": True,
            "disabled_reason": "從未成功下載，已由 financial_reports.cashflowStatement 取代",
            "params": {"start_date": "2020-01-01"},
            "indexes": [("stock_id", ASCENDING), ("date", DESCENDING)],
            "unique_keys": ["stock_id", "date", "type"],
            "needs_symbols": True,
            "batch_size": 50,
            "description": "現金流量表財報科目明細"
        },
        {
            "name": "股利政策表",
            "dataset": "TaiwanStockDividend",
            "collection": "dividend_detail",
            "params": {},
            "indexes": [("stock_id", ASCENDING), ("date", DESCENDING)],
            "unique_keys": ["stock_id", "date"],
            "needs_symbols": True,
            "batch_size": 100,
            "description": "股利發放計畫"
        },
        {
            "name": "除權除息結果表",
            "dataset": "TaiwanStockDividendResult",
            "collection": "dividend_results",
            "params": {},
            "indexes": [("stock_id", ASCENDING), ("date", DESCENDING)],
            "unique_keys": ["stock_id", "date"],
            "needs_symbols": True,
            "batch_size": 100,
            "description": "實際除權息資料"
        },
        {
            "name": "月營收表",
            "dataset": "TaiwanStockMonthRevenue",
            "collection": "month_revenue_detail",
            "params": {"start_date": "2020-01-01"},
            "indexes": [("stock_id", ASCENDING), ("date", DESCENDING)],
            "unique_keys": ["stock_id", "date"],
            "needs_symbols": True,
            "batch_size": 100,
            "description": "每月營收公告"
        },
        {
            "name": "減資恢復買賣參考價格",
            "dataset": "TaiwanStockCapitalReductionReferencePrice",
            "collection": "capital_reduction_price",
            "params": {},
            "indexes": [("stock_id", ASCENDING), ("date", DESCENDING)],
            "unique_keys": ["stock_id", "date"],
            "needs_symbols": False,
            "description": "減資參考價"
        },
        {
            "name": "台股下市資料表",
            "dataset": "TaiwanStockDelisting",
            "collection": "delisting",
            "params": {},
            "indexes": [("stock_id", ASCENDING)],
            "unique_keys": ["stock_id"],
            "needs_symbols": False,
            "description": "下市股票清單"
        },
        {
            "name": "台股分割後參考價",
            "dataset": "TaiwanStockSplitReferencePrice",
            "collection": "split_reference_price",
            "params": {},
            "indexes": [("stock_id", ASCENDING), ("date", DESCENDING)],
            "unique_keys": ["stock_id", "date"],
            "needs_symbols": False,
            "description": "股票分割參考價"
        },
        {
            "name": "台灣股票變更面額恢復買賣參考價格",
            "dataset": "TaiwanStockChangeParValueReferencePrice",
            "collection": "change_par_value_price",
            "params": {},
            "indexes": [("stock_id", ASCENDING), ("date", DESCENDING)],
            "unique_keys": ["stock_id", "date"],
            "needs_symbols": False,
            "description": "變更面額參考價"
        }
    ],
    
    "衍生性金融商品": [
        {
            "name": "期貨日成交資訊",
            "dataset": "TaiwanFuturesDaily",
            "collection": "futures_daily",
            "params": {"start_date": "2024-01-01"},
            "indexes": [("futures_id", ASCENDING), ("date", DESCENDING)],
            "unique_keys": ["futures_id", "date"],
            "needs_symbols": False,
            "description": "期貨每日行情"
        },
        {
            "name": "選擇權日成交資訊",
            "dataset": "TaiwanOptionsDaily",
            "collection": "options_daily",
            "params": {"start_date": "2024-01-01"},
            "indexes": [("contract_name", ASCENDING), ("date", DESCENDING)],
            "unique_keys": ["contract_name", "date"],
            "needs_symbols": False,
            "description": "選擇權每日行情"
        },
        {
            "name": "期貨三大法人買賣",
            "dataset": "TaiwanFuturesInstitutionalInvestors",
            "collection": "futures_institutional",
            "params": {"start_date": "2024-01-01"},
            "indexes": [("futures_id", ASCENDING), ("date", DESCENDING)],
            "unique_keys": ["futures_id", "date", "name"],
            "needs_symbols": False,
            "description": "期貨三大法人部位"
        },
        {
            "name": "選擇權三大法人買賣",
            "dataset": "TaiwanOptionsInstitutionalInvestors",
            "collection": "options_institutional",
            "params": {"start_date": "2024-01-01"},
            "indexes": [("contract_name", ASCENDING), ("date", DESCENDING)],
            "unique_keys": ["contract_name", "date", "name"],
            "needs_symbols": False,
            "description": "選擇權三大法人部位"
        },
        {
            "name": "期貨各券商每日交易",
            "dataset": "TaiwanFuturesTraders",
            "collection": "futures_traders",
            "params": {"start_date": "2024-01-01"},
            "indexes": [("date", DESCENDING), ("trader_id", ASCENDING)],
            "unique_keys": ["date", "trader_id", "futures_id"],
            "needs_symbols": False,
            "description": "期貨分點交易資料"
        },
        {
            "name": "選擇權各券商每日交易",
            "dataset": "TaiwanOptionsTraders",
            "collection": "options_traders",
            "params": {"start_date": "2024-01-01"},
            "indexes": [("date", DESCENDING), ("trader_id", ASCENDING)],
            "unique_keys": ["date", "trader_id", "contract_name"],
            "needs_symbols": False,
            "description": "選擇權分點交易資料"
        }
    ],
    
    "其他": [
        {
            "name": "黃金價格表",
            "dataset": "GoldPrice",
            "collection": "gold_price",
            "params": {"start_date": "2020-01-01"},
            "indexes": [("date", DESCENDING)],
            "unique_keys": ["date"],
            "needs_symbols": False,
            "description": "國際黃金現貨價格"
        },
        {
            "name": "原油資料表",
            "dataset": "CrudeOilPrices",
            "collection": "crude_oil_price",
            "params": {"start_date": "2020-01-01"},
            "indexes": [("date", DESCENDING)],
            "unique_keys": ["date", "name"],
            "needs_symbols": False,
            "disabled": True,
            "disabled_reason": "FinMind API 已移除 (HTTP 400) - 2026-02-22 測試確認",
            "description": "國際原油期貨價格"
        },
        {
            "name": "外幣對台幣資料表",
            "dataset": "ExchangeRate",
            "collection": "exchange_rate",
            "params": {"start_date": "2020-01-01"},
            "indexes": [("date", DESCENDING), ("currency", ASCENDING)],
            "unique_keys": ["date", "currency"],
            "needs_symbols": False,
            "disabled": True,
            "disabled_reason": "FinMind API 已移除 (HTTP 400) - 2026-02-22 測試確認",
            "description": "外匯匯率"
        },
        {
            "name": "央行利率資料表",
            "dataset": "GovernmentBondsYield",
            "collection": "government_bonds_yield",
            "params": {"start_date": "2020-01-01"},
            "indexes": [("date", DESCENDING)],
            "unique_keys": ["date", "duration"],
            "needs_symbols": False,
            "disabled": True,
            "disabled_reason": "FinMind API 已移除 (HTTP 400) - 2026-02-22 測試確認",
            "description": "政府公債殖利率"
        },
        {
            "name": "台股相關新聞",
            "dataset": "TaiwanStockNews",
            "collection": "stock_news",
            "params": {"start_date": (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")},
            "indexes": [("stock_id", ASCENDING), ("date", DESCENDING)],
            "unique_keys": ["stock_id", "date", "title"],
            "needs_symbols": True,
            "batch_size": 20,
            "disabled": True,
            "disabled_reason": "FinMind API 已移除 (HTTP 400) - 2026-02-22 測試確認",
            "description": "個股新聞（近 30 天）"
        }
    ]
}


def get_all_tables():
    """獲取所有資料表配置"""
    all_tables = []
    for category, tables in DATA_TABLES.items():
        for table in tables:
            table['category'] = category
            all_tables.append(table)
    return all_tables


def get_table_by_name(name: str):
    """根據名稱獲取資料表配置"""
    for category, tables in DATA_TABLES.items():
        for table in tables:
            if table['name'] == name:
                table['category'] = category
                return table
    return None


def get_tables_by_category(category: str):
    """根據類別獲取資料表列表"""
    return DATA_TABLES.get(category, [])
