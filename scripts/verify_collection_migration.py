#!/usr/bin/env python3
"""
集合名稱統一驗證腳本

用途: 檢查所有程式是否已更新為使用新的集合名稱

執行: python3 scripts/verify_collection_migration.py
"""

import pymongo
from pathlib import Path
import re

def check_database_collections():
    """檢查資料庫實際集合狀態"""
    print("=" * 80)
    print("📊 檢查資料庫集合狀態")
    print("=" * 80)
    print()
    
    client = pymongo.MongoClient('mongodb://localhost:27017/')
    db = client['tw_stock_analysis']
    
    collections = sorted(db.list_collection_names())
    
    print(f"當前集合數: {len(collections)} 個")
    print()
    
    # 檢查已刪除的集合是否存在
    deleted_collections = {
        'company_basic_info': 'stocks',
        'finmind_financials': 'financial_statements',
        'yahoo_financials': 'financial_statements',
        'yahoo_prices': '(已刪除)',
        'financial_reports': '(已刪除)'
    }
    
    issues = []
    for old_name, new_name in deleted_collections.items():
        if old_name in collections:
            issues.append(f"❌ {old_name} 仍然存在（應該 → {new_name}）")
        else:
            print(f"✅ {old_name} 已刪除 → {new_name}")
    
    print()
    
    # 檢查新集合是否存在
    print("檢查新集合:")
    required_new = ['stocks', 'financial_statements']
    for coll in required_new:
        if coll in collections:
            count = db[coll].count_documents({})
            print(f"✅ {coll} 存在 ({count:,} 筆)")
        else:
            issues.append(f"❌ {coll} 不存在")
    
    print()
    
    if issues:
        print("⚠️  發現問題:")
        for issue in issues:
            print(f"  {issue}")
        return False
    else:
        print("✅ 資料庫集合狀態正確")
        return True

def check_code_references():
    """檢查程式碼中的集合引用"""
    print()
    print("=" * 80)
    print("🔍 檢查程式碼引用")
    print("=" * 80)
    print()
    
    # 要檢查的集合名稱（已刪除的）
    old_collections = [
        'company_basic_info',
        'finmind_financials',
        'yahoo_financials',
        'yahoo_prices',
        'financial_reports'
    ]
    
    # 掃描所有 Python 檔案
    python_files = list(Path('.').rglob('*.py'))
    
    # 排除某些檔案
    exclude_patterns = [
        'venv',
        'node_modules',
        'consolidate_collections.py',  # 整合工具本身
        'verify_collection_migration.py',  # 本腳本
        '__pycache__'
    ]
    
    findings = {coll: [] for coll in old_collections}
    
    for py_file in python_files:
        # 跳過排除的路徑
        if any(pattern in str(py_file) for pattern in exclude_patterns):
            continue
        
        try:
            content = py_file.read_text()
            
            for coll in old_collections:
                # 檢查是否使用該集合
                patterns = [
                    rf"db\.{coll}\b",
                    rf"db\['{coll}'\]",
                    rf'db\["{coll}"\]',
                ]
                
                for pattern in patterns:
                    if re.search(pattern, content):
                        # 找出使用該集合的行號
                        lines = content.split('\n')
                        for line_num, line in enumerate(lines, 1):
                            if coll in line and not line.strip().startswith('#'):
                                findings[coll].append({
                                    'file': str(py_file),
                                    'line': line_num,
                                    'code': line.strip()[:80]
                                })
                        break
        except Exception:
            pass
    
    # 顯示結果
    issues_found = False
    
    for coll, uses in findings.items():
        if uses:
            issues_found = True
            print(f"⚠️  發現使用 {coll}:")
            
            # 去重並顯示
            seen = set()
            for use in uses:
                key = (use['file'], use['line'])
                if key not in seen:
                    seen.add(key)
                    print(f"  📄 {use['file']}:{use['line']}")
                    print(f"     {use['code']}")
            print()
    
    if not issues_found:
        print("✅ 沒有發現使用已刪除集合的程式")
        return True
    else:
        return False

def check_critical_scripts():
    """檢查關鍵腳本"""
    print()
    print("=" * 80)
    print("🎯 檢查關鍵腳本")
    print("=" * 80)
    print()
    
    critical_scripts = [
        'scripts/background_full_download.py',
        'scripts/calculate_all_indicators.py',
        'pattern_recognition/market_scanner.py',
        'pattern_recognition/position_monitor.py'
    ]
    
    all_ok = True
    
    for script_path in critical_scripts:
        path = Path(script_path)
        if not path.exists():
            print(f"⚠️  {script_path} 不存在")
            all_ok = False
            continue
        
        content = path.read_text()
        
        # 檢查是否使用新集合
        uses_stocks = 'db.stocks' in content or "db['stocks']" in content
        uses_financial_statements = 'financial_statements' in content
        
        # 檢查是否使用舊集合
        uses_company_basic = 'company_basic_info' in content
        uses_old_financial = 'finmind_financials' in content or 'yahoo_financials' in content
        
        status = "✅"
        notes = []
        
        if uses_company_basic and not uses_stocks:
            status = "❌"
            notes.append("仍使用 company_basic_info")
            all_ok = False
        elif uses_company_basic and uses_stocks:
            status = "⚠️ "
            notes.append("同時使用舊集合和新集合")
        
        if uses_old_financial and not uses_financial_statements:
            status = "❌"
            notes.append("仍使用舊財報集合")
            all_ok = False
        
        print(f"{status} {script_path}")
        if notes:
            for note in notes:
                print(f"     {note}")
    
    print()
    
    if all_ok:
        print("✅ 所有關鍵腳本已更新")
        return True
    else:
        print("❌ 部分腳本需要更新")
        return False

def main():
    """主函數"""
    print()
    print("=" * 80)
    print("🔧 MongoDB 集合名稱統一驗證")
    print("=" * 80)
    print()
    print("檢查項目:")
    print("  1. 資料庫集合狀態")
    print("  2. 程式碼引用")
    print("  3. 關鍵腳本")
    print()
    
    results = []
    
    # 檢查資料庫
    results.append(("資料庫集合", check_database_collections()))
    
    # 檢查程式碼
    results.append(("程式碼引用", check_code_references()))
    
    # 檢查關鍵腳本
    results.append(("關鍵腳本", check_critical_scripts()))
    
    # 總結
    print()
    print("=" * 80)
    print("📊 檢查總結")
    print("=" * 80)
    print()
    
    all_passed = True
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status} - {name}")
        if not passed:
            all_passed = False
    
    print()
    print("=" * 80)
    
    if all_passed:
        print("✅ 所有檢查通過")
        print("✅ 集合整合不會影響下載資料")
        print("=" * 80)
        return 0
    else:
        print("❌ 部分檢查未通過")
        print("⚠️  請修正後再執行")
        print("=" * 80)
        return 1

if __name__ == '__main__':
    exit(main())
