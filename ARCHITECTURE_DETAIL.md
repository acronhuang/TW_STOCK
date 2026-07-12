# 系統架構細部規格 — 台股智能分析系統

> **細部規格書 v1.0** · 反向工程自實際程式碼（`src/`, `scripts/`）+ 實機 DB schema（`172.16.9.166`）
> 本文是 [ARCHITECTURE.md](ARCHITECTURE.md)（概覽）的**細部補充**：函式簽章、演算法、門檻數字、欄位映射、資料契約。給要動程式碼的工程師看。

---

## 0. 版本分歧警告（先讀）

**本機 Windows bundle（`d:\stock_windows_bundle`）與正式機 `.166` 已分歧。** 以下檔案是 2026-07 維運期間在 `.166` 新建/修改，**不在**本機 bundle：

| 檔案 | 狀態 | 影響 |
|------|------|------|
| `src/moe/team_store.py` | 僅 `.166` | 本機 bundle 缺 → `db_upsert_one` 的 import 失敗、DB 雙寫變 no-op（僅 JSON 生效）。`.166` 上正常雙寫。 |
| `scripts/reverify_team.py` | 僅 `.166` | 兩層復驗 |
| `scripts/migrate_team_to_db.py` | 僅 `.166` | JSON→DB 灌庫 |
| `scripts/query_team.py` | 僅 `.166` | 團隊分析 CLI 查詢 |
| `dashboard/pages/{team,picks}.py` | 僅 `.166` | 新儀表板頁 |
| `dashboard/pages/{monitor,financials,charts,home,backtest_viz}.py` | `.166` 已修 | Mac 殘留/指錯表修正 |

> **結論**：以 `.166` 為權威運行版本。若要同步，需把 `.166` 的變更拉回本機 bundle。

---

## 1. 部署與模型（校正版）

| 節點 | env | 實際模型（以 `ROLE_TO_MODEL` 程式碼為準） |
|------|-----|------|
| `.28` | `OLLAMA_URL=http://172.16.9.28:11434` | `qwen2.5-14b:latest`（技術/基本面/顧問）、`qwen2.5-3b:latest`（總經/風險） |
| `.27` | `OLLAMA_CONSENSUS_URL=http://172.16.9.27:11434` | `hermes3:8b`（價值/籌碼 + 合議委員）、`qwen2.5-3b:latest`（合議委員） |

> ⚠️ **文件/程式碼不一致**：`role_router.py` 的檔頭 docstring 與 `router.py`（舊 `MoERouter`/`EXPERTS`）仍寫 `qwen3:8b` / `deepseek-r1:14b` / `qwen3.6:27b`，**與實際 `ROLE_TO_MODEL` 不符**。團隊分析走 `role_router.ask_role`，**不走** `router.MoERouter`（後者為死碼）。一律以 `ROLE_TO_MODEL` 程式值為準。

`ask_role()` 呼叫 Ollama：`POST {url}/api/generate`，body `{model, prompt, stream:False, keep_alive:'5m', options:{num_gpu:99}}`（強制全層 GPU）。合議 `_ask` 另加 `temperature:0.3`。

---

## 2. 資料契約（實機 DB schema）

DB `tw_stock_analysis`。價格/金額欄一律 `Decimal128`；因子/比率為 `float`。

### 2.1 `stock_price`（唯一索引 `(stock_id,date)`、`(symbol,date)`）
```
stock_id str · symbol str · date datetime · updated_at datetime · data_source str
open/high/low/close/max/min Decimal128 · adj_close Decimal128 · adjustment_factor Decimal128
volume/Trading_Volume Decimal128 · Trading_money Int64 · amount · spread float
market_cap · turnover_rate       ← market_metrics_calculator 寫回
```
**4 個寫入源**：twse_daily_update（TWSE/TPEX OpenAPI）、macro_sync（FinMind TAIEX，`symbol='TAIEX'`）、unified_downloader（FinMind `TaiwanStockPrice`）、backfill 腳本。去重鍵 `{stock_id,date}`（TAIEX 用 `{symbol,date}`）。

