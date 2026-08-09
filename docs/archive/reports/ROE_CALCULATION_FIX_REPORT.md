# ROE 計算錯誤修正報告

## 📋 問題描述

用戶發現 DuPont 分析頁面顯示台積電 (2330) 的 ROE 為 **8.68%**，標註為「偏低 (<10%) - 獲利能力不佳」，但實際上台積電的 ROE 應該在 20-30% 以上。

---

## 🔍 問題根本原因分析

### 1. **FinMind 資料結構問題**

**發現時間：2026-02-17 15:30**

- FinMind API 回傳的資產負債表**沒有直接提供 `totalLiabilities`（負債總額）**
- 只提供 `Liabilities_per`（負債百分比，如 34.77%）
- 導致資料庫中 `totalLiabilities = 0`，使得 `equityMultiplier = totalAssets / equity = 1`

**解決方案：**
```python
# reorganize_financial_data.py (Line 123)
total_liabilities = total_assets - total_equity if (total_assets and total_equity) else 0
```

### 2. **資料下載腳本覆蓋問題**

**發現時間：2026-02-17 15:45**

- `financial_statements` 集合中的資料被後續操作覆蓋
- 原本應儲存完整列表（101 筆資產負債表項目），但只剩單一欄位
- 需要重新執行 `download_financial_2330.py`

**解決方案：**
```bash
python3 scripts/download_financial_2330.py  # 重新下載完整資料
python3 scripts/reorganize_financial_data.py  # 重新計算負債
python3 scripts/migrate_financial_statements_to_reports.py  # 遷移到 financial_reports
```

### 3. **ROE 未年化問題（核心問題）**

**發現時間：2026-02-17 16:00**

FinMind 的財報數據是**單季制**，不是累計制：
- Q1 營收：592.6B
- Q2 營收：673.5B（不是 Q1+Q2 的累計）
- Q3 營收：759.7B
- Q4 營收：868.5B

**錯誤計算：**
```typescript
// 舊邏輯
const assetTurnover = revenue / totalAssets;  // 單季營收
const ROE = netMargin * assetTurnover * equityMultiplier;
// 結果：42.79% × 0.1232 × 1.533 = 8.08% ❌
```

**正確計算：**
```typescript
// 新邏輯 (financial.service.ts Line 447-455)
const isQuarterly = report.fiscalPeriod && report.fiscalPeriod.startsWith('Q');
const annualizationFactor = isQuarterly ? 4 : 1;
const annualizedRevenue = revenue * annualizationFactor;
const assetTurnover = annualizedRevenue / totalAssets;  // 年化營收
const ROE = netMargin * assetTurnover * equityMultiplier;
// 結果：42.79% × 0.4928 × 1.533 = 32.33% ✅
```

### 4. **優先使用舊 ROE 值的問題**

**發現時間：2026-02-17 16:15**

```typescript
// 舊邏輯 (Line 462)
const reportedROE = ratios?.roe || calculatedROE;  // 優先使用資料庫中未年化的值

// 新邏輯
const reportedROE = calculatedROE;  // 直接使用計算的年化值
```

---

## ✅ 修正結果驗證

### 修正前
```
2024 Q3 台積電財報：
- ROE: 8.08% ❌（偏低）
- 淨利率: 42.79%
- 資產週轉率: 0.12 ❌（未年化）
- 權益乘數: 1.00 ❌（負債為 0）
- 評級：偏低 (<10%) - 獲利能力不佳 ❌
```

### 修正後
```
2024 Q3 台積電財報：
- ROE: 32.33% ✅（優異）
- 淨利率: 42.79%
- 資產週轉率: 0.49 ✅（年化後）
- 權益乘數: 1.53 ✅（正確計算）
- 評級：優異 (>20%) - 獲利能力極佳 ✅
```

### 2025 Q3（最新財報）
```
- ROE: 35.89% ✅
- 淨利率: 45.64%
- 資產週轉率: 0.54 ✅
- 權益乘數: 1.46 ✅
- 評級：優異 (>20%) ✅
```

---

## 📝 修正的檔案清單

1. **scripts/reorganize_financial_data.py**
   - Line 123: 新增負債計算邏輯
   - Line 154: 在 balanceSheet 中加入 totalLiabilities

2. **scripts/migrate_financial_statements_to_reports.py** (新建)
   - 將修正後的資料遷移到 financial_reports 集合

3. **src/modules/financial/financial.service.ts**
   - Line 447-455: 新增季報年化邏輯
   - Line 462: 改為使用計算的 ROE，不再使用資料庫舊值

---

## 🎯 經驗教訓

### 1. **資料驗證的重要性**
- ❌ 不應該直接跳過有問題的資料（如 Q4）
- ✅ 應該追根究底，找出資料錯誤的源頭並修正

### 2. **財報數據的理解**
- FinMind 的季報是**單季制**，需要年化處理
- 資產負債表是**時點數**（期末餘額）
- 損益表是**期間數**（當季累計）

### 3. **API 資料結構的完整性**
- FinMind 沒有直接提供 `totalLiabilities`
- 需要通過 `totalAssets - equity` 計算
- 或從 `Liabilities_per` 反推

### 4. **快取管理**
- 修改計算邏輯後，需要重新編譯 (`npm run build`)
- 需要清除應用層快取（重啟伺服器）
- 資料庫層快取可能需要手動清除

---

## 📊 相關指標參考

### 台積電歷史 ROE（修正後）

| 季度 | ROE | 淨利率 | 資產週轉率 | 權益乘數 |
|------|-----|--------|------------|----------|
| 2025 Q3 | 35.89% | 45.64% | 0.54 | 1.46 |
| 2025 Q2 | 33.61% | 42.57% | 0.53 | 1.52 |
| 2025 Q1 | 30.66% | 43.00% | 0.47 | 1.55 |
| 2024 Q4 | 34.29% | 43.12% | 0.52 | 1.55 |
| 2024 Q3 | 32.33% | 42.79% | 0.49 | 1.53 |
| 2024 Q2 | 25.93% | 36.77% | 0.45 | 1.57 |
| 2024 Q1 | 24.02% | 38.00% | 0.41 | 1.58 |

**結論：台積電的 ROE 維持在 24-36% 之間，屬於優異水平** ✅

---

## 🔄 後續建議

1. **批次更新所有股票的財報資料**
   - 執行 `reorganize_financial_data.py` 處理所有股票
   - 確保所有公司都有正確的負債數據

2. **建立資料完整性檢查機制**
   ```python
   # 檢查異常資料
   if total_liabilities == 0 and total_assets > 0:
       logger.warning(f"{symbol} {year}Q{season} 負債為 0，資料可能不完整")
   ```

3. **ROE 顯示優化**
   - 在網頁上標註「年化」
   - 提供單季 vs 年化的切換選項

4. **資料來源多元化**
   - FinMind 資料不完整時，考慮補充其他資料源
   - 台灣公開資訊觀測站、Yahoo Finance 等

---

**報告日期：2026-02-17**  
**修正完成時間：2026-02-17 16:20**  
**狀態：✅ COMPLETE**
