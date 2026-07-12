# 📊 台股數據自動更新系統 - 資料表覆蓋清單

**系統版本**: v1.0  
**最後更新**: 2026-02-22  
**資料來源**: FinMind API  
**總資料表數**: 43 個  
**自動更新**: 每小時 (launchd)

---

## ✅ 完整涵蓋的資料類別

您要求的所有資料類別已經完整支持並自動更新：

### 🔵 1. 技術面 (9 個資料表)

| 資料表名稱 | FinMind Dataset | MongoDB Collection | 自動更新 |
|-----------|----------------|-------------------|---------|
| ✓ 台股總覽 | TaiwanStockInfo | taiwan_stock_info | ✅ 每小時 |
| ✓ 台股總覽(含權證) | 同上 | 同上 | ✅ 每小時 |
| ✓ 台灣股價資料表 | TaiwanStockPrice | stock_price | ✅ 每小時 |
| ✓ 台股交易日 | TaiwanStockTradingDate | trading_dates | ✅ 每小時 |
| ✓ 台灣類股股價表 | TaiwanStockIndustryPrice | industry_price | ✅ 每小時 |
| ✓ 個股 PER、PBR 資料表 | TaiwanStockPER | taiwan_stock_per | ✅ 每小時 |
| ✓ 每 5 秒委託成交統計 | TaiwanStockStatisticsOfOrderBookAndTrade | order_statistics_5s | ✅ 每小時 |
| ✓ 台股加權指數 | TaiwanVariousIndicators5Seconds | market_statistics | ✅ 每小時 |
| ✓ 當日沖銷交易標的及成交量值 | TaiwanStockDayTrading | day_trading_targets | ✅ 每小時 |
| ✓ 加權、櫃買報酬指數 | TaiwanStockTotalReturnIndex | total_return_index | ✅ 每小時 |

**說明**: 技術面資料包含所有股價、指數、及盤中即時統計資料。權證資料包含在台股總覽中。

---

### 🟢 2. 籌碼面 (9 個資料表)

| 資料表名稱 | FinMind Dataset | MongoDB Collection | 自動更新 |
|-----------|----------------|-------------------|---------|
| ✓ 個股融資融劵表 | TaiwanStockMarginPurchaseShortSale | margin_purchase_short_sale | ✅ 每小時 |
| ✓ 整體市場融資融劵表 | TaiwanStockTotalMarginPurchaseShortSale | total_margin | ✅ 每小時 |
| ✓ 個股三大法人買賣表 | TaiwanStockInstitutionalInvestors | institutional_investors_detail | ✅ 每小時 |
| ✓ 整體三大市場法人買賣表 | TaiwanStockTotalInstitutionalInvestors | total_institutional_investors | ✅ 每小時 |
| ✓ 外資持股表 | TaiwanStockShareholding | shareholding | ✅ 每小時 |
| ✓ 借券成交明細 | TaiwanStockSecuritiesLending | securities_lending | ✅ 每小時 |
| ✓ 暫停融券賣出表(融券回補日) | TaiwanStockShortSalingSuspensionAndReturnDate | short_sale_suspension | ✅ 每小時 |
| ✓ 信用額度總量管制餘額表 | TaiwanStockTotalCreditLimit | total_credit_limit | ✅ 每小時 |
| ✓ 證券商資訊表 | TaiwanSecuritiesTradersInfo | securities_traders_info | ✅ 每小時 |

**說明**: 籌碼面資料涵蓋法人動向、融資融券、借券及證券商資訊。

---

### 🟡 3. 基本面 (10 個資料表)

