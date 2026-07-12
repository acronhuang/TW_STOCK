#!/usr/bin/env python3
"""
测试"其他"类别的5个资料表下载
"""

import os
import sys
from datetime import datetime, timedelta

# 添加 src 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.downloaders.finmind_client import FinMindClient

def test_single_table(api_token, dataset, params):
    """测试单个表的API调用"""
    print(f"\n{'='*60}")
    print(f"测试: {dataset}")
    print(f"参数: {params}")
    print('='*60)
    
    client = FinMindClient(api_token)
    
    try:
        data = client.fetch_data(dataset, params)
        
        if data:
            print(f"✅ 成功: 获取 {len(data)} 笔数据")
            if data:
                print(f"   样本: {data[0]}")
            return True, len(data)
        else:
            print(f"❌ 失败: 无数据返回")
            return False, 0
            
    except Exception as e:
        print(f"❌ 错误: {e}")
        return False, 0


def main():
    api_token = os.getenv('FINMIND_API_TOKEN')
    if not api_token:
        print("❌ 错误: 未设置 FINMIND_API_TOKEN")
        sys.exit(1)
    
    # 定义5个表的测试参数
    tables = [
        {
            "name": "黃金價格",
            "dataset": "GoldPrice",
            "params": {"start_date": "2026-02-01"}  # 只测试最近数据
        },
        {
            "name": "原油價格",
            "dataset": "CrudeOilPrices",
            "params": {"start_date": "2026-02-01"}
        },
        {
            "name": "外匯匯率",
            "dataset": "ExchangeRate",
            "params": {"start_date": "2026-02-01"}
        },
        {
            "name": "央行利率",
            "dataset": "GovernmentBondsYield",
            "params": {"start_date": "2026-02-01"}
        },
        {
            "name": "台股新聞",
            "dataset": "TaiwanStockNews",
            "params": {
                "start_date": (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"),
                "stock_id": "2330"  # 测试台积电新聞
            }
        }
    ]
    
    print("="*70)
    print("測試「其他」類別的 5 個資料表 API 可用性")
    print("="*70)
    
    results = []
    for table in tables:
        success, count = test_single_table(api_token, table['dataset'], table['params'])
        results.append({
            'name': table['name'],
            'success': success,
            'count': count
        })
    
    # 汇总
    print(f"\n{'='*70}")
    print("測試結果匯總")
    print('='*70)
    
    success_count = sum(1 for r in results if r['success'])
    for r in results:
        status = "✅" if r['success'] else "❌"
        print(f"{status} {r['name']:12s}: {r['count']:6d} 筆")
    
    print('='*70)
    print(f"成功率: {success_count}/5 ({success_count*20}%)")
    print('='*70)
    
    return 0 if success_count == 5 else 1


if __name__ == '__main__':
    sys.exit(main())
