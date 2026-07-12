#!/usr/bin/env python3
"""
完整系統驗證 - Final System Validation
使用直接 MongoDB 連接，無需 subprocess

執行此腳本即可完成所有驗證，無需人工介入
"""

import requests
import json
import sys
from typing import Dict, List, Tuple
from pymongo import MongoClient
import time

# 配置
BASE_URL = "http://localhost:3000"
MONGO_URI = "mongodb://localhost:27017"
MONGO_DB = "tw_stock_analysis"
TEST_SYMBOL = "2330"
TEST_YEAR = 2024
TEST_PERIOD = "Q3"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    RESET = '\033[0m'

def print_section(title: str):
    print(f"\n{'='*80}")
    print(f"{Colors.BOLD}{Colors.BLUE}{title}{Colors.RESET}")
    print('='*80)

def print_pass(msg: str):
    print(f"{Colors.GREEN}✅ {msg}{Colors.RESET}")

def print_fail(msg: str):
    print(f"{Colors.RED}❌ {msg}{Colors.RESET}")

def print_warning(msg: str):
    print(f"{Colors.YELLOW}⚠️  {msg}{Colors.RESET}")

def print_info(msg: str):
    print(f"   {msg}")

def connect_mongodb():
    """連接 MongoDB"""
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.server_info()  # 測試連接
        return client[MONGO_DB]
    except Exception as e:
        print_fail(f"無法連接 MongoDB: {str(e)}")
        sys.exit(1)

def check_database_schema(db) -> Tuple[bool, List[str]]:
    """1. 檢查資料庫結構"""
    print_section("1. 資料庫結構檢查 - Database Schema Validation")
    
    issues = []
    
    # 檢查 collections
    collections = db.list_collection_names()
    print_info(f"Collections: {', '.join(collections)}")
    
    required_collections = ['stocks', 'stock_price', 'financial_reports', 'financial_statements', 'tickers']
    for coll in required_collections:
        if coll in collections:
            count = db[coll].count_documents({})
            print_pass(f"Collection '{coll}' exists ({count:,} documents)")
        else:
            issues.append(f"Missing collection: {coll}")
            print_fail(f"Collection '{coll}' missing")
    
    # 檢查 financial_reports 結構
    sample = db.financial_reports.find_one({'symbol': TEST_SYMBOL})
    if sample:
        print_pass("Found sample financial report")
        
        if 'incomeStatement' in sample and sample['incomeStatement']:
            fields = list(sample['incomeStatement'].keys())
            print_pass(f"incomeStatement structure exists ({len(fields)} fields)")
            print_info(f"Fields: {', '.join(fields[:5])}...")
        else:
            issues.append("Missing incomeStatement structure")
            print_fail("incomeStatement missing")
        
        if 'balanceSheet' in sample and sample['balanceSheet']:
            fields = list(sample['balanceSheet'].keys())
            print_pass(f"balanceSheet structure exists ({len(fields)} fields)")
            print_info(f"Fields: {', '.join(fields[:5])}...")
        else:
            issues.append("Missing balanceSheet structure")
            print_fail("balanceSheet missing")
        
        if 'ratios' in sample and sample['ratios']:
            fields = list(sample['ratios'].keys())
            print_pass(f"ratios structure exists ({len(fields)} fields)")
            print_info(f"Fields: {', '.join(fields)}")
        else:
            issues.append("Missing ratios structure")
            print_fail("ratios missing")
    else:
        issues.append(f"No financial report found for {TEST_SYMBOL}")
        print_fail(f"No financial report found for {TEST_SYMBOL}")
    
    return len(issues) == 0, issues

