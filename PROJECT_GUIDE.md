# 🚀 專業財經分析系統：開發規範與 AI 協作手冊

**最後更新**: 2026-02-21  
**版本**: 2.0  
**系統狀態**: ✅ 生產就緒（97/100）

這是一份完整的專案開發規範與 AI 協作手冊。您可以將其作為 VS Code AI 工具（如 GitHub Copilot、Cursor）的參考。

---

## 1. 專案核心目標

建立一個**全自動化**、**低冗餘**、**高資料一致性**的專業台股與全球財經分析系統。

### 核心原則
* **自動化**: 拒絕人工點擊允許，實現一鍵下載（Zero Manual Intervention）
* **精簡化**: 嚴禁重複腳本，優先重構現有模組（DRY 原則）
* **專業化**: 嚴格遵循專業資料庫（DB）開發規範，確保財報與交易數據邏輯正確
* **文檔化**: 程式碼與文檔同步更新，避免文檔過時

### 質量標準
* 數據品質: > 99.99%
* 程式碼覆蓋率: > 80%
* API 回應時間: < 100ms
* 文檔完整性: 100%

---

## 2. VS Code AI 角色設定 (Prompts)

### 🛠️ 開發 Agent (GitHub Copilot / Claude 3.5/4.5)

**指令**: 負責程式碼編寫、重構與自動化流程。

> **Role: VS Code Senior Full-Stack Engineer**
> 
> 1. **Anti-Redundancy (防止冗餘)**: 
>    - 建立新檔案前必須搜尋 `src/` 與 `scripts/`
>    - 若功能重複，必須「合併重構」而非「新增」
>    - 修改後確認舊程式不再使用並建議移至 `scripts/deprecated/`
> 
> 2. **Auto-Doc (自動文檔)**:
>    - 任何 `.py` 或 `.ts` 異動必須同步更新相關文檔
>    - 更新 `Readme.md`, `QUICK_START.md`, `DOCUMENTATION.md`
>    - 在程式碼中加入清晰的 Docstring 和註解
> 
> 3. **No Interruption (無中斷執行)**:
>    - 下載腳本需含 `try-except` 與自動重試機制
>    - 禁止 `input()` 等待人工確認
>    - 使用 `logging` 模組記錄所有操作
> 
> 4. **DB Integrity (資料庫完整性)**:
>    - 欄位命名語義化（`stock_id`, `open_price`）
>    - 價格欄位限用 `Decimal128/Numeric` 確保精確度
>    - 所有數據寫入前必須通過邏輯驗證
> 
> 5. **Task (任務優先級)**:
>    - P0: 數據品質修復（高優先）
>    - P1: Schema 一致性（中優先）
>    - P2: 程式碼重構（低優先）

### 🔍 監查 Agent (Gemini 2.0 Pro / GPT-4)

**指令**: 負責資料校閱、財務邏輯與專案進度管理。

> **Role: Financial Data QA & Project Manager**
> 
> 1. **Data Audit (數據審計)**:
>    - 執行 5 段檢查:
>      * 價格邏輯 (O/H/L/C: high ≥ open/close/low)
>      * 日期格式 (ISO 8601)
>      * 財報三表勾稽（資產 = 負債 + 股東權益）
>      * 除權息邏輯（EX 日期與還原權值）
>      * 成交量正值（volume > 0）
> 
> 2. **Field Validation (欄位驗證)**:
>    - 確保三者 100% 吻合:
>      * 網頁顯示內容
>      * 資料庫欄位名稱
>      * 程式變數名稱
> 
> 3. **Gap Analysis (缺口分析)**:
>    - 主動分析缺少的專業指標
>    - 對照業界標準（Bloomberg, Reuters）
>    - 提出補充建議
> 
> 4. **Persistence (持久化記錄)**:
>    - 定期總結開發決策
>    - 備份至 `chat_history.md`
>    - 更新 `PROJECT_COMPLETION_REPORT.json`

---

## 3. 系統架構與組織

### 3.1 目錄結構

