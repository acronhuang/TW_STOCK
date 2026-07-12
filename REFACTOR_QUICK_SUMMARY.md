# 🚀 重構計畫執行摘要 (Quick Reference)

**審計日期：** 2026-02-20

---

## 📊 一分鐘總覽

### 🔥 嚴重問題
```
❌ 嚴重重複：8 個下載腳本功能重複度 85-95%
⚠️ 中度問題：4 個計算腳本可整合
⚠️ 輕度問題：6 個驗證腳本可整合
```

### ✅ 預期效益
```
程式碼量減少：60% (5000行 → 2000行)
維護成本降低：70%
開發效率提升：統一入口 main.py
```

---

## 🗑️ 待刪除檔案清單（10-12 個）

### 下載類（8 個）- 完全刪除
```bash
❌ scripts/download_all_finmind_data.py           # 228 行
❌ scripts/download_complete_finmind_v2.py        # 350 行
❌ scripts/unified_download.py                    # 182 行
❌ scripts/batch_download_all_financials.py       # 349 行
❌ scripts/batch_download_financials.py           # 211 行
❌ scripts/fast_download_financials.py            # 207 行
❌ scripts/download_financial_2330.py             # 171 行
❌ scripts/download_finmind_complete.py           # 138 行
```
**刪除理由：** 功能完全重複，都在下載 FinMind 資料  
**替代方案：** 整合到 `src/downloaders/` 模組化 Class

### 優化類（1 個）
```bash
❌ scripts/optimize_collections.py                # 無備份機制
```
**保留替代：** `safe_optimize_collections.py`（有備份機制）

### 遷移類（2 個）- 執行後刪除
```bash
⚠️ scripts/migrate_financial_statements_to_reports.py
⚠️ scripts/verify_collection_migration.py
```
**刪除時機：** 確認資料遷移完成後

---

## 🏗️ 新架構設計

### 目標結構
```
tw-stock-analysis/
├── src/
│   ├── downloaders/              # 📥 下載模組（新建）
│   │   ├── finmind_client.py         # Base API Client
│   │   ├── financial_downloader.py   # 財報下載
│   │   ├── market_data_downloader.py # 行情下載
│   │   └── downloader_coordinator.py # 協調器
│   │
│   ├── calculators/              # 🧮 計算模組（新建）
│   │   ├── technical_indicators.py
│   │   ├── valuation_metrics.py
│   │   └── indicator_coordinator.py
│   │
│   ├── validators/               # ✅ 驗證模組（新建）
│   │   └── system_validator.py
│   │
│   ├── database/                 # 🗄️ 資料庫模組（新建）
│   │   ├── db_manager.py            # 統一連線管理
│   │   └── schema_validator.py
│   │
│   └── main.py                  # 🚀 唯一入口（新建）
│
├── scripts/                     # 📜 保留工具腳本（4個）
│   ├── safe_optimize_collections.py
│   ├── consolidate_collections.py
│   ├── final_system_validation.py
│   └── create_test_financial_data.py
│
└── pattern_recognition/         # 📊 型態識別（不變）
    └── （保持原樣，已模組化良好）
```

---

## 📋 重構執行步驟

### Phase 1：建立核心框架（第 1 週）
```bash
# 1. 建立目錄結構
mkdir -p src/downloaders src/calculators src/validators src/database

# 2. 實作 Base Class
# 文件：src/downloaders/finmind_client.py
# 功能：統一 API 呼叫、Token 管理、錯誤處理、頻率限制

# 3. 實作下載器
# 文件：src/downloaders/financial_downloader.py
# 整合：3 個財報下載腳本的功能

# 4. 實作主入口
# 文件：src/main.py
# 功能：統一命令列介面
```

**執行指令範例：**
```bash
# 下載所有資料
python src/main.py --download all

# 只下載財報
python src/main.py --download financial

# 指定股票
python src/main.py --download financial --symbols 2330 2317

# 計算技術指標
python src/main.py --calculate technical --symbols 2330

# 完整系統驗證
python src/main.py --validate
```

### Phase 2：整合與測試（第 2 週）
```bash
# 5. 實作其他下載器
# - market_data_downloader.py（行情資料）
# - institutional_downloader.py（法人資料）

# 6. 實作協調器
# - downloader_coordinator.py（管理 43 個資料表下載順序）

# 7. 測試所有下載功能
python src/main.py --download all --test-mode

# 8. 確認無誤後，刪除舊檔案
```

### Phase 3：資料庫優化（第 3 週）
```bash
# 9. 修正欄位型態（Float → Decimal128）
# 10. 統一欄位名稱（移除相容欄位 close/closePrice）
# 11. 實作 Schema 驗證器
```

---

## 🎯 核心模組設計

### 1. FinMindClient (Base Class)
```python
class FinMindClient:
    """所有下載器的基礎類別"""
    
    def __init__(self, token: str):
        self.token = token
        self.api_calls = 0
        self.max_calls_per_hour = 600
        
    def fetch_data(self, dataset: str, params: dict) -> dict:
        """統一 API 請求介面"""
        # - 自動管理 API 配額
        # - 錯誤重試（最多 3 次）
        # - 記錄日誌
        pass
```

### 2. FinancialReportDownloader
```python
class FinancialReportDownloader(FinMindClient):
    """財報專項下載器"""
    
    def download_all_financials(self, 
                               symbols: list,
                               include_otc: bool = True,
                               start_date: str = '2019-01-01'):
        """
        整合 3 個財報腳本的功能：
        - batch_download_financials.py
        - fast_download_financials.py
        - download_financial_2330.py
        
        新增功能：
        - 支援過濾上市/上櫃
        - 支援單一股票或批次
        - 自動續傳（斷點續下）
        """
        pass
```

