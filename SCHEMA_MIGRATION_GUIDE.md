# 📋 資料庫 Schema 重構執行指南

**日期：** 2026-02-20  
**狀態：** 執行中

---

## 🎯 重構目標

1. **Float → Decimal128**：所有金額/價格欄位改用 Decimal128
2. **統一欄位名稱**：close → closePrice, volume → tradeVolume
3. **加入驗證機制**：價格邏輯、範圍驗證
4. **更新程式碼**：Python 與 NestJS 同步更新

---

## ✅ 已完成項目

### 1. 備份（✅ 完成）
```bash
✅ 備份目錄：backup_20260220/
✅ 9 個腳本檔案已備份
✅ MongoDB 資料庫已備份
```

### 2. 遷移腳本建立（✅ 完成）
```bash
✅ scripts/database/migrate_to_decimal128.py
   - 轉換 5 個集合的數值欄位
   - 批次處理，支援大量資料
   - 完整日誌記錄

✅ scripts/database/unify_field_names.py
   - 統一 tickers 欄位名稱
   - 建立相容 View（過渡期）
   - 資料一致性檢查

✅ scripts/database/verify_decimal_migration.py
   - 驗證型態轉換
   - 檢查價格邏輯
   - 精度驗證
```

### 3. NestJS Schema 更新（✅ 完成）
```typescript
✅ src/modules/ticker/schemas/ticker.schema.ts
   - 所有價格欄位改用 Decimal128
   - 加入欄位驗證規則
   - 實作 Document Middleware（價格邏輯驗證）
   - 標記相容欄位為 deprecated

✅ src/modules/financial/schemas/financial-report.schema.ts
   - Income Statement 改用 Decimal128
   - Balance Sheet 改用 Decimal128
   - Cash Flow 改用 Decimal128
```

---

## 🚀 執行步驟（按順序）

### 步驟 1：執行 Decimal128 遷移
```bash
cd /Users/ming/Desktop/Stock/tw-stock-analysis

# 執行遷移（會提示確認）
python scripts/database/migrate_to_decimal128.py

# 預期時間：10-30 分鐘（視資料量而定）
# 日誌位置：logs/schema_migration_*.log
```

**預期輸出：**
```
🚀 開始資料庫 Schema 遷移：Float → Decimal128
============================================================
開始遷移 tickers 集合
總筆數: 2,000,000
已處理: 2,000,000/2,000,000 (100.0%) | 已更新: 1,850,000
✅ tickers 完成

開始遷移 financial_reports 集合
總筆數: 40,000
已處理: 40,000/40,000 (100.0%) | 已更新: 38,500
✅ financial_reports 完成

🎉 遷移完成！
總更新筆數：1,888,500
執行時間：1,234.56 秒
```

### 步驟 2：驗證遷移結果
```bash
# 執行驗證腳本
python scripts/database/verify_decimal_migration.py

# 預期輸出
```
🔍 開始驗證 Decimal128 遷移結果
============================================================
檢查 tickers 集合...
  ✅ openPrice: 100% Decimal128
  ✅ closePrice: 100% Decimal128
  ✅ highPrice: 100% Decimal128
  ✅ lowPrice: 100% Decimal128

檢查價格邏輯...
  ✅ highPrice >= closePrice 檢查通過
  ✅ lowPrice <= closePrice 檢查通過

✅ 所有檢查通過！遷移成功！
```

### 步驟 3：統一欄位名稱
```bash
# 執行欄位統一（建立相容 View）
python scripts/database/unify_field_names.py

# 這會：
# 1. 同步 close ↔ closePrice
# 2. 同步 volume ↔ tradeVolume
# 3. 建立 tickers_legacy View（過渡期使用）
```

### 步驟 4：更新 Python 程式碼
接下來需要更新所有使用數值欄位的 Python 程式碼：

```python
# ❌ 舊代碼
price = doc['closePrice']  # 這會得到 Decimal128 物件

# ✅ 新代碼
from bson.decimal128 import Decimal128
from decimal import Decimal

# 讀取時轉換
price = float(doc['closePrice'].to_decimal())

# 寫入時轉換
data = {
    'closePrice': Decimal128(Decimal('123.45')),
    'tradeVolume': 1000000  # 整數不需轉換
}
```

### 步驟 5：測試 NestJS API
```bash
# 啟動 NestJS 服務
cd /Users/ming/Desktop/Stock/tw-stock-analysis
npm run start:dev

