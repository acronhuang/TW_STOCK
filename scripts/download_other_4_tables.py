#!/usr/bin/env python3
"""直接测试并下载其他类别的4个表（跳过黄金）"""

import os
import sys
from datetime import datetime, timedelta
from pymongo import MongoClient

sys.path.insert(0, '/home/mdsadmin/Stock/tw-stock-analysis')
from src.downloaders.finmind_client import FinMindClient

def download_and_save(client, db, dataset, collection_name, params):
    """下载并保存单个表的数据"""
    print(f"\n{'='*70}")
    print(f"下载: {dataset} -> {collection_name}")
    print(f"参数: {params}")
    print('='*70)
    
    try:
        # 获取数据
        data = client.fetch_data(dataset, params)
        
        if not data:
            print(f"❌ 无数据返回")
            return False
        
        print(f"✅ API返回: {len(data)} 笔数据")
        
        # 保存到MongoDB
        collection = db[collection_name]
        saved_count = 0
        updated_count = 0
        
        for record in data:
            # 根据不同的表设置不同的唯一键
            if dataset == 'CrudeOilPrices':
                filter_query = {'date': record.get('date'), 'name': record.get('name')}
            elif dataset == 'ExchangeRate':
                filter_query = {'date': record.get('date'), 'currency': record.get('currency')}
            elif dataset == 'GovernmentBondsYield':
                filter_query = {'date': record.get('date'), 'duration': record.get('duration')}
            elif dataset == 'TaiwanStockNews':
                filter_query = {
                    'stock_id': record.get('stock_id'),
                    'date': record.get('date'),
                    'title': record.get('title')
                }
            else:
                filter_query = {'date': record.get('date')}
            
            record['updated_at'] = datetime.now()
            result = collection.update_one(filter_query, {'$set': record}, upsert=True)
            
            if result.upserted_id:
                saved_count += 1
            elif result.modified_count > 0:
                updated_count += 1
        
        print(f"✅ MongoDB保存: 新增 {saved_count} 笔, 更新 {updated_count} 笔")
        return True
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    api_token = os.getenv('FINMIND_API_TOKEN')
    if not api_token:
        print("❌ 错误: 未设置 FINMIND_API_TOKEN")
        sys.exit(1)
    
    client = FinMindClient(api_token)
    mongo_client = MongoClient('mongodb://localhost:27017/')
    db = mongo_client['tw_stock_analysis']
    
    # 定义4个表（跳过黄金）
    tables = [
        {
            "name": "原油價格",
            "dataset": "CrudeOilPrices",
            "collection": "crude_oil_price",
            "params": {"start_date": "2020-01-01"}
        },
        {
            "name": "外匯匯率",
            "dataset": "ExchangeRate",
            "collection": "exchange_rate",
            "params": {"start_date": "2020-01-01"}
        },
        {
            "name": "央行利率",
            "dataset": "GovernmentBondsYield",
            "collection": "government_bonds_yield",
            "params": {"start_date": "2020-01-01"}
        },
        {
            "name": "台股新聞",
            "dataset": "TaiwanStockNews",
            "collection": "stock_news",
            "params": {
                "start_date": (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),
                "stock_id": "2330"  # 先测试台积电
            }
        }
    ]
    
    print("="*70)
    print("直接下载「其他」类别的 4 个资料表（跳过黄金）")
    print("="*70)
    
    results = []
    for table in tables:
        success = download_and_save(
            client,
            db,
            table['dataset'],
            table['collection'],
            table['params']
        )
        results.append({'name': table['name'], 'success': success})
    
    # 汇总
    print(f"\n{'='*70}")
    print("下载结果汇总")
    print('='*70)
    
    success_count = sum(1 for r in results if r['success'])
    for r in results:
        status = "✅" if r['success'] else "❌"
        print(f"{status} {r['name']}")
    
    print('='*70)
    print(f"成功率: {success_count}/4 ({success_count*25}%)")
    print('='*70)
    
    mongo_client.close()
    return 0 if success_count == 4 else 1


if __name__ == '__main__':
    sys.exit(main())