### 2.2 `stock_factors`（索引 `(symbol,date)`）— 18 因子
```
symbol str · date datetime · updated_at datetime
# 由 twse_daily_update 直寫（float，TWSE 官方管理，_TWSE_MANAGED 攔截不被覆蓋）：
pe_ratio · pb_ratio · dividend_yield · earnings_yield
# 由 momentum_factors 寫：
return_1m/3m/6m/12m · rsi_14 · volatility_30d · ma_bias_20/60/120/240 · ma_above_long · ma_long_trend · foreign_streak · trust_streak
# 由 quality_factors 寫：
roe · roa · profit_margin · operating_margin · current_ratio · debt_ratio
# 由 volume_factors 寫：
volume_ratio · vol_pct_60d · obv_slope · vp_divergence · vol_state
```

### 2.3 `quarterly_earnings`（唯一索引 `(symbol,year,season)`）— 巢狀
```
symbol str · year int · season int · report_type '合併' · data_source · updated_at
income   dict{ revenue, operating_income, net_income, eps, operating_margin, net_margin, gross_margin, unit_fixed }
balance  dict{ cash, accounts_receivable, inventory, current_assets, ppe, total_assets,
               current_liabilities, long_term_debt, retained_earnings, equity_parent,
               total_liabilities, total_equity, roe }
cashflow dict{ }   ← 目前空
```
**單位陷阱**：`twse_quarterly_sync.normalize_income` 把 t187ap14 的「千元＋累計 YTD」轉「元＋單季」（season>1 減同年前季，湊不齊則寫 None），標 `unit_fixed=True`。

### 2.4 `institutional_flow`（三大法人 T86，實際使用表）
```
stock_id str · date datetime · data_source('TWSE_T86'/'TPEX_3INSTI')
foreign_net · trust_net · dealer_net · total_net   全 Decimal128（單位：股）
```
> 舊表 `institutional_trading`（停 2026-02）、`institutional_investors` 皆棄用。

### 2.5 `taiwan_stock_info`
```
stock_id str · stock_name str · industry_category/l1/l2 str · security_type('Stock')
type('twse'/'tpex') · outstanding_shares float(千股，用時×1000) · date str · updated_at
```

### 2.6 `team_analysis`（`.166` · 索引：`(symbol,date)` uniq、`(date,final_verdict)`、`(date,verify.status)`）
```
symbol str · name str · date datetime · source_file str · created_at/updated_at
reports  dict{ macro-analyst, technical-analyst, fundamental-analyst, value-analyst, risk-manager, chip-analyst }
evidence list[ {metric,db,live,source,flag} ]
advisor  str|null            ← phase2 顧問草案
consensus dict{ votes:[{model,vote,reason}], tally:{買進,持有,賣出}, final, n, dissent }|null
final_verdict str|null       ← _verdict(advisor)
price_at_analysis number|null
verify dict{ status:fresh/stale/unknown, truth_close, checked_at,
             finmind:{finmind_close, db_close, match, ref_date, checked_at} }
senvision list · extra dict · updated_at
```

### 2.7 其他核心
- `monthly_revenue`：`symbol,year_month,revenue,mom_growth,yoy_growth,cumulative_*` 等。
- `macro_indicators`：`indicator('interest_rate'/'cpi'/'money_supply'/'leading'/'exchange_rate'),date,data{}`。
- `dividend_detail`：`stock_id,year,cash_earnings_distribution(Decimal128),cash_ex_dividend_date,...`。

---

## 3. 子系統一：資料擷取

MongoDB 統一 `mongodb://localhost:27017/tw_stock_analysis`。

### 3.1 `twse_daily_update.py`（每日股價/籌碼/PE，7 fetch + 3 upsert；CLI `--date --dry-run --no-tpex --no-institutional --no-peratio`）