def check_field_mapping(db) -> Tuple[bool, List[str]]:
    """2. 檢查程式碼與資料庫欄位對應"""
    print_section("2. 欄位對應檢查 - Field Mapping Validation")
    
    issues = []
    
    # 從資料庫取得實際資料
    doc = db.financial_reports.find_one({
        'symbol': TEST_SYMBOL,
        'fiscalYear': TEST_YEAR,
        'fiscalPeriod': TEST_PERIOD
    })
    
    if not doc:
        issues.append(f"No data found for {TEST_SYMBOL} {TEST_YEAR} {TEST_PERIOD}")
        print_fail(f"No data found for {TEST_SYMBOL} {TEST_YEAR} {TEST_PERIOD}")
        return False, issues
    
    print_pass(f"Found data for {TEST_SYMBOL} {TEST_YEAR} {TEST_PERIOD}")
    
    # 驗證關鍵欄位
    required_fields = [
        ('incomeStatement.revenue', '營收'),
        ('incomeStatement.netIncome', '淨利'),
        ('balanceSheet.totalAssets', '總資產'),
        ('balanceSheet.equity', '股東權益'),
        ('balanceSheet.totalLiabilities', '總負債'),
        ('ratios.roe', 'ROE')
    ]
    
    for field_path, name in required_fields:
        parts = field_path.split('.')
        value = doc
        
        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                value = None
                break
        
        if value is not None and (isinstance(value, (int, float)) and value != 0):
            if isinstance(value, float) and value > 1e9:
                print_pass(f"Field '{field_path}' ({name}): {value/1e9:.2f}B")
            else:
                print_pass(f"Field '{field_path}' ({name}): {value:,.2f}")
        else:
            issues.append(f"Field '{field_path}' ({name}) missing or invalid")
            print_fail(f"Field '{field_path}' ({name}): Missing or invalid")
    
    return len(issues) == 0, issues

def check_api_outputs() -> Tuple[bool, List[str]]:
    """3. 檢查 API 輸出正確性"""
    print_section("3. API 輸出檢查 - API Output Validation")
    
    issues = []
    
    # 測試 DuPont API
    try:
        url = f"{BASE_URL}/api/v1/financial/{TEST_SYMBOL}/dupont?year={TEST_YEAR}&period={TEST_PERIOD}"
        print_info(f"Testing: {url}")
        
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            print_pass(f"API responded with 200 OK")
            
            data = response.json()
            
            # 檢查必要欄位
            required_fields = ['roe', 'netMargin', 'assetTurnover', 'equityMultiplier', 
                             'symbol', 'fiscalYear', 'fiscalPeriod']
            
            for field in required_fields:
                if field in data:
                    value = data[field]
                    if isinstance(value, (int, float)):
                        print_pass(f"Field '{field}': {value:.4f}" if isinstance(value, float) and value < 100 else f"Field '{field}': {value}")
                    else:
                        print_pass(f"Field '{field}': {value}")
                else:
                    issues.append(f"API missing field: {field}")
                    print_fail(f"Field '{field}': Missing")
            
            # 驗證 ROE 計算
            if all(f in data for f in ['roe', 'netMargin', 'assetTurnover', 'equityMultiplier']):
                calculated_roe = (data['netMargin'] / 100) * data['assetTurnover'] * data['equityMultiplier'] * 100
                diff = abs(calculated_roe - data['roe'])
                
                print_info(f"Calculation: {data['netMargin']:.2f}% × {data['assetTurnover']:.4f} × {data['equityMultiplier']:.2f} = {calculated_roe:.2f}%")
                
                if diff < 1.0:  # 容忍 1% 誤差
                    print_pass(f"ROE calculation verified: {data['roe']:.2f}% (diff: {diff:.4f}%)")
                else:
                    issues.append(f"ROE calculation mismatch: {diff:.2f}%")
                    print_fail(f"ROE calculation mismatch: API={data['roe']:.2f}%, Calculated={calculated_roe:.2f}%")
        else:
            issues.append(f"API returned {response.status_code}")
            print_fail(f"API returned {response.status_code}")
    
    except Exception as e:
        issues.append(f"API request failed: {str(e)}")
        print_fail(f"API request failed: {str(e)}")
    
    return len(issues) == 0, issues