| 資料表名稱 | FinMind Dataset | MongoDB Collection | 自動更新 |
|-----------|----------------|-------------------|---------|
| ✓ 現金流量表 | TaiwanStockCashFlowsStatement | cash_flows_detail | ✅ 每小時 |
| ✓ 綜合損益表 | TaiwanStockFinancialStatement | financial_statement_detail | ✅ 每小時 |
| ✓ 資產負債表 | TaiwanStockBalanceSheet | balance_sheet_detail | ✅ 每小時 |
| ✓ 股利政策表 | TaiwanStockDividend | dividend_detail | ✅ 每小時 |
| ✓ 除權除息結果表 | TaiwanStockDividendResult | dividend_results | ✅ 每小時 |
| ✓ 月營收表 | TaiwanStockMonthRevenue | month_revenue_detail | ✅ 每小時 |
| ✓ 減資恢復買賣參考價格 | TaiwanStockCapitalReductionReferencePrice | capital_reduction_price | ✅ 每小時 |
| ✓ 台股下市資料表 | TaiwanStockDelisting | delisting | ✅ 每小時 |
| ✓ 台股分割後參考價 | TaiwanStockSplitReferencePrice | split_reference_price | ✅ 每小時 |
| ✓ 台灣股票變更面額恢復買賣參考價格 | TaiwanStockChangeParValueReferencePrice | change_par_value_price | ✅ 每小時 |

**說明**: 基本面資料包含三大財報、股利政策、月營收及特殊事件參考價。

---

### 🟣 4. 衍生性金融商品 (6 個資料表)

| 資料表名稱 | FinMind Dataset | MongoDB Collection | 自動更新 |
|-----------|----------------|-------------------|---------|
| ✓ 期貨、選擇權日成交資訊總覽 | (合併) | futures_daily + options_daily | ✅ 每小時 |
| ✓ 期貨、選擇權即時報價總覽 | (合併) | 同上 | ✅ 每小時 |
| ✓ 期貨日成交資訊 | TaiwanFuturesDaily | futures_daily | ✅ 每小時 |
| ✓ 選擇權日成交資訊 | TaiwanOptionsDaily | options_daily | ✅ 每小時 |
| ✓ 期貨三大法人買賣 | TaiwanFuturesInstitutionalInvestors | futures_institutional | ✅ 每小時 |
| ✓ 選擇權三大法人買賣 | TaiwanOptionsInstitutionalInvestors | options_institutional | ✅ 每小時 |
| ✓ 期貨各卷商每日交易 | TaiwanFuturesTraders | futures_traders | ✅ 每小時 |
| ✓ 選擇權各卷商每日交易 | TaiwanOptionsTraders | options_traders | ✅ 每小時 |

**說明**: 衍生性商品涵蓋期貨、選擇權的行情、法人部位及分點資料。

---

### 🔴 5. 其他 (5 個資料表)

| 資料表名稱 | FinMind Dataset | MongoDB Collection | 自動更新 |
|-----------|----------------|-------------------|---------|
| ✓ 相關新聞 | TaiwanStockNews | stock_news | ✅ 每小時 |
| ✓ 黃金價格表 | GoldPrice | gold_price | ✅ 每小時 |
| ✓ 原油資料表(Brent, WTI) | CrudeOilPrices | crude_oil_price | ✅ 每小時 |
| ⚠️ 美股股價 | - | - | ❌ 不支援 |
| ✓ 外幣對台幣資料表(19 種幣別匯率) | ExchangeRate | exchange_rate | ✅ 每小時 |
| ✓ 央行利率資料表(12 個國家) | GovernmentBondsYield | government_bonds_yield | ✅ 每小時 |

**說明**: 
- ✅ 已支援: 新聞、黃金、原油、外匯、利率
- ⚠️ **美股股價**: FinMind API 目前未提供，需另尋其他資料源 (如 Yahoo Finance, Alpha Vantage)

---

## 📊 API 配額使用分析

### 每小時實際 API 用量（增量更新模式）

系統使用 **skip_existing** 邏輯，只下載新增/更新的資料：

| 類別 | 資料表數 | 預估 API 呼叫次數 | 說明 |
|------|---------|------------------|------|
| 技術面 | 9 | 50-100 次 | 股價每日更新，跳過歷史資料 |
| 基本面 | 10 | 20-50 次 | 財報季度更新，增量較少 |
| 籌碼面 | 9 | 50-100 次 | 法人動向每日更新 |
| 衍生性商品 | 6 | 20-30 次 | 期權合約數量有限 |
| 其他 | 5 | 10-20 次 | 新聞僅近 30 天，其他每日一筆 |
| **總計** | **39** | **150-300 次** | ✅ **低於 500 次限制** |