| 函式 | 來源 URL | collection | 去重鍵 | data_source |
|------|----------|-----------|--------|-------------|
| `fetch_twse` | `openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL` | stock_price | `{stock_id,date}` | TWSE_OpenAPI |
| `fetch_tpex` | `www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes` | stock_price | `{stock_id,date}` | TPEX_OpenAPI |
| `fetch_twse_institutional(date)` | `www.twse.com.tw/rwd/zh/fund/T86?date=YYYYMMDD&selectType=ALLBUT0999` | institutional_flow | `{stock_id,date}` | TWSE_T86 |
| `fetch_tpex_institutional` | `www.tpex.org.tw/openapi/v1/tpex_3insti_daily_trading`（須帶 UA） | institutional_flow | `{stock_id,date}` | TPEX_3INSTI |
| `fetch_twse_peratio` | `openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL` | stock_factors | `{symbol,date}` | TWSE_BWIBBU |
| `fetch_tpex_peratio` | `www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis` | stock_factors | `{symbol,date}` | TPEX_PERATIO |

- 股價欄映射：`Code→stock_id/symbol, Date(ROC7)→date, Opening/Highest/Lowest/ClosingPrice→open/high/low/close(+adj_close), TradeVolume→volume, TradeValue→amount`。全走 `_to_dec()`→Decimal128。`close is None`（停牌）跳過。
- 法人（T86，固定索引）：`row[4]→foreign_net, row[7]→trust_net, row[10]→dealer_net, row[11]→total_net`。
- PE/PB：`_to_f`→float（**非 Decimal128**）；`PEratio→pe_ratio, PBratio→pb_ratio, DividendYield→dividend_yield`；**只 `$set` 非 None 欄位**（不覆寫既有因子）。
- 轉換：`_roc_to_date('1150224')→datetime(2026,2,24)`；`_to_dec` 去千分位/`+`，空值→None。

### 3.2 `twse_openapi_sync.py`（13 補充表 + 完整度檢查；`BASE=openapi.twse.com.tw/v1`）

13 個 `sync_*` 函式逐筆 `update_one(upsert=True)`。代表：`sync_after_hours`(`/exchangeReport/BFT41U`→after_hours_trading)、`sync_margin_trading`(`/exchangeReport/MI_MARGN`→margin_purchase_short_sale)、`sync_major_news`(`/opendata/t187ap04_L`→major_news `{code,date,subject}`)、`sync_foreign_top20`(`/fund/MI_QFIIS_sort_20`→foreign_top20)、`sync_etf_rank`(`/ETFReport/ETFRank`→etf_dca_rank)、`sync_securities_lending`(`/SBL/TWT96U`→securities_lending `{twse_code,date}`)、`sync_odd_lot`(`/exchangeReport/TWT53U`)、`sync_day_trading`(`/exchangeReport/TWTB4U`)、`sync_punish`、`sync_notice`、`sync_major_shareholders`、`sync_insider_transfer`、`sync_margin_suspension`。

**完整度檢查 `check_integrity(db)`**（`TABLE_CHECKS` = `(最低筆數, 容許落後交易日)`；參考日=stock_price 最新 date；落後以交易日計）：

| collection | 最低筆數 | 落後 | | collection | 最低筆數 | 落後 |
|---|--:|:--:|---|---|--:|:--:|
| stock_price | 4000 | 0 | | odd_lot_trading | 800 | 0 |
| stock_factors | 1800 | 0 | | major_news | 1 | 4 |
| institutional_flow | 800 | 1 | | punished_stocks | 0 | 5 |
| margin_purchase_short_sale | 800 | 0 | | foreign_top20 | 20 | 0 |
| day_trading_targets | 800 | 0 | | etf_dca_rank | 10 | 0 |
| securities_lending | 800 | 0 | | margin_suspension | 10 | 4 |
| after_hours_trading | 1000 | 0 | | | | |

`PIPELINE_STALE_DAYS=5`：stock_price 最新日落後今日 >5 日曆天 → 判 pipeline 停擺。`--check-only` 發 LINE。