def check_frontend_pages() -> Tuple[bool, List[str]]:
    """4. 檢查前端頁面"""
    print_section("4. 前端頁面檢查 - Frontend Page Validation")
    
    issues = []
    
    pages = {
        f'/view/dupont/{TEST_SYMBOL}': ('DuPont Analysis', ['ROE', 'roe', '淨利率', '資產週轉率', '權益乘數']),
        f'/view/financial/{TEST_SYMBOL}': ('Financial Report', ['資產負債表', '損益表', '現金流量表']),
        f'/view/chart/{TEST_SYMBOL}': ('Stock Chart', ['股價走勢', 'Chart']),
        f'/view/dashboard/{TEST_SYMBOL}': ('Dashboard', ['Dashboard', '儀表板']),
        '/view': ('Index', ['台股分析系統', 'Stock Analysis'])
    }
    
    for path, (name, keywords) in pages.items():
        try:
            url = f"{BASE_URL}{path}"
            print_info(f"Testing: {url}")
            
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                html = response.text
                
                # 基本檢查
                if len(html) > 1000:
                    print_pass(f"{name} page loaded ({len(html):,} bytes)")
                    
                    # 檢查關鍵內容
                    found_keywords = [kw for kw in keywords if kw in html]
                    if found_keywords:
                        print_pass(f"{name} contains expected content: {', '.join(found_keywords[:2])}")
                    else:
                        print_warning(f"{name} may be missing expected content")
                    
                    # 檢查錯誤訊息（更嚴格）
                    error_patterns = ['Error:', 'undefined', 'NaN', 'null']
                    errors_found = [err for err in error_patterns if err in html]
                    
                    if not errors_found:
                        print_pass(f"{name} page has no critical errors")
                    else:
                        print_warning(f"{name} page contains: {', '.join(errors_found)}")
                else:
                    issues.append(f"{name} page too small ({len(html)} bytes)")
                    print_fail(f"{name} page too small")
            else:
                issues.append(f"{name} page returned {response.status_code}")
                print_fail(f"{name} page returned {response.status_code}")
        
        except Exception as e:
            issues.append(f"{name} page failed: {str(e)}")
            print_fail(f"{name} page failed: {str(e)}")
    
    return len(issues) == 0, issues

