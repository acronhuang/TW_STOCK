#!/usr/bin/env python3
"""
从 cashflowStatement._raw 提取现金流数据并更新到 cashFlow 字段
"""
from pymongo import MongoClient
from bson.decimal128 import Decimal128

def extract_cashflow_data():
    """提取现金流数据"""
    client = MongoClient('mongodb://localhost:27017/')
    db = client['tw_stock_analysis']
    
    # 查找所有有原始现金流数据的记录
    reports = db.financial_reports.find({'cashflowStatement._raw': {'$exists': True}})
    
    updated_count = 0
    total_count = 0
    
    for report in reports:
        total_count += 1
        raw_cashflow = report.get('cashflowStatement', {}).get('_raw', {})
        
        if not raw_cashflow:
            continue
        
        # 提取关键字段
        # 营业活动现金流
        operating_cf = raw_cashflow.get('CashFlowsFromOperatingActivities') or \
                      raw_cashflow.get('NetCashInflowFromOperatingActivities') or \
                      raw_cashflow.get('現金流量') or 0
        
        # 投资活动现金流
        investing_cf = raw_cashflow.get('CashProvidedByInvestingActivities') or \
                      raw_cashflow.get('CashFlowsFromInvestingActivities') or 0
        
        # 融资活动现金流
        financing_cf = raw_cashflow.get('CashFlowsProvidedFromFinancingActivities') or \
                      raw_cashflow.get('CashFlowsFromFinancingActivities') or 0
        
        # 资本支出
        capex = abs(raw_cashflow.get('PropertyAndPlantAndEquipment', 0) or 0)
        
        # 自由现金流 = 营业现金流 - 资本支出
        free_cf = operating_cf - capex if operating_cf else 0
        
        # 支付股利
        dividend_paid = abs(raw_cashflow.get('CashDividendsPaid', 0) or 0)
        
        # 更新 cashFlow 字段
        cashflow_data = {
            'operatingCashFlow': Decimal128(str(operating_cf)),
            'investingCashFlow': Decimal128(str(investing_cf)),
            'financingCashFlow': Decimal128(str(financing_cf)),
            'freeCashFlow': Decimal128(str(free_cf)),
            'netCashFlow': operating_cf + investing_cf + financing_cf,
            'capitalExpenditure': Decimal128(str(capex)),
            'dividendPaid': dividend_paid
        }
        
        # 更新数据库
        db.financial_reports.update_one(
            {'_id': report['_id']},
            {'$set': {'cashFlow': cashflow_data}}
        )
        
        updated_count += 1
        
        if updated_count % 100 == 0:
            print(f'已处理 {updated_count}/{total_count} 条记录...')
    
    print(f'\n✅ 完成！')
    print(f'总记录数: {total_count}')
    print(f'已更新: {updated_count}')
    
    # 验证更新结果
    print('\n验证结果（以 2330 为例）:')
    sample = db.financial_reports.findOne(
        {'symbol': '2330'}, 
        {'period': 1, 'cashFlow.operatingCashFlow': 1, '_id': 0}
    )
    if sample:
        ocf = sample.get('cashFlow', {}).get('operatingCashFlow')
        if ocf and isinstance(ocf, Decimal128):
            ocf_value = float(ocf.to_decimal())
            print(f"期间: {sample.get('period')}")
            print(f"营业现金流: {ocf_value:,.0f} 元 ({ocf_value/1e8:.2f} 亿元)")

if __name__ == '__main__':
    print('开始提取现金流数据...\n')
    extract_cashflow_data()
