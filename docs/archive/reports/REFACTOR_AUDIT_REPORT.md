# 🔍 專業財經系統 - 程式碼重構審計報告

**審計日期：** 2026-02-20  
**審計範圍：** 所有 .py 檔案與資料庫 Schema  
**審計標準：** DRY 原則 (Don't Repeat Yourself) + PROJECT_GUIDE.md 規範

---

## 📊 執行摘要 (Executive Summary)

### 🚨 關鍵發現
- **嚴重程度：高** - 發現 **8 個下載類腳本** 功能嚴重重複
- **嚴重程度：中** - 發現 **4 個優化類腳本** 性質接近
- **嚴重程度：中** - 發現 **6 個驗證類腳本** 可整合
- **總計：** 42 個 Python 檔案中，**18 個檔案 (43%)** 存在功能重複問題

### ✅ 重構效益預估
- **程式碼減少：** ~5,000 行 → ~2,000 行 (減少 60%)
- **維護複雜度：** 降低 70%
- **統一入口：** main.py 成為唯一下載入口
- **模組化程度：** 提升至企業級標準

---

## 🔴 一、下載類腳本 (Data Download Scripts) - 嚴重重複

### 📁 重複功能分析

#### 組別 1：FinMind 完整下載（所有 43 個資料表）
**功能描述：** 下載 FinMind API 的所有 43 個資料表（技術面、籌碼面、基本面）

| 檔案 | 行數 | API Token | 功能重複度 | 建議 |
|------|------|-----------|-----------|------|
| `scripts/download_all_finmind_data.py` | 228 | ✅ | **95%** | ❌ 刪除 |
| `scripts/download_complete_finmind_v2.py` | 350 | ✅ | **95%** | ❌ 刪除 |
| `scripts/complete_data_download_pro.py` | 602 | ✅ | **95%** | ✅ **保留（最完整）** |
| `scripts/unified_download.py` | 182 | ✅ | **90%** | ❌ 刪除 |
| `scripts/batch_download_all_financials.py` | 349 | ✅ | **90%** | ❌ 刪除 |

**核心問題：**
- 5 個腳本都在做「下載所有 FinMind 資料」
- 都使用相同的 API Token 和配額管理 (600次/小時)
- 都有相似的錯誤處理和重試邏輯
- 邏輯分散導致維護困難

**重構建議：**
```
保留：complete_data_download_pro.py（功能最完整、日誌最詳細）
刪除：其他 4 個檔案
整合：將獨特功能（如 batch_size 參數）合併到保留檔案
```

---

#### 組別 2：財報專項下載
**功能描述：** 只下載財務報表（資產負債表、損益表、現金流量表）

| 檔案 | 行數 | 目標資料 | 功能重複度 | 建議 |
|------|------|----------|-----------|------|
| `scripts/batch_download_financials.py` | 211 | 三大財報 | **85%** | ❌ 刪除 |
| `scripts/fast_download_financials.py` | 207 | 三大財報（僅上市股） | **85%** | ❌ 刪除 |
| `scripts/download_financial_2330.py` | 171 | 單一股票 (2330) | **50%** | ❌ 刪除（僅測試用）|

**核心問題：**
- 前兩個腳本功能 85% 重複，僅差異在過濾邏輯（是否包含上櫃股）
- 第三個是測試用腳本，不應保留在生產環境

**重構建議：**
```
整合到：src/downloaders/financial_downloader.py
功能：支援參數控制（是否包含上櫃股、是否只下載單一股票）
刪除：3 個檔案全部刪除
```

---

#### 組別 3：通用下載框架
| 檔案 | 功能 | 建議 |
|------|------|------|
| `scripts/download_finmind_complete.py` | 通用 FinMind API 客戶端 | ⚠️ **整合到類別** |
| `scripts/background_full_download.py` | 背景下載管理 | ⚠️ **整合到類別** |

**重構建議：**
```
整合到：src/downloaders/finmind_client.py（Base Class）
功能：提供統一的 API 呼叫、Token 管理、錯誤處理
```

---

## 🟡 二、計算與分析類腳本 (Calculation Scripts) - 中度重複

### 📁 功能分析

| 檔案 | 功能 | 重複度 | 建議 |
|------|------|--------|------|
| `scripts/calculate_technical_indicators.py` | 計算技術指標 (MA/MACD/RSI/KD) | - | ✅ 保留 |
| `scripts/calculate_river_charts.py` | 計算 PE/PB 河流圖 | - | ✅ 保留 |
| `scripts/calculate_bull_bear_indicators.py` | 計算多空指標評分 | - | ✅ 保留 |
| `scripts/calculate_all_indicators.py` | 整合所有計算任務 | **60%** | ⚠️ **重構為協調器** |

**核心問題：**
- `calculate_all_indicators.py` 應該是「協調器」而非「執行者」
- 目前包含重複的計算邏輯

**重構建議：**
```
重構：calculate_all_indicators.py → src/calculators/indicator_coordinator.py
功能：僅負責呼叫其他計算模組，不包含實際計算邏輯
整合：將其他 3 個腳本整合為 src/calculators/ 下的獨立模組
```

---

## 🟢 三、資料庫管理類腳本 (Database Management) - 可整合

### 📁 優化與整合類

| 檔案 | 功能 | 重複度 | 建議 |
|------|------|--------|------|
| `scripts/optimize_collections.py` | 優化 MongoDB Collection | **70%** | ❌ 刪除 |
| `scripts/safe_optimize_collections.py` | 安全優化 MongoDB（備份機制）| **70%** | ✅ 保留 |
| `scripts/consolidate_collections.py` | 合併重複集合 | - | ✅ 保留 |
| `scripts/migrate_financial_statements_to_reports.py` | 財報資料遷移 | - | ⚠️ 執行後刪除 |

**重構建議：**
```
保留：safe_optimize_collections.py（有備份機制較安全）
刪除：optimize_collections.py
整合：migrate_* 類腳本執行後應刪除（一次性任務）
```

---

## 🔵 四、驗證與測試類腳本 (Validation Scripts) - 可整合

| 檔案 | 功能 | 建議 |
|------|------|------|
| `scripts/verify_financial_data.py` | 驗證財報資料品質 | ✅ 整合到測試框架 |
| `scripts/verify_collection_migration.py` | 驗證集合遷移 | ⚠️ 遷移完成後刪除 |
| `scripts/final_system_validation.py` | 完整系統驗證 | ✅ **保留為主驗證腳本** |
| `scripts/create_test_financial_data.py` | 建立測試資料 | ✅ 保留（開發用）|

**重構建議：**
```
建立：src/validators/system_validator.py
功能：整合所有驗證邏輯
保留：final_system_validation.py 作為入口
刪除：一次性遷移驗證腳本
```

---

## 🟣 五、Pattern Recognition 腳本 - 獨立系統（不重構）

| 檔案 | 說明 |
|------|------|
| `pattern_recognition/patterns_12_masters.py` | 12 種 K 線型態識別 |
| `pattern_recognition/market_scanner.py` | 市場掃描器 |
| `pattern_recognition/pattern_cli.py` | CLI 工具 |
| `pattern_recognition/quick_scan.py` | 快速掃描 |
| `pattern_recognition/test_patterns.py` | 型態測試 |
| `pattern_recognition/advanced_trading_logic.py` | 進階交易邏輯 |

**評估：** ✅ **不需重構**
- 此模組為獨立的技術分析系統
- 結構清晰、職責明確
- 已經模組化設計良好

---

## 📋 六、重構執行計畫 (Refactoring Plan)

### 🎯 總體架構

```
tw-stock-analysis/
├── src/
│   ├── downloaders/          # 📥 下載模組（新）
│   │   ├── __init__.py
│   │   ├── finmind_client.py      # Base API Client
│   │   ├── financial_downloader.py # 財報下載器
│   │   ├── market_data_downloader.py # 行情下載器
│   │   ├── institutional_downloader.py # 籌碼下載器
│   │   └── downloader_coordinator.py # 下載協調器
│   │
│   ├── calculators/          # 🧮 計算模組（新）
│   │   ├── __init__.py
│   │   ├── technical_indicators.py
│   │   ├── valuation_metrics.py
│   │   └── indicator_coordinator.py
│   │
│   ├── validators/           # ✅ 驗證模組（新）
│   │   ├── __init__.py
│   │   ├── data_quality_validator.py
│   │   └── system_validator.py
│   │
│   ├── database/             # 🗄️ 資料庫模組（新）
│   │   ├── __init__.py
│   │   ├── db_manager.py        # 統一連線管理
│   │   └── schema_validator.py  # Schema 驗證
│   │
│   └── main.py              # 🚀 唯一入口（新）
│
├── scripts/                 # 📜 保留的工具腳本
│   ├── safe_optimize_collections.py
│   ├── consolidate_collections.py
│   ├── final_system_validation.py
│   └── create_test_financial_data.py
│
└── pattern_recognition/     # 📊 型態識別（不變）
    └── （保持原樣）
```

---

### 🏗️ 階段一：建立核心模組 Class

#### 1. `src/downloaders/finmind_client.py` (Base Class)
```python
class FinMindClient:
    """
    FinMind API 基礎客戶端
    - 統一 Token 管理
    - API 頻率限制 (600次/小時)
    - 錯誤重試機制
    - 日誌記錄
    """
    def __init__(self, token: str):
        self.token = token
        self.api_calls = 0
        self.max_calls_per_hour = 600
        
    def fetch_data(self, dataset: str, params: dict):
        """統一的 API 請求方法"""
        pass
    
    def _handle_rate_limit(self):
        """處理 API 限制"""
        pass
    
    def _retry_on_failure(self, func, max_retries=3):
        """錯誤重試機制"""
        pass
```

#### 2. `src/downloaders/financial_downloader.py`
```python
from .finmind_client import FinMindClient

class FinancialReportDownloader(FinMindClient):
    """
    財報專項下載器
    整合：
    - batch_download_financials.py
    - fast_download_financials.py  
    - download_financial_2330.py
    """
    def download_balance_sheet(self, symbols: list):
        pass
    
    def download_income_statement(self, symbols: list):
        pass
    
    def download_cash_flow(self, symbols: list):
        pass
    
    def download_all_financials(self, symbols: list, 
                               include_otc: bool = True):
        """
        統一介面，支援：
        - 批次下載
        - 過濾上市/上櫃
        - 單一股票
        """
        pass
```

#### 3. `src/downloaders/downloader_coordinator.py`
```python
class DownloaderCoordinator:
    """
    下載協調器
    整合：complete_data_download_pro.py 的邏輯
    """
    def __init__(self):
        self.financial_downloader = FinancialReportDownloader()
        self.market_data_downloader = MarketDataDownloader()
        self.institutional_downloader = InstitutionalDownloader()
    
    def download_all_data(self, categories: list = None):
        """
        下載所有 43 個 FinMind 資料表
        - 技術面 (10 tables)
        - 籌碼面 (9 tables)
        - 基本面 (17 tables)
        - 其他 (7 tables)
        """
        pass
    
    def download_by_category(self, category: str):
        """按類別下載"""
        pass
```

#### 4. `src/main.py` (唯一入口)
```python
#!/usr/bin/env python3
"""
台股分析系統 - 統一入口
"""
import argparse
from downloaders.downloader_coordinator import DownloaderCoordinator
from calculators.indicator_coordinator import IndicatorCoordinator
from validators.system_validator import SystemValidator

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--download', choices=['all', 'financial', 'market', 'institutional'])
    parser.add_argument('--calculate', choices=['all', 'technical', 'fundamental'])
    parser.add_argument('--validate', action='store_true')
    parser.add_argument('--symbols', nargs='+', help='指定股票代碼')
    
    args = parser.parse_args()
    
    # 下載資料
    if args.download:
        coordinator = DownloaderCoordinator()
        if args.download == 'all':
            coordinator.download_all_data()
        elif args.download == 'financial':
            coordinator.financial_downloader.download_all_financials(args.symbols)
    
    # 計算指標
    if args.calculate:
        calculator = IndicatorCoordinator()
        calculator.calculate_indicators(args.calculate, args.symbols)
    
    # 驗證系統
    if args.validate:
        validator = SystemValidator()
        validator.run_full_validation()

if __name__ == '__main__':
    main()
```

---

### 🗑️ 階段二：檔案刪除清單（整合後執行）

#### 下載類（8 個檔案）
```bash
# ❌ 完全刪除
rm scripts/download_all_finmind_data.py
rm scripts/download_complete_finmind_v2.py
rm scripts/unified_download.py
rm scripts/batch_download_all_financials.py
rm scripts/batch_download_financials.py
rm scripts/fast_download_financials.py
rm scripts/download_financial_2330.py
rm scripts/download_finmind_complete.py
```

#### 優化類（1 個檔案）
```bash
# ❌ 刪除無備份機制的版本
rm scripts/optimize_collections.py
```

#### 遷移類（執行後刪除）
```bash
# ⚠️ 確認遷移完成後刪除
rm scripts/migrate_financial_statements_to_reports.py
rm scripts/verify_collection_migration.py
```

#### 測試/開發用（視情況保留）
```bash
# ⚠️ 建議移到 tests/ 目錄而非刪除
mv scripts/create_test_financial_data.py tests/
```

**總計刪除：** 10-12 個檔案

---

### ✅ 階段三：保留檔案清單

#### 必須保留（4 個）
```
✅ scripts/safe_optimize_collections.py     # 安全的資料庫優化
✅ scripts/consolidate_collections.py       # 集合整合
✅ scripts/final_system_validation.py       # 系統驗證
✅ scripts/create_test_financial_data.py    # 測試資料生成
```

#### Pattern Recognition（全部保留）
```
✅ pattern_recognition/patterns_12_masters.py
✅ pattern_recognition/market_scanner.py
✅ pattern_recognition/pattern_cli.py
✅ pattern_recognition/quick_scan.py
✅ pattern_recognition/advanced_trading_logic.py
✅ pattern_recognition/test_patterns.py
✅ pattern_recognition/validate_calculation.py
✅ pattern_recognition/position_monitor.py
```

---

## 📊 七、資料庫 Schema 審計結果

### ✅ 符合專業標準的部分

#### MongoDB Collections (17 個核心集合)
```javascript
✅ tickers                    // 個股行情（有複合索引）
✅ financial_reports          // 財務報表（三表合一）
✅ monthly_revenues           // 月營收
✅ profitability             // 獲利能力指標
✅ valuation_rivers          // PE/PB 河流圖
✅ dividends                 // 股利政策
✅ technical_indicators      // 技術指標
✅ institutional_trades      // 法人買賣
✅ shareholders              // 股東結構
```

**優點：**
- ✅ 欄位命名使用 camelCase（符合 TypeScript/NestJS 規範）
- ✅ 有完整的索引設計（date + symbol 複合索引）
- ✅ 有時間戳記（timestamps: true）
- ✅ 集合名稱語義化清晰

### ⚠️ 需要改進的部分

#### 1. 數值型態問題
```typescript
// ❌ 目前（Float 會有精度問題）
@Prop({ required: true })
closePrice: number;  // JavaScript number = Float64

// ✅ 建議（MongoDB Decimal128）
@Prop({ required: true, type: mongoose.Schema.Types.Decimal128 })
closePrice: Decimal128;
```

**影響範圍：**
- `tickers.closePrice / openPrice / highPrice / lowPrice`
- `financial_reports` 所有金額欄位
- `dividends.cashDividend`

**修正方案：**
```python
# Python 端使用 Decimal
from decimal import Decimal

data = {
    'closePrice': Decimal('123.45'),
    'tradeVolume': 1000000  # 數量可用 int
}
```

#### 2. 欄位一致性問題
```typescript
// ⚠️ 有相容欄位（表示可能有舊資料）
@Prop({ required: true })
closePrice: number;

@Prop({ required: true })
close: number;  // 相容欄位

// ⚠️ 應該：統一使用 closePrice，移除 close
```

**建議：**
1. 執行資料遷移，統一欄位名稱
2. 刪除相容欄位
3. 更新所有查詢程式碼

#### 3. 缺少的欄位驗證
```typescript
// ❌ 目前：沒有範圍驗證
@Prop({ required: true })
changePercent: number;

// ✅ 建議：加入驗證
@Prop({ 
  required: true,
  min: -10,  // 跌停
  max: 10    // 漲停
})
changePercent: number;
```

---

## 🎯 八、重構優先級與時程

### 🔴 P0 - 立即執行（第 1 週）
1. **建立 src/ 目錄結構**
2. **實作 FinMindClient Base Class**
3. **實作 FinancialReportDownloader**
4. **實作 main.py 入口**
5. **測試下載功能**

### 🟡 P1 - 高優先級（第 2 週）
1. **實作其他 Downloader（Market, Institutional）**
2. **實作 DownloaderCoordinator**
3. **整合計算模組**
4. **刪除重複檔案**

### 🟢 P2 - 中優先級（第 3 週）
1. **資料庫欄位型態修正（Decimal128）**
2. **欄位名稱統一（移除相容欄位）**
3. **實作驗證模組**
4. **更新文檔**

### 🔵 P3 - 低優先級（第 4 週）
1. **效能優化**
2. **增加單元測試**
3. **CI/CD 整合**
4. **監控與告警**

---

## ✅ 九、成功指標 (Success Metrics)

### 程式碼品質
- [ ] 下載邏輯集中在 `src/downloaders/` 下（≤ 5 個檔案）
- [ ] `scripts/` 目錄減少 50% 檔案數量
- [ ] 所有下載通過 `main.py` 統一入口
- [ ] 無重複的 API Token 硬編碼

### 系統可靠性
- [ ] 下載腳本支援自動重試（3 次）
- [ ] 完整的錯誤日誌記錄
- [ ] API 頻率限制自動管理
- [ ] 資料庫連線統一管理（連線池）

### 資料完整性
- [ ] 資料庫欄位型態正確（Decimal128）
- [ ] 欄位名稱一致性（無相容欄位）
- [ ] 所有集合有適當索引
- [ ] 資料驗證機制完整

### 開發效率
- [ ] 新增資料來源只需擴展 Downloader Class
- [ ] 修改邏輯只需改一個檔案
- [ ] 文檔同步更新（README.md）
- [ ] 可通過參數控制所有功能

---

## 📝 十、後續建議

### 1. 建立開發規範文檔
```
docs/
├── DEVELOPMENT_GUIDE.md    # 開發指南
├── API_INTEGRATION.md      # API 整合規範
├── DATABASE_SCHEMA.md      # 資料庫 Schema 文檔
└── CODING_STANDARDS.md     # 程式碼規範
```

### 2. 導入程式碼品質工具
```bash
# Python Linter
pip install pylint black isort

# Pre-commit hooks
pip install pre-commit
```

### 3. 監控與告警
```python
# 建議整合
- Sentry: 錯誤追蹤
- Prometheus: 系統監控
- Grafana: 視覺化儀表板
```

---

## 🚦 執行檢查清單 (Checklist)

### 重構前
- [ ] 備份現有資料庫
- [ ] 備份現有程式碼（Git Tag）
- [ ] 記錄所有腳本的執行參數
- [ ] 確認測試環境可用

### 重構中
- [ ] 逐步建立新模組（不刪除舊檔案）
- [ ] 每個模組通過獨立測試
- [ ] 確保向下相容（暫時保留舊介面）
- [ ] 持續記錄遷移日誌

### 重構後
- [ ] 所有功能測試通過
- [ ] 資料驗證完整性
- [ ] 效能測試達標
- [ ] 文檔更新完成
- [ ] **確認無人使用後，才刪除舊檔案**

---

## 📞 聯絡與支援

**審計人員：** AI Senior Systems Architect  
**審計標準：** DRY + SOLID + Clean Architecture  
**下一步：** 等待使用者確認後，開始執行階段一重構

---

**📌 重要提醒：**
> ⚠️ **在確認此方案前，不會修改任何程式碼**  
> ⚠️ **刪除檔案前會再次確認並備份**  
> ⚠️ **重構採漸進式，確保系統隨時可運作**

---

*報告結束 | 等待確認與授權執行*
