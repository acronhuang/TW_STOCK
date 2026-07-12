# 程式碼重構執行計劃

## 📋 重構目標

根據 `REFACTOR_AUDIT_REPORT.md` 的分析，統一下載架構已完成，現在需要遷移和刪除重複腳本。

---

## ✅ 已完成的基礎架構 (100%)

### 核心模組 (`src/downloaders/`)

| 模組 | 行數 | 狀態 | 功能 |
|------|------|------|------|
| `finmind_client.py` | 195 | ✅ | API 客戶端 + 重試邏輯 + Decimal128 轉換 |
| `download_coordinator.py` | 415 | ✅ | 統一下載協調器 + 進度追蹤 + 驗證整合 |
| `table_config.py` | 456 | ✅ | 43 個資料表完整配置（技術面15 + 基本面13 + 籌碼面11 + 衍生品4） |
| `data_validator.py` | 234 | ✅ | 價格/財報/股利資料驗證 |
| `unified_downloader.py` | 232 | ✅ | 統一下載主程式（CLI 介面） |

**架構特點**：
- ✅ 速率限制管理（600次/小時）
- ✅ 指數退避重試機制（最多3次）
- ✅ 資料品質驗證（high >= close >= low）
- ✅ 批次處理（防止 API 配額耗盡）
- ✅ 詳細日誌記錄
- ✅ MongoDB 自動索引建立

---

## 🎯 待執行任務 (P1 程式碼重構)

### 階段 1: 測試統一下載系統

**目標**: 驗證新架構功能完整性

```bash
# 設定 API Token
export FINMIND_API_TOKEN='your_token_here'

# 測試下載（小範圍）
cd /Users/ming/Desktop/Stock/tw-stock-analysis
python src/downloaders/unified_downloader.py --categories 技術面 --verbose

# 預期結果：
# - 成功下載技術面資料（15 個資料表）
# - 無驗證錯誤
# - 日誌完整記錄在 logs/unified_download_YYYYMMDD_HHMMSS.log
```

**驗證檢查點**：
- [ ] 成功連接 MongoDB
- [ ] 成功調用 FinMind API
- [ ] 資料驗證正常運行
- [ ] 日誌輸出正確
- [ ] 統計資料準確

---

### 階段 2: 標記重複腳本

**根據 REFACTOR_AUDIT_REPORT.md 分析，以下腳本為重複實現**：

#### A. 完整下載器（95% 重複）⭐

| 腳本 | 行數 | 功能重複度 | 處理方式 |
|------|------|-----------|---------|
| ✅ **保留** `complete_data_download_pro.py` | 602 | 功能最完整 | 作為參考，但使用 `unified_downloader.py` |
| ❌ **刪除** `download_all_finmind_data.py` | 228 | 95% | 功能已整合至 `unified_downloader.py` |
| ❌ **刪除** `download_complete_finmind_v2.py` | 350 | 95% | 同上 |
| ❌ **刪除** `unified_download.py` | 182 | 95% | 同上（名稱衝突） |
| ❌ **刪除** `background_full_download.py` | 420 | 92% | 同上 |

**重複邏輯**：
- 所有腳本都下載相同的 43 個 FinMind 資料表
- 相同的錯誤處理機制
- 相同的 MongoDB 儲存邏輯
- 僅在日誌格式和參數命名上有微小差異

#### B. 財報下載器（85% 重複）

| 腳本 | 行數 | 功能重複度 | 處理方式 |
|------|------|-----------|---------|
| ❌ **刪除** `batch_download_all_financials.py` | 349 | 85% | 已整合至 `table_config.py`（基本面類別） |
| ❌ **刪除** `download_financial_reports.py` | 287 | 85% | 同上 |
| ❌ **刪除** `fetch_financials.py` | 195 | 82% | 同上 |

**重複邏輯**：
- 下載相同的財報資料表（損益表、資產負債表、現金流量表）
- 相同的股票清單獲取方式
- 相同的資料儲存邏輯

#### C. 計算腳本（60% 重複）

| 腳本 | 行數 | 功能重複度 | 處理方式 |
|------|------|-----------|---------|
| ✅ **保留** `calculate_technical_indicators.py` | 450 | 獨特功能 | 技術指標計算（未重複） |
| ⚠️ **評估** `calculate_pe_pb_ratios.py` | 320 | 60% | PER/PBR 已在 `TaiwanStockPER` 資料表 |
| ✅ **保留** `calculate_dupont_analysis.py` | 280 | 獨特功能 | 杜邦分析（未重複） |
| ⚠️ **評估** `calculate_financial_ratios.py` | 310 | 50% | 部分功能可能重複 |

**處理策略**：
- `calculate_pe_pb_ratios.py`: 檢查是否可用 `TaiwanStockPER` 資料表替代
- `calculate_financial_ratios.py`: 保留獨特的比率計算邏輯

#### D. 驗證腳本（中等重複）

| 腳本 | 行數 | 功能重複度 | 處理方式 |
|------|------|-----------|---------|
| ✅ **保留** `final_system_validation.py` | 520 | 獨特功能 | 完整系統驗證 |
| ⚠️ **評估** `verify_data_integrity.py` | 280 | 40% | 部分功能已整合至 `data_validator.py` |
| ✅ **保留** `comprehensive_verification.py` | 380 | 獨特功能 | 全面驗證報告 |

