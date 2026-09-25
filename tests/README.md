# 測試分層策略

本專案測試依「資料相依程度」分三層,對應 CI 的兩道閘門,兼顧**秒級回歸防護**與**整合驗證**。

| 層 | marker | 數量 | 需要 MongoDB? | 在哪跑 |
|---|---|:--:|---|---|
| 純邏輯 | `unit` | 163 | ❌ 完全免 DB | `unit-gate`(無 mongo service)+ `test` |
| 整合(可種子) | `needs_data` | 47 | ✅ 需最小種子資料 | `test`(seed 後執行;無種子→自動 skip) |
| 世界事實/深資料 | `prod_data` | 22 | ✅ 需 live 正式庫 | **不進 CI**,由 .166 排程/手動驗證 |

> 分層已收口:232 測試全數歸位(unit 163 + needs_data 47 + prod_data 22),**無 tier marker 殘留 = 0**。

> `pytest.ini` 已設 `--strict-markers`:用未註冊的 marker 會直接報錯,防止誤標。

---

## 三層定義與判準

### 1. `unit` — 純邏輯,免 DB
純函式或以 fake/注入 DB 測試,**不連任何外部服務**。這是回歸安全網。
- 例:`test_web_search`、`test_evidence_guard`、`test_valuation_eps`(fake `_FakeDB`)、`test_seed_valuation`(mongomock 灘種→估值離線契約)、`TradingRules.position_334`(純數學)。
- 判準:不 import live 連線、不查真實資料;跑得快(整層 < 10 秒)。

### 2. `needs_data` — 整合邏輯,可用最小種子驗證
查 `stock_price` / `stock_factors` 等,但**邏輯類、可用合成資料滿足**(如報酬/beta/週期/風險指標)。
- 例:`test_risk_manager`、`test_trading_rules`(StopLoss/MarketCycle/InstitutionPhase/BuyThreeQuestions)、`test_trading_rules_steps`、`test_valuation`(DCF/DDM/PE Band,守衛式斷言)、`test_valuation_steps`、`test_ranking_steps`(筆數=limit + 分數遞減 + PE 範圍不變式)。
- 機制:`conftest.py` 的 `_guard_needs_data` autouse fixture 檢查 canary(`stock_price` 是否有 `2330`):
  - **有種子** → 正常執行並驗證。
  - **無種子/DB 不可達** → 自動 `skip`(不 fail)。canary 為懶查詢,**不會拖慢純 unit 測試**。

### 3. `prod_data` — 世界事實或深資料,只對 live 庫有意義
斷言「真實世界的事實」或需大規模/多年真實資料,**合成種子造假既脆弱又違反 ADR-0011**。
- 例:`test_data_integrity`(斷言 10 萬+ 筆、新鮮度門檻從 `data_quality.DEFAULT_HEALTH_CONFIG` 單一真相源取,與 data_health 排程共用不漂移)、`test_financial_health`(台積電 grade A / EPS>50 / ROE>10)、`test_peer_comparison`(產業=半導體、同業>10)、`test_stock_ranker`(rank 預設 financial_check)。
- CI 以 `-m "not prod_data"` 排除;應在 .166 真實庫(如 `data_health` 排程)驗證。
- **定期驗證**:`scripts/prod_data_health_report.py --alert`(cron `45 22 * * *`,見 `deploy/crontab.txt`)
  在 .166 真實庫跑 `-m prod_data`,產 `logs/prod_data_report_<date>.md` + 寫 `prod_data_health_history`
  快照,有 fail/error 才發 `schedule_alerts`(網頁🔔可見)。

---

## prod_data 紅燈處置準則(runbook)

⚠️ **關鍵心法**:CI 測試紅燈 = 程式壞了(單一語意);**prod_data 紅燈是三義的**。
切勿反射式改碼或調門檻贋過去 —— 先偵查燈號屬於哪一類:

```
prod_data 某測轉紅
├─ 🔴 程式回歸        → 修 code(和 CI 一樣)
├─ 🌍 世界變了        → 改斷言/門檻(測試編碼了一個過期的事實,如 EPS>50)
└─ 📉 資料管線問題    → 修下載/新鮮度(code 與 test 都沒錯)
```

**三分判別法**(看 `logs/prod_data_report_<date>.md` 的失敗訊息):

| 線索 | 判為 | 處置 |
|---|---|---|
| 訊息含「距今 N 天」、筆數低於門檻、新鮮度/覆蓋類 | 📉 資料管線 | 查 `data_health` 排程、補下載;**不改 code/test** |
| 斷言的是公司數字(grade/ROE/EPS)、產業分類、同業數 | 🌍 世界事實 | 確認真實財報/分類後,**更新測試門檻**(這是正常維護) |
| 前兩者都不是、且迴異於相關 commit | 🔴 程式回歸 | 當 bug 修,**別改測試** |

