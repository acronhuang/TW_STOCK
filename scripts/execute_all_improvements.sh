#!/bin/bash
# P0/P1/P2 完整執行與驗證腳本

set -e  # 遇到錯誤立即停止

echo "================================================================================"
echo "🚀 P0/P1/P2 完整執行腳本"
echo "================================================================================"
echo ""
echo "本腳本將依序執行："
echo "  P0: 強制 Decimal128 精度遷移"
echo "  P1-A: 日期統一清洗"
echo "  P1-B: 原子性調整後收盤價計算"
echo "  P2-A: 股票分割數據下載"
echo "  P2-B: 市值與換手率計算"
echo ""
echo "================================================================================"
echo ""

# 檢查 MongoDB 連線
echo "🔍 檢查 MongoDB 連線..."
if ! mongosh --quiet --eval "db.adminCommand('ping')" > /dev/null 2>&1; then
    echo "❌ MongoDB 未啟動，請先啟動 MongoDB"
    exit 1
fi
echo "✅ MongoDB 連線正常"
echo ""

# 檢查 Python 環境
echo "🔍 檢查 Python 環境..."
if ! python3 -c "import pymongo; from bson.decimal128 import Decimal128" > /dev/null 2>&1; then
    echo "❌ Python 套件缺失，請執行: pip install pymongo"
    exit 1
fi
echo "✅ Python 環境正常"
echo ""

# 切換到專案根目錄
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo "📁 專案根目錄: $PROJECT_ROOT"
echo ""

# ============================================================================
# P0: 強制 Decimal128 精度遷移
# ============================================================================
echo "================================================================================"
echo "P0: 強制 Decimal128 精度遷移"
echo "================================================================================"
echo ""

read -p "是否執行 P0 強制精度遷移？(y/n) " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "開始 P0 遷移..."
    echo "YES" | python3 src/migrations/p0_force_decimal_migration.py --execute
    
    echo ""
    echo "✅ P0 完成"
    echo ""
else
    echo "⏭️  跳過 P0"
fi

# ============================================================================
# P1-A: 日期清洗
# ============================================================================
echo "================================================================================"
echo "P1-A: 日期統一清洗"
echo "================================================================================"
echo ""

read -p "是否執行 P1-A 日期清洗？(y/n) " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "開始 P1-A 日期清洗..."
    echo "YES" | python3 src/utils/date_cleaner.py --execute
    
    echo ""
    echo "✅ P1-A 完成"
    echo ""
else
    echo "⏭️  跳過 P1-A"
fi

# ============================================================================
# P1-B: 原子性調整後收盤價計算
# ============================================================================
echo "================================================================================"
echo "P1-B: 原子性調整後收盤價計算"
echo "================================================================================"
echo ""

read -p "是否執行 P1-B adj_close 計算？(y/n) " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    # 先預覽前10支股票
    echo "預覽前10支股票..."
    python3 src/calculators/adj_close_calculator_atomic.py --all --limit 10 --dry-run
    
    echo ""
    read -p "預覽完成，是否繼續執行全部？(y/n) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "開始 P1-B 全部計算..."
        echo "YES" | python3 src/calculators/adj_close_calculator_atomic.py --all --execute
        
        echo ""
        echo "✅ P1-B 完成"
        echo ""
    else
        echo "⏭️  取消 P1-B"
    fi
else
    echo "⏭️  跳過 P1-B"
fi

# ============================================================================
# P2-A: 股票分割數據下載
# ============================================================================
echo "================================================================================"
echo "P2-A: 股票分割數據下載"
echo "================================================================================"
echo ""

read -p "是否執行 P2-A 股票分割數據下載？(y/n) " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    # 檢查 API Token
    if [ -z "$FINMIND_API_TOKEN" ]; then
        echo "⚠️  FINMIND_API_TOKEN 未設定"
        read -p "請輸入 FinMind API Token: " api_token
        export FINMIND_API_TOKEN="$api_token"
    fi
    
    # 先預覽前5支股票
    echo "預覽前5支股票..."
    python3 src/downloaders/stock_split_downloader.py --all --limit 5 --dry-run
    
    echo ""
    read -p "預覽完成，是否繼續執行全部？(y/n) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "開始 P2-A 全部下載..."
        echo "YES" | python3 src/downloaders/stock_split_downloader.py --all --execute
        
        echo ""
        echo "✅ P2-A 完成"
        echo ""
    else
        echo "⏭️  取消 P2-A"
    fi
else
    echo "⏭️  跳過 P2-A"
fi