```
tw-stock-analysis/
├── src/                          # 核心應用程式碼
│   ├── downloaders/              # 統一下載系統（✨ 推薦使用）
│   │   ├── unified_downloader.py  # 主入口
│   │   ├── base_downloader.py     # 基礎類別
│   │   ├── price_downloader.py    # 股價下載
│   │   ├── financial_downloader.py # 財報下載
│   │   └── dividend_downloader.py  # 股利下載
│   │
│   ├── modules/                  # NestJS 模組
│   │   ├── ticker/               # 價格數據模組
│   │   │   └── schemas/
│   │   │       └── ticker.schema.ts  # ✅ Decimal128
│   │   └── financial/            # 財報模組
│   │
│   └── utils/                    # 工具函數
│
├── scripts/                      # 輔助腳本
│   ├── validate_system.py        # ⭐ 系統驗證
│   ├── check_download_status.py  # 進度查詢
│   ├── fix_p0_issues.py          # P0 修復（已執行）
│   ├── test_p2_unified_downloader.sh  # P2 測試
│   ├── cleanup_duplicate_scripts.sh   # 清理腳本
│   │
│   └── deprecated/               # ⚠️ 已廢棄腳本
│       ├── downloaders/
│       ├── financial_downloaders/
│       └── README.md
│
├── logs/                         # 日誌目錄
│   ├── test/                     # 測試日誌
│   └── reports/                  # 報告日誌
│
├── pattern_recognition/          # 技術分析模組
├── public/                       # 前端資源
├── views/                        # 網頁模板
│
├── Readme.md                     # ⭐ 主要說明文件
├── QUICK_START.md                # 快速開始指南
├── DOCUMENTATION.md              # 完整系統文檔
├── PROJECT_GUIDE.md              # 本文件
│
├── P0_FIX_COMPLETE_REPORT.md     # P0 完成報告
├── P0_P1_COMPLETE_SUMMARY.md     # P0/P1 總結
├── CODE_REFACTOR_EXECUTION_PLAN.md  # P2 執行計畫
│
├── .env                          # 環境變數（含 API Token）
├── docker-compose.yml            # Docker 設定
├── package.json                  # Node.js 套件
└── tsconfig.json                 # TypeScript 設定
```

### 3.2 核心模組說明

#### **統一下載系統** (推薦使用)
- **路徑**: `src/downloaders/`
- **主程式**: `unified_downloader.py` (1,532 行)
- **特色**: 
  - 模組化設計（5 個檔案，單一職責）
  - 自動重試機制
  - 錯誤處理與日誌記錄
  - 支援增量下載
  - 無人工介入

**使用範例**:
```bash
# 完整下載
python3 src/downloaders/unified_downloader.py

# 僅下載股價
python3 src/downloaders/unified_downloader.py --types price

# 指定日期範圍
python3 src/downloaders/unified_downloader.py --start-date 2024-01-01
```

#### **廢棄腳本** (不建議使用)
- **路徑**: `scripts/deprecated/`
- **內容**: 
  - `downloaders/background_full_download.py`
  - 其他已移除的重複腳本
- **原因**: 功能重疊、缺乏維護、程式碼品質低
- **說明**: 見 `scripts/deprecated/README.md`

---

## 4. 專業資料庫設計規範

### 4.1 欄位命名規範

**強制使用 snake_case**:
```javascript
✅ 正確:
stock_id, trade_date, open_price, close_price, 
total_assets, net_income, return_on_equity

❌ 錯誤:
StockId, tradeDate, openPrice, ClosePrice,
TotalAssets, netIncome, returnOnEquity
```

**語義化命名**:
```javascript
✅ 正確:
closing_price (明確指收盤價)
total_liabilities (總負債)
earnings_per_share (每股盈餘)

❌ 錯誤:
price (不明確)
debt (太簡略)
eps (縮寫不利閱讀)
```

### 4.2 數據型別規範

**價格欄位必須使用 Decimal128**:
```typescript
// NestJS Schema
@Schema()
export class Ticker {
  @Prop({ type: SchemaTypes.Decimal128, required: true })
  open: Types.Decimal128;

  @Prop({ type: SchemaTypes.Decimal128, required: true })
  high: Types.Decimal128;

  @Prop({ type: SchemaTypes.Decimal128, required: true })
  low: Types.Decimal128;

  @Prop({ type: SchemaTypes.Decimal128, required: true })
  close: Types.Decimal128;
}
```

