#!/usr/bin/env python3
"""
检查优先列表中未下载的股票
"""

import sys
from pathlib import Path
from pymongo import MongoClient

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def main():
    # 连接数据库
    client = MongoClient("mongodb://localhost:27017/")
    db = client["tw_stock_analysis"]
    
    # 读取优先列表
    priority_file = project_root / "data" / "priority_stocks.txt"
    priority_stocks = []
    
    with open(priority_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split(',')
            if parts:
                stock_id = parts[0].strip()
                stock_name = parts[1].strip() if len(parts) > 1 else ""
                priority_stocks.append((stock_id, stock_name))
    
    print("=" * 80)
    print("优先列表下载状态检查")
    print("=" * 80)
    print(f"优先列表总数: {len(priority_stocks)} 支股票\n")
    
    # 检查每支股票的下载状态
    downloaded = []
    missing = []
    
    for stock_id, stock_name in priority_stocks:
        doc = db.taiwan_stock_info.find_one(
            {'stock_id': stock_id},
            {'outstanding_shares': 1}
        )
        
        if doc and doc.get('outstanding_shares'):
            downloaded.append((stock_id, stock_name))
            print(f"✅ {stock_id} {stock_name}: 已下载")
        else:
            missing.append((stock_id, stock_name))
            print(f"❌ {stock_id} {stock_name}: 未下载")
    
    # 统计
    print(f"\n{'=' * 80}")
    print(f"统计结果")
    print(f"{'=' * 80}")
    print(f"已下载: {len(downloaded)} 支 ({len(downloaded)/len(priority_stocks)*100:.1f}%)")
    print(f"未下载: {len(missing)} 支 ({len(missing)/len(priority_stocks)*100:.1f}%)")
    
    if missing:
        print(f"\n{'=' * 80}")
        print(f"未下载的核心股票清单 ({len(missing)} 支)")
        print(f"{'=' * 80}")
        for stock_id, stock_name in missing:
            print(f"  {stock_id} {stock_name}")
        
        # 保存到文件
        missing_file = project_root / "data" / "missing_priority_stocks.txt"
        with open(missing_file, 'w', encoding='utf-8') as f:
            f.write("# 未下载的核心股票清单\n")
            f.write("# 格式: 股票代码,股票名称\n\n")
            for stock_id, stock_name in missing:
                f.write(f"{stock_id},{stock_name}\n")
        
        print(f"\n缺失列表已保存至: {missing_file}")
        print(f"\n下一步执行命令:")
        print(f"  export FINMIND_API_TOKEN=\"$(grep FINMIND_API_TOKEN .env | cut -d'=' -f2)\"")
        print(f"  python3 src/downloaders/outstanding_shares_downloader.py --priority-list --skip-existing --execute")
    else:
        print(f"\n✅ 所有优先股票都已下载完成！")
    
    print(f"\n{'=' * 80}")


if __name__ == '__main__':
    main()
