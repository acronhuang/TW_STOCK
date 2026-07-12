# 資料庫改進執行指南

## 📋 工具清單

所有工具已創建完成：

✅ **P0: 精度修復**
- `src/migrations/p0_force_decimal_migration.py` - 強制 Decimal128 遷移
- `src/utils/quick_type_check.py` - 快速類型檢查

✅ **P1: 原子性與完整性**
- `src/utils/date_cleaner.py` - 日期統一清洗
- `src/calculators/adj_close_calculator_atomic.py` - 原子性 adj_close 計算

✅ **P2: 缺失欄位**
- `src/downloaders/stock_split_downloader.py` - 股票分割數據下載
- `src/calculators/market_metrics_calculator.py` - 市值與換手率計算

✅ **執行腳本**
- `scripts/execute_all_improvements_auto.sh` - 自動執行（推薦）
- `scripts/execute_all_improvements.sh` - 交互式執行
- `scripts/check_tools.sh` - 檢查工具完整性

---

## 🚀 執行步驟

### 方法 1: 自動執行（推薦）

```bash
cd /Users/ming/Desktop/Stock/tw-stock-analysis

# 一鍵執行所有改進（自動確認）
./scripts/execute_all_improvements_auto.sh
```

這個腳本會：
1. 檢查環境（MongoDB、Python）
2. 自動執行所有 P0/P1/P2 階段
3. 自動驗證結果

**估計時間**: 40-60 分鐘

---

### 方法 2: 交互式執行

```bash
cd /Users/ming/Desktop/Stock/tw-stock-analysis

# 交互式執行（每個階段需確認）
./scripts/execute_all_improvements.sh
```

這個腳本會在每個階段詢問是否繼續。

---

### 方法 3: 手動分階段執行

如果想完全控制每個步驟：

#### P0: 精度修復（5-10分鐘）

```bash
cd /Users/ming/Desktop/Stock/tw-stock-analysis

# 預覽
python3 src/migrations/p0_force_decimal_migration.py --dry-run

# 執行
echo "YES" | python3 src/migrations/p0_force_decimal_migration.py --execute

# 驗證
python3 src/utils/quick_type_check.py
```

#### P1-A: 日期清洗（3-5分鐘）

```bash
# 預覽
python3 src/utils/date_cleaner.py --dry-run

# 執行
echo "YES" | python3 src/utils/date_cleaner.py --execute
```

#### P1-B: 原子性 adj_close（10-15分鐘）

```bash
# 測試單支股票
python3 src/calculators/adj_close_calculator_atomic.py --stock-id 2330 --dry-run

# 執行全部
echo "YES" | python3 src/calculators/adj_close_calculator_atomic.py --all --execute
```

#### P2-A: 股票分割（5-10分鐘）

```bash
# 設定 API Token
export FINMIND_API_TOKEN="$(grep FINMIND_API_TOKEN .env | cut -d'=' -f2 | tr -d '"' | tr -d "'")"

# 測試單支
python3 src/downloaders/stock_split_downloader.py --stock-id 2330 --dry-run

# 執行全部
echo "YES" | python3 src/downloaders/stock_split_downloader.py --all --execute
```

#### P2-B: 市值與換手率（10-15分鐘）

```bash
# 測試單支
python3 src/calculators/market_metrics_calculator.py --stock-id 2330 --dry-run

# 執行全部
echo "YES" | python3 src/calculators/market_metrics_calculator.py --all --execute
```

---

## ✅ 驗證結果

執行完成後，運行驗證腳本：

```python
python3 << 'EOF'
from pymongo import MongoClient
from bson.decimal128 import Decimal128

db = MongoClient()['tw_stock_analysis']

print("="*80)
print("驗證報告")
print("="*80)

# P0: 精度
div = db.dividend_detail.find_one({'cash_earnings_distribution': {'$exists': True, '$ne': None}})
is_decimal = isinstance(div.get('cash_earnings_distribution'), Decimal128) if div else False
print(f"\n[P0] Decimal128: {'✅' if is_decimal else '❌'}")

# P1-B: adj_close
total = db.stock_price.count_documents({})
with_adj = db.stock_price.count_documents({'adj_close': {'$exists': True, '$ne': None}})
coverage = with_adj / total * 100 if total > 0 else 0
print(f"\n[P1-B] adj_close 覆蓋率: {coverage:.2f}% {'✅' if coverage >= 98 else '⚠️'}")

# P2-B: 市值與換手率
with_mc = db.stock_price.count_documents({'market_cap': {'$exists': True, '$ne': None}})
with_tr = db.stock_price.count_documents({'turnover_rate': {'$exists': True, '$ne': None}})
mc_coverage = with_mc / total * 100 if total > 0 else 0
tr_coverage = with_tr / total * 100 if total > 0 else 0

print(f"\n[P2-B] market_cap: {mc_coverage:.2f}% {'✅' if mc_coverage >= 80 else '⚠️'}")
print(f"[P2-B] turnover_rate: {tr_coverage:.2f}% {'✅' if tr_coverage >= 80 else '⚠️'}")

# P2-A: 股票分割
if 'stock_split_events' in db.list_collection_names():
    events = db.stock_split_events.count_documents({})
    print(f"\n[P2-A] 股票分割事件: {events:,} 個 {'✅' if events > 0 else '⚠️'}")
else:
    print(f"\n[P2-A] 股票分割事件: ⚠️ 集合不存在")

print("\n" + "="*80)
EOF
```

---

## 📊 預期結果

| 項目 | 目標 | 狀態 |
|------|------|------|
| P0: Decimal128 轉換 | 100% | ✅ |
| P1-A: 日期統一 | 100% | ✅ |
| P1-B: adj_close 覆蓋率 | ≥ 98% | ✅ |
| P1-B: 數據完整性 | 100% | ✅ |
| P2-A: 股票分割數據 | 有數據 | ✅ |
| P2-B: 市值覆蓋率 | ≥ 80% | ✅ |
| P2-B: 換手率覆蓋率 | ≥ 80% | ✅ |

---

## 🔍 查看日誌

所有執行日誌保存在 `logs/` 目錄：

```bash
# 查看最新日誌
ls -lht logs/ | head -10

# 查看 P0 日誌
tail -100 logs/force_decimal_migration_*.log

# 查看 P1-B 日誌
tail -100 logs/atomic_adj_close_*.log
```

---

## 📚 詳細文檔

- [DATABASE_PROFESSIONAL_IMPROVEMENTS.md](DATABASE_PROFESSIONAL_IMPROVEMENTS.md) - 完整技術報告
- [P0_P1_P2_COMPLETION_REPORT.md](P0_P1_P2_COMPLETION_REPORT.md) - 完成報告
- [QUICK_START_IMPROVEMENTS.md](QUICK_START_IMPROVEMENTS.md) - 詳細執行指南

---

## 🚨 故障排除

### MongoDB 連線失敗

```bash
# 啟動 MongoDB（macOS）
brew services start mongodb-community

# 檢查連線
mongosh --eval "db.adminCommand('ping')"
```

### Python 套件缺失

```bash
pip install pymongo requests
```

### 執行緩慢

使用 `--limit` 參數測試：

```bash
python3 src/calculators/adj_close_calculator_atomic.py --all --limit 10 --execute
```

---

**建議執行時間**: 非交易時段，避免影響服務

**下一步**: 執行 `./scripts/execute_all_improvements_auto.sh` 🚀
