# 台股資料字典

**更新時間**: 2026-02-20 23:32:20

---

## 📊 資料庫統計

- **總資料表數**: 10
- **已完成下載**: 3
- **總記錄數**: 0
- **最後下載時間**: 2026-02-20 23:32:20

---

## 技術面

### ❌ 台股總覽

**說明**: 台股所有上市櫃股票基本資訊

- **Dataset**: `TaiwanStockInfo`
- **Collection**: `taiwan_stock_info`
- **需要股票代碼**: 否
- **狀態**: ❌ 未下載或失敗
- **索引**: `stock_id`
- **唯一鍵**: `stock_id`

### ❌ 台灣股價資料表

**說明**: 個股每日開高低收量價資料

- **Dataset**: `TaiwanStockPrice`
- **Collection**: `stock_price`
- **需要股票代碼**: 是
- **狀態**: ❌ 未下載或失敗
- **索引**: `stock_id`, `date`
- **唯一鍵**: `stock_id`, `date`

### ❌ 個股 PER、PBR

**說明**: 個股本益比、股價淨值比

- **Dataset**: `TaiwanStockPER`
- **Collection**: `taiwan_stock_per`
- **需要股票代碼**: 是
- **狀態**: ❌ 未下載或失敗
- **索引**: `stock_id`, `date`
- **唯一鍵**: `stock_id`, `date`

### ❌ 台股加權指數

**說明**: 大盤指數及市場統計

- **Dataset**: `TaiwanVariousIndicators5Seconds`
- **Collection**: `market_statistics`
- **需要股票代碼**: 否
- **狀態**: ❌ 未下載或失敗
- **索引**: `date`
- **唯一鍵**: `date`

### ❌ 台股交易日

**說明**: 台股開市交易日曆

- **Dataset**: `TaiwanStockTradingDate`
- **Collection**: `trading_dates`
- **需要股票代碼**: 否
- **狀態**: ❌ 未下載或失敗
- **索引**: `date`
- **唯一鍵**: `date`

### ❌ 台灣類股股價表

**說明**: 產業分類指數價格

- **Dataset**: `TaiwanStockIndustryPrice`
- **Collection**: `industry_price`
- **需要股票代碼**: 否
- **狀態**: ❌ 未下載或失敗
- **索引**: `industry`, `date`
- **唯一鍵**: `industry`, `date`

### ❌ 每 5 秒委託成交統計

**說明**: 盤中 5 秒委買賣統計（近一週）

- **Dataset**: `TaiwanStockStatisticsOfOrderBookAndTrade`
- **Collection**: `order_statistics_5s`
- **需要股票代碼**: 是
- **狀態**: ❌ 未下載或失敗
- **索引**: `stock_id`, `date`
- **唯一鍵**: `stock_id`, `date`, `time`

### ❌ 當日沖銷交易標的

**說明**: 可當沖股票名單

- **Dataset**: `TaiwanStockDayTrading`
- **Collection**: `day_trading_targets`
- **需要股票代碼**: 否
- **狀態**: ❌ 未下載或失敗
- **索引**: `date`, `stock_id`
- **唯一鍵**: `stock_id`, `date`

### ❌ 加權、櫃買報酬指數

**說明**: 含息報酬指數

- **Dataset**: `TaiwanStockTotalReturnIndex`
- **Collection**: `total_return_index`
- **需要股票代碼**: 否
- **狀態**: ❌ 未下載或失敗
- **索引**: `date`
- **唯一鍵**: `date`, `type`

## 籌碼面

### ❌ 個股融資融劵表

**說明**: 個股融資融券餘額變化

- **Dataset**: `TaiwanStockMarginPurchaseShortSale`
- **Collection**: `margin_purchase_short_sale`
- **需要股票代碼**: 是
- **狀態**: ❌ 未下載或失敗
- **索引**: `stock_id`, `date`
- **唯一鍵**: `stock_id`, `date`

### ❌ 整體市場融資融劵表

**說明**: 全市場融資融券統計

- **Dataset**: `TaiwanStockTotalMarginPurchaseShortSale`
- **Collection**: `total_margin`
- **需要股票代碼**: 否
- **狀態**: ❌ 未下載或失敗
- **索引**: `date`
- **唯一鍵**: `date`

### ❌ 個股三大法人買賣表

**說明**: 外資、投信、自營商買賣超

- **Dataset**: `TaiwanStockInstitutionalInvestors`
- **Collection**: `institutional_investors_detail`
- **需要股票代碼**: 是
- **狀態**: ❌ 未下載或失敗
- **索引**: `stock_id`, `date`
- **唯一鍵**: `stock_id`, `date`

### ❌ 整體三大市場法人買賣表

**說明**: 三大法人市場總買賣