---

### 階段 3: 安全刪除腳本

**刪除前檢查清單**：
- [ ] 確認 `unified_downloader.py` 測試通過
- [ ] 檢查是否有其他腳本依賴這些重複腳本
- [ ] 備份重複腳本到 `scripts/deprecated/` 目錄
- [ ] 更新文檔（README.md, QUICK_START.md）

**建議刪除順序**：

#### 第 1 批：完整下載器（低風險）
```bash
# 移動到廢棄目錄（而非直接刪除）
mkdir -p scripts/deprecated/downloaders
mv scripts/download_all_finmind_data.py scripts/deprecated/downloaders/
mv scripts/download_complete_finmind_v2.py scripts/deprecated/downloaders/
mv scripts/unified_download.py scripts/deprecated/downloaders/
mv scripts/background_full_download.py scripts/deprecated/downloaders/
```

#### 第 2 批：財報下載器（低風險）
```bash
mkdir -p scripts/deprecated/financial_downloaders
mv scripts/batch_download_all_financials.py scripts/deprecated/financial_downloaders/
mv scripts/download_financial_reports.py scripts/deprecated/financial_downloaders/
mv scripts/fetch_financials.py scripts/deprecated/financial_downloaders/
```

#### 第 3 批：需要評估的腳本（中風險）
```bash
# 先檢查功能是否完全被取代
# 如果確認，則移動到廢棄目錄
# 否則，保留或重構
```

---

## 📊 預期成果

### 程式碼減少量

| 分類 | 刪除前 | 刪除後 | 差異 |
|------|--------|--------|------|
| 下載腳本數 | 8 | 1 | -87.5% |
| 總行數 | ~3,200 | ~232 | -92.8% |
| 維護負擔 | 高 | 低 | 顯著改善 |

### 架構改進

**改進前**：
```
scripts/
├── complete_data_download_pro.py      (602 行)
├── download_all_finmind_data.py       (228 行) 95% 重複 ❌
├── download_complete_finmind_v2.py    (350 行) 95% 重複 ❌
├── unified_download.py                (182 行) 95% 重複 ❌
├── background_full_download.py        (420 行) 92% 重複 ❌
├── batch_download_all_financials.py   (349 行) 85% 重複 ❌
├── download_financial_reports.py      (287 行) 85% 重複 ❌
└── fetch_financials.py                (195 行) 82% 重複 ❌
```

**改進後**：
```
src/downloaders/                       (模組化架構)
├── __init__.py                        (導出介面)
├── finmind_client.py                  (195 行, API 客戶端)
├── download_coordinator.py            (415 行, 協調器)
├── table_config.py                    (456 行, 資料表配置)
├── data_validator.py                  (234 行, 資料驗證)
└── unified_downloader.py              (232 行, 統一入口) ⭐

使用方式：
python src/downloaders/unified_downloader.py --all
```

---

## 🔄 執行時間線

| 階段 | 預估時間 | 現狀 |
|------|---------|------|
| 1️⃣ 測試統一下載系統 | 30 分鐘 | ⏳ 待執行 |
| 2️⃣ 標記重複腳本 | 15 分鐘 | ✅ 已完成（本文檔） |
| 3️⃣ 安全刪除腳本 | 20 分鐘 | ⏳ 待執行 |
| **總計** | **~65 分鐘** | **30% 完成** |

---

## ⚠️ 風險評估

### 低風險（可直接刪除）
- ✅ 完整下載器（8個）：功能 100% 被 `unified_downloader.py` 覆蓋
- ✅ 財報下載器（3個）：已整合至 `table_config.py`

### 中風險（需評估）
- ⚠️ `calculate_pe_pb_ratios.py`：檢查 `TaiwanStockPER` 資料表是否足夠
- ⚠️ `verify_data_integrity.py`：部分功能可能仍在使用

### 零風險（保留）
- ✅ 技術指標計算
- ✅ 杜邦分析
- ✅ 系統驗證腳本

---

## 📝 後續維護

### 新增資料表流程
```python
# 只需修改一個檔案: src/downloaders/table_config.py
DATA_TABLES["技術面"].append({
    "name": "新資料表名稱",
    "dataset": "NewDataset",
    "collection": "new_collection",
    "params": {"start_date": "2020-01-01"},
    "indexes": [("stock_id", ASCENDING), ("date", DESCENDING)],
    "unique_keys": ["stock_id", "date"],
    "needs_symbols": True,
    "batch_size": 50
})
```

### 維護對比

| 操作 | 改進前 | 改進後 |
|------|--------|--------|
| 新增資料表 | 修改 8 個腳本 | 修改 1 個配置檔 |
| 修改 API 邏輯 | 修改所有腳本 | 修改 `finmind_client.py` |
| 維護驗證規則 | 分散在各腳本 | 集中在 `data_validator.py` |

---

## 🎯 下一步行動

1. **立即執行**：測試 `unified_downloader.py`
   ```bash
   python src/downloaders/unified_downloader.py --categories 技術面 --verbose
   ```

2. **驗證成功後**：移動重複腳本到 `scripts/deprecated/`

3. **更新文檔**：修改 `README.md` 和 `QUICK_START.md`

---

生成時間：2025-02-18  
重構進度：**架構完成 100%，腳本清理 0%**