# 測試 API 端點
curl http://localhost:3000/api/tickers/2330?date=2026-02-19
```

---

## 📝 Python 程式碼更新檢查清單

需要更新的檔案（使用 Decimal）：

### 已識別需要更新的文件
```bash
# 下載類（未來重構時處理）
□ scripts/batch_download_financials.py
□ scripts/complete_data_download_pro.py

# 計算類（需立即更新）
□ scripts/calculate_technical_indicators.py
□ scripts/calculate_river_charts.py
□ scripts/calculate_bull_bear_indicators.py

# 驗證類
□ scripts/verify_financial_data.py
□ scripts/final_system_validation.py
```

### 更新範例
```python
# 在檔案開頭加入
from bson.decimal128 import Decimal128
from decimal import Decimal

# 讀取資料時
def get_stock_price(symbol: str, date: str):
    doc = db.tickers.find_one({'symbol': symbol, 'date': date})
    
    # ❌ 舊方式
    # price = doc['closePrice']  # Decimal128 物件
    
    # ✅ 新方式
    price = float(doc['closePrice'].to_decimal())
    return price

# 寫入資料時
def save_stock_price(data: dict):
    # ✅ 轉換為 Decimal128
    data['closePrice'] = Decimal128(Decimal(str(data['closePrice'])))
    data['openPrice'] = Decimal128(Decimal(str(data['openPrice'])))
    
    db.tickers.insert_one(data)
```

---

## ⚠️ 注意事項

### 過渡期策略
1. **相容欄位保留**：close/volume 欄位暫時保留
2. **View 提供相容性**：tickers_legacy View 映射舊欄位
3. **程式碼逐步遷移**：可以分批更新程式碼
4. **雙寫確保一致**：寫入時同步新舊欄位

### 刪除相容欄位時機
```bash
# 條件：
✅ 所有 Python 程式碼已更新為 closePrice/tradeVolume
✅ 所有 API 測試通過
✅ 無任何程式碼使用 close/volume 欄位
✅ 已運行至少 2 週無問題

# 執行：
python scripts/database/remove_legacy_fields.py
```

---

## 🔄 回滾方案

### 如果遷移失敗
```bash
# 完全回滾資料庫
mongorestore --drop --db tw_stock_analysis backup_20260220/mongodb_backup/tw_stock_analysis/

# 回滾 NestJS Schema
git checkout HEAD -- src/modules/ticker/schemas/
git checkout HEAD -- src/modules/financial/schemas/
```

### 如果 API 出現問題
```bash
# 暫時使用相容 View
# 將所有查詢改為 db.tickers_legacy
# 保留所有欄位相容性，待修正後再切回
```

---

## 📊 執行進度追蹤

### 遷移狀態
- [x] 建立遷移腳本
- [x] 更新 NestJS Schema
- [ ] 執行 Decimal128 遷移
- [ ] 驗證遷移結果
- [ ] 統一欄位名稱
- [ ] 更新 Python 程式碼
- [ ] 測試所有 API
- [ ] 監控運行 1 週
- [ ] 移除相容欄位

### 程式碼更新進度
- [ ] 計算類腳本（3 個）
- [ ] 驗證類腳本（2 個）
- [ ] 下載類腳本（留待重構）

---

## 🎯 下一步建議

### 立即執行（優先級 P0）
```bash
1. 執行 Decimal128 遷移
   python scripts/database/migrate_to_decimal128.py

2. 驗證遷移結果
   python scripts/database/verify_decimal_migration.py

3. 統一欄位名稱
   python scripts/database/unify_field_names.py
```

### 本週完成（優先級 P1）
```bash
4. 更新計算類 Python 程式碼
5. 測試所有 API 端點
6. 監控錯誤日誌
```

### 下週完成（優先級 P2）
```bash
7. 重構下載功能（43 個資料表）
8. 刪除舊腳本檔案
```

---

## 📞 問題與支援

### 常見問題

**Q: 遷移需要多久？**
A: 取決於資料量，預估 10-30 分鐘。tickers 集合最大（~200萬筆）

**Q: 遷移期間可以使用系統嗎？**
A: 建議停機維護，或在非營業時間執行

**Q: 如何確認遷移成功？**
A: 執行驗證腳本，確保所有檢查通過

**Q: Python 程式碼一定要全部更新嗎？**
A: 過渡期可以混用，但建議儘快全部更新完成

---

**準備好了嗎？執行以下命令開始遷移：**

```bash
cd /Users/ming/Desktop/Stock/tw-stock-analysis
chmod +x scripts/database/migrate_to_decimal128.py
python scripts/database/migrate_to_decimal128.py
```

---

*Schema 重構執行指南 v1.0 | 2026-02-20*