### 3.3 `macro_sync.py`（總經；CLI `--set-cpi/--set-rate/--set-m1b/--set-m2/--set-signal*`）
- `sync_taiex`：FinMind `TaiwanStockPrice/TAIEX`（需 token）→ stock_price `{symbol:'TAIEX',date}`，`data_source='FinMind_TAIEX'`。
- `fetch_bot_usd`：台銀 `rate.bot.com.tw/xrt/flcsv/0/L6M/USD`（免金鑰）→ macro_indicators `exchange_rate{usd_twd,change_1m}`。
- 月頻 SEED（`--set-*` 覆寫）：`interest_rate.discount_rate=2.000`、`cpi.yoy=2.20`、`money_supply.m1b_yoy=8.25/m2_yoy=6.45`、`leading.signal_score=39/紅燈`。

### 3.4 `twse_quarterly_sync.py`（季報 EPS；`{symbol,year,season}` unique）
上市 `openapi.twse.com.tw/v1/opendata/t187ap14_L`、上櫃 `www.tpex.org.tw/openapi/v1/mopsfin_t187ap14_O`。`normalize_income` 千元累計→元單季（見 §2.3）。`$set` 只更 income，`$setOnInsert` 設 balance/cashflow/report_type。

### 3.5 `unified_downloader.py` → `download_coordinator.py` → `finmind_client.py` + `table_config.py`（FinMind 43 表）
- CLI：`--all`/`--categories 技術面,基本面,籌碼面,衍生性商品,其他`/`--no-skip`。需 `FINMIND_API_TOKEN`。
- `FinMindClient`：base `api.finmindtrade.com/api/v4/data`；配額 600/hr；429 重試（max 3, backoff×2）；`_convert_to_decimal128` 轉數值欄。
- `table_config.DATA_TABLES` 5 類；每表 `{dataset,collection,unique_keys,needs_symbols,batch_size}`；`needs_symbols=True` 逐股下載（`batch_size` 誤用為股數上限）。
- **啟用表**：TaiwanStockInfo→taiwan_stock_info、TaiwanStockPrice→stock_price、TaiwanStockMarginPurchaseShortSale、TaiwanStockSecuritiesLending、TaiwanStockDividend→dividend_detail、TaiwanStockMonthRevenue、GoldPrice、期權 6 表等。
- **已 disabled**（原因）：TaiwanStockPER（由 daily_update 直寫取代）、財報三表（由 financial_reports 取代）、TaiwanStockInstitutionalInvestors（由 T86 取代）、CrudeOilPrices/ExchangeRate/GovernmentBondsYield/TaiwanStockNews（FinMind API 已移除，HTTP 400）。

---

## 4. 子系統二：分析引擎

### 4.1 `src/factors/`（寫 stock_factors，唯一索引 `(symbol,date)`）

**`FactorLibrary`**（`factor_calculator.py`）統一介面：`calculate_all_factors(symbol,date)`、`calculate_and_store(symbols,start,end,factor_types,batch_size=100)`、`get_factors`、`get_cross_section`、`calculate_factor_stats`。寫入排除 None，且 `_TWSE_MANAGED={pe_ratio,pb_ratio,dividend_yield,earnings_yield,data_source}` **不被覆蓋**（→ value_factors 算的 PE/PB 實際不寫回）。

**`MomentumFactors`**（輸入 stock_price.adj_close、institutional_flow）：

| 欄位 | 公式 |
|---|---|
| `return_1m/3m/6m/12m` | `(P_end-P_start)/P_start×100`，回溯 30/90/180/365 天 |
| `rsi_14` | `100-100/(1+RS)`，RS=近14日 **簡單平均** gains/losses（**非 Wilder**） |
| `volatility_30d` | `std(日報酬)×√252×100`，window=30 |
| `ma_bias_20/60/120/240` | `(close-MA_N)/MA_N×100` |
| `ma_above_long` | 站上幾條長均(60/120/240)，0~3 |
| `ma_long_trend` | 1=長多(60>120>240)/−1=長空/0=糾結 |
| `foreign_streak`/`trust_streak` | 外資/投信連續買賣超天數（±N），lookback=40 |