**Python 寫入範例**:
```python
from bson.decimal128 import Decimal128

document = {
    'stock_id': '2330',
    'date': datetime(2024, 1, 1),
    'open': Decimal128('580.00'),
    'high': Decimal128('585.00'),
    'low': Decimal128('578.00'),
    'close': Decimal128('582.00'),
    'volume': 25000000
}
```

### 4.3 邏輯驗證規範

**價格邏輯檢查**:
```python
def validate_price_logic(data):
    """驗證價格邏輯正確性"""
    assert data['high'] >= data['low'], "High must >= Low"
    assert data['high'] >= data['open'], "High must >= Open"
    assert data['high'] >= data['close'], "High must >= Close"
    assert data['low'] <= data['open'], "Low must <= Open"
    assert data['low'] <= data['close'], "Low must <= Close"
    assert data['volume'] > 0, "Volume must > 0"
```

**財報三表勾稽**:
```python
def validate_balance_sheet(data):
    """驗證資產負債表平衡"""
    assets = data['total_assets']
    liabilities = data['total_liabilities']
    equity = data['total_equity']
    
    # 資產 = 負債 + 股東權益
    assert abs(assets - (liabilities + equity)) < 1000, \
        f"Balance sheet mismatch: {assets} != {liabilities + equity}"
```

### 4.4 索引優化規範

**複合索引**:
```javascript
// MongoDB 索引設計
db.stock_price.createIndex({ stock_id: 1, date: -1 })
db.financial_statements.createIndex({ stock_id: 1, year: -1, period: -1 })
db.dividends.createIndex({ stock_id: 1, ex_dividend_date: -1 })
```

**索引使用原則**:
1. 最常查詢的欄位放最前面
2. 日期欄位使用降序（最新資料優先）
3. 複合索引不超過 3 個欄位
4. 定期檢查索引效能（`explain()`）

---

## 5. 三階段品質優化（已完成）

### P0: 數據品質修復 ✅

**執行時間**: 2026-02-20 10:15-10:45  
**執行腳本**: `scripts/fix_p0_issues.py`  

**修復內容**:
1. **刪除無效價格記錄**: 48,176 筆
   - high/low 缺失或為 0
   - 不符合邏輯的極端值

2. **處理股利數據**: 87 筆
   - 計算還原權值因子
   - 驗證 EX 日期正確性

3. **邏輯正確率提升**: 93.6% → 99.9999%
   - 僅剩 7 筆極端情況（人工確認為實際狀況）

**詳細報告**: [P0_FIX_COMPLETE_REPORT.md](P0_FIX_COMPLETE_REPORT.md)

### P1: Schema 一致性驗證 ✅

**執行時間**: 2026-02-20 11:00-11:30  
**驗證範圍**: NestJS Schema, MongoDB 數據型別

**驗證結果**:
1. **ticker.schema.ts**: ✅ 完美實現
   - 所有價格欄位使用 Decimal128
   - 內建邏輯驗證
   - 完整索引定義

2. **stock_price 集合**: ✅ 數據型別正確
   - MongoDB 自動處理型別轉換
   - 無需手動 Schema 定義

3. **三方審計差異解釋**: ✅ 釐清
   - Claude/Gemini: 靜態代碼分析（程式碼重複 43%）
   - Copilot: 動態數據查詢（數據品質問題）
   - 結論: 兩者互補，非衝突

**詳細報告**: [P0_P1_COMPLETE_SUMMARY.md](P0_P1_COMPLETE_SUMMARY.md)

### P2: 程式碼重構 ✅

**執行時間**: 2026-02-21 10:00-11:00  
**重構範圍**: 下載系統整合、腳本清理、文檔更新

**重構內容**:
1. **測試統一下載系統**: ✅ 通過
   - 測試腳本: `scripts/test_p2_unified_downloader.sh`
   - 環境檢查: .env, MongoDB, Python 套件
   - 功能測試: taiwan_stock_info 3,452 筆
   - 日誌: `logs/test/p2_test_20260221_102550.log`

2. **清理重複腳本**: ✅ 完成
   - 清理腳本: `scripts/cleanup_duplicate_scripts.sh`
   - 移動檔案: 1 個 (`background_full_download.py`)
   - 已不存在: 6 個（可能之前已清理）
   - 目錄結構: `scripts/deprecated/` + README.md

