# 資料庫改進計畫執行指南

## 📋 總覽

本指南涵蓋三個階段的資料庫改進工作：

- **P0 (立即行動)**: 價格欄位精度遷移 - Decimal128
- **P1 (短期計畫)**: 命名規範化 + 調整後收盤價計算
- **P2 (中期計畫)**: 關鍵欄位補齊

## ⚠️ 重要提醒

1. **備份資料庫**: 在執行任何遷移前，請先備份！
   ```bash
   mongodump --db tw_stock_analysis --out ./backup_$(date +%Y%m%d)
   ```

2. **預覽模式**: 所有工具都支持 `--dry-run`，請先預覽再執行

3. **執行順序**: 建議按 P0 → P1 → P2 順序執行

---

## 🔴 P0: 價格欄位精度遷移

### 目標
將所有數值欄位從 `float` (double) 遷移到 `Decimal128`，消除浮點數誤差。

### 影響集合
- `dividend_detail`: 所有股利金額欄位
- `taiwan_stock_per`: `PER`, `PBR`, `price` 等
- `month_revenue_detail`: 營收欄位

### 執行步驟

#### 1. 預覽影響範圍
```bash
python3 src/migrations/p0_decimal_migration.py --dry-run
```

預期輸出：
```
🚀 開始 P0 階段：Decimal128 精度遷移
================================================================================
模式: 預覽模式（不會實際修改數據）
...
📊 遷移總結報告
集合數量: 3
總更新: 15,234 筆
```

#### 2. 實際執行
```bash
python3 src/migrations/p0_decimal_migration.py --execute
```

系統會要求輸入 `YES` 確認。

#### 3. 驗證結果
```bash
mongosh tw_stock_analysis --eval "
  var doc = db.dividend_detail.findOne();
  Object.keys(doc).forEach(function(k) {
    if (typeof doc[k] === 'object' && doc[k] && doc[k].constructor.name === 'Decimal128') {
      print(k + ': Decimal128 ✓');
    }
  });
"
```

### 預估時間
- 預覽: ~5 秒
- 實際執行: ~2-5 分鐘（視資料量而定）

---

## 🟡 P1-A: 命名規範化遷移

### 目標
統一所有欄位命名為 `snake_case`，消除混亂的 camelCase。

### 影響集合
- `stock_price`: `closePrice` → `close`, `tradeVolume` → `volume`
- `dividend_detail`: 所有 PascalCase 欄位 → snake_case
- `taiwan_stock_per`: `PER` → `pe_ratio`, `PBR` → `pb_ratio`

### 執行步驟

#### 1. 預覽影響範圍
```bash
python3 src/migrations/p1_naming_migration.py --dry-run
```

#### 2. 實際執行
```bash
python3 src/migrations/p1_naming_migration.py --execute
```

#### 3. 驗證結果
```bash
mongosh tw_stock_analysis --eval "
  print('=== stock_price 欄位檢查 ===');
  var sample = db.stock_price.findOne();
  print('close: ' + (sample.close ? '✓' : '✗'));
  print('volume: ' + (sample.volume ? '✓' : '✗'));
  print('closePrice (舊): ' + (sample.closePrice ? '還存在!' : '已清除 ✓'));
"
```

### ⚠️ 重要注意
此遷移會**重命名欄位**，會影響現有的查詢程式碼！請確保：
1. 先執行 P0（確保數據類型正確）
2. 更新所有程式碼中的欄位引用

### 預估時間
- 預覽: ~2 秒
- 實際執行: ~30 秒（使用批次操作）

---

## 🟢 P1-B: 調整後收盤價計算

### 目標
計算並新增 `adj_close` 欄位，這是所有量化回測的基礎。

### 調整邏輯
根據除權息事件，從最新日期往回推算：
- **現金股利**: `adj_close_before = adj_close_after × (close - dividend) / close`
- **股票股利**: `adj_close_before = adj_close_after × 10 / (10 + stock_dividend)`

### 執行步驟

#### 1. 單一股票測試
```bash
# 以台積電 (2330) 為例
python3 src/calculators/adj_close_calculator.py --stock-id 2330 --dry-run
```

查看輸出的調整因子和事件：
```
計算 2330 的調整後收盤價
股價記錄數: 1,234
除權息事件數: 15
  2025-06-15: cash_dividend = 2.75
  2024-12-15: cash_dividend = 2.75
  ...
```

#### 2. 小批次測試（前 10 支股票）
```bash
python3 src/calculators/adj_close_calculator.py --all --limit 10 --dry-run
```

#### 3. 全面執行（所有股票）
```bash
python3 src/calculators/adj_close_calculator.py --all --execute
```

這會處理 **~1,300 支股票**，預計需要 **5-10 分鐘**。

