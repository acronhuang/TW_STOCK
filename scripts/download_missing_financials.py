#!/usr/bin/env python3
"""
批量下載缺失的企業財報數據

目標：為 1,773 支沒有財報的企業下載財報數據
"""
import os
import requests
from pymongo import MongoClient
from datetime import datetime
import time
from typing import List, Dict

# FinMind API 配置
FINMIND_TOKEN = os.getenv('FINMIND_API_TOKEN', '')
FINMIND_API = "https://api.finmindtrade.com/api/v4/data"
API_QUOTA = 600  # 每小時配額

class FinancialDataDownloader:
    def __init__(self):
        self.client = MongoClient('mongodb://localhost:27017/')
        self.db = self.client['tw_stock_analysis']
        self.api_calls_this_minute = 0
        self.last_reset = datetime.now()
        self.success_count = 0
        self.error_count = 0
        
    def get_missing_symbols(self) -> List[str]:
        """獲取沒有財報的企業股票代碼"""
        # 所有企業股票（數字開頭）
        all_symbols = self.db.stock_price.distinct('symbol')
        企業 = [s for s in all_symbols if s and s[0] in '123456789']
        
        # 有財報的股票
        有財報 = set(self.db.financial_reports.distinct('symbol')).union(
            set(self.db.financial_statements.distinct('symbol'))
        )
        
        # 缺財報的企業
        缺財報 = [s for s in 企業 if s not in 有財報]
        return sorted(缺財報)
    
    def rate_limit(self):
        """速率限制：免費版 10 次/分鐘"""
        current_time = datetime.now()
        
        # 重置計數器（每分鐘）
        if (current_time - self.last_reset).seconds >= 60:
            self.api_calls_this_minute = 0
            self.last_reset = current_time
        
        # 達到限制，等待
        if self.api_calls_this_minute >= 9:  # 保守一點，9次/分鐘
            wait_time = 60 - (current_time - self.last_reset).seconds
            if wait_time > 0:
                print(f"  ⏳ 達到速率限制，等待 {wait_time} 秒...")
                time.sleep(wait_time)
                self.api_calls_this_minute = 0
                self.last_reset = datetime.now()
    
    def fetch_financial_data(self, dataset: str, symbol: str, 
                            start_date: str = '2020-01-01',
                            end_date: str = '2025-12-31') -> List[Dict]:
        """從 FinMind 獲取財報數據"""
        self.rate_limit()
        
        try:
            params = {
                "dataset": dataset,
                "data_id": symbol,
                "start_date": start_date,
                "end_date": end_date,
                "token": FINMIND_TOKEN
            }
            
            response = requests.get(FINMIND_API, params=params, timeout=30)
            self.api_calls_this_minute += 1
            
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 200:
                    return data.get('data', [])
                else:
                    print(f"  ⚠️  API 返回狀態 {data.get('status')}: {data.get('msg', '')}")
            else:
                print(f"  ❌ HTTP {response.status_code}")
                
            return []
            
        except Exception as e:
            print(f"  ❌ 錯誤: {e}")
            return []
    
    def download_symbol_financials(self, symbol: str) -> bool:
        """下載單支股票的所有財報類型"""
        print(f"\n處理 {symbol}...")
        
        財報類型 = [
            ("TaiwanStockBalanceSheet", "資產負債表"),
            ("TaiwanStockFinancialStatement", "損益表"),
            ("TaiwanStockCashFlowsStatement", "現金流量表")
        ]
        
        success = False
        
        for dataset, name in 財報類型:
            print(f"  下載{name}...", end='')
            data = self.fetch_financial_data(dataset, symbol)
            
            if data:
                # 存入對應集合
                collection = self.db[dataset]
               
                # 批量更新
                for record in data:
                    collection.update_one(
                        {
                            'stock_id': record.get('stock_id'),
                            'date': record.get('date')
                        },
                        {'$set': record},
                        upsert=True
                    )
                
                print(f" ✅ {len(data)} 筆")
                success = True
            else:
                print(f" ⚠️  無數據")
        
        return success
    
    def run(self, limit: int = None):
        """執行批量下載"""
        缺財報 = self.get_missing_symbols()
        
        print('=' * 80)
        print('批量下載缺失的企業財報')
        print('=' * 80)
        print(f'\n待下載股票數: {len(缺財報)}')
        
        if limit:
            缺財報 = 缺財報[:limit]
            print(f'本次下載: 前 {limit} 支股票')
        
        if not FINMIND_TOKEN:
            print('\n❌ 錯誤: 未設定 FINMIND_API_TOKEN 環境變數')
            print('請執行: export FINMIND_API_TOKEN="你的token"')
            return
        
        print(f'\n開始時間: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        print(f'速率限制: 免費版 10 次/分鐘')
        print(f'預估時間: 約 {len(缺財報) * 3 / 10:.0f} 分鐘\n')
        
        start_time = time.time()
        
        for i, symbol in enumerate(缺財報, 1):
            print(f'\n[{i}/{len(缺財報)}] ', end='')
            
            if self.download_symbol_financials(symbol):
                self.success_count += 1
            else:
                self.error_count += 1
            
            # 每 10 支顯示進度
            if i % 10 == 0:
                elapsed = time.time() - start_time
                rate = i / (elapsed / 60)  # 股票/分鐘
                remaining = (len(缺財報) - i) / rate if rate > 0 else 0
                
                print(f'\n{"="*80}')
                print(f'進度: {i}/{len(缺財報)} ({i/len(缺財報)*100:.1f}%)')
                print(f'成功: {self.success_count}, 失敗: {self.error_count}')
                print(f'已用時間: {elapsed/60:.1f} 分鐘')
                print(f'預估剩餘: {remaining:.1f} 分鐘')
                print(f'{"="*80}')
        
        # 最終統計
        total_time = time.time() - start_time
        print(f'\n{"="*80}')
        print('下載完成')
        print(f'{"="*80}')
        print(f'總處理: {len(缺財報)} 支')
        print(f'成功: {self.success_count}')
        print(f'失敗: {self.error_count}')
        print(f'總耗時: {total_time/60:.1f} 分鐘')
        print(f'{"="*80}')
        
        # 重新計算覆蓋率
        print(f'\n檢查更新後覆蓋率...')
        self.check_coverage()
        
        self.client.close()
    
    def check_coverage(self):
        """檢查財報覆蓋率"""
        all_symbols = self.db.stock_price.distinct('symbol')
        企業 = [s for s in all_symbols if s and s[0] in '123456789']
        有財報 = set(self.db.financial_reports.distinct('symbol')).union(
            set(self.db.financial_statements.distinct('symbol'))
        )
        企業有財報 = [s for s in 企業 if s in 有財報]
        
        print(f'企業股票數: {len(企業)}')
        print(f'有財報: {len(企業有財報)} ({len(企業有財報)/len(企業)*100:.1f}%)')


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='批量下載缺失的企業財報')
    parser.add_argument('--limit', type=int, help='限制下載股票數量（測試用）')
    args = parser.parse_args()
    
    downloader = FinancialDataDownloader()
    downloader.run(limit=args.limit)
