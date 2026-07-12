#!/usr/bin/env python3
"""
修正資料庫中的 ROE 值 - Fix Stored ROE Values in Database
重新計算所有季度報表的 ROE，使用正確的年化邏輯
"""

from pymongo import MongoClient
import sys
from typing import Dict

MONGO_URI = "mongodb://localhost:27017"
MONGO_DB = "tw_stock_analysis"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'

def recalculate_roe(doc: Dict) -> float:
    """重新計算 ROE（含季度年化）"""
    try:
        # 提取資料
        revenue = doc.get('incomeStatement', {}).get('revenue', 0)
        net_income = doc.get('incomeStatement', {}).get('netIncome', 0)
        total_assets = doc.get('balanceSheet', {}).get('totalAssets', 0)
        equity = doc.get('balanceSheet', {}).get('equity', 0)
        fiscal_period = doc.get('fiscalPeriod', '')
        
        if revenue == 0 or total_assets == 0 or equity == 0:
            return None
        
        # 判斷是否為季度資料，進行年化
        is_quarterly = fiscal_period.startswith('Q')
        annualization_factor = 4 if is_quarterly else 1
        
        # 計算年化營收
        annualized_revenue = revenue * annualization_factor
        
        # 杜邦分析三步驟
        net_margin = (net_income / revenue)  # 淨利率（不年化）
        asset_turnover = annualized_revenue / total_assets  # 資產週轉率（年化）
        equity_multiplier = total_assets / equity  # 權益乘數
        
        # ROE = 淨利率 × 資產週轉率 × 權益乘數
        roe = net_margin * asset_turnover * equity_multiplier * 100
        
        return roe
    
    except Exception as e:
        print(f"{Colors.RED}計算錯誤: {str(e)}{Colors.RESET}")
        return None

def main():
    print(f"""
{Colors.BLUE}{'='*80}
修正資料庫 ROE 值 - Fix Database ROE Values
Taiwan Stock Analysis System
{'='*80}{Colors.RESET}

連接資料庫...
""")
    
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        db = client[MONGO_DB]
        client.server_info()
        print(f"{Colors.GREEN}✅ MongoDB 連接成功{Colors.RESET}\n")
    except Exception as e:
        print(f"{Colors.RED}❌ 無法連接 MongoDB: {str(e)}{Colors.RESET}")
        sys.exit(1)
    
    # 找出所有需要修正的季度報表
    collection = db.financial_reports
    
    # 統計
    total = collection.count_documents({})
    quarterly = collection.count_documents({'fiscalPeriod': {'$regex': '^Q'}})
    
    print(f"總財報數: {total:,}")
    print(f"季度報表數: {quarterly:,} ({quarterly/total*100:.1f}%)")
    print(f"\n開始重新計算 ROE...\n")
    
    # 批次處理
    updated = 0
    skipped = 0
    errors = 0
    
    cursor = collection.find({'fiscalPeriod': {'$regex': '^Q'}})
    
    for doc in cursor:
        symbol = doc.get('symbol', 'N/A')
        fiscal_year = doc.get('fiscalYear', 'N/A')
        fiscal_period = doc.get('fiscalPeriod', 'N/A')
        
        old_roe = doc.get('ratios', {}).get('roe', 0)
        
        # 重新計算
        new_roe = recalculate_roe(doc)
        
        if new_roe is None:
            skipped += 1
            continue
        
        # 檢查是否需要更新（差異超過 0.1%）
        diff = abs(new_roe - old_roe)
        
        if diff > 0.1:
            try:
                # 更新資料庫
                collection.update_one(
                    {'_id': doc['_id']},
                    {'$set': {'ratios.roe': new_roe}}
                )
                
                updated += 1
                
                # 顯示重要變化
                if diff > 10:  # 差異超過 10% 才顯示
                    print(f"{Colors.YELLOW}{symbol:6} {fiscal_year}{fiscal_period}: " +
                          f"{old_roe:6.2f}% → {new_roe:6.2f}% (Δ {diff:+6.2f}%){Colors.RESET}")
            except Exception as e:
                errors += 1
                print(f"{Colors.RED}更新失敗 {symbol} {fiscal_year}{fiscal_period}: {str(e)}{Colors.RESET}")
    
    # 完成報告
    print(f"\n{Colors.BLUE}{'='*80}{Colors.RESET}")
    print(f"處理完成！")
    print(f"  {Colors.GREEN}✅ 已更新: {updated:,} 筆{Colors.RESET}")
    print(f"  ⏭  跳過: {skipped:,} 筆（資料不完整）")
    
    if errors > 0:
        print(f"  {Colors.RED}❌ 錯誤: {errors:,} 筆{Colors.RESET}")
    
    print(f"{Colors.BLUE}{'='*80}{Colors.RESET}\n")
    
    # 驗證修正結果（抽樣檢查台積電）
    print(f"驗證修正結果（台積電 2330）:")
    
    tsmc_q3 = collection.find_one({
        'symbol': '2330',
        'fiscalYear': 2024,
        'fiscalPeriod': 'Q3'
    })
    
    if tsmc_q3:
        roe = tsmc_q3.get('ratios', {}).get('roe', 0)
        print(f"  2024 Q3 ROE: {roe:.2f}%")
        
        if 30 <= roe <= 35:
            print(f"  {Colors.GREEN}✅ ROE 值正確（在合理範圍內）{Colors.RESET}")
        else:
            print(f"  {Colors.YELLOW}⚠️  ROE 值異常: {roe:.2f}%{Colors.RESET}")
    
    print()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}處理已中斷{Colors.RESET}")
        sys.exit(2)
    except Exception as e:
        print(f"\n{Colors.RED}嚴重錯誤: {str(e)}{Colors.RESET}")
        import traceback
        traceback.print_exc()
        sys.exit(3)