#### 4. 驗證結果
```bash
# 查看台積電的調整後收盤價
mongosh tw_stock_analysis --eval "
  db.stock_price.find(
    {stock_id: '2330'},
    {date: 1, close: 1, adj_close: 1, adjustment_factor: 1}
  ).sort({date: -1}).limit(5).forEach(function(doc) {
    var close = doc.close.toString();
    var adj = doc.adj_close ? doc.adj_close.toString() : 'N/A';
    var factor = doc.adjustment_factor ? doc.adjustment_factor.toString() : 'N/A';
    print(doc.date.toISOString().split('T')[0] + ' | close=' + close + ' | adj_close=' + adj + ' | factor=' + factor);
  });
"
```

預期輸出：
```
2026-02-20 | close=750.00 | adj_close=750.00 | factor=1.0000
2026-02-19 | close=748.00 | adj_close=748.00 | factor=1.0000
2026-02-18 | close=745.00 | adj_close=745.00 | factor=1.0000
...
```

### 預估時間
- 單支股票: ~1 秒
- 全部股票 (~1,300): ~5-10 分鐘

---

## 🔵 P2: 關鍵欄位補齊

### 目標
補齊專業財經分析所需的關鍵欄位。

### 補齊項目
1. **security_type**: 區分股票、ETF、權證等
2. **industry_l1/l2**: 多級行業分類
3. **is_delisted**: 標記下市股票（避免倖存者偏差）

### 執行步驟

#### 1. 預覽所有任務
```bash
python3 src/migrations/p2_field_enrichment.py --task all --dry-run
```

#### 2. 分別執行（推薦逐步檢查）

**任務 1: 新增證券類型**
```bash
python3 src/migrations/p2_field_enrichment.py --task add-security-type --dry-run
python3 src/migrations/p2_field_enrichment.py --task add-security-type --execute
```

驗證：
```bash
mongosh tw_stock_analysis --eval "
  db.taiwan_stock_info.aggregate([
    {\\$group: {_id: '\\$security_type', count: {\\$sum: 1}}},
    {\\$sort: {count: -1}}
  ]).forEach(printjson);
"
```

預期輸出：
```
{ _id: 'Stock', count: 1245 }
{ _id: 'ETF', count: 52 }
{ _id: 'Warrant', count: 48 }
```

**任務 2: 拆分行業分類**
```bash
python3 src/migrations/p2_field_enrichment.py --task split-industry --dry-run
python3 src/migrations/p2_field_enrichment.py --task split-industry --execute
```

**任務 3: 標記下市股票**
```bash
python3 src/migrations/p2_field_enrichment.py --task mark-delisted --dry-run
python3 src/migrations/p2_field_enrichment.py --task mark-delisted --execute
```

#### 3. 或一次執行全部
```bash
python3 src/migrations/p2_field_enrichment.py --task all --execute
```

### 預估時間
- 預覽: ~3 秒
- 實際執行: ~10 秒

---

## 📊 完整執行流程（一條龍）

### 前置準備

1. **備份資料庫**
   ```bash
   mongodump --db tw_stock_analysis --out ./backup_$(date +%Y%m%d)
   ```

2. **檢查 MongoDB 狀態**
   ```bash
   mongosh tw_stock_analysis --eval "db.stats()"
   ```

### 執行順序

#### 階段一：預覽所有變更
```bash
# P0: 預覽精度遷移
python3 src/migrations/p0_decimal_migration.py --dry-run

# P1-A: 預覽命名規範化
python3 src/migrations/p1_naming_migration.py --dry-run

# P1-B: 預覽調整後收盤價（測試單支股票）
python3 src/calculators/adj_close_calculator.py --stock-id 2330 --dry-run

# P2: 預覽欄位補齊
python3 src/migrations/p2_field_enrichment.py --task all --dry-run
```

#### 階段二：實際執行
```bash
# P0: 執行精度遷移
python3 src/migrations/p0_decimal_migration.py --execute

# P1-A: 執行命名規範化
python3 src/migrations/p1_naming_migration.py --execute

# P1-B: 執行調整後收盤價計算
python3 src/calculators/adj_close_calculator.py --all --execute

# P2: 執行欄位補齊
python3 src/migrations/p2_field_enrichment.py --task all --execute
```

### 總預估時間
- 預覽: ~15 秒
- 實際執行: ~8-15 分鐘（視資料量而定）

---

## 🔍 驗證與測試

