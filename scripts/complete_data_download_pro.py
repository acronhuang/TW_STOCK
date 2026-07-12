#!/usr/bin/env python3
"""
完整資料下載腳本 (專業版)
使用付費 API 下載所有 43 個 FinMind 資料表
"""

import requests
import time
from datetime import datetime, timedelta
from pymongo import MongoClient, ASCENDING, DESCENDING
import logging
from typing import List, Dict
import os
import sys

# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'logs/complete_download_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# FinMind API 設定
API_TOKEN = os.getenv("FINMIND_API_TOKEN", "")
API_BASE_URL = "https://api.finmindtrade.com/api/v4/data"
API_QUOTA_PER_HOUR = 600
API_CALL_COUNT = 0

# MongoDB 連線
client = MongoClient('mongodb://localhost:27017/')
db = client['tw_stock_analysis']

# 完整的 43 個資料表配置
DATA_TABLES = {
    "技術面": [
        {
            "name": "台股總覽",
            "dataset": "TaiwanStockInfo",
            "collection": "taiwan_stock_info",
            "params": {},
            "indexes": [("stock_id", ASCENDING)],
            "needs_symbols": False
        },
        {
            "name": "台灣股價資料表",
            "dataset": "TaiwanStockPrice",
            "collection": "stock_price",
            "params": {"start_date": "2020-01-01"},
            "indexes": [("stock_id", ASCENDING), ("date", DESCENDING)],
            "needs_symbols": True,
            "batch_size": 50
        },
        {
            "name": "個股 PER、PBR",
            "dataset": "TaiwanStockPER",
            "collection": "taiwan_stock_per",
            "params": {"start_date": "2020-01-01"},
            "indexes": [("stock_id", ASCENDING), ("date", DESCENDING)],
            "needs_symbols": True,
            "batch_size": 50
        },
        {
            "name": "台股加權指數",
            "dataset": "TaiwanVariousIndicators5Seconds",
            "collection": "market_statistics",
            "params": {"start_date": "2025-01-01"},
            "indexes": [("date", DESCENDING)],
            "needs_symbols": False
        },
        {
            "name": "台股交易日",
            "dataset": "TaiwanStockTradingDate",
            "collection": "trading_dates",
            "params": {},
            "indexes": [("date", DESCENDING)],
            "needs_symbols": False
        },
        {
            "name": "台灣類股股價表",
            "dataset": "TaiwanStockIndustryPrice",
            "collection": "industry_price",
            "params": {"start_date": "2020-01-01"},
            "indexes": [("industry", ASCENDING), ("date", DESCENDING)],
            "needs_symbols": False
        },
        {
            "name": "每 5 秒委託成交統計",
            "dataset": "TaiwanStockStatisticsOfOrderBookAndTrade",
            "collection": "order_statistics_5s",
            "params": {"start_date": (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")},
            "indexes": [("stock_id", ASCENDING), ("date", DESCENDING)],
            "needs_symbols": True,
            "batch_size": 20
        },
        {
            "name": "當日沖銷交易標的",
            "dataset": "TaiwanStockDayTrading",
            "collection": "day_trading_targets",
            "params": {},
            "indexes": [("date", DESCENDING)],
            "needs_symbols": False
        },
        {
            "name": "加權、櫃買報酬指數",
            "dataset": "TaiwanStockTotalReturnIndex",
            "collection": "total_return_index",
            "params": {"start_date": "2020-01-01"},
            "indexes": [("date", DESCENDING)],
            "needs_symbols": False
        }
    ],
    
    "籌碼面": [
        {
            "name": "個股融資融劵表",
            "dataset": "TaiwanStockMarginPurchaseShortSale",
            "collection": "margin_purchase_short_sale",
            "params": {"start_date": "2020-01-01"},
            "indexes": [("stock_id", ASCENDING), ("date", DESCENDING)],
            "needs_symbols": True,
            "batch_size": 50
        },
        {
            "name": "整體市場融資融劵表",
            "dataset": "TaiwanStockTotalMarginPurchaseShortSale",
            "collection": "total_margin",
            "params": {"start_date": "2020-01-01"},
            "indexes": [("date", DESCENDING)],
            "needs_symbols": False
        },
        {
            "name": "個股三大法人買賣表",
            "dataset": "TaiwanStockInstitutionalInvestors",
            "collection": "institutional_investors_detail",
            "params": {"start_date": "2020-01-01"},
            "indexes": [("stock_id", ASCENDING), ("date", DESCENDING)],
            "needs_symbols": True,
            "batch_size": 50
        },
        {
            "name": "整體三大市場法人買賣表",
            "dataset": "TaiwanStockTotalInstitutionalInvestors",
            "collection": "total_institutional_investors",
            "params": {"start_date": "2020-01-01"},
            "indexes": [("date", DESCENDING)],
            "needs_symbols": False
        },
        {
            "name": "外資持股表",
            "dataset": "TaiwanStockShareholding",
            "collection": "shareholding",
            "params": {"start_date": "2020-01-01"},
            "indexes": [("stock_id", ASCENDING), ("date", DESCENDING)],
            "needs_symbols": True,
            "batch_size": 50
        },
        {
            "name": "借券成交明細",
            "dataset": "TaiwanStockSecuritiesLending",
            "collection": "securities_lending",
            "params": {"start_date": "2020-01-01"},
            "indexes": [("stock_id", ASCENDING), ("date", DESCENDING)],
            "needs_symbols": True,
            "batch_size": 50
        },
        {
            "name": "暫停融券賣出表",
            "dataset": "TaiwanStockShortSalingSuspensionAndReturnDate",
            "collection": "short_sale_suspension",
            "params": {},
            "indexes": [("stock_id", ASCENDING), ("date", DESCENDING)],
            "needs_symbols": False
        },
        {
            "name": "信用額度總量管制餘額表",
            "dataset": "TaiwanStockTotalCreditLimit",
            "collection": "total_credit_limit",
            "params": {"start_date": "2020-01-01"},
            "indexes": [("date", DESCENDING)],
            "needs_symbols": False
        },
        {
            "name": "證券商資訊表",
            "dataset": "TaiwanSecuritiesTradersInfo",
            "collection": "securities_traders_info",
            "params": {},
            "indexes": [("trader_id", ASCENDING)],
            "needs_symbols": False
        }
    ],
    
    "基本面": [
        {
            "name": "綜合損益表",
            "dataset": "TaiwanStockFinancialStatement",
            "collection": "financial_statement_detail",
            "params": {"start_date": "2020-01-01"},
            "indexes": [("stock_id", ASCENDING), ("date", DESCENDING)],
            "needs_symbols": True,
            "batch_size": 50
        },
        {
            "name": "資產負債表",
            "dataset": "TaiwanStockBalanceSheet",
            "collection": "balance_sheet_detail",
            "params": {"start_date": "2020-01-01"},
            "indexes": [("stock_id", ASCENDING), ("date", DESCENDING)],
            "needs_symbols": True,
            "batch_size": 50
        },
        {
            "name": "現金流量表",
            "dataset": "TaiwanStockCashFlowsStatement",
            "collection": "cash_flows_detail",
            "params": {"start_date": "2020-01-01"},
            "indexes": [("stock_id", ASCENDING), ("date", DESCENDING)],
            "needs_symbols": True,
            "batch_size": 50
        },
        {
            "name": "股利政策表",
            "dataset": "TaiwanStockDividend",
            "collection": "dividend_detail",
            "params": {},
            "indexes": [("stock_id", ASCENDING), ("date", DESCENDING)],
            "needs_symbols": True,
            "batch_size": 100
        },
        {
            "name": "除權除息結果表",
            "dataset": "TaiwanStockDividendResult",
            "collection": "dividend_results",
            "params": {},
            "indexes": [("stock_id", ASCENDING), ("date", DESCENDING)],
            "needs_symbols": True,
            "batch_size": 100
        },
        {
            "name": "月營收表",
            "dataset": "TaiwanStockMonthRevenue",
            "collection": "month_revenue_detail",
            "params": {"start_date": "2020-01-01"},
            "indexes": [("stock_id", ASCENDING), ("date", DESCENDING)],
            "needs_symbols": True,
            "batch_size": 100
        },
        {
            "name": "減資恢復買賣參考價格",
            "dataset": "TaiwanStockCapitalReductionReferencePrice",
            "collection": "capital_reduction_price",
            "params": {},
            "indexes": [("stock_id", ASCENDING), ("date", DESCENDING)],
            "needs_symbols": False
        },
        {
            "name": "台股下市資料表",
            "dataset": "TaiwanStockDelisting",
            "collection": "delisting",
            "params": {},
            "indexes": [("stock_id", ASCENDING)],
            "needs_symbols": False
        },
        {
            "name": "台股分割後參考價",
            "dataset": "TaiwanStockSplitReferencePrice",
            "collection": "split_reference_price",
            "params": {},
            "indexes": [("stock_id", ASCENDING), ("date", DESCENDING)],
            "needs_symbols": False
        },
        {
            "name": "台灣股票變更面額恢復買賣參考價格",
            "dataset": "TaiwanStockChangeParValueReferencePrice",
            "collection": "change_par_value_price",
            "params": {},
            "indexes": [("stock_id", ASCENDING), ("date", DESCENDING)],
            "needs_symbols": False
        }
    ],
    
    "衍生性金融商品": [
        {
            "name": "期貨、選擇權日成交資訊總覽",
            "dataset": "TaiwanFuturesDaily",
            "collection": "futures_daily_overview",
            "params": {"start_date": "2024-01-01"},
            "indexes": [("date", DESCENDING)],
            "needs_symbols": False
        },
        {
            "name": "期貨日成交資訊",
            "dataset": "TaiwanFuturesDaily",
            "collection": "futures_daily",
            "params": {"start_date": "2024-01-01"},
            "indexes": [("futures_id", ASCENDING), ("date", DESCENDING)],
            "needs_symbols": False
        },
        {
            "name": "選擇權日成交資訊",
            "dataset": "TaiwanOptionsDaily",
            "collection": "options_daily",
            "params": {"start_date": "2024-01-01"},
            "indexes": [("contract_name", ASCENDING), ("date", DESCENDING)],
            "needs_symbols": False
        },
        {
            "name": "期貨三大法人買賣",
            "dataset": "TaiwanFuturesInstitutionalInvestors",
            "collection": "futures_institutional",
            "params": {"start_date": "2024-01-01"},
            "indexes": [("futures_id", ASCENDING), ("date", DESCENDING)],
            "needs_symbols": False
        },
        {
            "name": "選擇權三大法人買賣",
            "dataset": "TaiwanOptionsInstitutionalInvestors",
            "collection": "options_institutional",
            "params": {"start_date": "2024-01-01"},
            "indexes": [("contract_name", ASCENDING), ("date", DESCENDING)],
            "needs_symbols": False
        },
        {
            "name": "期貨各卷商每日交易",
            "dataset": "TaiwanFuturesTraders",
            "collection": "futures_traders",
            "params": {"start_date": "2024-01-01"},
            "indexes": [("date", DESCENDING)],
            "needs_symbols": False
        },
        {
            "name": "選擇權各卷商每日交易",
            "dataset": "TaiwanOptionsTraders",
            "collection": "options_traders",
            "params": {"start_date": "2024-01-01"},
            "indexes": [("date", DESCENDING)],
            "needs_symbols": False
        }
    ],
    
    "其他": [
        {
            "name": "黃金價格表",
            "dataset": "GoldPrice",
            "collection": "gold_price",
            "params": {"start_date": "2020-01-01"},
            "indexes": [("date", DESCENDING)],
            "needs_symbols": False
        },
        {
            "name": "原油資料表",
            "dataset": "CrudeOilPrices",
            "collection": "crude_oil_price",
            "params": {"start_date": "2020-01-01"},
            "indexes": [("date", DESCENDING)],
            "needs_symbols": False
        },
        {
            "name": "美股股價",
            "dataset": "USStockPrice",
            "collection": "us_stock_price",
            "params": {"start_date": "2020-01-01", "stock_id": "AAPL"},
            "indexes": [("stock_id", ASCENDING), ("date", DESCENDING)],
            "needs_symbols": False,
            "note": "需要指定股票代碼"
        },
        {
            "name": "外幣對台幣資料表",
            "dataset": "ExchangeRate",
            "collection": "exchange_rate",
            "params": {"start_date": "2020-01-01"},
            "indexes": [("date", DESCENDING)],
            "needs_symbols": False
        },
        {
            "name": "央行利率資料表",
            "dataset": "GovernmentBondsYield",
            "collection": "government_bonds_yield",
            "params": {"start_date": "2020-01-01"},
            "indexes": [("date", DESCENDING)],
            "needs_symbols": False
        },
        {
            "name": "台股相關新聞",
            "dataset": "TaiwanStockNews",
            "collection": "stock_news",
            "params": {"start_date": (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")},
            "indexes": [("stock_id", ASCENDING), ("date", DESCENDING)],
            "needs_symbols": True,
            "batch_size": 20
        }
    ]
}


def fetch_finmind_data(dataset: str, params: Dict) -> List[Dict]:
    """從 FinMind API 獲取資料"""
    global API_CALL_COUNT
    
    try:
        all_params = {
            "dataset": dataset,
            "token": API_TOKEN,
            **params
        }
        
        response = requests.get(API_BASE_URL, params=all_params, timeout=30)
        API_CALL_COUNT += 1
        
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 200:
                return data.get('data', [])
            else:
                logger.warning(f"API 回應狀態: {data.get('status')}, 訊息: {data.get('msg')}")
                return []
        else:
            logger.error(f"HTTP 錯誤: {response.status_code}")
            return []
            
    except Exception as e:
        logger.error(f"API 請求失敗: {e}")
        return []


def get_all_symbols() -> List[str]:
    """獲取所有股票代碼"""
    symbols = db.stocks.distinct('symbol')
    logger.info(f"從資料庫獲取 {len(symbols)} 個股票代碼")
    return symbols


def create_indexes(collection_name: str, indexes: List):
    """建立索引"""
    try:
        collection = db[collection_name]
        for index in indexes:
            collection.create_index([index], background=True)
        logger.info(f"✅ {collection_name} 索引建立完成")
    except Exception as e:
        logger.warning(f"索引建立警告: {e}")


def download_table(table_config: Dict, category: str) -> Dict:
    """下載單一資料表"""
    global API_CALL_COUNT
    
    name = table_config['name']
    dataset = table_config['dataset']
    collection_name = table_config['collection']
    params = table_config.get('params', {})
    indexes = table_config.get('indexes', [])
    needs_symbols = table_config.get('needs_symbols', False)
    batch_size = table_config.get('batch_size', 100)
    
    logger.info(f"\n{'='*80}")
    logger.info(f"📥 【{category}】{name}")
    logger.info(f"   Dataset: {dataset} → {collection_name}")
    logger.info(f"   API 使用: {API_CALL_COUNT}/{API_QUOTA_PER_HOUR}")
    logger.info(f"{'='*80}")
    
    collection = db[collection_name]
    total_records = 0
    total_saved = 0
    
    try:
        if needs_symbols:
            # 需要逐股票下載
            symbols = get_all_symbols()
            logger.info(f"  處理 {min(batch_size, len(symbols))} 檔股票...")
            
            for i, symbol in enumerate(symbols[:batch_size], 1):
                if API_CALL_COUNT >= API_QUOTA_PER_HOUR - 10:
                    logger.warning(f"  ⚠️  接近 API 配額上限，暫停下載")
                    break
                
                symbol_params = {**params, "stock_id": symbol}
                data = fetch_finmind_data(dataset, symbol_params)
                
                if data:
                    for record in data:
                        record['symbol'] = symbol
                        collection.update_one(
                            {'symbol': symbol, 'date': record.get('date')},
                            {'$set': record},
                            upsert=True
                        )
                    total_records += len(data)
                    total_saved += len(data)
                    logger.info(f"  [{i}/{min(batch_size, len(symbols))}] {symbol}... ✅ {len(data)}")
                else:
                    logger.info(f"  [{i}/{min(batch_size, len(symbols))}] {symbol}... ⚠️ ")
                
                time.sleep(0.1)  # 避免請求過快
                
        else:
            # 整體下載（不需要股票代碼）
            data = fetch_finmind_data(dataset, params)
            
            if data:
                for record in data:
                    unique_key = {'date': record.get('date')}
                    if 'stock_id' in record:
                        unique_key['stock_id'] = record['stock_id']
                    
                    collection.update_one(unique_key, {'$set': record}, upsert=True)
                
                total_records = len(data)
                total_saved = len(data)
                logger.info(f"  ✅ {total_records} 筆 (存 {total_saved})")
            else:
                logger.warning(f"  ⚠️  無資料")
        
        # 建立索引
        if indexes:
            create_indexes(collection_name, indexes)
        
        return {
            "name": name,
            "category": category,
            "dataset": dataset,
            "collection": collection_name,
            "status": "success",
            "records": total_records,
            "saved": total_saved
        }
        
    except Exception as e:
        logger.error(f"  ❌ 錯誤: {e}")
        return {
            "name": name,
            "category": category,
            "status": "error",
            "error": str(e)
        }


def main():
    """主程式"""
    start_time = datetime.now()
    
    logger.info("\n" + "="*80)
    logger.info("🚀 FinMind 完整資料下載 (專業版)")
    logger.info("="*80)
    logger.info(f"📅 時間: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"💰 配額: {API_QUOTA_PER_HOUR} 次/小時")
    logger.info(f"📊 總資料表: 43 個")
    logger.info("="*80 + "\n")
    
    results = []
    task_count = 0
    
    for category, tables in DATA_TABLES.items():
        for table in tables:
            task_count += 1
            logger.info(f"\n{'#'*80}")
            logger.info(f"# [{task_count}/43] {category} - {table['name']}")
            logger.info(f"# API: {API_CALL_COUNT}/{API_QUOTA_PER_HOUR}")
            logger.info(f"{'#'*80}\n")
            
            if API_CALL_COUNT >= API_QUOTA_PER_HOUR - 10:
                logger.warning("⚠️  API 配額不足，停止下載")
                break
            
            result = download_table(table, category)
            results.append(result)
            
            # 每 10 個任務休息一下
            if task_count % 10 == 0:
                logger.info("\n⏸️  休息 5 秒...")
                time.sleep(5)
    
    # 生成報告
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    logger.info("\n" + "="*80)
    logger.info("📊 下載完成報告")
    logger.info("="*80)
    logger.info(f"總耗時: {duration:.0f} 秒")
    logger.info(f"API 使用: {API_CALL_COUNT}/{API_QUOTA_PER_HOUR}")
    logger.info(f"完成任務: {len([r for r in results if r.get('status') == 'success'])}/{len(results)}")
    
    # 統計各類別
    for category in DATA_TABLES.keys():
        category_results = [r for r in results if r.get('category') == category]
        success_count = len([r for r in category_results if r.get('status') == 'success'])
        total_records = sum(r.get('records', 0) for r in category_results)
        logger.info(f"\n{category}:")
        logger.info(f"  完成: {success_count}/{len(category_results)}")
        logger.info(f"  記錄數: {total_records:,}")
    
    logger.info("\n" + "="*80)
    logger.info("✅ 所有任務執行完畢")
    logger.info("="*80 + "\n")


if __name__ == "__main__":
    main()
