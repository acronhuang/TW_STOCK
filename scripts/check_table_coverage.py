#!/usr/bin/env python3
"""
检查所有资料表的配置与FinMind API的对应关系
根据用户提供的清单验证系统配置
"""

import sys
sys.path.insert(0, '/home/mdsadmin/Stock/tw-stock-analysis')

from src.downloaders.table_config import DATA_TABLES

# 用户要求的表清单
user_requirements = {
    "技術面": [
        "台股總覽",
        "台股總覽(含權證)",
        "台灣股價資料表",
        "台股交易日",
        "台灣類股股價表",
        "個股 PER、PBR 資料表",
        "每 5 秒委託成交統計",
        "台股加權指數",
        "當日沖銷交易標的及成交量值",
        "加權、櫃買報酬指數"
    ],
    "籌碼面": [
        "個股融資融劵表",
        "整體市場融資融劵表",
        "個股三大法人買賣表",
        "整體三大市場法人買賣表",
        "外資持股表",
        "借券成交明細",
        "暫停融券賣出表(融券回補日)",
        "信用額度總量管制餘額表",
        "證券商資訊表"
    ],
    "基本面": [
        "現金流量表",
        "綜合損益表",
        "資產負債表",
        "股利政策表",
        "除權除息結果表",
        "月營收表",
        "減資恢復買賣參考價格",
        "台股下市資料表",
        "台股分割後參考價",
        "台灣股票變更面額恢復買賣參考價格"
    ],
    "衍生性金融商品": [
        "期貨、選擇權日成交資訊總覽",
        "期貨、選擇權即時報價總覽",
        "期貨日成交資訊",
        "選擇權日成交資訊",
        "期貨三大法人買賣",
        "選擇權三大法人買賣",
        "期貨各卷商每日交易",
        "選擇權各卷商每日交易"
    ],
    "其他": [
        "相關新聞",
        "黃金價格表",
        "原油資料表(Brent, WTI)",
        "美股股價",
        "外幣對台幣資料表(19 種幣別匯率)",
        "央行利率資料表(12 個國家)"
    ]
}

def fuzzy_match(user_name, config_name):
    """模糊匹配表名"""
    # 移除空格和标点符号进行比较
    import re
    clean_user = re.sub(r'[()（）、，,\s]', '', user_name.lower())
    clean_config = re.sub(r'[()（）、，,\s]', '', config_name.lower())
    
    # 检查是否包含关键词
    if clean_user in clean_config or clean_config in clean_user:
        return True
    
    # 特殊规则
    if '新聞' in user_name and '新聞' in config_name:
        return True
    if '原油' in user_name and '原油' in config_name:
        return True
    if '美股' in user_name and '美股' in config_name:
        return True
        
    return False

def main():
    print("="*80)
    print("資料表配置檢查報告")
    print("="*80)
    print()
    
    total_required = 0
    total_configured = 0
    missing_tables = []
    
    for category, requirements in user_requirements.items():
        print(f"\n【{category}】")
        print("-" * 60)
        
        config_tables = DATA_TABLES.get(category, [])
        config_names = {t['name']: t for t in config_tables}
        
        for req_name in requirements:
            total_required += 1
            found = False
            matched_config = None
            
            # 精确匹配
            if req_name in config_names:
                found = True
                matched_config = config_names[req_name]
            else:
                # 模糊匹配
                for config_name, config in config_names.items():
                    if fuzzy_match(req_name, config_name):
                        found = True
                        matched_config = config
                        break
            
            if found:
                total_configured += 1
                dataset = matched_config.get('dataset', 'N/A')
                collection = matched_config.get('collection', 'N/A')
                print(f"  ✅ {req_name}")
                print(f"     → {matched_config['name']}")
                print(f"     → Dataset: {dataset}, Collection: {collection}")
            else:
                print(f"  ❌ {req_name} (未配置)")
                missing_tables.append({'category': category, 'name': req_name})
    
    # 汇总
    print(f"\n{'='*80}")
    print("配置覆蓋率匯總")
    print("="*80)
    print(f"用戶需求表數: {total_required}")
    print(f"已配置表數:   {total_configured}")
    print(f"覆蓋率:       {total_configured}/{total_required} ({total_configured/total_required*100:.1f}%)")
    
    if missing_tables:
        print(f"\n缺失的資料表 ({len(missing_tables)} 個):")
        for item in missing_tables:
            print(f"  - [{item['category']}] {item['name']}")
    else:
        print("\n✅ 所有用戶需求的資料表都已配置！")
    
    print("="*80)


if __name__ == '__main__':
    main()
