#!/usr/bin/env python3
"""
形態學12神招 - 單股測試
測試單一股票的型態識別
"""

import sys
from pathlib import Path

# 添加專案路徑
project_root = Path('/home/mdsadmin/Stock/tw-stock-analysis')
sys.path.insert(0, str(project_root))

from pattern_recognition.patterns_12_masters import Pattern12Masters
from pymongo import MongoClient
import pandas as pd
from datetime import datetime

def test_single_stock(symbol='2330'):
    """測試單一股票"""
    print("=" * 80)
    print(f"📊 測試股票: {symbol}")
    print("=" * 80)
    
    # 連接資料庫
    client = MongoClient('mongodb://localhost:27017/')
    db = client['tw_stock_analysis']
    
    # 取得資料
    print(f"\n1. 從資料庫載入{symbol}的價格資料...")
    cursor = db.stock_price.find(
        {'symbol': symbol},
        {'_id': 0}
    ).sort('date', 1).limit(250)
    
    data = list(cursor)
    print(f"   載入 {len(data)} 筆資料")
    
    if len(data) < 60:
        print(f"   ❌ 資料不足（需要至少60筆）")
        return
    
    # 建立DataFrame
    df = pd.DataFrame(data)
    
    # 確保必要欄位
    required_cols = ['date', 'open', 'high', 'low', 'close', 'volume']
    missing = [col for col in required_cols if col not in df.columns]
    
    if missing:
        print(f"   ❌ 缺少欄位: {missing}")
        return
    
    print(f"   ✅ 資料格式正確")
    print(f"   日期範圍: {df['date'].iloc[0]} ~ {df['date'].iloc[-1]}")
    print(f"   最新收盤價: {df['close'].iloc[-1]}")
    
    # 測試型態識別
    print(f"\n2. 開始型態識別...")
    detector = Pattern12Masters()
    
    signals = detector.scan_all_patterns(df, symbol)
    
    print(f"\n3. 識別結果:")
    print(f"   找到 {len(signals)} 個型態信號")
    
    if signals:
        print(f"\n詳細信號:")
        for i, signal in enumerate(signals, 1):
            print(f"\n   信號 {i}:")
            print(f"      型態: {signal.pattern_name}")
            print(f"      類型: {signal.pattern_type} ({signal.signal_type})")
            print(f"      信心度: {signal.confidence*100:.1f}%")
            print(f"      當前價: {signal.current_price:.2f}")
            print(f"      進場價: {signal.entry_price:.2f}")
            print(f"      停損價: {signal.stop_loss:.2f}")
            print(f"      目標價1: {signal.target_1:.2f}")
            if signal.target_2:
                print(f"      目標價2: {signal.target_2:.2f}")
            print(f"      潛在獲利: {signal.potential_gain:.2f}%")
            print(f"      風險報酬比: {signal.risk_reward:.2f}:1")
            print(f"      狀態: {signal.status}")
    else:
        print(f"   ⚠️  未找到任何型態")
        print(f"\n   可能原因:")
        print(f"      1. 該股票目前沒有形成經典型態")
        print(f"      2. 型態尚未完成（forming狀態）")
        print(f"      3. 信心度不足")
    
    client.close()
    print("\n" + "=" * 80)

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='測試單一股票型態識別')
    parser.add_argument('--symbol', default='2330', help='股票代碼')
    args = parser.parse_args()
    
    test_single_stock(args.symbol)