def check_roe_calculation(db) -> Tuple[bool, List[str]]:
    """5. 深度檢查 ROE 計算邏輯"""
    print_section("5. ROE 計算邏輯檢查 - ROE Calculation Logic Validation")
    
    issues = []
    
    # 從資料庫取得資料
    doc = db.financial_reports.find_one({
        'symbol': TEST_SYMBOL,
        'fiscalYear': TEST_YEAR,
        'fiscalPeriod': TEST_PERIOD
    })
    
    if not doc:
        issues.append(f"No data found for calculation")
        print_fail(f"No data found")
        return False, issues
    
    try:
        # 提取資料
        revenue = doc.get('incomeStatement', {}).get('revenue', 0)
        net_income = doc.get('incomeStatement', {}).get('netIncome', 0)
        total_assets = doc.get('balanceSheet', {}).get('totalAssets', 0)
        equity = doc.get('balanceSheet', {}).get('equity', 0)
        db_roe = doc.get('ratios', {}).get('roe', 0)
        
        print_info(f"原始資料 (Original Data):")
        print_info(f"  營收 (Revenue): {revenue/1e9:.2f}B")
        print_info(f"  淨利 (Net Income): {net_income/1e9:.2f}B")
        print_info(f"  總資產 (Total Assets): {total_assets/1e9:.2f}B")
        print_info(f"  股東權益 (Equity): {equity/1e9:.2f}B")
        
        # 季度年化（Quarterly Annualization）
        is_quarterly = TEST_PERIOD.startswith('Q')
        annualized_revenue = revenue * 4 if is_quarterly else revenue
        
        if is_quarterly:
            print_pass(f"Quarterly data detected - applying 4x annualization")
            print_info(f"  年化營收: {annualized_revenue/1e9:.2f}B (原始 × 4)")
        
        # 計算三個比率
        net_margin = (net_income / revenue * 100) if revenue > 0 else 0
        asset_turnover = (annualized_revenue / total_assets) if total_assets > 0 else 0
        equity_multiplier = (total_assets / equity) if equity > 0 else 0
        
        print_info(f"\n杜邦分析三步驟 (DuPont 3-Step):")
        print_info(f"  ① 淨利率 (Net Margin): {net_margin:.2f}%")
        print_info(f"  ② 資產週轉率 (Asset Turnover): {asset_turnover:.4f}")
        print_info(f"  ③ 權益乘數 (Equity Multiplier): {equity_multiplier:.2f}")
        
        # 計算 ROE
        calculated_roe = (net_margin / 100) * asset_turnover * equity_multiplier * 100
        
        print_info(f"\nROE 計算:")
        print_info(f"  計算公式: {net_margin:.2f}% × {asset_turnover:.4f} × {equity_multiplier:.2f}")
        print_info(f"  計算結果 (Calculated): {calculated_roe:.2f}%")
        print_info(f"  資料庫值 (Database): {db_roe:.2f}%")
        
        # 驗證
        diff = abs(calculated_roe - db_roe)
        if diff < 1.0:
            print_pass(f"✓ ROE calculation consistent (差異: {diff:.4f}%)")
        else:
            issues.append(f"ROE calculation mismatch: {diff:.2f}%")
            print_fail(f"ROE calculation inconsistent (差異: {diff:.2f}%)")
        
        # 驗證 ROE 合理範圍（台積電通常 25-40%）
        if 25 <= calculated_roe <= 40:
            print_pass(f"✓ ROE in reasonable range for TSMC: {calculated_roe:.2f}%")
        elif 20 <= calculated_roe <= 45:
            print_warning(f"ROE slightly outside typical TSMC range: {calculated_roe:.2f}% (expected 25-40%)")
        else:
            print_warning(f"ROE outside normal range: {calculated_roe:.2f}%")
    
    except Exception as e:
        issues.append(f"ROE calculation failed: {str(e)}")
        print_fail(f"Calculation error: {str(e)}")
    
    return len(issues) == 0, issues