**`QualityFactors`**（財報三層 fallback：quarterly_earnings → financial_statements → financial_reports）：`roe/roa=淨利÷權益或資產×100`、`profit_margin/operating_margin`、`current_ratio`、`debt_ratio=負債÷資產×100`。

**`ValueFactors`**（多被 _TWSE_MANAGED 攔）：`pe=price/EPS`（EPS=淨利/(股數×1000)，0<PE<1000）、`pb=price/每股淨值`、`dividend_yield=前年配息/price×100`、`earnings_yield=1/PE×100`。

**`VolumeFactors`**（最精緻；常數 VOL_MA=20/VOL_PCT=60/PIVOT_K=3/CAP_VOL_PCT=88/CHOKE_RATIO=0.12）：`volume_ratio`(量比)、`vol_pct_60d`(量能百分位)、`obv_slope`(OBV 20日回歸斜率÷均量)、`vp_divergence`(−1/0/+1 底/頂背離：兩擺動低點 c↓但 obv↑)、`vol_state`(0無/1絕望量/2鎖籌/3窒息量)。

### 4.2 `src/indicators/`（純函式吃 DataFrame，不碰 DB）
- `ma.py`：SMA `MA_{5,10,20,60,120,240}`、EMA `{12,26}`、交叉、支撐壓力。
- `kd.py`：`RSV=(close−LLV9)/(HHV9−LLV9)×100`，K/D 用 EMA(span=5,α=1/3)。訊號 overbought=80/oversold=20。
- `bollinger.py`：中軌MA20±2σ，`BB_Width`、`BB_Percent(%B)`；squeeze<10；近125日最小=squeeze_on。
- `rsi.py`：**Wilder EMA**（α=1/period）— ⚠️ 與 momentum_factors 的簡單平均版**公式不同**，stock_factors.rsi_14 來自後者。
- `macd.py`：DIF=EMA12−EMA26、DEM=EMA9、Histogram。
- `obv.py`：漲+量跌−量；⚠️ volume 欄預設名 `trading_volume`（與別處 `volume` 不同）。

### 4.3 `src/morphology/`（第一代規則式，score 0~1；權重總和=1）
`PatternDetector` 整合 5 偵測器（`batch_detect` 為未實作 stub）：
- **破底翻**：支撐=low.rolling(20).min；跌破→5日內收復×1.02+量×1.5。score=收復×0.4+量×0.4+價×0.2。
- **雙底 W**：argrelextrema(order=5)找低點；間隔10~40天，第二底≥第一底×0.98，突破頸線×1.03+量×1.5。目標=頸線+(頸線−底)。
- **頸線突破**：頸線=high.rolling(60).max；close>頸線×1.03+振幅>0.03+量×2.0+連2日確認。
- **量能突破/量價背離**。
- `PatternScorer` 權重：破底翻0.30/W底0.30/頸線0.25/量能0.10/均線0.05。評級 A≥0.8…F<0.2。

### 4.4 `src/senvision/`（第二代 ZigZag+多框架，score 0~3.6，**主力**）
- `Pattern` dataclass（neckline/target/stop_loss/risk_reward_ratio/confidence/key_points）；`PatternType` Enum 12+ 型態。
- 4 偵測器（W底/M頭/三重底/三重頂）+ pattern_bridge 12 神招；`_compute_confidence` 基礎0.35→突破/量能/RRR/對稱加分，夾0.20~0.95。RRR 用**頸線當 entry**。
- `multi_timeframe.TIMEFRAME_CONFIG`：D(閾0.05)/W(0.08)/M(0.10)/Q(0.12)/6M(0.15)/Y(0.20)。
- **`score_signal()` 綜合評分 0~3.6**：技術(confidence 1.0+量0.15+RRR0.15+切線0.12+S/R0.08+均線0.10+KD0.10+%B0.08+RSI0.08) + 基本面(PER0.08+營收YoY0.10+ROE0.08) + 籌碼(法人0.12+外資連買0.05) + 量價(量比0.06+OBV0.06+背離±) + 多框架confluence(0.12) + `_TF_BONUS`(D0~Y0.25)。輸入來自 stock_factors/monthly_revenue/institutional_flow。