- **Dataset**: `TaiwanStockTotalInstitutionalInvestors`
- **Collection**: `total_institutional_investors`
- **需要股票代碼**: 否
- **狀態**: ❌ 未下載或失敗
- **索引**: `date`
- **唯一鍵**: `date`

### ❌ 外資持股表

**說明**: 外資持股比例

- **Dataset**: `TaiwanStockShareholding`
- **Collection**: `shareholding`
- **需要股票代碼**: 是
- **狀態**: ❌ 未下載或失敗
- **索引**: `stock_id`, `date`
- **唯一鍵**: `stock_id`, `date`

### ❌ 借券成交明細

**說明**: 借券交易資料

- **Dataset**: `TaiwanStockSecuritiesLending`
- **Collection**: `securities_lending`
- **需要股票代碼**: 是
- **狀態**: ❌ 未下載或失敗
- **索引**: `stock_id`, `date`
- **唯一鍵**: `stock_id`, `date`

### ❌ 暫停融券賣出表

**說明**: 禁止融券股票名單

- **Dataset**: `TaiwanStockShortSalingSuspensionAndReturnDate`
- **Collection**: `short_sale_suspension`
- **需要股票代碼**: 否
- **狀態**: ❌ 未下載或失敗
- **索引**: `stock_id`, `date`
- **唯一鍵**: `stock_id`, `suspend_date`

### ❌ 信用額度總量管制餘額表

**說明**: 信用交易額度管制

- **Dataset**: `TaiwanStockTotalCreditLimit`
- **Collection**: `total_credit_limit`
- **需要股票代碼**: 否
- **狀態**: ❌ 未下載或失敗
- **索引**: `date`
- **唯一鍵**: `date`

### ❌ 證券商資訊表

**說明**: 券商基本資料

- **Dataset**: `TaiwanSecuritiesTradersInfo`
- **Collection**: `securities_traders_info`
- **需要股票代碼**: 否
- **狀態**: ❌ 未下載或失敗
- **索引**: `trader_id`
- **唯一鍵**: `trader_id`

## 基本面

### ✅ 綜合損益表

**說明**: 損益表財報科目明細

- **Dataset**: `TaiwanStockFinancialStatement`
- **Collection**: `financial_statement_detail`
- **需要股票代碼**: 是
- **記錄數**: 0
- **狀態**: ✅ 已下載
- **索引**: `stock_id`, `date`
- **唯一鍵**: `stock_id`, `date`, `type`

### ✅ 資產負債表

**說明**: 資產負債表財報科目明細

- **Dataset**: `TaiwanStockBalanceSheet`
- **Collection**: `balance_sheet_detail`
- **需要股票代碼**: 是
- **記錄數**: 0
- **狀態**: ✅ 已下載
- **索引**: `stock_id`, `date`
- **唯一鍵**: `stock_id`, `date`, `type`

### ✅ 現金流量表

**說明**: 現金流量表財報科目明細

- **Dataset**: `TaiwanStockCashFlowsStatement`
- **Collection**: `cash_flows_detail`
- **需要股票代碼**: 是
- **記錄數**: 0
- **狀態**: ✅ 已下載
- **索引**: `stock_id`, `date`
- **唯一鍵**: `stock_id`, `date`, `type`

### ❌ 股利政策表

**說明**: 股利發放計畫

- **Dataset**: `TaiwanStockDividend`
- **Collection**: `dividend_detail`
- **需要股票代碼**: 是
- **狀態**: ❌ 未下載或失敗
- **索引**: `stock_id`, `date`
- **唯一鍵**: `stock_id`, `date`

### ❌ 除權除息結果表

**說明**: 實際除權息資料

- **Dataset**: `TaiwanStockDividendResult`
- **Collection**: `dividend_results`
- **需要股票代碼**: 是
- **狀態**: ❌ 未下載或失敗
- **索引**: `stock_id`, `date`
- **唯一鍵**: `stock_id`, `date`

### ❌ 月營收表

**說明**: 每月營收公告

- **Dataset**: `TaiwanStockMonthRevenue`
- **Collection**: `month_revenue_detail`
- **需要股票代碼**: 是
- **狀態**: ❌ 未下載或失敗
- **索引**: `stock_id`, `date`
- **唯一鍵**: `stock_id`, `date`

### ❌ 減資恢復買賣參考價格

**說明**: 減資參考價

- **Dataset**: `TaiwanStockCapitalReductionReferencePrice`
- **Collection**: `capital_reduction_price`
- **需要股票代碼**: 否
- **狀態**: ❌ 未下載或失敗
- **索引**: `stock_id`, `date`
- **唯一鍵**: `stock_id`, `date`

### ❌ 台股下市資料表

**說明**: 下市股票清單

- **Dataset**: `TaiwanStockDelisting`
- **Collection**: `delisting`
- **需要股票代碼**: 否
- **狀態**: ❌ 未下載或失敗
- **索引**: `stock_id`
- **唯一鍵**: `stock_id`