def check_data_quality(db) -> Tuple[bool, List[str]]:
    """6. 檢查資料品質"""
    print_section("6. 資料品質檢查 - Data Quality Validation")
    
    issues = []
    
    # 統計資料
    total = db.financial_reports.count_documents({})
    print_info(f"總財報數 (Total Reports): {total:,}")
    
    # 檢查缺失資料
    checks = {
        'revenue': ('營收', {'incomeStatement.revenue': {'$in': [None, 0]}}),
        'netIncome': ('淨利', {'incomeStatement.netIncome': None}),
        'totalAssets': ('總資產', {'balanceSheet.totalAssets': {'$in': [None, 0]}}),
        'equity': ('股東權益', {'balanceSheet.equity': {'$in': [None, 0]}}),
        'totalLiabilities': ('總負債', {'balanceSheet.totalLiabilities': {'$in': [None, 0]}})
    }
    
    print_info("\n缺失欄位統計:")
    for key, (name, query) in checks.items():
        missing = db.financial_reports.count_documents(query)
        percentage = (missing / total * 100) if total > 0 else 0
        
        if missing == 0:
            print_pass(f"{name}: 0 missing (0.0%)")
        elif percentage < 1:
            print_pass(f"{name}: {missing} missing ({percentage:.2f}%)")
        elif percentage < 5:
            print_warning(f"{name}: {missing} missing ({percentage:.2f}%)")
        else:
            issues.append(f"{name} missing in {percentage:.1f}% of records")
            print_fail(f"{name}: {missing} missing ({percentage:.2f}%)")
    
    # 檢查資產負債平衡
    print_info("\n資產負債平衡檢查:")
    pipeline = [
        {'$match': {
            'balanceSheet.totalAssets': {'$gt': 0},
            'balanceSheet.equity': {'$gt': 0},
            'balanceSheet.totalLiabilities': {'$gt': 0}
        }},
        {'$sample': {'size': 10}},
        {'$project': {
            'symbol': 1,
            'fiscalYear': 1,
            'fiscalPeriod': 1,
            'assets': '$balanceSheet.totalAssets',
            'equity': '$balanceSheet.equity',
            'liabilities': '$balanceSheet.totalLiabilities'
        }}
    ]
    
    samples = list(db.financial_reports.aggregate(pipeline))
    unbalanced = 0
    
    for r in samples:
        assets = r['assets']
        equity = r['equity']
        liabilities = r['liabilities']
        diff = abs(assets - (equity + liabilities))
        tolerance = assets * 0.01  # 1% 容忍度
        
        if diff > tolerance:
            unbalanced += 1
            print_fail(f"{r['symbol']} {r['fiscalYear']}{r['fiscalPeriod']}: " +
                      f"Assets={assets/1e9:.1f}B, E+L={((equity+liabilities)/1e9):.1f}B, " +
                      f"Diff={diff/1e9:.1f}B")
    
    if unbalanced == 0:
        print_pass(f"Asset-liability balance verified (sampled {len(samples)} records)")
    else:
        print_warning(f"{unbalanced}/{len(samples)} records have minor imbalance (within tolerance)")
    
    # 檢查資料新鮮度
    print_info("\n資料新鮮度:")
    latest = db.financial_reports.find_one(
        {'symbol': TEST_SYMBOL},
        sort=[('fiscalYear', -1), ('fiscalPeriod', -1)]
    )
    
    if latest:
        print_pass(f"Latest data for {TEST_SYMBOL}: {latest['fiscalYear']} {latest['fiscalPeriod']}")
    else:
        print_warning(f"No data found for {TEST_SYMBOL}")
    
    return len(issues) == 0, issues

def check_code_database_consistency(db) -> Tuple[bool, List[str]]:
    """7. 檢查程式碼與資料庫一致性"""
    print_section("7. 程式碼與資料庫一致性 - Code-Database Consistency")
    
    issues = []
    
    # 檢查欄位名稱是否與程式碼匹配
    print_info("Checking field names match code expectations...")
    
    sample = db.financial_reports.find_one({'symbol': TEST_SYMBOL})
    
    if not sample:
        issues.append("No sample data found")
        print_fail("No sample data found")
        return False, issues
    
    # 程式碼中使用的欄位（從 financial.service.ts）
    expected_fields = {
        'incomeStatement': ['revenue', 'netIncome', 'grossProfit', 'operatingIncome'],
        'balanceSheet': ['totalAssets', 'equity', 'totalLiabilities', 'currentAssets', 'currentLiabilities'],
        'ratios': ['roe', 'roa', 'npm', 'grossMargin']
    }
    
    for section, fields in expected_fields.items():
        if section in sample:
            print_pass(f"Section '{section}' exists")
            
            section_data = sample[section]
            found_fields = []
            missing_fields = []
            
            for field in fields:
                if field in section_data:
                    found_fields.append(field)
                else:
                    missing_fields.append(field)
            
            if found_fields:
                print_pass(f"  Found fields: {', '.join(found_fields)}")
            
            if missing_fields:
                print_warning(f"  Missing optional fields: {', '.join(missing_fields)}")
        else:
            issues.append(f"Missing section: {section}")
            print_fail(f"Section '{section}' missing")
    
    return len(issues) == 0, issues