### 4.5 `src/calculators/`（寫回 stock_price，Decimal128，`--dry-run/--execute`）
- `adj_close_calculator_atomic`：讀 dividend_detail，**由最新往回推** adj_factor（現金 `×(close−現金)/close`、配股 `×10/(10+配股)`）→ 寫 `adj_close=close×factor`、`adjustment_factor`。
- `market_metrics_calculator`：`market_cap=close×股數`、`turnover_rate=volume/股數×100`（股數=info.outstanding_shares×1000）。

### 4.6 `financial_health.py`（`FinancialHealthAnalyzer`，6維健檢，全市場1963支）
資料：quarterly_earnings 近8季 TTM（需≥3季）+ financial_statements + stock_factors。

| 維度 | 權重 | 內容 |
|---|--:|---|
| profitability | 0.25 | net/operating/gross margin |
| growth | 0.20 | revenue/net_income/eps YoY（TTM vs 前4季）|
| safety | 0.20 | 負債比↓/流動比/獲利季數 |
| efficiency | 0.10 | 資產週轉 revenue/total_assets |
| quality | 0.15 | ROE+ROA |
| value | 0.10 | PE↓/PB↓/殖利率↑ |

`total=Σscore×weight`；評級 A+≥85…**F<25(地雷)**。**杜邦**：`ROE=淨利率×資產週轉×權益乘數`。地雷警示：4季虧損/負債>80%/流動比<1/淨利率<0/營收YoY<−15% 等。

---

## 5. 子系統三：決策策略與回測

### 5.1 `daily_recommendations.py`（四法選股，每日17:30，發5則LINE）

**法一 `scan_factor_ranking(60)`**：`StockRanker.rank(60)` + 交叉驗證，**全條件成立**：total_score≥70、風險∈{低,中}、upside>0、財報健康≥60、真實PE=price/trailing_eps 落在 **3<PE<25**。排序 `(sharpe≤0,−upside)`。

**法二 `scan_senvision()`**：讀 `results/scan_auto_*.csv`（非即時）；狀態='剛突破' 且型態∈{W-Bottom,HS-Bottom,Triple-Bottom,Triangle-Up,Flag-Rising}；財報≥60、風險≠極高；排序 −pat_score 取前15。

**法三 `scan_hsieh()`**：`HsiehValueScreen.screen(top=15)`（見 §5.3）。

**法四 `scan_pku()`**：`TradingRules.market_cycle()`；⚠️ `market_risk_level` 恆 None（方法不在 TradingRules）。

**`cross_reference`**：以 sym 合併三法，`sources≥2` 為「多策略共同推薦」，排序 `(−len(sources),sym)`。北大不參與（大盤層級）。

### 5.2 `stock_ranker.py`（六因子）
權重：value0.25/quality0.20/momentum0.15/safety0.15/institutional0.15/growth0.10。計分：value(PE/PB百分位↓+殖利率↑)、quality(健檢 profitability×0.5+quality×0.3+safety×0.2)、momentum(RSI靠50最高+月報酬百分位)、safety(波動度百分位↓)、institutional(近10天外資+投信：皆正80/一正65/皆負20/一負35)、growth(月營收YoY)。`rank()` 排除ETF、FinancialFilter 剔地雷。等級 A≥75…D<45。

### 5.3 謝富旭存股（**兩套實作**）
**`hsieh_value.py`（日腳本採用）**六條件全過：負債比<60%、流動比>100%、保留盈餘/股本≥2.0、營益率抗跌、殖利率≥4%、連續配息≥3年。流動性≥300張/日。
**`hsieh_dividend.py`（100分制）**：獲利25+安全25+配息20+估價20+抗壓10，≥50入選；估價四區間(便宜≥8%殖利率→20分…昂貴<5%→3分)；連配≥5年。