### 3. DownloaderCoordinator
```python
class DownloaderCoordinator:
    """下載協調器（取代 complete_data_download_pro.py）"""
    
    def download_all_data(self, categories: list = None):
        """
        下載所有 43 個 FinMind 資料表
        
        分類管理：
        - 技術面（10 tables）
        - 籌碼面（9 tables）
        - 基本面（17 tables）
        - 其他（7 tables）
        """
        pass
```

### 4. main.py（唯一入口）
```python
def main():
    """統一命令列入口"""
    
    # 參數解析
    parser.add_argument('--download', choices=['all', 'financial', 'market'])
    parser.add_argument('--calculate', choices=['all', 'technical'])
    parser.add_argument('--validate', action='store_true')
    parser.add_argument('--symbols', nargs='+')
    
    # 執行對應功能
    # - 下載資料
    # - 計算指標
    # - 驗證系統
```

---

## 🚦 執行檢查清單

### 重構前必做
- [ ] **Git 建立 Tag：** `git tag -a v1.0-before-refactor -m "重構前備份"`
- [ ] **資料庫備份：** `mongodump --out backup_$(date +%Y%m%d)`
- [ ] **記錄所有執行中的任務：** 確認是否有排程腳本在運行
- [ ] **通知團隊成員：** 避免同時修改程式碼

### 重構中必做
- [ ] **漸進式開發：** 新舊並存，測試通過才刪除舊檔
- [ ] **持續測試：** 每個模組完成立即測試
- [ ] **記錄日誌：** `logs/refactor_$(date +%Y%m%d).log`
- [ ] **每日 Commit：** 小步快跑，方便回滾

### 重構後必做
- [ ] **功能測試：** 下載、計算、驗證全流程測試
- [ ] **效能測試：** 確認不比原版慢
- [ ] **資料驗證：** 比對新舊資料一致性
- [ ] **文檔更新：** README.md, API 說明
- [ ] **刪除舊檔案：** 確認無人使用後才刪除

---

## ⚠️ 資料庫 Schema 改進項目

### 高優先級
```typescript
// ❌ 問題：Float 精度問題
closePrice: number

// ✅ 修正：使用 Decimal128
closePrice: mongoose.Schema.Types.Decimal128
```

**影響集合：**
- `tickers`（所有價格欄位）
- `financial_reports`（所有金額欄位）
- `dividends`（現金股利）

### 中優先級
```typescript
// ❌ 問題：重複欄位（為了相容性保留）
closePrice: number
close: number  // 相容欄位

// ✅ 修正：統一使用 closePrice
```

**執行步驟：**
1. 資料遷移：`close` → `closePrice`
2. 更新所有查詢程式碼
3. 刪除 `close` 欄位定義
4. 更新 Schema 文檔

---

## 📞 決策表

| 問題 | 決策 | 理由 |
|------|------|------|
| 是否保留 `complete_data_download_pro.py`? | ❌ 不保留，整合到 Class | 應為模組而非腳本 |
| 是否保留 `calculate_all_indicators.py`? | ⚠️ 重構為協調器 | 只負責呼叫，不含邏輯 |
| Pattern Recognition 是否重構? | ✅ 不需要 | 已經模組化良好 |
| `scripts/` 目錄是否完全清空? | ❌ 保留 4 個工具腳本 | 資料庫維護需要 |
| 是否需要向下相容? | ⚠️ 過渡期需要 | 逐步遷移，避免中斷 |

---

## 🎓 DRY 原則檢查清單

### ✅ 符合 DRY
- [ ] 資料庫連線：統一 `db_manager.py`
- [ ] API 呼叫：統一 `finmind_client.py`
- [ ] Token 管理：從環境變數讀取，不硬編碼
- [ ] 錯誤處理：統一重試邏輯
- [ ] 日誌記錄：統一格式與目錄

### ❌ 違反 DRY（待修正）
- [ ] 8 個下載腳本重複 API 呼叫邏輯
- [ ] Token 硬編碼在多個檔案中
- [ ] 資料庫連線分散在各腳本
- [ ] 重複的資料驗證邏輯

---

## 🏆 成功指標

### 量化指標
```
✅ 程式碼行數減少 ≥ 60%
✅ scripts/ 檔案數量 ≤ 6 個
✅ 所有下載通過 main.py 入口
✅ API Token 零硬編碼
✅ 測試覆蓋率 ≥ 80%
```

### 質化指標
```
✅ 新增資料源：只需擴展一個 Class
✅ 修改邏輯：只需改一個檔案
✅ 新人上手：30 分鐘理解架構
✅ Bug 修復：5 分鐘定位問題
✅ Code Review：通過 DRY/SOLID 檢查
```

---

## 📄 相關文檔

- **詳細報告：** [REFACTOR_AUDIT_REPORT.md](./REFACTOR_AUDIT_REPORT.md)
- **開發規範：** [PROJECT_GUIDE.md](./PROJECT_GUIDE.md)
- **架構指令：** [.github/instructions/copilot-instructions.md](./.github/instructions/copilot-instructions.md)

---

**⏰ 下一步：等待您的確認**

請審閱此方案，確認後我將開始執行 Phase 1 重構。

---

*快速摘要 v1.0 | 2026-02-20*