**重點原則**:
- 🌍 類是「正常維護」—— world-fact 測試的門檻(EPS>50、同業>10)本就會隨真實世界漂移;隨財報季改一次不是技術債,是預期。
- 📉 類切勿用調門檻蒛掉 —— 那只是把壞掉的資料管線藏起來。
- 🔴 類才走 code fix,和 CI 紅燈同樣處理。
- **頻率**:資料基礎建設類每日看(與 data_health 重疊);公司財務類只在**財報季更新後**才有意義地變動 → 日常 smoke、季度重點複核。

---

## 種子資料(讓 `needs_data` 真正執行)

`scripts/seed_test_data.py` 灌入**最小**資料集:

- `stock_price`:10 檔非-ETF 個股(`2330/2317/2454/2603/2412/2308/2881/2882/1301/3008`)+ `TAIEX/0050/0056`,各 120 交易日
  - OHLC 用 **Decimal128**(對齊正式 schema,消費端 `.to_decimal()`)
  - 個股 = 大盤 × 1.0 + 雜訊 → **beta ≈ 1**(落在測試要求的 0.3–3.0)
  - `|日報酬| < 20%`(避開分割/爛價過濾)
- `stock_factors`:12 檔各一筆,**含 `StockRanker.FIELDS` 全部欄位**(`pe_ratio/pb_ratio/dividend_yield/roe/operating_margin/rsi_14/return_1m/volatility_30d`),否則建構期會 `ValueError`。另灌 `2330` 近 36 個月 PE 歷史(讓 PE Band ≥20 筆)。2330 本位 + 其餘 9 檔 → `StockRanker.rank(limit=10)` 能滿 10 筆。
- `quarterly_earnings`:`2330` 8 季正淨利/營收/EPS → DCF `fair_value>0`、`_get_trailing_eps` 可算。
- `taiwan_stock_info`:`2330` 流通股數 → DCF `_get_shares_outstanding`。
- `dividend_detail`:`2330 / 0056` 各 4 年正現金股利 → DDM `fair_value>0`。
- `macro_indicators`(money_supply/interest_rate/cpi/exchange_rate)+ `institutional_flow`(2330 近 5 日外資買超)→ MacroAnalyzer `market_signal()`/`overview()` 可算 → `test_bdd_macro`、`test_cli::test_macro_command`。

**安全護欄**:若 `stock_price` 已有 `> 50` 個 symbol(疑似正式庫)→ 直接拒絕執行,避免誤刪/污染真實資料。

> **離線契約測試**:`tests/test_seed_valuation.py`(marker `unit`)以 `mongomock` 灌入此種子後跑 `ValuationAnalyzer`,將 `test_valuation.py` 的 6 個 `needs_data` 情境「種子後真能算出結果」定型入 DB-free 閘門 — 種子欄位/schema 或估值邏輯任一端漂移都會在 `unit-gate` 秒級被抓。

---

## 常用指令

```bash
# 本地秒級回歸(免 Mongo)—— 提交前必跑
make test-unit                 # 等同 pytest -m unit

# 完整跑(需本機 MongoDB;可先種子)
MONGODB_URI=mongodb://localhost:27017 MONGODB_DATABASE=tw_stock_analysis \
    python scripts/seed_test_data.py
pytest tests/ -m "not slow and not prod_data" -k "not api"

# 只跑某一層
pytest -m needs_data
pytest -m prod_data            # 需連 live 正式庫才有意義
```

## CI 對應(`.github/workflows/ci.yml`)

- **`unit-gate`**:無 mongo service,`pytest -m unit`。純邏輯回歸**秒級攔截**;`test` job `needs: unit-gate`。
- **`test`**:起 `mongo:7.0` → 跑 `scripts/seed_test_data.py` → `pytest -m "not slow and not prod_data" -k "not api"`。
- 另有 `lint / deps-audit / hardcode-gate / secrets` 護欄。

---

## 新增測試時怎麼標?

```
這個測試要連 DB 嗎?
├─ 否 ──────────────────────────────→ @pytest.mark.unit
└─ 是
    ├─ 合成最小資料就能驗證邏輯? ──→ @pytest.mark.needs_data(記得種子能覆蓋所需 symbol/欄位)
    └─ 斷言真實世界事實/需大規模真資料? → @pytest.mark.prod_data(不進 CI 閘)
```

> **必須擇一標記**:CI `unit-gate` 的 **tier-marker gate**(`scripts/check_tier_markers.py`)
> 會擋下任何未標 `unit/needs_data/prod_data` 的測試(以 pytest 自身解析 module/class/function
> 三層 marker)。本機可先跑 `python scripts/check_tier_markers.py` 自查。