### 5.4 北大法則 `trading_rules.py`
**四季 `market_cycle()`（0050近60日）**：冬藏(ma5<ma20<ma60,ret20<−5→倉0-10%)/春播(ma5>ma60,ret20<3,vol<1.2→20-30%)/秋收(ma5>ma20>ma60,ret20>5,vol>1.3→20-30%)/夏長(ma5>ma20,ret20>0→50-70%)。**買入三問**：Q1漲(return_1m>−5)/Q2誰買(foreign_net>0)/Q3還能漲(RSI<70)。**止損**：<cost×0.95無條件/破MA60/均線空頭。

### 5.5 `agan.py`（阿甘投資法）
`agan_market_signal`：國發會信號分數 9~45 → 藍/黃藍/綠/黃紅/紅燈擇時。`AganMoatScreen`（護城河龍頭）：市值前200、ROE(TTM)≥15%、負債<50%、連配≥5年。

### 5.6 回測 `src/backtesting/`
**`Backtest.run()`**：load_data(stock_price→float) → 逐交易日{historical_data=date≤current → strategy.generate_signals → _execute_signals → record_equity} → PerformanceCalculator。`_execute_signals`：BUY 用 cash×0.2，`shares=int(pv/price/1000)×1000`（整張）；SELL 全出；單標的單部位。預設 cash=1M/position_size=0.2/commission=0.003。

**三策略 `generate_signals`**：MA交叉(5/20 黃金→BUY)、RSI(14,<30→BUY/>70→SELL)、ValueMomentum(PE<15且mom>0→BUY/PE>30或mom<−10→SELL)。

**`PerformanceMetrics`**（rf=1%,252日）：總報酬、年化`(final/init)^(1/years)−1`、波動`std×√252`、最大回撤`min((eq−cummax)/cummax)`、Sharpe、Sortino(下檔σ)、Calmar(年化/|MDD|)、勝率、獲利因子(Σwins/|Σlosses|)。交易配對 FIFO。

**`Portfolio`**：買賣兩邊同費率0.003（未分證交稅）；加倉重算加權均價；`record_equity=cash+Σmarket_value`。

---

## 6. 子系統四：MoE 團隊分析

### 6.1 角色路由 `role_router.py`
`ROLE_TO_MODEL`（11 角色，實值）：investment-advisor/technical/fundamental/stock-team-orchestrator→`qwen2.5-14b`；value/chip→`hermes3:8b`；risk/macro→`qwen2.5-3b`；coder→`qwen2.5-coder:7b`；embed→`nomic-embed-text`；tw-polish→`llama-3-taiwan:8b`。`MODEL_TO_URL`：qwen→.28、hermes3→.27。`ask_role(role,question,include_role_prompt=True,timeout=300)`。`ROLE_PROMPTS` 8 個分析角色（fundamental 不做估值、value 做DCF/DDM/PE Band、risk 給VaR/Sharpe/Beta、advisor 要張數/進場/停損/目標/持有期）。

### 6.2 合議 `consensus.py`
`COMMITTEE=[hermes3:8b, qwen2.5-3b:latest]`（皆.27，temp0.3）。`VOTES=(買進,持有,賣出)`。`_SYNONYM` 順序賣>買>持（避免「不建議買進」誤判）。
**`deliberate(symbol,name,advisor_draft,data_summary)`**：
1. 委員 prompt（草案+關鍵數據，規則「首行只寫買/持/賣，次行理由」）。
2. 逐委員 `_ask`→`_extract_vote`（首行→全文）；理由跳過純票別/純標題行（`【…】`），截60字。
3. `tally`計票；`final`：無有效票→`_advisor_rating(草案)or持有`；唯一領先→leaders[0]；**平手→草案評級(若在平手選項)否則持有**。
4. 回 `{votes,tally,final,n,dissent}`。