### ❌ 台股分割後參考價

**說明**: 股票分割參考價

- **Dataset**: `TaiwanStockSplitReferencePrice`
- **Collection**: `split_reference_price`
- **需要股票代碼**: 否
- **狀態**: ❌ 未下載或失敗
- **索引**: `stock_id`, `date`
- **唯一鍵**: `stock_id`, `date`

### ❌ 台灣股票變更面額恢復買賣參考價格

**說明**: 變更面額參考價

- **Dataset**: `TaiwanStockChangeParValueReferencePrice`
- **Collection**: `change_par_value_price`
- **需要股票代碼**: 否
- **狀態**: ❌ 未下載或失敗
- **索引**: `stock_id`, `date`
- **唯一鍵**: `stock_id`, `date`

## 衍生性金融商品

### ❌ 期貨日成交資訊

**說明**: 期貨每日行情

- **Dataset**: `TaiwanFuturesDaily`
- **Collection**: `futures_daily`
- **需要股票代碼**: 否
- **狀態**: ❌ 未下載或失敗
- **索引**: `futures_id`, `date`
- **唯一鍵**: `futures_id`, `date`

### ❌ 選擇權日成交資訊

**說明**: 選擇權每日行情

- **Dataset**: `TaiwanOptionsDaily`
- **Collection**: `options_daily`
- **需要股票代碼**: 否
- **狀態**: ❌ 未下載或失敗
- **索引**: `contract_name`, `date`
- **唯一鍵**: `contract_name`, `date`

### ❌ 期貨三大法人買賣

**說明**: 期貨三大法人部位

- **Dataset**: `TaiwanFuturesInstitutionalInvestors`
- **Collection**: `futures_institutional`
- **需要股票代碼**: 否
- **狀態**: ❌ 未下載或失敗
- **索引**: `futures_id`, `date`
- **唯一鍵**: `futures_id`, `date`, `name`

### ❌ 選擇權三大法人買賣

**說明**: 選擇權三大法人部位

- **Dataset**: `TaiwanOptionsInstitutionalInvestors`
- **Collection**: `options_institutional`
- **需要股票代碼**: 否
- **狀態**: ❌ 未下載或失敗
- **索引**: `contract_name`, `date`
- **唯一鍵**: `contract_name`, `date`, `name`

### ❌ 期貨各券商每日交易

**說明**: 期貨分點交易資料

- **Dataset**: `TaiwanFuturesTraders`
- **Collection**: `futures_traders`
- **需要股票代碼**: 否
- **狀態**: ❌ 未下載或失敗
- **索引**: `date`, `trader_id`
- **唯一鍵**: `date`, `trader_id`, `futures_id`

### ❌ 選擇權各券商每日交易

**說明**: 選擇權分點交易資料

- **Dataset**: `TaiwanOptionsTraders`
- **Collection**: `options_traders`
- **需要股票代碼**: 否
- **狀態**: ❌ 未下載或失敗
- **索引**: `date`, `trader_id`
- **唯一鍵**: `date`, `trader_id`, `contract_name`

## 其他

### ❌ 黃金價格表

**說明**: 國際黃金現貨價格

- **Dataset**: `GoldPrice`
- **Collection**: `gold_price`
- **需要股票代碼**: 否
- **狀態**: ❌ 未下載或失敗
- **索引**: `date`
- **唯一鍵**: `date`

### ❌ 原油資料表

**說明**: 國際原油期貨價格

- **Dataset**: `CrudeOilPrices`
- **Collection**: `crude_oil_price`
- **需要股票代碼**: 否
- **狀態**: ❌ 未下載或失敗
- **索引**: `date`
- **唯一鍵**: `date`, `name`

### ❌ 外幣對台幣資料表

**說明**: 外匯匯率

- **Dataset**: `ExchangeRate`
- **Collection**: `exchange_rate`
- **需要股票代碼**: 否
- **狀態**: ❌ 未下載或失敗
- **索引**: `date`, `currency`
- **唯一鍵**: `date`, `currency`

### ❌ 央行利率資料表

**說明**: 政府公債殖利率

- **Dataset**: `GovernmentBondsYield`
- **Collection**: `government_bonds_yield`
- **需要股票代碼**: 否
- **狀態**: ❌ 未下載或失敗
- **索引**: `date`
- **唯一鍵**: `date`, `duration`

### ❌ 台股相關新聞

**說明**: 個股新聞（近 30 天）

- **Dataset**: `TaiwanStockNews`
- **Collection**: `stock_news`
- **需要股票代碼**: 是
- **狀態**: ❌ 未下載或失敗
- **索引**: `stock_id`, `date`
- **唯一鍵**: `stock_id`, `date`, `title`

---

## 🔌 API 使用統計

- **總調用次數**: 590
- **配額**: 600
- **使用率**: 98.33%
- **剩餘**: 10
