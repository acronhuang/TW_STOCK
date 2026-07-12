#!/usr/bin/env python3
"""
监控股利数据下载进度
"""
from pymongo import MongoClient
import time
from datetime import datetime

def show_progress():
    client = MongoClient('mongodb://localhost:27017/')
    db = client['tw_stock_analysis']
    
    print('\n' + '='*70)
    print(f'股利数据下载进度监控 - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print('='*70)
    
    # 总股票数
    total_stocks = db.tickers.count_documents({})
    
    # dividend_detail 进度
    detail_count = db.dividend_detail.count_documents({}) if 'dividend_detail' in db.list_collection_names() else 0
    detail_stocks = len(db.dividend_detail.distinct('stock_id')) if 'dividend_detail' in db.list_collection_names() else 0
    
    print(f'\n📊 dividend_detail (股利政策表):')
    print(f'  总记录数: {detail_count:,} 笔')
    print(f'  覆盖股票: {detail_stocks}/{total_stocks} 档 ({detail_stocks/total_stocks*100:.1f}%)')
    
    # dividend_results 进度  
    result_count = db.dividend_results.count_documents({})
    result_stocks = len(db.dividend_results.distinct('stock_id'))
    
    print(f'\n📊 dividend_results (除权除息结果表):')
    print(f'  总记录数: {result_count:,} 笔')
    print(f'  覆盖股票: {result_stocks}/{total_stocks} 档 ({result_stocks/total_stocks*100:.1f}%)')
    
    # 最近更新
    if detail_count > 0:
        latest = db.dividend_detail.find_one(sort=[('_id', -1)])
        if latest:
            print(f'\n📅 最近下载:')
            print(f'  股票: {latest.get("stock_id")}')
            print(f'  日期: {latest.get("date")}')
    
    client.close()
    print('\n' + '='*70 + '\n')

if __name__ == '__main__':
    try:
        while True:
            show_progress()
            print('等待 30 秒后刷新... (Ctrl+C 退出)')
            time.sleep(30)
    except KeyboardInterrupt:
        print('\n\n✅ 监控已停止')