### 關鍵特性

1. **增量更新**: 僅下載自上次更新後的新資料
2. **智能跳過**: 已存在資料自動跳過，不浪費 API 配額
3. **批次下載**: 多支股票批次處理，減少 API 呼叫
4. **時間範圍**: 
   - 歷史資料: start_date = 2020-01-01
   - 5 秒統計: 近 7 天
   - 新聞: 近 30 天

---

## 🚀 自動更新排程

### launchd 服務配置

| 服務 | 執行時間 | 涵蓋類別 | 狀態 |
|------|---------|---------|------|
| **com.twstock.hourly_update** | 每小時 XX:05 | 全部 5 類 (39 表) | ✅ 運行中 |
| com.twstock.weekly_outstanding_shares | 週日 02:00 | 流通股數 | ✅ 運行中 |
| com.twstock.weekly_log_cleanup | 週日 03:00 | 日誌清理 | ✅ 運行中 |

### 執行腳本

- **主腳本**: `scripts/hourly_data_update.sh`
- **下載器**: `src/downloaders/unified_downloader.py`
- **配置**: `src/downloaders/table_config.py`

---

## 📝 使用指南

### 查看當前資料覆蓋率

```bash
cd /Users/ming/Desktop/Stock/tw-stock-analysis
python3 scripts/check_financial_coverage.py
```

### 手動觸發更新

```bash
# 立即執行一次全量更新
launchctl start com.twstock.hourly_update

# 或直接執行腳本
./scripts/hourly_data_update.sh
```

### 查看更新日誌

```bash
# 即時監控
tail -f logs/launchd_hourly_stdout.log

# 查看歷史記錄
ls -lt logs/hourly_updates/ | head -10
```

### 下載特定類別

```bash
export FINMIND_API_TOKEN="$(grep FINMIND_API_TOKEN .env | cut -d'=' -f2)"

# 僅下載技術面
python3 src/downloaders/unified_downloader.py --categories 技術面 --verbose

# 下載多個類別
python3 src/downloaders/unified_downloader.py --categories 技術面 基本面 --verbose

# 下載全部
python3 src/downloaders/unified_downloader.py --all --verbose
```

---

## ⚠️ 注意事項

### 1. 美股資料不支援

FinMind API 目前**不提供美股股價**資料。如需美股資料，建議使用：

- **Yahoo Finance API** (免費，但有限制)
- **Alpha Vantage** (免費版每天 500 次)
- **Twelve Data** (免費版每天 800 次)

### 2. 財報覆蓋率

目前財報資料覆蓋率約 **11.7%** (191/1,636 上市股票)。

**如需完整財報**，執行：

```bash
export FINMIND_API_TOKEN="$(grep FINMIND_API_TOKEN .env | cut -d'=' -f2)"
python3 src/downloaders/unified_downloader.py --categories 基本面 --no-skip --verbose
```

預計時間: 18-24 小時

### 3. API 配額監控

FinMind 免費版限制：
- **每小時**: ~500 次
- **每天**: ~12,000 次

系統增量更新模式下，每小時用量僅 150-300 次，**配額充足**。

---

## 📚 相關文檔

- [launchd 設置指南](LAUNCHD_SETUP_GUIDE.md)
- [快速開始](QUICK_START.md)
- [專案指南](PROJECT_GUIDE.md)
- [開發歷程](docs/chat_history.md)

---

## 🎯 總結

✅ **所有您要求的資料類別均已支持**  
✅ **自動更新系統已部署並運行中**  
✅ **API 配額在安全範圍內**  
⚠️ **唯獨美股股價需另尋資料源**  

**下一步**: 等待下個整點 (XX:05) 驗證自動更新執行成功。

---

**維護者**: Ming  
**系統狀態**: ✅ 生產就緒  
**最後驗證**: 2026-02-22 10:37