### 完整驗證腳本
```bash
mongosh tw_stock_analysis --quiet --eval "
print('===== 資料庫改進驗證報告 =====\n');

// P0: Decimal128 驗證
print('[P0] Decimal128 精度驗證:');
var div = db.dividend_detail.findOne();
var hasDecimal = div && div.cash_earnings_distribution && 
                 div.cash_earnings_distribution.constructor.name === 'Decimal128';
print('  dividend_detail: ' + (hasDecimal ? '✓' : '✗'));

// P1-A: 命名規範驗證
print('\n[P1-A] 命名規範驗證:');
var price = db.stock_price.findOne();
print('  close欄位: ' + (price && price.close ? '✓' : '✗'));
print('  volume欄位: ' + (price && price.volume ? '✓' : '✗'));
print('  舊欄位已清除: ' + (price && !price.closePrice ? '✓' : '✗'));

// P1-B: adj_close 驗證
print('\n[P1-B] 調整後收盤價驗證:');
var adjCount = db.stock_price.countDocuments({adj_close: {\\$exists: true}});
var totalCount = db.stock_price.countDocuments({});
var coverage = (adjCount / totalCount * 100).toFixed(2);
print('  有 adj_close 的記錄: ' + adjCount.toLocaleString() + ' / ' + totalCount.toLocaleString() + ' (' + coverage + '%)');

// P2: 新欄位驗證
print('\n[P2] 新欄位驗證:');
var info = db.taiwan_stock_info.findOne({security_type: {\\$exists: true}});
print('  security_type: ' + (info ? '✓' : '✗'));
print('  industry_l1: ' + (info && info.industry_l1 ? '✓' : '✗'));

var delistedCount = db.taiwan_stock_info.countDocuments({is_delisted: true});
print('  下市標記數量: ' + delistedCount);

print('\n===== 驗證完成 =====');
"
```

預期輸出：
```
===== 資料庫改進驗證報告 =====

[P0] Decimal128 精度驗證:
  dividend_detail: ✓

[P1-A] 命名規範驗證:
  close欄位: ✓
  volume欄位: ✓
  舊欄位已清除: ✓

[P1-B] 調整後收盤價驗證:
  有 adj_close 的記錄: 5,119,117 / 5,119,117 (100.00%)

[P2] 新欄位驗證:
  security_type: ✓
  industry_l1: ✓
  下市標記數量: 88

===== 驗證完成 =====
```

---

## 🚨 故障排除

### 問題 1: 權限錯誤
```
PermissionError: [Errno 13] Permission denied
```
**解決方案:**
```bash
chmod +x src/migrations/*.py src/calculators/*.py
```

### 問題 2: MongoDB 連線失敗
```
pymongo.errors.ServerSelectionTimeoutError
```
**解決方案:**
```bash
# 檢查 MongoDB 是否運行
brew services list | grep mongodb-community

# 啟動 MongoDB
brew services start mongodb-community
```

### 問題 3: 模組找不到
```
ModuleNotFoundError: No module named 'pymongo'
```
**解決方案:**
```bash
pip3 install pymongo
```

### 問題 4: 數據不一致
如果發現某些欄位沒有正確轉換，可以：

1. 檢查日誌檔案（`logs/` 目錄）
2. 重新執行特定任務
3. 如有需要，從備份恢復後重試

---

## 📈 效果評估

### 改進前後對比

| 指標 | 改進前 | 改進後 | 改善 |
|------|--------|--------|------|
| 價格精度 | Float (±1e-15 誤差) | Decimal128 (無誤差) | ✅ 100% |
| 欄位命名 | camelCase/PascalCase 混用 | 統一 snake_case | ✅ |
| 回測可用性 | ✗ (無 adj_close) | ✓ (有 adj_close) | ✅ |
| 證券分類 | ✗ | ✓ (Stock/ETF/Warrant) | ✅ |
| 行業分類 | 單級 | 多級 (L1/L2) | ✅ |
| 倖存者偏差防護 | ✗ | ✓ (下市標記) | ✅ |

### 量化分析能力提升

改進後，系統可以支持：
- ✅ **回測**: 使用 adj_close 進行歷史策略驗證
- ✅ **同業比較**: 使用多級行業分類
- ✅ **ETF 分析**: 區分 ETF 與個股
- ✅ **精確計算**: Decimal128 消除浮點誤差
- ✅ **無偏分析**: 包含下市股票，避免倖存者偏差

---

## 📚 相關文檔

- [SMART_DOWNLOAD_GUIDE.md](SMART_DOWNLOAD_GUIDE.md) - 智能下載系統使用指南
- [REFACTOR_AUDIT_REPORT.md](REFACTOR_AUDIT_REPORT.md) - 系統重構審計報告

---

## ✅ 完成檢查清單

執行完成後，請確認：

- [ ] P0: Decimal128 遷移完成，數值欄位無浮點誤差
- [ ] P1-A: 欄位命名統一為 snake_case
- [ ] P1-B: 所有股票都有 adj_close 欄位
- [ ] P2: 新增 security_type, industry_l1/l2, is_delisted
- [ ] 驗證腳本通過所有檢查
- [ ] 日誌檔案無錯誤訊息
- [ ] 更新程式碼中的欄位引用（如有必要）

---

**準備好了嗎？** 從備份開始，然後執行第一個命令：

```bash
mongodump --db tw_stock_analysis --out ./backup_$(date +%Y%m%d)
python3 src/migrations/p0_decimal_migration.py --dry-run
```

祝改進順利！🚀
