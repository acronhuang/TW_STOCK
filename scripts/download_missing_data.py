#!/usr/bin/env python3
"""
FinMind 缺失數據下載腳本
專門下載 dividend, holdings, institutional_trading
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from FinMind.data import DataLoader
from pymongo import MongoClient
from datetime import datetime, timedelta
from tqdm import tqdm
import time

FINMIND_API_TOKEN = os.getenv('FINMIND_API_TOKEN', '')

class MissingDataDownloader:
    def __init__(self, api_token):
        self.api = DataLoader()
        self.api.login_by_token(api_token=api_token)
        self.client = MongoClient('mongodb://localhost:27017/')
        self.db = self.client['tw_stock_analysis']
        
    def test_api(self):
        """測試 API 是否可用"""
        try:
            df = self.api.taiwan_stock_dividend(stock_id='2330', start_date='2024-01-01', end_date='2024-12-31')
            if isinstance(df, dict) and df.get('status') == 402:
                return False, "API 達到請求上限"
            if hasattr(df, 'empty'):
                return True, "API 正常"
            return False, "API 返回異常"
        except KeyError as e:
            if str(e) == "'data'":
                return False, "API 達到請求上限"
            return False, str(e)
        except Exception as e:
            return False, str(e)
    
    def get_stock_list(self):
        """從資料庫獲取股票列表"""
        stocks = list(self.db.stock_list.find({}, {'stock_id': 1}))
        return [s['stock_id'] for s in stocks if s.get('stock_id')]
    
    def download_dividend(self, stock_ids, start_date, end_date):
        """下載除權息數據"""
        print(f"\n下載除權息數據...")
        print(f"股票數: {len(stock_ids)}")
        
        records = []
        success = 0
        
        for stock_id in tqdm(stock_ids, desc='dividend'):
            try:
                df = self.api.taiwan_stock_dividend(stock_id=stock_id)
                
                if isinstance(df, dict) and df.get('status') == 402:
                    print(f"\n⚠️  API 達到請求上限（已處理 {success}/{len(stock_ids)}）")
                    break
                
                if hasattr(df, 'empty') and not df.empty:
                    # 篩選日期範圍
                    df = df[(df['date'] >= start_date) & (df['date'] <= end_date)]
                    if not df.empty:
                        data = df.to_dict('records')
                        records.extend(data)
                        success += 1
                
                time.sleep(0.1)  # 避免請求過快
                
            except Exception as e:
                if "'data'" in str(e):
                    print(f"\n⚠️  API 達到請求上限（已處理 {success}/{len(stock_ids)}）")
                    break
                continue
        
        # 儲存到資料庫
        if records:
            from pymongo import UpdateOne
            operations = [
                UpdateOne(
                    {'stock_id': r['stock_id'], 'date': r['date']},
                    {'$set': r},
                    upsert=True
                )
                for r in records
            ]
            result = self.db.dividend.bulk_write(operations)
            print(f"✓ dividend: 成功 {success} 支，記錄 {len(records)} 筆")
            return success, len(records)
        
        return success, 0
    
    def download_holdings(self, stock_ids, start_date, end_date):
        """下載大戶持股數據"""
        print(f"\n下載大戶持股數據...")
        print(f"股票數: {len(stock_ids)}")
        
        records = []
        success = 0
        
        for stock_id in tqdm(stock_ids, desc='holdings'):
            try:
                df = self.api.taiwan_stock_holding_shares_per(
                    stock_id=stock_id,
                    start_date=start_date,
                    end_date=end_date
                )
                
                if isinstance(df, dict) and df.get('status') == 402:
                    print(f"\n⚠️  API 達到請求上限（已處理 {success}/{len(stock_ids)}）")
                    break
                
                if hasattr(df, 'empty') and not df.empty:
                    data = df.to_dict('records')
                    records.extend(data)
                    success += 1
                
                time.sleep(0.1)
                
            except Exception as e:
                if "'data'" in str(e):
                    print(f"\n⚠️  API 達到請求上限（已處理 {success}/{len(stock_ids)}）")
                    break
                continue
        
        if records:
            from pymongo import UpdateOne
            operations = [
                UpdateOne(
                    {'stock_id': r['stock_id'], 'date': r['date']},
                    {'$set': r},
                    upsert=True
                )
                for r in records
            ]
            result = self.db.institutional_holdings.bulk_write(operations)
            print(f"✓ holdings: 成功 {success} 支，記錄 {len(records)} 筆")
            return success, len(records)
        
        return success, 0
    
    def download_trading(self, stock_ids, start_date, end_date):
        """下載法人買賣超數據"""
        print(f"\n下載法人買賣超數據...")
        print(f"股票數: {len(stock_ids)}")
        
        records = []
        success = 0
        
        for stock_id in tqdm(stock_ids, desc='trading'):
            try:
                df = self.api.taiwan_stock_institutional_investors(
                    stock_id=stock_id,
                    start_date=start_date,
                    end_date=end_date
                )
                
                if isinstance(df, dict) and df.get('status') == 402:
                    print(f"\n⚠️  API 達到請求上限（已處理 {success}/{len(stock_ids)}）")
                    break
                
                if hasattr(df, 'empty') and not df.empty:
                    data = df.to_dict('records')
                    records.extend(data)
                    success += 1
                
                time.sleep(0.1)
                
            except Exception as e:
                if "'data'" in str(e):
                    print(f"\n⚠️  API 達到請求上限（已處理 {success}/{len(stock_ids)}）")
                    break
                continue
        
        if records:
            from pymongo import UpdateOne
            operations = [
                UpdateOne(
                    {'stock_id': r['stock_id'], 'date': r['date']},
                    {'$set': r},
                    upsert=True
                )
                for r in records
            ]
            result = self.db.institutional_trading.bulk_write(operations)
            print(f"✓ trading: 成功 {success} 支，記錄 {len(records)} 筆")
            return success, len(records)
        
        return success, 0


def main():
    if not FINMIND_API_TOKEN:
        print("✗ 請設定 FINMIND_API_TOKEN")
        return 1
    
    print("="*70)
    print("FinMind 缺失數據下載")
    print("="*70)
    
    downloader = MissingDataDownloader(FINMIND_API_TOKEN)
    
    # 測試 API
    print("\n測試 API...")
    api_ok, msg = downloader.test_api()
    if not api_ok:
        print(f"✗ {msg}")
        print("\n建議:")
        print("  1. 等待 1 小時後重試")
        print("  2. 或升級到 FinMind Premium")
        return 1
    
    print(f"✓ {msg}")
    
    # 獲取股票列表
    stock_ids = downloader.get_stock_list()
    print(f"\n總股票數: {len(stock_ids)}")
    
    # 日期範圍（過去 5 年）
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=365*5)).strftime('%Y-%m-%d')
    print(f"期間: {start_date} ~ {end_date}")
    
    # 下載數據
    results = {}
    
    # 1. dividend
    s, r = downloader.download_dividend(stock_ids, start_date, end_date)
    results['dividend'] = {'stocks': s, 'records': r}
    
    # 2. holdings  
    s, r = downloader.download_holdings(stock_ids, start_date, end_date)
    results['holdings'] = {'stocks': s, 'records': r}
    
    # 3. trading
    s, r = downloader.download_trading(stock_ids, start_date, end_date)
    results['trading'] = {'stocks': s, 'records': r}
    
    # 總結
    print("\n" + "="*70)
    print("下載完成")
    print("="*70)
    for name, data in results.items():
        print(f"{name:20} {data['stocks']:>4} 支  {data['records']:>8,} 筆")
    print("="*70)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
