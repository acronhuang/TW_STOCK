# P0/P1/P2 快速執行指南

## 🚀 快速開始（推薦）

```bash
cd /Users/ming/Desktop/Stock/tw-stock-analysis

# 賦予執行權限
chmod +x scripts/execute_all_improvements.sh

# 一鍵執行所有改進
./scripts/execute_all_improvements.sh
```

腳本會交互式引導你完成所有步驟。

---

## 📋 分階段執行

### P0: 精度修復（立即執行，估時：5-10分鐘）

```bash
# 1. 預覽
python3 src/migrations/p0_force_decimal_migration.py --dry-run

# 2. 執行
echo "YES" | python3 src/migrations/p0_force_decimal_migration.py --execute

# 3. 驗證
python3 src/utils/quick_type_check.py
```

**預期結果**: 所有數值欄位轉換為 Decimal128

---

### P1-A: 日期清洗（估時：3-5分鐘）

```bash
# 1. 預覽
python3 src/utils/date_cleaner.py --dry-run

# 2. 執行
echo "YES" | python3 src/utils/date_cleaner.py --execute
```

**預期結果**: 所有日期統一為 ISODate 格式

---

### P1-B: 原子性 adj_close 計算（估時：10-15分鐘）

```bash
# 1. 測試單支股票
python3 src/calculators/adj_close_calculator_atomic.py --stock-id 2330 --dry-run

# 2. 預覽前10支
python3 src/calculators/adj_close_calculator_atomic.py --all --limit 10 --dry-run

# 3. 執行全部
echo "YES" | python3 src/calculators/adj_close_calculator_atomic.py --all --execute
```

**預期結果**: adj_close 覆蓋率 ≥ 98%，數據完整性 100%

---

### P2-A: 股票分割數據（估時：5-10分鐘）

```bash
# 1. 設定 API Token
export FINMIND_API_TOKEN="your_token_here"

# 2. 測試單支
python3 src/downloaders/stock_split_downloader.py --stock-id 2330 --dry-run

# 3. 預覽前5支
python3 src/downloaders/stock_split_downloader.py --all --limit 5 --dry-run

# 4. 執行全部
echo "YES" | python3 src/downloaders/stock_split_downloader.py --all --execute
```

**預期結果**: 儲存所有股票分割/減資事件

---

### P2-B: 市值與換手率（估時：10-15分鐘）

```bash
# 1. 測試單支
python3 src/calculators/market_metrics_calculator.py --stock-id 2330 --dry-run

# 2. 預覽前10支
python3 src/calculators/market_metrics_calculator.py --all --limit 10 --dry-run

# 3. 執行全部
echo "YES" | python3 src/calculators/market_metrics_calculator.py --all --execute
```

**預期結果**: market_cap 和 turnover_rate 覆蓋率 ≥ 80%

---

## ✅ 快速驗證

### 一鍵驗證所有改進