### 6.3 主編排 `team_daily_verified.py`
`ANALYST_ROLES`(6，不含advisor)。`analyze_symbol(symbol,quick)`：
1. `fetch_all_data`（打本地API:8888 的9端點）
2. `verify_metrics`（FinMind複核，額度25檔）
3. `senvision_patterns`（scan_auto CSV 取前4）
4. `_ma_inst_extra`（MA乖離+法人連續）
5. 6角色迴圈（technical 追加蔡森；追加 EVIDENCE_SUFFIX；timeout300）
6. `not quick`→顧問整合（timeout600）
7. `_consensus_for`→合議

**verify_metrics 複核4項**：收盤(stock_price.close vs FinMind TaiwanStockPrice, tol **3%**)、本益比(stock_factors.pe_ratio vs TaiwanStockPER, tol **5%**)、殖利率(tol **5%**)、法人10日淨(僅DB)。flag：`✅`/`⚠️背離`/`⚠️DB缺`/`📁本地`/`📊`/`—無資料`。

**phase1**：逐檔 analyze_symbol → save_results（逐檔存JSON可續）→ db_upsert_one。`--quick` 省顧問。
**phase2 `--phase2`**：load_results → 對缺advisor者只 run_advisor + _consensus_for → 存檔/雙寫（**不重跑6角色**）。
**`--date`** 解跨午夜/時區；load 找不到當日檔退回最新一份。
**`_verdict(advisor)`** 三段回退抽「評級：X」（修掉「條件式買進」蓋掉的舊bug）。

### 6.4 完整資料流（一檔）
```
選股(tier/industry50/all/--symbols)→ analyze_symbol:
  fetch_all_data(API:8888) + verify_metrics(FinMind) + senvision(CSV) + _ma_inst_extra
  → 6角色 ask_role(macro/risk→3b@.28, tech/fund→14b@.28, value/chip→hermes8b@.27)
  → [not quick] advisor 整合(14b@.28,600s,產「評級：X」)
  → _consensus_for → deliberate(委員@.27 投票→tally→final)
  → {symbol,evidence,reports,advisor,senvision,extra,consensus}
  → save_results(JSON) + db_upsert_one(team_analysis)
  → build_line → LINE(>4500字分段)
```

---

## 7. 跨系統發現與工程注意

1. **RSI 雙公式**：indicators/rsi.py=Wilder EMA；factors/momentum_factors.py=簡單平均。stock_factors.rsi_14 用後者。
2. **value factors 不寫回**：`_TWSE_MANAGED` 攔截 pe/pb/殖利率/earnings_yield。
3. **兩代形態引擎**：morphology(規則,0~1) vs senvision(ZigZag,0~3.6，主力)。
4. **謝富旭兩套**：hsieh_value(六條件,日腳本用) vs hsieh_dividend(100分制)，門檻略異(連配3 vs 5年)。
5. **scan_pku risk 恆 None**：market_risk_level 方法不在 TradingRules。
6. **回測簡化**：買賣同費率0.003未分證交稅、單標的單部位、SELL全出。
7. **文件/程式不一致**：role_router docstring 與 router.py 寫舊模型(qwen3/deepseek/qwen3.6)，實際用 qwen2.5+hermes3。router.py MoERouter 為死碼。
8. **持久層本機缺失**：team_store/reverify/migrate/query 僅在 .166（見 §0）。
9. **單位**：outstanding_shares 千股(×1000)；季報 income 需 normalize 為元單季；institutional 單位股(÷1000=張)。
10. **Token 依賴**：僅 FinMind 路徑(unified_downloader/macro_sync TAIEX/verify_metrics)需 FINMIND_API_TOKEN；TWSE/TPEX OpenAPI + 台銀匯率免token。

---

*本細部規格由 4 個平行深挖 agent 讀實際程式碼 + 實機 DB schema 反向工程而成。演進時請同步更新。*
