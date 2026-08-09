# 專案檔案整理

## 📂 核心功能檔案（必須保留）

### 資料下載
- `batch_download_all_financials.py` - 批次下載所有股票財報
- `fast_download_financials.py` - 快速下載（跳過 OTC）
- `download_goodinfo.py` - GoodInfo 爬蟲（備用資料源）

### 資料處理
- `reorganize_financial_data.py` - 重組財報資料（計算負債）
- `migrate_to_mongodb.py` - 資料遷移至 MongoDB
- `update_stock_names.py` - 更新公司名稱
- `fix_company_names.py` - 修復公司名稱

### 驗證與測試
- ✅ **`validate_system.py`** - **統一驗證腳本**（整合所有檢查）
  - 資料庫檢查
  - API 服務檢查
  - ROE 計算驗證
  - 資料完整性檢查
  - 資料品質檢查
  - 效能測試
  - 自動修復功能

---

## 🗑️ 可能重複的測試檔案

### 1. `system_health_check.py` 
- **功能**: 系統健康檢查
- **狀態**: 功能已整合至 `validate_system.py`
- **決策**: ⚠️ 可考慮刪除（功能重複）

### 2. `functional_tests.py`
- **功能**: 功能測試套件（19 項測試）
- **狀態**: 功能已整合至 `validate_system.py`
- **決策**: ⚠️ 可考慮刪除（功能重複）

### 3. `deep_data_quality_check.py`
- **功能**: 深度資料品質檢查
- **狀態**: 功能已整合至 `validate_system.py`
- **決策**: ⚠️ 可考慮刪除（功能重複）

### 4. `fix_data_quality_issues.py`
- **功能**: 修復資料品質問題
- **狀態**: 自動修復功能已整合至 `validate_system.py`
- **決策**: ⚠️ 可考慮刪除（功能重複）

### 5. `check_data_structure.py`
- **功能**: 檢查資料結構（除錯用）
- **狀態**: 臨時除錯腳本
- **決策**: ⚠️ 可考慮刪除（除錯完成）

---

## 🔧 專用工具檔案（保留）

### 6. `check_download_status.py`
- **功能**: 查詢下載進度
- **用途**: 監控批次下載狀態
- **決策**: ✅ **保留**（專用工具）

### 7. `test_dupont_industry.py`
- **功能**: 測試產業判斷邏輯
- **用途**: 開發測試用
- **決策**: ✅ **保留**（開發工具）

### 8. `create_test_financial_data.py`
- **功能**: 建立測試資料
- **用途**: 開發測試用
- **決策**: ✅ **保留**（開發工具）

---

## 📋 建議整理方案

### 方案 A：保守方案（建議）
**不刪除任何檔案**，但建立明確的使用指引：

1. **日常使用**: 只執行 `validate_system.py`
2. **開發除錯**: 依需求使用其他工具腳本
3. **建立 README**: 說明每個腳本的用途

### 方案 B：清理方案
**移動而非刪除**：

```bash
# 建立歸檔目錄
mkdir -p scripts/archive

# 移動已整合的腳本
mv scripts/system_health_check.py scripts/archive/
mv scripts/functional_tests.py scripts/archive/
mv scripts/deep_data_quality_check.py scripts/archive/
mv scripts/fix_data_quality_issues.py scripts/archive/
mv scripts/check_data_structure.py scripts/archive/
```

---

## 🎯 最終決策

建議採用 **方案 A（保守方案）**：

### 理由
1. **安全**: 不會誤刪重要功能
2. **彈性**: 開發時可能需要這些工具
3. **歷史**: 保留開發過程的記錄

### 執行方式
建立一個 `SCRIPTS_GUIDE.md` 說明使用方式：

```markdown
# 腳本使用指南

## 日常維護
- `python3 scripts/validate_system.py` - 系統完整驗證

## 資料下載
- `python3 scripts/batch_download_all_financials.py` - 下載財報
- `python3 scripts/check_download_status.py` - 查詢進度

## 開發除錯（進階）
- 其他 test_*.py 和 check_*.py 檔案為開發工具
```

---

## ✅ 結論

**不刪除任何檔案**，改為：
1. 建立清晰的使用指南
2. 主要使用 `validate_system.py`
3. 保留其他檔案作為開發工具

這樣既安全又專業！