```python
python3 << 'EOF'
from pymongo import MongoClient
from bson.decimal128 import Decimal128
from datetime import datetime

db = MongoClient()['tw_stock_analysis']

print("="*80)
print("資料庫改進驗證報告")
print("="*80)

# P0: 精度驗證
print("\n[P0] 精度狀態:")
div = db.dividend_detail.find_one({'cash_earnings_distribution': {'$exists': True, '$ne': None}})
if div:
    is_decimal = isinstance(div.get('cash_earnings_distribution'), Decimal128)
    print(f"  dividend_detail: {'✅ Decimal128' if is_decimal else '❌ Float'}")

price = db.stock_price.find_one({'close': {'$exists': True}})
if price:
    is_decimal = isinstance(price.get('close'), Decimal128)
    print(f"  stock_price: {'✅ Decimal128' if is_decimal else '❌ Float'}")

# P1-A: 日期驗證
print("\n[P1-A] 日期格式:")
price = db.stock_price.find_one({'date': {'$exists': True}})
if price:
    is_datetime = isinstance(price.get('date'), datetime)
    print(f"  stock_price.date: {'✅ ISODate' if is_datetime else '❌ 其他格式'}")

# P1-B: adj_close 驗證
print("\n[P1-B] adj_close 覆蓋率:")
total = db.stock_price.count_documents({})
with_adj = db.stock_price.count_documents({'adj_close': {'$exists': True, '$ne': None}})
coverage = with_adj / total * 100 if total > 0 else 0
status = "✅" if coverage >= 98 else "⚠️"
print(f"  {status} {coverage:.2f}% ({with_adj:,}/{total:,})")

# P2-A: 股票分割驗證
print("\n[P2-A] 股票分割數據:")
if 'stock_split_events' in db.list_collection_names():
    total_events = db.stock_split_events.count_documents({})
    print(f"  ✅ {total_events:,} 個事件")
else:
    print(f"  ⚠️  集合不存在")

# P2-B: 市值與換手率驗證
print("\n[P2-B] 市值與換手率:")
with_mc = db.stock_price.count_documents({'market_cap': {'$exists': True, '$ne': None}})
with_tr = db.stock_price.count_documents({'turnover_rate': {'$exists': True, '$ne': None}})
mc_coverage = with_mc / total * 100 if total > 0 else 0
tr_coverage = with_tr / total * 100 if total > 0 else 0
mc_status = "✅" if mc_coverage >= 80 else "⚠️"
tr_status = "✅" if tr_coverage >= 80 else "⚠️"
print(f"  market_cap: {mc_status} {mc_coverage:.2f}%")
print(f"  turnover_rate: {tr_status} {tr_coverage:.2f}%")

print("\n" + "="*80)
print("驗證完成")
print("="*80)
EOF
```

---

## 🔍 故障排除

### 問題 1: MongoDB 連線失敗

```bash
# 檢查 MongoDB 狀態
mongosh --eval "db.adminCommand('ping')"

# 啟動 MongoDB（macOS）
brew services start mongodb-community

# 啟動 MongoDB（Docker）
docker-compose up -d mongodb
```

### 問題 2: Python 套件缺失

```bash
pip install pymongo requests
```

### 問題 3: 權限錯誤

```bash
chmod +x scripts/execute_all_improvements.sh
```

### 問題 4: API Token 無效

```bash
# 檢查 token
echo $FINMIND_API_TOKEN

# 設定 token
export FINMIND_API_TOKEN="your_token_here"
```

### 問題 5: 執行緩慢

```bash
# 使用 --limit 分批執行
python3 src/calculators/adj_close_calculator_atomic.py --all --limit 100 --execute

# 檢查 MongoDB 索引
mongosh tw_stock_analysis --eval "db.stock_price.getIndexes()"
```

---

## 📊 日誌位置

所有工具都會在 `logs/` 目錄產生詳細日誌：

```bash
logs/
├── force_decimal_migration_20250217_204500.log
├── date_cleaning_20250217_205000.log
├── atomic_adj_close_20250217_210000.log
├── stock_split_20250217_212000.log
└── market_metrics_20250217_213000.log
```

查看最新日誌：
```bash
tail -f logs/*.log
```

---

## 🎯 成功標準

| 項目 | 標準 | 驗證方式 |
|------|------|----------|
| P0: 精度 | 100% Decimal128 | `quick_type_check.py` |
| P1-A: 日期 | 100% ISODate | 驗證腳本 |
| P1-B: adj_close | ≥ 98% 覆蓋率 | 驗證腳本 |
| P1-B: 原子性 | 100% 完整性 | 隨機抽樣檢查 |
| P2-A: 分割 | 有數據 | 集合存在且有記錄 |
| P2-B: 市值 | ≥ 80% 覆蓋率 | 驗證腳本 |

---

## 📞 獲取幫助

1. **查看詳細文檔**:  
   [DATABASE_PROFESSIONAL_IMPROVEMENTS.md](DATABASE_PROFESSIONAL_IMPROVEMENTS.md)

2. **查看日誌**:  
   `logs/` 目錄中的最新日誌

3. **重新執行驗證**:  
   使用上面的一鍵驗證腳本

---

**總執行時間**: 約 40-60 分鐘（取決於數據量和系統性能）

**建議執行時間**: 非交易時段，避免影響其他服務