3. **更新文檔**: ✅ 完成
   - `Readme.md`: 全面更新系統架構和使用說明
   - `QUICK_START.md`: 加入統一下載系統說明
   - `PROJECT_GUIDE.md`: 本文件（開發規範）

**程式碼架構改進**:
- **Before**: 7-8 個重複下載腳本，功能重疊 43%
- **After**: 1 個統一下載系統（5 個模組），模組化設計

**執行計畫**: [CODE_REFACTOR_EXECUTION_PLAN.md](CODE_REFACTOR_EXECUTION_PLAN.md)

---

## 6. 數據涵蓋範疇與完整性檢查

### 6.1 數據清單

| 維度 | 核心檢查項目 | 完成狀態 |
| --- | --- | --- |
| **技術面** | 台股總覽(含權證)、股價表、交易日、類股、PER/PBR、5秒成交統計、大盤加權/報酬指數、當沖資料 | ✅ 基礎完成 |
| **籌碼面** | 三大法人買賣(個股/整體)、融資融券、外資持股、借券明細、信用額度、券商分點資訊 | ⏳ 部分完成 |
| **基本面** | 三大財報(現金流量/損益/資產負債)、股利政策、除權息、月營收、減資/下市/分割恢復買賣參考價 | ✅ 完成 |
| **衍生性** | 期貨/選擇權(日成交/即時/三大法人/券商交易) | ⏳ 規劃中 |
| **總經** | 相關新聞、黃金、原油(Brent, WTI)、美股、外幣匯率(19種)、央行利率(12國) | ⏳ 規劃中 |

### 6.2 專業指標補充建議

**技術面**:
- [ ] 均線系統 (MA 5/10/20/60/120)
- [ ] RSI (相對強弱指標)
- [ ] MACD (移動平均收斂發散指標)
- [ ] 布林通道 (Bollinger Bands)
- [ ] KD 指標

**籌碼面**:
- [ ] 券商分點分佈圖
- [ ] 關鍵主力進出成本分析
- [ ] 融資融券變化趨勢
- [ ] 外資持股比例變化

**基本面**:
- [x] ROE/ROA 杜邦分析（已完成）
- [ ] 自由現金流
- [ ] 本益比河流圖
- [ ] 股價淨值比趨勢
- [ ] 法說會摘要（文字分析）

**衍生性**:
- [ ] 未平倉量 (OI) 變化
- [ ] 選擇權隱含波動率 (IV)
- [ ] Put/Call Ratio
- [ ] Max Pain 計算

**總經**:
- [ ] 恐懼與貪婪指數
- [ ] 十年期美債殖利率
- [ ] CPI/PPI 數據
- [ ] Fed 利率決議
- [ ] VIX 指數

---

## 7. 專案執行 SOP

### 7.1 日常開發流程

**Step 1: 確認功能需求**
```bash
# 搜尋現有實現
grep -r "function_name" src/
grep -r "function_name" scripts/

# 確認無重複後再開發
```

**Step 2: 開發新功能**
```bash
# 1. 創建功能分支
git checkout -b feature/new-feature

# 2. 開發並測試
pytest tests/

# 3. 更新文檔
# 編輯 Readme.md, QUICK_START.md

# 4. 提交代碼
git add .
git commit -m "feat: add new feature"
```

**Step 3: 代碼審查**
```bash
# 1. 檢查代碼品質
pylint src/
eslint src/

# 2. 執行測試
npm test
python3 -m pytest

# 3. 系統驗證
python3 scripts/validate_system.py
```

**Step 4: 部署上線**
```bash
# 1. Build
npm run build

# 2. 啟動服務
npm start

# 3. 驗證 API
curl "http://localhost:3000/health"
```

### 7.2 數據下載流程

**首次下載（完整）**:
```bash
# 1. 驗證環境
python3 scripts/validate_system.py

# 2. 完整下載所有資料
python3 src/downloaders/unified_downloader.py

# 3. 檢查進度
python3 scripts/check_download_status.py

# 4. 驗證數據品質
mongosh tw_stock_analysis --eval "db.stock_price.countDocuments()"
```

**增量更新（每日）**:
```bash
# 自動增量更新（只下載新數據）
python3 src/downloaders/unified_downloader.py --incremental

# 或使用 cron 定時執行
0 18 * * 1-5 /usr/bin/python3 /path/to/unified_downloader.py --incremental
```