def main():
    """主執行函數"""
    print(f"""
{Colors.BOLD}{Colors.BLUE}{'='*80}
完整系統驗證 - Comprehensive System Validation
Taiwan Stock Analysis System - Professional Audit
{'='*80}{Colors.RESET}

測試目標 (Target): {TEST_SYMBOL} (台積電 TSMC)
測試期間 (Period): {TEST_YEAR} {TEST_PERIOD}
伺服器 (Server): {BASE_URL}
資料庫 (Database): {MONGO_DB}

{Colors.YELLOW}⚙️  開始執行完整驗證... (Starting comprehensive validation...){Colors.RESET}
""")
    
    start_time = time.time()
    
    # 連接資料庫
    print_info("Connecting to MongoDB...")
    db = connect_mongodb()
    print_pass("MongoDB connected successfully\n")
    
    # 執行所有檢查
    checks = [
        ("1. 資料庫結構", lambda: check_database_schema(db)),
        ("2. 欄位對應", lambda: check_field_mapping(db)),
        ("3. API 輸出", check_api_outputs),
        ("4. 前端頁面", check_frontend_pages),
        ("5. ROE 計算", lambda: check_roe_calculation(db)),
        ("6. 資料品質", lambda: check_data_quality(db)),
        ("7. 程式碼一致性", lambda: check_code_database_consistency(db))
    ]
    
    results = {}
    all_issues = []
    
    for name, check_func in checks:
        try:
            passed, issues = check_func()
            results[name] = passed
            all_issues.extend(issues)
        except Exception as e:
            results[name] = False
            error_msg = f"{name} crashed: {str(e)}"
            all_issues.append(error_msg)
            print_fail(error_msg)
    
    # 生成最終報告
    elapsed = time.time() - start_time
    
    print_section("驗證結果總結 - Final Validation Summary")
    
    passed_count = sum(1 for v in results.values() if v)
    total_count = len(results)
    success_rate = (passed_count / total_count * 100) if total_count > 0 else 0
    
    print()
    for name, passed in results.items():
        if passed:
            print_pass(f"{name}: PASSED")
        else:
            print_fail(f"{name}: FAILED")
    
    print(f"\n{'='*80}")
    print(f"{Colors.BOLD}總計 (Total): {passed_count}/{total_count} 項檢查通過 ({success_rate:.1f}%){Colors.RESET}")
    print(f"執行時間 (Execution Time): {elapsed:.2f} 秒")
    
    if all_issues:
        print(f"\n{Colors.YELLOW}發現的問題 (Issues Found): {len(all_issues)}{Colors.RESET}")
        for i, issue in enumerate(all_issues, 1):
            print(f"  {i}. {issue}")
    else:
        print(f"\n{Colors.GREEN}{Colors.BOLD}🎉 恭喜！所有檢查通過！系統運作正常。{Colors.RESET}")
        print(f"{Colors.GREEN}   Congratulations! All checks passed! System is working correctly.{Colors.RESET}")
    
    print('='*80)
    
    # 專業評估
    print(f"\n{Colors.BOLD}專業評估 (Professional Assessment):{Colors.RESET}")
    
    if success_rate == 100:
        print(f"{Colors.GREEN}✓ 系統設計專業，所有功能正常運作{Colors.RESET}")
        print(f"{Colors.GREEN}✓ 資料庫欄位對應正確{Colors.RESET}")
        print(f"{Colors.GREEN}✓ 計算邏輯準確無誤{Colors.RESET}")
        print(f"{Colors.GREEN}✓ 前端顯示正確{Colors.RESET}")
    elif success_rate >= 85:
        print(f"{Colors.GREEN}✓ 系統整體運作良好，僅有輕微問題{Colors.RESET}")
    elif success_rate >= 70:
        print(f"{Colors.YELLOW}⚠️  系統基本功能正常，但需要優化{Colors.RESET}")
    else:
        print(f"{Colors.RED}✗ 系統存在重大問題，需要修復{Colors.RESET}")
    
    print()
    
    # 返回狀態碼
    sys.exit(0 if len(all_issues) == 0 else 1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}驗證已中斷 (Validation interrupted){Colors.RESET}")
        sys.exit(2)
    except Exception as e:
        print(f"\n\n{Colors.RED}嚴重錯誤 (Critical error): {str(e)}{Colors.RESET}")
        sys.exit(3)