# ============================================================================
# P2-B: 市值與換手率計算
# ============================================================================
echo "================================================================================"
echo "P2-B: 市值與換手率計算"
echo "================================================================================"
echo ""

read -p "是否執行 P2-B 市值與換手率計算？(y/n) " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    # 先預覽前10支股票
    echo "預覽前10支股票..."
    python3 src/calculators/market_metrics_calculator.py --all --limit 10 --dry-run
    
    echo ""
    read -p "預覽完成，是否繼續執行全部？(y/n) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "開始 P2-B 全部計算..."
        echo "YES" | python3 src/calculators/market_metrics_calculator.py --all --execute
        
        echo ""
        echo "✅ P2-B 完成"
        echo ""
    else
        echo "⏭️  取消 P2-B"
    fi
else
    echo "⏭️  跳過 P2-B"
fi

# ============================================================================
# 最終驗證
# ============================================================================
echo "================================================================================"
echo "🔍 最終驗證"
echo "================================================================================"
echo ""

# 驗證 Decimal128 精度
echo "[1] 驗證 Decimal128 精度..."
python3 -c "
from pymongo import MongoClient
from bson.decimal128 import Decimal128

client = MongoClient('mongodb://localhost:27017/')
db = client['tw_stock_analysis']

# 檢查 dividend_detail
div = db.dividend_detail.find_one({'cash_earnings_distribution': {'\$exists': True, '\$ne': None}})
is_decimal = isinstance(div.get('cash_earnings_distribution'), Decimal128) if div else False
print(f'dividend_detail.cash_earnings_distribution: {'✅ Decimal128' if is_decimal else '❌ 不是 Decimal128'}')

# 檢查 stock_price
price = db.stock_price.find_one({'close': {'\$exists': True}})
is_decimal = isinstance(price.get('close'), Decimal128) if price else False
print(f'stock_price.close: {'✅ Decimal128' if is_decimal else '❌ 不是 Decimal128'}')
"

echo ""

# 驗證 adj_close 覆蓋率
echo "[2] 驗證 adj_close 覆蓋率..."
python3 -c "
from pymongo import MongoClient

client = MongoClient('mongodb://localhost:27017/')
db = client['tw_stock_analysis']

total = db.stock_price.count_documents({})
with_adj = db.stock_price.count_documents({'adj_close': {'\$exists': True, '\$ne': None}})

coverage = with_adj / total * 100 if total > 0 else 0
print(f'adj_close 覆蓋率: {coverage:.2f}% ({with_adj:,}/{total:,})')

if coverage >= 95:
    print('✅ 覆蓋率良好')
else:
    print('⚠️  覆蓋率偏低')
"

echo ""

# 驗證市值與換手率
echo "[3] 驗證市值與換手率..."
python3 -c "
from pymongo import MongoClient

client = MongoClient('mongodb://localhost:27017/')
db = client['tw_stock_analysis']

total = db.stock_price.count_documents({})
with_market_cap = db.stock_price.count_documents({'market_cap': {'\$exists': True, '\$ne': None}})
with_turnover = db.stock_price.count_documents({'turnover_rate': {'\$exists': True, '\$ne': None}})

mc_coverage = with_market_cap / total * 100 if total > 0 else 0
tr_coverage = with_turnover / total * 100 if total > 0 else 0

print(f'market_cap 覆蓋率: {mc_coverage:.2f}% ({with_market_cap:,}/{total:,})')
print(f'turnover_rate 覆蓋率: {tr_coverage:.2f}% ({with_turnover:,}/{total:,})')

if mc_coverage >= 80 and tr_coverage >= 80:
    print('✅ 覆蓋率良好')
else:
    print('⚠️  覆蓋率偏低（可能部分股票缺少流通股數資料）')
"

echo ""

# 驗證股票分割數據
echo "[4] 驗證股票分割數據..."
python3 -c "
from pymongo import MongoClient

client = MongoClient('mongodb://localhost:27017/')
db = client['tw_stock_analysis']

if 'stock_split_events' in db.list_collection_names():
    total_events = db.stock_split_events.count_documents({})
    print(f'股票分割事件: {total_events:,} 個')
    
    if total_events > 0:
        print('✅ 股票分割數據已下載')
    else:
        print('⚠️  沒有股票分割數據')
else:
    print('⚠️  stock_split_events 集合不存在')
"

echo ""
echo "================================================================================"
echo "✅ 所有階段完成！"
echo "================================================================================"
echo ""
echo "日誌位置: ./logs/"
echo "請檢查各階段日誌確認詳細結果"
echo ""
