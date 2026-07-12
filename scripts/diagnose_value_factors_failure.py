#!/usr/bin/env python3
"""
診斷還原後的 value_factors.py 失敗原因
"""

from pymongo import MongoClient
from datetime import datetime
from bson import Decimal128

def _to_float(value):
    """統一轉換為 float"""
    if value is None:
        return None
    if isinstance(value, Decimal128):
        return float(value.to_decimal())
    return float(value)

def main():
    client = MongoClient('mongodb://localhost:27017/')
    db = client['tw_stock_analysis']
    
    test_symbol = '2330'
    test_date = datetime(2024, 2, 20)
    
    print("=" * 80)
    print("診斷 PE/PB 計算失敗原因")
    print("=" * 80)
    
    print(f"\n測試股票: {test_symbol}")
    print(f"測試日期: {test_date.strftime('%Y-%m-%d')}")
    
    # 步驟 1: 檢查股價
    print("\n【步驟 1: 檢查股價】")
    price_doc = db.stock_price.find_one({
        'symbol': test_symbol,
        'date': test_date
    })
    
    if price_doc:
        price = _to_float(price_doc.get('close'))
        print(f"✓ 找到股價: {price}")
    else:
        print(f"✗ 找不到股價")
        return
    
    # 步驟 2: 檢查財報（netIncome）
    print("\n【步驟 2: 檢查財報 (netIncome)】")
    financial_doc = db.financial_reports.find_one(
        {
            'symbol': test_symbol,
            'incomeStatement.netIncome': {'$exists': True, '$ne': None}
        },
        sort=[('fiscalYear', -1), ('fiscalPeriod', -1)]
    )
    
    if financial_doc:
        print(f"✓ 找到財報")
        print(f"  fiscalYear: {financial_doc.get('fiscalYear')}")
        print(f"  fiscalPeriod: {financial_doc.get('fiscalPeriod')}")
        income_statement = financial_doc.get('incomeStatement', {})
        net_income = _to_float(income_statement.get('netIncome'))
        print(f"  netIncome: {net_income}")
        
        if not net_income or net_income <= 0:
            print(f"  ⚠️ netIncome 無效: {net_income}")
    else:
        print(f"✗ 找不到財報 (netIncome)")
        
        # 檢查是否有任何財報
        any_financial = db.financial_reports.find_one({'symbol': test_symbol})
        if any_financial:
            print(f"  股票有財報，但查詢條件可能有問題")
            print(f"  incomeStatement 結構: {list(any_financial.get('incomeStatement', {}).keys())[:10]}")
        else:
            print(f"  股票完全沒有財報")
        return
    
    # 步驟 3: 檢查財報（equity）
    print("\n【步驟 3: 檢查財報 (equity)】")
    financial_doc_pb = db.financial_reports.find_one(
        {
            'symbol': test_symbol,
            'balanceSheet.equity': {'$exists': True, '$ne': None}
        },
        sort=[('fiscalYear', -1), ('fiscalPeriod', -1)]
    )
    
    if financial_doc_pb:
        print(f"✓ 找到財報")
        balance_sheet = financial_doc_pb.get('balanceSheet', {})
        equity = _to_float(balance_sheet.get('equity'))
        print(f"  equity: {equity}")
        
        if not equity or equity <= 0:
            print(f"  ⚠️ equity 無效: {equity}")
    else:
        print(f"✗ 找不到財報 (equity)")
        return
    
    # 步驟 4: 檢查 outstanding_shares
    print("\n【步驟 4: 檢查 outstanding_shares】")
    stock_info = db.taiwan_stock_info.find_one(
        {'stock_id': test_symbol},
        sort=[('date', -1)]
    )
    
    if stock_info:
        outstanding_shares = _to_float(stock_info.get('outstanding_shares'))
        print(f"✓ 找到 outstanding_shares: {outstanding_shares}")
        print(f"  日期: {stock_info.get('date')}")
        
        if not outstanding_shares or outstanding_shares <= 0:
            print(f"  ⚠️ outstanding_shares 無效: {outstanding_shares}")
            return
    else:
        print(f"✗ 找不到 outstanding_shares")
        return
    
    # 步驟 5: 手動計算 PE
    print("\n【步驟 5: 手動計算 PE】")
    print(f"price = {price}")
    print(f"net_income = {net_income}")
    print(f"outstanding_shares = {outstanding_shares}")
    
    eps = net_income / (outstanding_shares * 1000)
    print(f"EPS = {net_income} / ({outstanding_shares} * 1000) = {eps}")
    
    if eps > 0:
        pe = price / eps
        print(f"PE = {price} / {eps} = {pe}")
        
        if pe > 0 and pe < 1000:
            print(f"✅ PE 計算成功: {pe:.2f}")
        else:
            print(f"⚠️ PE 超出範圍: {pe}")
    else:
        print(f"❌ EPS <= 0，無法計算 PE")
    
    # 步驟 6: 手動計算 PB
    print("\n【步驟 6: 手動計算 PB】")
    print(f"price = {price}")
    print(f"equity = {equity}")
    print(f"outstanding_shares = {outstanding_shares}")
    
    bvps = equity / (outstanding_shares * 1000)
    print(f"BVPS = {equity} / ({outstanding_shares} * 1000) = {bvps}")
    
    if bvps > 0:
        pb = price / bvps
        print(f"PB = {price} / {bvps} = {pb}")
        
        if pb > 0 and pb < 100:
            print(f"✅ PB 計算成功: {pb:.2f}")
        else:
            print(f"⚠️ PB 超出範圍: {pb}")
    else:
        print(f"❌ BVPS <= 0，無法計算 PB")
    
    client.close()

if __name__ == '__main__':
    main()
