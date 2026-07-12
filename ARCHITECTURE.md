# 系統架構文件 — 台股智能分析系統

> **版本 3.0** · 基於 `172.16.9.166` (ming-ai02) 實機反向整理
> 本文取代 macOS 時代的舊版架構文件，反映系統實際在 Linux 三節點上的運作。

一套跑在內網三節點上的台股量化 + 多模型 AI 分析平台：從免費官方 API 抓資料、算因子與型態、四法選股，再由七角色 LLM 團隊加 `.27` 合議投票給出買/持/賣定案。

---

## 目錄

1. [部署拓撲](#1-部署拓撲)
2. [資料流](#2-資料流)
3. [分層架構](#3-分層架構)
4. [MoE 團隊分析](#4-moe-團隊分析七角色--27-合議)
5. [量化四法選股](#5-量化四法選股)
6. [資料層（MongoDB 集合）](#6-資料層mongodb-集合)
7. [API 端點總表](#7-api-端點總表)
8. [儀表板頁面](#8-儀表板頁面)
9. [排程（cron）](#9-排程cron)
10. [目錄結構](#10-目錄結構)
11. [移轉狀態與已知問題](#11-移轉狀態與已知問題)

---

## 1. 部署拓撲

三節點內網。主機承載一切資料與運算，兩台 Ollama 節點分工推理。

```
┌─────────────────────────────────────────────────────────────────┐
│  172.16.9.166 · ming-ai02 · Ubuntu                    【主機】     │
│  ─────────────────────────────────────────────────────────────  │
│   mongod        MongoDB  tw_stock_analysis  (~65 活躍集合)         │
│   systemd       twstock-api        FastAPI    127.0.0.1:8888      │
│   systemd       twstock-dashboard  Streamlit  0.0.0.0:8501        │
│   cron          排程  (TZ=Asia/Taipei)                            │
│   .venv         所有 Python 分析程式                               │
└───────────────┬───────────────────────────────┬─────────────────┘
                │ role_router 路由 LLM 角色       │
     ┌──────────▼──────────┐         ┌───────────▼──────────────┐
     │  172.16.9.28         │         │  172.16.9.27              │
     │  主力推理 (OLLAMA_URL)│         │  合議 (OLLAMA_CONSENSUS)  │
     │  ─────────────────   │         │  ──────────────────────  │
     │  qwen2.5-14b         │         │  hermes3:8b              │
     │    技術/基本面/顧問    │         │    價值/籌碼              │
     │  qwen2.5-3b          │         │  委員會投票               │
     │    總經/風險          │         │    hermes3:8b + qwen3b   │
     └─────────────────────┘         └──────────────────────────┘
```

| 節點 | 角色 | 環境變數 | 模型 |
|------|------|----------|------|
| `.166` | 主機（資料/儲存/運算/介面/排程） | — | — |
| `.28` | 主力推理 | `OLLAMA_URL` | `qwen2.5-14b`, `qwen2.5-3b` |
| `.27` | 合議委員 + 換視角角色 | `OLLAMA_CONSENSUS_URL` | `hermes3:8b`, `qwen2.5-3b` |

**服務管理**：API 與 Dashboard 皆為 systemd 服務（`systemctl {start,stop,restart,status} twstock-api / twstock-dashboard`），開機自啟。排程一律走 `cron`（非 macOS launchctl）。

---

## 2. 資料流

```
 官方免費 API                 下載/同步層                MongoDB              分析/決策            出口
─────────────           ─────────────────         ──────────────      ──────────────    ─────────────

 TWSE OpenAPI  ─┐
 TPEX OpenAPI  ─┼─► twse_daily_update.py ──► stock_price ────┐
                │   (股價/法人/PE·PB)          institutional_flow │
 FinMind API  ──┼─► macro_sync.py ─────────► stock_price(TAIEX)  │
                │   (加權指數/總經)             macro_indicators   │
                │                                                 ├─► factors ──► stock_factors
                ├─► twse_openapi_sync.py ──► 11 張補充表          │   indicators
                │   (融資券/當沖/借券…)                            │   morphology(蔡森)
                │                                                 │   financial_health
                └─► twse_quarterly_sync.py ► quarterly_earnings ──┤   backtesting
                                                                  │
                                            ┌─────────────────────┘
                                            ▼
                      ┌──────────────── 決策線 A：量化四法 ────────────────┐
                      │  daily_recommendations.py                          │
                      │   因子排行 + 蔡森型態 + 謝富旭存股 + 北大風控        │──► results/daily_picks/*.json
                      │   → 交叉比對「多策略共同推薦」                       │──► LINE 推播
                      └────────────────────────────────────────────────────┘
                      ┌──────────────── 決策線 B：AI 團隊 ─────────────────┐
                      │  team_daily_verified.py                            │
                      │   phase1: 6 分析師角色 → phase2: 顧問整合 + .27合議  │──► team_analysis 集合
                      │   verify_metrics: FinMind 複核 DB                   │──► results/team_analysis/*.json
                      └────────────────────────────────────────────────────┘
                                            │
                            ┌───────────────┼───────────────┐
                            ▼               ▼               ▼
                     FastAPI :8888    Streamlit :8501     LINE
                     (~26 端點)        (9 頁儀表板)      (每日推播)
```

**關鍵時序特性**：TWSE/TPEX OpenAPI 有約 **T+1 延遲**。因此每日 17:00 抓「當日 API 提供的最新交易日」，隔日再由 `backfill_recent_gaps.py` 回補法人與 PE/PB（T+1 才公布）。所有價格以 `Decimal128` 儲存，避免浮點誤差。

---

## 3. 分層架構

### ① 資料取得 (`src/downloaders`, `scripts`)

| 元件 | 職責 | 寫入 |
|------|------|------|
| `twse_daily_update.py` | TWSE/TPEX 股價、三大法人(T86)、PE/PB/殖利率 | `stock_price`, `institutional_flow`, `stock_factors` |
| `twse_openapi_sync.py` | 11 張補充表 + 每日完整度檢查 | 融資券/當沖/借券/盤後/零股… |
| `macro_sync.py` | FinMind 加權指數(TAIEX) + 總經指標(CPI/利率/M1B) | `stock_price(TAIEX)`, `macro_indicators` |
| `twse_quarterly_sync.py` | 季報（損益/資產負債/現金流） | `quarterly_earnings` |
| `sync_revenue_openapi.py` | 月營收 | `monthly_revenue` |
| `unified_downloader.py` | 分類批次下載器（技術面/籌碼面/基本面/衍生性） | 多表 |
| `src/downloaders/finmind_client.py` | FinMind API 客戶端 | — |
| `backfill_*.py` | 缺漏回補（按日期補股價/因子/法人） | 對應表 |

**資料來源**：TWSE OpenAPI · TPEX OpenAPI（`openapi/v1/…` 與 `www/zh-tw/afterTrading/…`）· FinMind API（需 `FINMIND_API_TOKEN`）。

### ② 儲存 (`MongoDB tw_stock_analysis`)

單一資料庫，約 65 個活躍集合。詳見 [§6](#6-資料層mongodb-集合)。

### ③ 分析引擎 (`src/`)

| 模組 | 內容 | 代表檔 |
|------|------|--------|
| `factors/` | 動能/價值/品質因子計算 | `factor_calculator.py`, `momentum_factors.py`, `quality_factors.py` |
| `indicators/` | 技術指標 | `ma.py`, `kd.py`, `bollinger.py`, `rsi`（MACD/OBV 等） |
| `morphology/` | 型態偵測 | `pattern_detector.py`, `bottom_reversal.py`, `neckline_breakout.py` |
| `senvision/` | 蔡森型態系統（多週期/視覺化） | `analysis.py`, `multi_timeframe.py`, `chart_visualizer.py` |
| `analysis/` | 財報健康度、總經、同業比較 | `financial_health.py`, `macro_indicators.py`, `peer_comparison.py` |
| `calculators/` | 還原股價、市場指標 | `adj_close_calculator_atomic.py`, `market_metrics_calculator.py` |
| `backtesting/` | 回測引擎 + 策略 + 績效 + 投組 | `backtest.py`, `strategy.py`, `performance.py`, `portfolio.py` |
| `ml/` | 機器學習 | `anomaly_detector.py`, `predictor.py`（XGBoost 5 日預測） |
| `sentiment/` | 情緒分析（新聞/PTT/內部人） | `analyzer.py` |
| `chip_analysis/` | 籌碼分析 | — |

**回測策略**（`src/backtesting/strategy.py`）：`MovingAverageCrossover`（均線交叉）、`RSIMeanReversion`（RSI 均值回歸）、`ValueMomentum`（價值動能）；另有 `examples/` 的 `MomentumStrategy`。績效指標含總報酬/年化/夏普/Sortino/Calmar/最大回撤/勝率/獲利因子。

### ④ 決策輸出 (`src/strategy`, `scripts/daily_recommendations.py`, `src/moe`)

兩條決策線：量化四法（[§5](#5-量化四法選股)）與 AI 團隊（[§4](#4-moe-團隊分析七角色--27-合議)）。

| 策略模組 | 內容 |
|----------|------|
| `strategy/hsieh_value.py`, `hsieh_dividend.py`, `hsieh_watchlist.py` | 謝富旭深度價值存股 |
| `strategy/agan.py` | 北大法則（市場週期 + 風控）|
| `strategy/live_advisor.py` | 即時交易建議 |
| `strategy/integrated_strategy_v21.py` | 整合策略 v21 |
| `strategy/trading_rules.py`, `screen_liquidity.py` | 交易規則、流動性篩選 |
| `analysis/stock_ranker.py` | 因子綜合排行 |

### ⑤ 介面 (`src/api`, `dashboard`, `src/alerts`)

- **FastAPI** `:8888` — ~26 個唯讀端點（[§7](#7-api-端點總表)）
- **Streamlit** `:8501` — 9 頁儀表板（[§8](#8-儀表板頁面)）
- **LINE** — `src/alerts/line_notifier.py`，每日推播選股與完整度檢查

---

## 4. MoE 團隊分析（七角色 + .27 合議）

由 `scripts/team_daily_verified.py` 驅動，是系統的決策核心。角色到模型的映射在 `src/moe/role_router.py` 的 `ROLE_TO_MODEL`；合議在 `src/moe/consensus.py`。

### 角色路由

| 階段 | 角色 | 模型 | 節點 |
|------|------|------|------|
| phase1 | 🎯 總經分析師 `macro-analyst` | `qwen2.5-3b` | `.28` |
| phase1 | 📈 技術分析師 `technical-analyst` | `qwen2.5-14b` | `.28` |
| phase1 | 💰 基本面分析師 `fundamental-analyst` | `qwen2.5-14b` | `.28` |
| phase1 | 💎 價值分析師 `value-analyst` | `hermes3:8b` | `.27` |
| phase1 | 🛡️ 風險管理 `risk-manager` | `qwen2.5-3b` | `.28` |
| phase1 | 🏦 籌碼分析師 `chip-analyst` | `hermes3:8b` | `.27` |
| phase2 | 🎩 投資顧問 `investment-advisor` | `qwen2.5-14b` | `.28` |
| phase2 | 🗳️ 合議委員會 | `hermes3:8b` + `qwen2.5-3b` | `.27` |

### 兩階段流程

```
phase1  (--quick)                          phase2  (--phase2)
─────────────────                          ──────────────────
每檔並讀 DB 資料                             讀 phase1 存檔
  ↓                                          ↓
6 角色各出報告 + 引用數值                     🎩 投資顧問整合 6 份報告 → 草案評級
  ↓  (~28 秒/檔)                              ↓
verify_metrics: FinMind 複核收盤/PE          🗳️ consensus.deliberate()
  ↓                                          .27 委員會獨立投票 → 多數決定案
存 JSON + 雙寫 team_analysis                  平手時採顧問草案評級
                                             ↓  (~21–31 秒/檔)
                                            買進 / 持有 / 賣出
                                            雙寫 team_analysis (final_verdict, consensus)
```

- **執行方式**：全市場約 2000 檔。`--date YYYYMMDD` 指定存讀檔日期（避免跨午夜/時區錯位）。
- **持久化**：結果雙寫至 `team_analysis` 集合（`src/moe/team_store.py`），供 `/api/team` 與儀表板即時查詢。
- **復驗**：`scripts/reverify_team.py` 兩層——快層比對「分析當下收盤 vs DB 權威收盤」標記 `fresh/stale/unknown`；慢層抽樣打 FinMind 複核 DB 收盤正確性。

---

## 5. 量化四法選股

`scripts/daily_recommendations.py` 每日 17:30 執行，四法獨立選股後交叉比對。

| 選股法 | 邏輯 | 資料源 |
|--------|------|--------|
| 📊 **因子排行** | 綜合評分 ≥70、有上漲空間、財報健康 ≥60 | `stock_factors`, `stock_ranker` |
| 📈 **蔡森型態** | W 底/頸線突破等型態，依型態分排序 | `senvision`, 掃描 CSV |
| 💎 **謝富旭存股** | 高殖利率、低負債、獲利穩、連續配息 | `hsieh_value`, `hsieh_dividend` |
| 🏛️ **北大法則** | 市場週期（四季）判持股水位 + 風控 | `agan.py`, `macro_indicators` |

**交叉比對** → 被 2 種以上方法同時選中者為「多策略共同推薦」。輸出 `results/daily_picks/picks_*.json` + LINE 兩則（策略整合 + 謝富旭清單）。

---

## 6. 資料層（MongoDB 集合）

資料庫 `tw_stock_analysis`，共 67 個集合（含 1 個 view）。以下依用途分組列出**活躍**集合。

### 核心事實表
| 集合 | 內容 | 概量 |
|------|------|------|
| `stock_price` | 日 OHLCV + 加權指數(TAIEX) | 5,087,554 |
| `stock_factors` | PE/PB/殖利率 + RSI/KD/MA/動能/ROE 等 | 3,672,305 |
| `trading_dates` | 交易日曆 | 6,937 |

### 財報與基本面
| 集合 | 內容 | 概量 |
|------|------|------|
| `quarterly_earnings` | **季報（實際使用）**：損益/資產負債/現金流 | 31,523 |
| `monthly_revenue` | 月營收 | 5,626 |
| `taiwan_stock_info` | 上市櫃基本資料（名稱/產業/流通股） | 3,453 |
| `taiwan_stock_per` | PER/PBR/殖利率（TWSE，較舊） | 537,665 |
| `dividend_detail` | 股利明細 | 17,243 |
| `financial_statements` | 財報（192 檔，稀疏） | 4,331 |
| `financial_reports` | ⚠️ **棄用舊表**（204 檔，勿用） | 4,238 |

### 籌碼面
| 集合 | 內容 | 概量 |
|------|------|------|
| `institutional_flow` | 三大法人買賣超（T86，實際使用） | 114,891 |
| `institutional_investors` | 法人（舊） | 730,558 |
| `institutional_trading` | 法人（已棄用，停在 2026-02） | 344,837 |
| `margin_purchase_short_sale` | 融資融券 | 106,618 |
| `securities_lending` | 借券 | 86,251 |
| `foreign_shareholding` | 外資持股 | 12,400 |
| `foreign_top20` | 外資買超前 20 | 1,420 |

### 交易/市場補充（`twse_openapi_sync`）
`after_hours_trading`(盤後,1.1M) · `day_trading_targets`(當沖,79k) · `odd_lot_trading`(零股,95k) · `margin_suspension`(11k) · `punished_stocks`(處置) · `etf_dca_rank`(ETF定期定額) · `major_news`(重大訊息,12k) · `insider_transfer`(內部人) · `delisting`(下市) · `gold_price`/`gold_prices`(黃金) · `total_margin`/`total_institutional_investors`/`market_statistics`(市場總計)

### 分析輸出
| 集合 | 內容 | 概量 |
|------|------|------|
| `team_analysis` ★ | 7 角色報告 + 合議定案 + 復驗（本次新增） | 2,999 |
| `alert_history` / `alert_rules` | 告警記錄/規則 | 227 / 25 |
| `portfolio_positions` / `portfolio_trades` | 投組部位/交易 | 18 / 17 |

### 名單
`stock_list`(3,065) · `stocks`(2,361) · `stocks_full`(1,688) · `tickers`(1,345) · `tickers_legacy`(view→tickers)

> **注意**：`balance_sheet_detail`, `cash_flows_detail`, `institutional_holdings`, `shareholding`, `industry_price`, `dividend`(空), `financial_statement_detail` 等為 **0 筆空表**；`*_backup_20260224` 為一次性備份。財報請以 `quarterly_earnings` 為準，勿用 `financial_reports`。

---

## 7. API 端點總表

FastAPI，綁 `127.0.0.1:8888`，systemd `twstock-api`。全部為唯讀 `GET`。Swagger UI 在 `/docs`。

| 端點 | 說明 |
|------|------|
| `/api/price/{symbol}` | 個股近 N 日股價 |
| `/api/factors/{symbol}` | 最新因子（PE/PB/殖利率/ROE/RSI 等） |
| `/api/valuation/{symbol}` | DCF + DDM + PE Band 估值 |
| `/api/risk/{symbol}` | 個股風險（VaR/Sharpe/MDD） |
| `/api/risk/portfolio` | 投組風險 |
| `/api/peer/{symbol}` | 同業比較 |
| `/api/industry/{industry}` | 產業排名 |
| `/api/ranking` | 綜合選股排行 |
| `/api/score/{symbol}` | 單股綜合評分 |
| `/api/macro` | 總經環境與市場訊號 |
| `/api/sentiment/{symbol}` | 情緒分析（新聞/PTT/內部人） |
| `/api/predict/{symbol}` | XGBoost 5 日方向預測 |
| `/api/anomaly/{symbol}` | 異常偵測 |
| `/api/institutional/{symbol}` | 法人買賣超 |
| `/api/revenue/{symbol}` | 月營收 |
| `/api/dividend/{symbol}` | 股利明細 |
| `/api/pku` | 北大四大法則（週期+止損+買入三問+主力階段） |
| `/api/hsieh/research/{symbol}` | 謝富旭研究法（財報驚喜/EPS/成長/填息/配股） |
| `/api/hsieh` | 謝富旭存股選股 |
| `/api/advisor` | 策略交易建議 |
| `/api/financial/{symbol}` | 財報健康分析（6 維 + 杜邦 + 警示） |
| `/api/scan` | 全市場：排行 + 風險篩選 + 推薦 |
| `/api/stocks` | 所有有數據的股票代號/名稱 |
| `/api/team/{symbol}` ★ | 個股團隊分析（6 報告+佐證+顧問+合議+復驗） |
| `/api/team` ★ | 全市場定案彙總（可依 date/verdict/status 篩選） |
| `/api/health` | 健康檢查（最新股價日 + 集合筆數） |

> ★ = 本次新增。存取方式：伺服器本機或 SSH tunnel（`ssh -L 8888:localhost:8888 …`）。

---

## 8. 儀表板頁面

Streamlit，綁 `0.0.0.0:8501`（內網可達），systemd `twstock-dashboard`。導航在 `dashboard/app.py` 的 sidebar radio。

| 頁面 | 檔案 | 內容 |
|------|------|------|
| 系統總覽 | `home.py` | DB 統計、最新日期、覆蓋率 |
| K線圖與技術指標 | `charts.py` | K線 + MA/BB/KD/量能（文字輸入選股） |
| 互動回測 ★ | `backtest_viz.py` | 選策略/股票池/期間，現場跑回測引擎 |
| 因子分析面板 | `factors.py` | 因子分佈與排行 |
| 財報摘要儀表 | `financials.py` | 季報趨勢（讀 `quarterly_earnings`） |
| 策略比較工具 | `strategy_compare.py` | 策略績效比較 |
| 實時數據監控 | `monitor.py` | 資料新鮮度、覆蓋率、cron 狀態 |
| 團隊分析 ★ | `team.py` | 全市場定案表 + 單檔明細 + 復驗狀態 |
| 每日選股推薦 ★ | `picks.py` | 四法選股 + 多策略共同推薦 |

> ★ = 本次新增/重寫。`dashboard/.streamlit/config.toml` 設 `showSidebarNavigation=false` 關閉自動多頁導航。

---

## 9. 排程（cron）

`crontab -l`，**TZ=Asia/Taipei**（已從 UTC 修正）。

| 時刻 | 工作 | 腳本 |
|------|------|------|
| 每時 :05 | 盤中資料增量更新 | `hourly_data_update.sh` |
| 17:00 一–五 | 股價+法人+PE → 回補 → 因子 → 全市場掃描 | `daily_senvision.sh` |
| 17:10 一–五 | 加權指數 + 總經指標 | `macro_sync.py` |
| 17:30 一–五 | 四法選股推薦（→LINE） | `daily_recommendations.py` |
| 17:30 一–五 | TWSE 補充表同步 | `twse_openapi_sync.py` |
| 18:00 一–五 | 量價掃描 | `volume_price_scan.py` |
| 18:05 一–五 | OBV 底背離掃描 | `obv_bottom_divergence_scan.py` |
| 18:30 一–五 | 團隊分析（已查證 50 檔） | `team_daily_50.sh` |
| 21:00 一–五 | 資料完整度檢查（→LINE） | `twse_openapi_sync.py --check-only` |
| 01:00 每日 | 股利明細同步 | `sync_dividend_detail.py` |
| 週日 02:00 | 流通股數 | `sync_shares_openapi.py` |
| 每月 | 月營收 · 季報 | `sync_revenue_openapi.py`, `quarterly_earnings_sync.sh` |
| 週日 01:00 | MongoDB 備份 | `backup_mongodb.sh` |
| 每日 03:00 | log 輪替 | `log_rotation.sh` |

---

## 10. 目錄結構

```
tw-stock-analysis/
├── src/
│   ├── downloaders/      資料下載（TWSE/TPEX/FinMind, unified_downloader）
│   ├── factors/          因子計算（動能/價值/品質）
│   ├── indicators/       技術指標（MA/KD/BB/RSI/MACD/OBV）
│   ├── morphology/       型態偵測（W底/頸線突破）
│   ├── senvision/        蔡森型態系統（多週期/視覺化）
│   ├── analysis/         財報健康/總經/同業/選股排行
│   ├── calculators/      還原股價/市場指標
│   ├── backtesting/      回測引擎 + 策略 + 績效 + 投組
│   ├── strategy/         決策策略（謝富旭/北大/live_advisor）
│   ├── ml/               機器學習（異常/XGBoost 預測）
│   ├── sentiment/        情緒分析
│   ├── moe/              團隊分析核心（role_router/consensus/team_store）
│   ├── api/              FastAPI server
│   ├── alerts/           LINE 通知
│   └── domain/, utils/, migrations/, cli/, chip_analysis/, portfolio/
├── scripts/              操作進入點（cron 驅動 + 手動工具，數百支）
│   ├── team_daily_verified.py     團隊分析（phase1/phase2）
│   ├── daily_recommendations.py   四法選股
│   ├── twse_daily_update.py       每日股價/法人/PE
│   ├── twse_openapi_sync.py       補充表 + 完整度檢查
│   ├── macro_sync.py              加權指數 + 總經
│   ├── parallel_factor_calculation.py  因子批算
│   ├── reverify_team.py     ★    團隊分析復驗（快層+慢層）
│   ├── migrate_team_to_db.py ★    team_analysis 灌庫
│   ├── query_team.py         ★    團隊分析 CLI 查詢
│   └── *.sh                        daily_senvision / team_daily_50 / hourly_data_update …
├── dashboard/
│   ├── app.py                     Streamlit 入口 + 導航
│   ├── pages/                     9 頁
│   └── .streamlit/config.toml     關閉自動多頁導航
├── results/
│   ├── daily_picks/               四法選股每日結果
│   └── team_analysis/             團隊分析每日結果
├── charts/                        回測範例 CSV
├── logs/                          執行日誌（cron_*, hourly_updates/）
├── .env                           設定（MONGODB_URI, OLLAMA_URL, FINMIND_TOKEN, LINE_*）
└── ARCHITECTURE.md                本文件
```

---

## 11. 移轉狀態與已知問題

系統從 macOS 搬到這台 Linux。**檔案層完整**（程式 tarball 40,147 項全對、MongoDB dump 完整），但**程式碼層留有多處 macOS 假設**，於首次在 Linux + 全市場使用時逐一浮現。

### 已修正的移轉殘留
| 問題 | 原本（macOS） | 修正 |
|------|--------------|------|
| **時區** | 系統停在 UTC，cron 用系統時區判讀 → 每日更新實際跑在台北凌晨 01:00、且少抓一天 | `timedatectl set-timezone Asia/Taipei` + 重啟 cron |
| **服務檢測** | 監控頁用 `launchctl`（macOS） | 改查 `cron`/systemd |
| **硬編碼路徑** | `~/Desktop/Stock/…`（Mac 桌面） | 動態 `PROJECT_ROOT` |
| **指錯表** | 多頁讀棄用的 `financial_reports`（204 檔） | 改 `quarterly_earnings`（1984 檔） |
| **巨型選單** | 選股用 `stock_price.distinct`（含 15k 權證）塞爆瀏覽器 | 改文字輸入 / 上市櫃池 |
| **合議品質** | 平手裁決依 dict 順序偏「買進」；投票理由抽到樣板字 | 平手採顧問草案；理由跳過標題行 |
| **phase2 檔名** | 用當天日期，跨午夜找不到 phase1 存檔 | 加 `--date` + 退回最新一份 |

### 本次新增能力
- `team_analysis` 集合 + JSON/DB 雙寫 + `migrate_team_to_db.py` + 兩層復驗 `reverify_team.py`
- `/api/team` 與 `/api/team/{symbol}` 端點
- 儀表板：**團隊分析**、**每日選股**、**互動回測** 三頁；dashboard 改 systemd 服務綁 0.0.0.0
- CLI：`query_team.py`

### 尚待處理（可選）
- **下市股仍在分析名單**：理隆(2018)、興航等已下市公司每天仍被團隊分析跑，用舊價、虛增 unknown 數。宜於 `select_universe_all` 加「排除最新報價超過 N 天」過濾。
- **07-08 TPEX 權證缺口**：該日約 3,800 檔權證未收錄（免費 API 限制），個股不受影響。

---

*本文件由實機勘查反向整理。如系統演進，請同步更新。*
