# 🚀 台股智能分析系統# 🚀 台股智能分析系統 (Taiwan Stock Analysis System)



> 企業級台股資料分析平台 - 基於 Python 3.14 + MongoDB 7.0> 基於 NestJS + MongoDB + Redis 的企業級台股資料分析平台



[![Python](https://img.shields.io/badge/Python-3.14-3776AB?logo=python)](https://www.python.org/)[![NestJS](https://img.shields.io/badge/NestJS-10.0-E0234E?logo=nestjs)](https://nestjs.com/)

[![MongoDB](https://img.shields.io/badge/MongoDB-7.0-47A248?logo=mongodb)](https://www.mongodb.com/)[![TypeScript](https://img.shields.io/badge/TypeScript-5.1-3178C6?logo=typescript)](https://www.ty## 🐍 Python 分## 🐍 Python 分析工具

[![FinMind](https://img.shields.io/badge/FinMind-API-00ADD8)](https://finmindtrade.com/)

專案包含強大的 Python 分析工具，用於進階技術分析和形態識別。

---

### 🎨 **最新更新：圖表顯示優化** (2026-02-12)

## ✨ 快速導航

✅ **解決圖形不完整、字無法讀取的問題**：

📖 **[完整文件 DOCUMENTATION.md](./DOCUMENTATION.md)** ⭐ 所有功能說明都在這裡！- 📐 圖表尺寸增大 20% (24x28 inches)

- 🔤 全面增大字體 30-43%

| 文件 | 說明 |- 📊 K線加粗 100%，更清晰

|------|------|- 📁 檔案大小優化 80%（360KB 左右）

| 📖 [DOCUMENTATION.md](./DOCUMENTATION.md) | **完整系統文件** - 功能、使用方式、FAQ |- 🖼️ 150 DPI 高品質輸出

| 🗄️ [DATABASE_MIGRATION_GUIDE.md](./DATABASE_MIGRATION_GUIDE.md) | 資料庫遷移指南 |

| 📝 [DATABASE_QUICK_REFERENCE.md](./DATABASE_QUICK_REFERENCE.md) | 資料庫快速參考 |📚 [查看完整優化報告](./docs/CHART_OPTIMIZATION_REPORT.md)

| 📊 [FINMIND_DATA_EXPLANATION.md](./FINMIND_DATA_EXPLANATION.md) | FinMind 數據說明 |

---

---

### 🎯 **新功能！蔡森老師形態學12神招 - 單一時間週期分析** ⭐

## 🎯 系統特色

為每個時間週期（週、雙週、月、季、半年、年、5年、10年）**獨立生成**清晰的單一形態圖！

✅ **完整資料下載** - 2,333 檔台股完整歷史數據  

✅ **技術指標分析** - MA、RSI、MACD、KD、BB、多空指標  ```bash

✅ **形態識別** - 12 種經典買賣形態自動識別  # 分析單一時間週期（週線）

✅ **多時間週期** - 支援日/週/月/季/半年/年/5年線  python3 scripts/individual_timeframe_charts.py --symbol 2330 --timeframe weekly

✅ **自動化監控** - 背景持續更新，即時監控  

# 一次生成所有時間週期（8張獨立圖表）

---python3 scripts/individual_timeframe_charts.py --symbol 0050 --all



## ⚡ 快速開始# 指定輸出目錄

python3 scripts/individual_timeframe_charts.py --symbol 2454 --all --output charts/tsai/

### 1. 檢查下載進度```



```bash**特色**:

# 即時查看背景下載狀態- ✅ 每個時間週期獨立大圖（16x10 inches）

python3 scripts/check_download_status.py- ✅ 清晰易讀，適合深入分析

- ✅ 自動生成摘要報告

# 或使用監控腳本- ✅ 完美支援列印（A4紙張）

./monitor_download.sh

```📚 **[完整使用指南](./docs/INDIVIDUAL_TIMEFRAME_GUIDE.md)** ⭐ 新手必看！



### 2. 計算技術指標---



```bash### 📊 多時間週期形態分析

# 計算單一股票

python3 scripts/calculate_all_indicators.py --symbol 2330**核心功能！** 同時分析 8 個時間週期的形態學表現（日線、週線、雙週線、月線、季線、半年線、年線、5年線）包含強大的 Python 分析工具，用於進階技術分析和形態識別。



# 計算所有股票（背景下載完成後）### 🎯 **新功能！快速開始三步驟** → [📚 查看快速指南](./docs/QUICK_START_3_STEPS.md)

python3 scripts/calculate_all_indicators.py --all

```1. **每週自選股分析** - 掌握持股趨勢變化

2. **市場強弱勢掃描** - 找出前 50 強勢股和後 50 弱勢股

### 3. 掃描形態訊號3. **個股深度分析** - 形態學 + 技術指標綜合研判



```bash---

# 掃描買入訊號

python3 pattern_recognition/pattern_cli.py scan --buy --min-confidence 0.85### 📊 多時間週期形態分析



# 掃描賣出訊號**核心功能！** 同時分析 8 個時間週期的形態學表現（日線、週線、雙週線、月線、季線、半年線、年線、5年線）tlang.org/)

python3 pattern_recognition/pattern_cli.py scan --sell --min-confidence 0.85[![MongoDB](https://img.shields.io/badge/MongoDB-7.0-47A248?logo=mongodb)](https://www.mongodb.com/)

[![Redis](https://img.shields.io/badge/Redis-7.0-DC382D?logo=redis)](https://redis.io/)

# 分析特定股票

python3 pattern_recognition/pattern_cli.py stock 2330## ✨ 核心功能

```

- ✅ **27+ MongoDB Collections** - 完整台股資料覆蓋

---- ✅ **134+ REST API 端點** - 全面的資料查詢介面

- ✅ **技術指標分析** - MA, MACD, RSI, KD, 布林通道等

## 📊 核心功能- ✅ **財務報表分析** - 損益表、資產負債表、現金流量表

- ✅ **籌碼分析** - 三大法人、董監持股、股東結構

### 🔽 資料下載系統- ✅ **估值分析** - PE/PB 河流圖、百分位估值

- **背景下載**: `background_full_download.py` - 2,333 檔股票完整數據- ✅ **產業分析** - 產業熱度、產業輪動追蹤

- **狀態監控**: `check_download_status.py` - 即時進度追蹤- ✅ **量價分析** - 獨特的量價關係分析系統

- **數據來源**: FinMind API (股價、法人、財報、公司資訊)- ✅ **Redis 快取** - 5-15x 查詢效能提升

- ✅ **自動排程** - 每日自動抓取資料

### 📈 技術指標計算- ✅ **Swagger 文檔** - 完整的 API 互動式文檔

- **趨勢指標**: MA5/10/20/60/120/240/1200

- **動能指標**: RSI、MACD、KD## 📋 系統需求

- **波動指標**: BB (布林通道)、ATR

- **多空指標**: 牛熊力道、河流圖- **Node.js** >= 20.x

- **MongoDB** >= 7.0

### 🎯 形態識別系統 (12種)- **Redis** >= 7.0

**買入形態**: 突破整理、黃金交叉、W底、頭肩底、上升三角、V型反轉  - **npm** >= 9.x

**賣出形態**: 跌破支撐、死亡交叉、M頭、頭肩頂、下降三角、倒V反轉

## 🚀 快速開始

---

### 1. 安裝依賴

## 🗄️ 資料庫管理

```bash

### 備份與還原cd /Users/ming/Desktop/Stock/tw-stock-analysis

```bashnpm install

# 備份資料庫```

./backup_mongodb.sh

### 2. 啟動資料庫服務 (Docker)

# 還原資料庫

./restore_mongodb.sh /path/to/backup.tar.gz```bash

```# 啟動 MongoDB 和 Redis (使用獨立 Port 避免衝突)

docker-compose up -d mongodb_stock redis_stock

### 資料庫資訊

- **位置**: `/opt/homebrew/var/mongodb`# 檢查服務狀態

- **配置**: `/opt/homebrew/etc/mongod.conf`docker-compose ps

- **資料庫**: tw_stock_analysis```

- **集合數**: 15 個

服務端口：

---- **MongoDB**: `localhost:27018`

- **Redis**: `localhost:6380`

## 📁 專案結構

### 3. 設定環境變數

```

tw-stock-analysis/```bash

├── scripts/                          # Python 核心腳本 (6個)# 複製環境變數範本

│   ├── background_full_download.py   # 背景下載cp .env.example .env

│   ├── check_download_status.py      # 進度檢查

│   ├── calculate_all_indicators.py   # 指標計算# 編輯 .env (如需修改配置)

│   ├── calculate_technical_indicators.py# 預設配置已可直接使用

│   ├── calculate_bull_bear_indicators.py```

│   └── calculate_river_charts.py

├── pattern_recognition/              # 形態識別 (4個核心)### 4. 啟動應用程式

│   ├── pattern_cli.py                # CLI 工具

│   ├── patterns_12_masters.py        # 12種形態```bash

│   ├── market_scanner.py             # 市場掃描# 開發模式 (熱重載)

│   └── quick_scan.py                 # 快速掃描npm run start:dev

├── backup_mongodb.sh                 # 資料庫備份

├── restore_mongodb.sh                # 資料庫還原# 生產模式

├── monitor_download.sh               # 監控腳本npm run build

├── DOCUMENTATION.md                  # 📖 完整文件npm run start:prod

├── DATABASE_MIGRATION_GUIDE.md       # 遷移指南```

└── README.md                         # 本文件

```### 5. 訪問服務



---- 🌐 **應用首頁**: http://localhost:3000

- 📚 **Swagger API 文檔**: http://localhost:3000/api-docs

## 🚦 當前狀態- 🔍 **健康檢查**: http://localhost:3000/api/v1/health

- 💾 **資料庫狀態**: http://localhost:3000/api/v1/health/database

**背景下載**: ✅ 進行中 (14.1%, 330/2333 檔)  

**資料庫**: ✅ MongoDB 正常運行  ## 📊 API 端點總覽

**形態識別**: ✅ 可用  

**技術指標**: ✅ 準備就緒  ### 核心資料 API



---#### 個股行情 (`/api/v1/tickers`)

```bash

## 📚 詳細文件GET  /api/v1/tickers/:symbol              # 取得最新行情

GET  /api/v1/tickers/:symbol/history      # 取得歷史行情

### 主要文件GET  /api/v1/tickers/date/:date           # 取得指定日期全市場

- 📖 **[DOCUMENTATION.md](./DOCUMENTATION.md)** - 完整系統文件（必讀！）GET  /api/v1/tickers/ranking/top-gainers  # 漲幅排行

  - 所有功能詳細說明GET  /api/v1/tickers/ranking/top-losers   # 跌幅排行

  - 使用範例GET  /api/v1/tickers/ranking/top-volume   # 成交量排行

  - 常見問題 FAQ```

  - 系統維護指南

#### 技術分析 (`/api/v1/technical`)

### 專題文件```bash

- 🗄️ **[DATABASE_MIGRATION_GUIDE.md](./DATABASE_MIGRATION_GUIDE.md)** - 資料庫遷移GET  /api/v1/technical/:symbol            # 技術指標

  - 4種遷移方法GET  /api/v1/technical/:symbol/signals    # 技術信號

  - 詳細步驟說明GET  /api/v1/technical/:symbol/chart      # 圖表資料

  - 故障排除```



- 📊 **[FINMIND_DATA_EXPLANATION.md](./FINMIND_DATA_EXPLANATION.md)** - FinMind API#### 財務報表 (`/api/v1/financial`)

  - 數據範圍說明```bash

  - API 限制GET  /api/v1/financial/:symbol            # 財報查詢

  - 為何需要本地計算指標GET  /api/v1/financial/:symbol/latest     # 最新財報

GET  /api/v1/financial/:symbol/history    # 歷史財報

- 📝 **[DATABASE_QUICK_REFERENCE.md](./DATABASE_QUICK_REFERENCE.md)** - 快速參考```

  - 常用指令

  - 資料庫查詢範例#### 月營收 (`/api/v1/revenue`)

```bash

---GET  /api/v1/revenue/:symbol              # 月營收資料

GET  /api/v1/revenue/:symbol/latest       # 最新月營收

## ❓ 常見問題GET  /api/v1/revenue/high-growth          # 高成長股

```

**Q: 下載需要多久？**  

A: 約 4-6 天完成 2,333 檔股票的完整下載。#### 估值分析 (`/api/v1/valuation`)

```bash

**Q: 為什麼要計算指標？**  GET  /api/v1/valuation/:symbol            # PE/PB 河流圖

A: FinMind 只提供原始數據，技術指標需本地計算。詳見 [FINMIND_DATA_EXPLANATION.md](./FINMIND_DATA_EXPLANATION.md)GET  /api/v1/valuation/:symbol/percentile # 百分位分析

GET  /api/v1/valuation/undervalued        # 低估股票

**Q: 如何遷移資料庫？**  ```

A: 使用 `backup_mongodb.sh` 和 `restore_mongodb.sh`。詳見 [DATABASE_MIGRATION_GUIDE.md](./DATABASE_MIGRATION_GUIDE.md)

### 完整 API 文檔

**更多問題**: 請參考 [DOCUMENTATION.md](./DOCUMENTATION.md) 的 FAQ 章節

訪問 http://localhost:3000/api-docs 查看完整的 134+ API 端點互動式文檔

---

## 🛠️ 開發命令

## 🎉 版本資訊

### 開發相關

**當前版本**: 2.0  ```bash

**更新日期**: 2026-02-17  npm run start:dev     # 開發模式 (熱重載)

**狀態**: ✅ 生產就緒  npm run start:debug   # 偵錯模式

npm run build         # 建置專案

### v2.0 更新 (2026-02-17)npm run start:prod    # 生產模式

- ✅ 完成專案清理 (刪除 82+ 個重複檔案)```

- ✅ 精簡至 6 個核心 Python 腳本

- ✅ 整併文件系統### 程式碼品質

- ✅ 全面功能測試通過```bash

- ✅ 文件重新整理npm run lint          # 程式碼檢查

npm run format        # 程式碼格式化

---npm test              # 執行測試

npm run test:cov      # 測試覆蓋率

## 📞 支援```



- 📖 完整文件: [DOCUMENTATION.md](./DOCUMENTATION.md)### 資料收集

- 📧 系統日誌: `logs/` 目錄```bash

- 📝 下載日誌: `full_download_20260216.log`npm run fetch:recent      # 抓取最近資料

npm run fetch:historical  # 抓取歷史資料

---npm run fetch:quick       # 快速抓取 (測試用)

```

**專案維護**: 2026-02-17  

**系統版本**: 2.0  ### 資料庫維護

**授權**: 私有專案```bash

npm run optimize:indexes  # 優化資料庫索引
npm run check:integrity   # 資料完整性檢查
```

## 🗄️ 資料庫架構

### MongoDB Collections (17個核心 Collections)

| Collection | 用途 | 記錄數量級 |
|-----------|------|-----------|
| `tickers` | 個股每日行情 | 數百萬 |
| `technical_indicators` | 技術指標 | 數百萬 |
| `financial_reports` | 財務報表 | 數十萬 |
| `monthly_revenues` | 月營收 | 數十萬 |
| `profitability` | 獲利能力 | 數十萬 |
| `dividends` | 股利政策 | 數萬 |
| `valuation_rivers` | PE/PB 河流圖 | 數十萬 |
| `shareholders` | 股東結構 | 數十萬 |
| `director_holdings` | 董監持股 | 數十萬 |
| `institutional_trades` | 法人買賣 | 數百萬 |
| `industries` | 產業分類 | 數百 |
| `stock_industries` | 個股產業對應 | 數千 |
| `industry_heats` | 產業熱度 | 數萬 |
| `volume_price_analysis` | 量價分析 | 數十萬 |
| `strategy_recommendations` | 策略推薦 | 數萬 |
| `data_integrity_logs` | 資料完整性日誌 | 數千 |
| `system_logs` | 系統日誌 | Capped Collection |

### Redis 快取策略

- **個股最新資料**: TTL 60 秒
- **歷史資料**: TTL 300 秒 (5分鐘)
- **排行榜**: TTL 60 秒
- **財報資料**: TTL 3600 秒 (1小時)

## 📁 專案結構

```
tw-stock-analysis/
├── src/
│   ├── common/                    # 共用模組
│   │   ├── utils/                 # 工具服務
│   │   │   ├── date-util.service.ts
│   │   │   ├── number-util.service.ts
│   │   │   └── cache-util.service.ts
│   │   └── common.module.ts
│   │
│   ├── modules/                   # 功能模組 (27+)
│   │   ├── ticker/                # 個股行情
│   │   ├── technical/             # 技術分析
│   │   ├── financial/             # 財務報表
│   │   ├── revenue/               # 月營收
│   │   ├── profitability/         # 獲利分析
│   │   ├── dividend/              # 股利政策
│   │   ├── valuation/             # 估值分析
│   │   ├── institutional/         # 法人買賣
│   │   ├── shareholder/           # 股東結構
│   │   ├── director/              # 董監持股
│   │   ├── industry/              # 產業分析
│   │   ├── volume-price/          # 量價分析
│   │   ├── strategy/              # 交易策略
│   │   ├── scraper/               # 資料爬蟲
│   │   ├── scheduler/             # 排程系統
│   │   └── health/                # 健康檢查
│   │
│   ├── app.module.ts              # 主模組
│   └── main.ts                    # 應用入口
│
├── scripts/                       # 工具腳本
├── docker-compose.yml             # Docker 配置
├── init-mongo.js                  # MongoDB 初始化
├── package.json                   # 專案配置
├── tsconfig.json                  # TypeScript 配置
└── README.md                      # 專案說明
```

## 🔧 環境變數說明

```bash
# 應用程式
NODE_ENV=development              # 環境 (development/production)
PORT=3000                         # 服務端口

# MongoDB (專用實例)
MONGODB_URI=mongodb://localhost:27018/tw_stock_analysis
MONGODB_PORT=27018                # 使用 27018 避免衝突

# Redis (專用實例)
REDIS_HOST=localhost
REDIS_PORT=6380                   # 使用 6380 避免衝突

# 快取策略
CACHE_TTL=300                     # 預設快取時間 (秒)
CACHE_MAX_ITEMS=1000              # 最大快取項目數

# 功能開關
SWAGGER_ENABLED=true              # Swagger 文檔
ENABLE_SCHEDULER=true             # 自動排程
```

## 🎯 開發注意事項

### 1. 時區處理
台股以 `Asia/Taipei` (UTC+8) 為準，使用 `luxon` 處理時區：

```typescript
import { DateTime } from 'luxon';
const now = DateTime.now().setZone('Asia/Taipei');
```

### 2. 錯誤處理
使用 NestJS 內建的例外過濾器：

```typescript
throw new NotFoundException(`找不到股票代碼: ${symbol}`);
```

### 3. 快取使用
統一使用 `CacheUtilService`：

```typescript
const data = await this.cacheUtil.getOrSet(
  key,
  async () => fetchData(),
  300 // TTL
);
```

## � Python 分析工具

專案包含強大的 Python 分析工具，用於進階技術分析和形態識別。

### 📊 多時間週期形態分析

**新功能！** 同時分析 8 個時間週期的形態學表現（日線、週線、雙週線、月線、季線、半年線、年線、5年線）

```bash
# 單一股票分析（生成圖表）
python3 scripts/multi_timeframe_pattern_chart.py --symbol 2330 --chart

# 生成文字報告
python3 scripts/multi_timeframe_pattern_chart.py --symbol 2330 --report

# 批次分析多檔股票
python3 scripts/batch_multi_timeframe_charts.py --symbols 2330,0050,2454,2317,0056

# 分析前 10 檔權值股
python3 scripts/batch_multi_timeframe_charts.py --top 10
```

**支援的形態**:
- 🚀 **W底**（雙重底）- 看漲信號 (80% 信心度)
- 🔻 **M頭**（雙重頂）- 看跌信號 (75% 信心度)
- ➡️ **箱型整理** - 中性信號 (65% 信心度)
- 🚀 **圓弧底** - 看漲信號 (70% 信心度)

**多時間週期確認**:
- 當同一形態出現在多個時間週期時，信號可靠度大幅提升
- 例如：日線 + 月線都出現 M頭 → **強烈看跌信號**

📚 **完整文檔**:
- [三步驟快速開始](./docs/QUICK_START_3_STEPS.md) ⭐ **推薦先看這個！**
- [日常工作流程指南](./docs/DAILY_WORKFLOW_GUIDE.md)
- [多時間週期形態分析指南](./docs/MULTI_TIMEFRAME_PATTERN_GUIDE.md)
- [快速參考](./docs/MULTI_TIMEFRAME_QUICK_REF.md)

---

### �️ 每週自選股分析

```bash
# 分析你的自選股，生成週報
python3 scripts/weekly_watchlist_analysis.py

# 使用自訂自選股清單
python3 scripts/weekly_watchlist_analysis.py --watchlist my_watchlist.txt
```

**自動產出**:
- ✅ 多時間週期看漲確認（重點關注）
- ⚠️ 多時間週期看跌確認（風險警示）
- 📊 完整週報 + 8 個時間週期圖表

---

### 🔍 市場強弱勢掃描

```bash
# 找出前 50 強勢股 + 後 50 弱勢股
python3 scripts/market_strength_scanner.py --top 50 --bottom 50

# 快速測試（100 檔）
python3 scripts/market_strength_scanner.py --top 10 --bottom 10 --max-stocks 100
```

**評分機制**:
- 多時間週期加權評分（-100 到 +100）
- 長週期（季線、半年線）權重更高
- 自動排序，找出最強/最弱的股票

---

### 🎯 完整技術分析

```bash
# 形態學 + 技術指標綜合分析
python3 scripts/full_technical_analysis.py --symbol 2330

# 批次分析
python3 scripts/full_technical_analysis.py --symbols 2330,0050,2454

# 同時生成圖表
python3 scripts/full_technical_analysis.py --symbol 2330 --with-charts
```

**綜合研判**:
- 📊 多時間週期形態摘要
- 📈 技術指標（MA, RSI, MACD, KD）
- 🎯 綜合評分與投資建議

---

### 📈 單一工具使用

#### 單一時間週期形態分析
```bash
# 繪製帶形態標註的 K線圖
python3 scripts/chart_with_patterns.py --symbol 2330 --days 120

# 批次生成多檔股票的形態圖表
python3 scripts/batch_pattern_charts.py --symbols 2330,0050,2454
```

#### 技術指標分析
```bash
# 多時間週期技術指標圖表（MA, RSI, MACD 等）
python3 scripts/multi_timeframe_chart.py --symbol 2330

# 完整技術分析報告
python3 scripts/analyze_complete.py --symbol 2330
```

#### 市場掃描
```bash
# 全市場形態掃描
python3 scripts/pattern_scan_market.py --pattern w_bottom

# 找出所有出現 M頭的股票
python3 scripts/pattern_scan_market.py --pattern m_top
```

### 🔧 Python 環境設置

```bash
# 安裝 Python 依賴
pip3 install -r requirements.txt

# 或使用虛擬環境
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 📊 工具輸出

所有圖表和報告會儲存在：
- **圖表**: `charts/` 目錄
- **報告**: `charts/` 目錄（.txt 文件）
- **格式**: PNG (300 DPI), UTF-8 純文字

---

## �🐳 Docker 部署

### 僅啟動資料庫
```bash
docker-compose up -d mongodb_stock redis_stock
```

### 完整部署 (包含應用)
```bash
docker-compose --profile full up -d
```

### 停止服務
```bash
docker-compose down

# 同時刪除資料卷
docker-compose down -v
```

## 📈 效能優化

1. **MongoDB 索引**: 17個 Collections 共 40+ 索引
2. **Redis 快取**: 關鍵查詢快取 5-15x 提升
3. **連接池**: MongoDB/Redis 連接池配置
4. **查詢優化**: 使用 `.lean()` 減少記憶體使用

## 🤝 貢獻指南

歡迎提交 Issue 和 Pull Request！

## 📄 授權

MIT License

## 📞 聯絡方式

如有問題，請開啟 Issue 或聯繫專案維護者。

---

**專案狀態**: 🚧 Active Development

**最後更新**: 2024-12-21