### 7.3 問題排查流程

**數據異常**:
```bash
# 1. 檢查數據品質
python3 scripts/validate_system.py

# 2. 查看日誌
tail -f logs/download_*.log

# 3. 手動修復（參考 P0）
python3 scripts/fix_p0_issues.py
```

**API 錯誤**:
```bash
# 1. 檢查服務狀態
curl "http://localhost:3000/health"

# 2. 查看日誌
tail -f logs/*.log

# 3. 重啟服務
npm restart
```

**資料庫連線問題**:
```bash
# 1. 檢查 MongoDB 狀態
docker ps | grep mongodb

# 2. 重啟 MongoDB
docker-compose restart mongodb

# 3. 驗證連線
mongosh tw_stock_analysis --eval "db.stats()"
```

---

## 8. AI 協作最佳實踐

### 8.1 有效提問技巧

**✅ 好的提問**:
```
請檢查 stock_price 集合中是否有 high < low 的異常數據，
並生成修復腳本。需要：
1. 查詢異常數據數量
2. 列出前 10 筆異常記錄
3. 建議修復策略（刪除或修正）
4. 生成自動化修復腳本
```

**❌ 壞的提問**:
```
數據有問題，幫我修一下。
```

### 8.2 代碼審查請求

**✅ 好的請求**:
```
請審查 src/downloaders/unified_downloader.py，重點：
1. 是否有重複代碼可以重構
2. 錯誤處理是否完整
3. 日誌記錄是否充足
4. 是否遵循 Python PEP 8 規範
5. 是否有潛在的效能問題
```

**❌ 壞的請求**:
```
幫我看看這個檔案有沒有問題。
```

### 8.3 文檔更新請求

**✅ 好的請求**:
```
我剛新增了 MA 計算功能（src/indicators/ma.py），請：
1. 更新 Readme.md 的功能清單
2. 在 QUICK_START.md 加入使用範例
3. 更新 DOCUMENTATION.md 的 API 說明
4. 在程式碼中加入 Docstring
```

**❌ 壞的請求**:
```
新功能做好了，更新一下文檔。
```

---

## 9. 附錄

### 9.1 常用指令速查

**系統驗證**:
```bash
python3 scripts/validate_system.py
```

**下載資料**:
```bash
# 完整下載
python3 src/downloaders/unified_downloader.py

# 僅下載股價
python3 src/downloaders/unified_downloader.py --types price

# 增量更新
python3 src/downloaders/unified_downloader.py --incremental
```

**啟動服務**:
```bash
npm run build && npm start
```

**測試 API**:
```bash
# 健康檢查
curl "http://localhost:3000/health"

# 杜邦分析（台積電）
curl "http://localhost:3000/api/v1/financial/2330/dupont?year=2024&period=Q3"
```

**資料庫操作**:
```bash
# 連線資料庫
mongosh tw_stock_analysis

# 查詢統計
db.stock_price.countDocuments()
db.taiwan_stock_info.countDocuments()

# 查詢特定股票
db.stock_price.find({stock_id: "2330"}).limit(5)
```

### 9.2 相關鏈接

**內部文檔**:
- [Readme.md](Readme.md) - 主要說明文件
- [QUICK_START.md](QUICK_START.md) - 快速開始
- [DOCUMENTATION.md](DOCUMENTATION.md) - 完整文檔

**品質報告**:
- [P0_FIX_COMPLETE_REPORT.md](P0_FIX_COMPLETE_REPORT.md)
- [P0_P1_COMPLETE_SUMMARY.md](P0_P1_COMPLETE_SUMMARY.md)
- [CODE_REFACTOR_EXECUTION_PLAN.md](CODE_REFACTOR_EXECUTION_PLAN.md)

**外部資源**:
- [FinMind API 文檔](https://api.finmindtrade.com/docs)
- [MongoDB 文檔](https://www.mongodb.com/docs/)
- [NestJS 文檔](https://docs.nestjs.com/)
- [Decimal128 說明](https://www.mongodb.com/docs/manual/reference/bson-types/#decimal128)

---

**最後更新**: 2026-02-21  
**維護者**: Ming  
**版本**: 2.0
