# 規劃 · 紅線元件盤點與 Backlog

> 「紅線元件」＝已棄用、故障、缺失、或有技術債的組件。附優先級 Backlog。

---

## 一、資料層紅線

### 空表（0 筆，但仍被某些程式參照）
`balance_sheet_detail` · `cash_flows_detail` · `financial_statement_detail` · `institutional_holdings` · ~~`shareholding`~~（**✅ 已接 TDCC 免費開放資料**，`tdcc_shareholding_sync.py`，每週）· `industry_price` · `dividend`(空) · `order_statistics_5s` · `total_return_index` · `short_sale_suspension` · `total_credit_limit` · `securities_traders_info`
→ **建議**：確認無下游依賴後 drop，或補資料源。

### 棄用舊表（有資料但不該用）
| 集合 | 問題 | 現用替代 |
|------|------|---------|
| `financial_reports`(204) | 稀疏，多頁誤指向 | `quarterly_earnings`(1984) |
| `financial_statements`(192) | 稀疏 | `quarterly_earnings` |
| `institutional_trading` | 停在 2026-02 | `institutional_flow` |
| `institutional_investors` | 舊 | `institutional_flow` |
| `taiwan_stock_per` | 停在 2026-02 | `stock_factors.pe_ratio` |
| `tickers` / `tickers_legacy` | 舊代碼表 | `taiwan_stock_info` |

### 一次性備份表（應歸檔）
`financial_reports_backup_20260224_163043` · `financial_statements_backup_…` · `taiwan_stock_per_backup_…`

### 舊格式殘留（schema 驗證揪出，2026-07）
`stock_price` 有 **~4,470 筆 2021 年舊格式文件**（主要 5450 等）+ **23 筆 close=null**：
- `close` 存成 float（非 `Decimal128`）、`date` 存成字串（非 `datetime`）、缺 `stock_id`。
- 一批早期匯入未正規化的資料。已由 P3 schema 驗證（warn 模式）標記，不影響運作。
→ **建議**：一次性 migration 把這 4,470 筆轉為正規格式（Decimal128 + datetime + 補 stock_id），之後可考慮把 `stock_price` 驗證器升級為 `error`。診斷指令：
```
db.stock_price.aggregate([{$group:{_id:{$type:"$close"},n:{$sum:1}}}])   # double=4470, null=23
```

---

## 二、程式碼紅線

| # | 元件 | 問題 | 嚴重度 |
|---|------|------|:--:|
| P1 | `src/moe/router.py` (`MoERouter`) | **死碼**：寫舊模型 qwen3.6/deepseek，團隊分析不走它 | 中 |
| P2 | `role_router.py` docstring | 與 `ROLE_TO_MODEL` 程式值不符（宣稱 qwen3/deepseek） | 低（誤導） |
| P3 | RSI 雙公式 | `indicators/rsi.py`(Wilder) vs `momentum_factors`(簡單平均)，輸出用後者 | 中 |
| P4 | value factors 不寫回 | `_TWSE_MANAGED` 攔截，算了白算 | 低 |
| P5 | `scan_pku` risk 恆 None | `market_risk_level` 方法不在 `TradingRules` | 中 |
| P6 | 謝富旭兩套實作 | `hsieh_value`(六條件) vs `hsieh_dividend`(100分制) 門檻不一 | 低 |
| P7 | `morphology.batch_detect` | 未實作 stub，回 0.0 | 低 |
| P8 | OBV volume 欄名 | `indicators/obv.py` 用 `trading_volume`，他處用 `volume` | 低 |
| P9 | 回測費用模型 | 買賣同費率 0.003，未分證交稅 | 低 |

---

## 三、缺失元件（文件記載但檔案不存在於本機 bundle）
> ~~皆已在 `.166` 建立，本機 bundle 缺（版本分歧）。~~ **✅ 已解（2026-07）**：`team_store.py`、`reverify_team.py`、`migrate_team_to_db.py`、`query_team.py` 及新儀表板頁已 pull 回本機，md5 逐檔對齊。**唯版控（git）仍未導入**——同步仍靠人工 md5 比對，見 Backlog P0。

---

## 三之二、已建立的資料完整性防護機制（P0–P3，2026-07 上線）

> 從「被動告警 + 人工補」升級為四層防護。詳見 [運維手冊](規劃-運維手冊-完整度異常處理.md)。

| 層 | 機制 | 元件 | 排程 |
|---|------|------|------|
| P0 可信偵測 | 完整度檢查排除 TAIEX（停擺偵測恢復）+ 時區守衛 | `twse_openapi_sync.py`（`_MARKET_FILTER`, `_check_timezone`）| — |
| P0 真相錨點 | **自適應門檻**：固定母體表門檻＝max(靜態, 近20日中位×0.85)，修正靜態門檻太低漏抓 | `twse_openapi_sync.py`（`_adaptive_min`, `_ADAPTIVE_TABLES`）| — |
| P0 正確錨 | **值合理性檢查**：stock_price OHLC 不變量（結構自洽），抓「筆數夠但值全錯」，逾 5 筆併入 backfill 自癒 | `twse_openapi_sync.py`（`_value_sanity_bad`）| — |
| P0 存活錨 | **看門狗**：各 job 寫心跳，獨立比對排程窗，job 靜默停擺即告警（補「誰看守看守者」）| `watchdog.py` + `system_heartbeat` 集合 | 每日 08:00/14:00 |
| P1 自動修復 | check→自動補→複檢→仍失敗才升級 | `twse_openapi_sync.py --heal` + `backfill_by_date.py` | 週一~五 21:00 |
| P2 主動驗證 | 每日健康快照+趨勢劣化預警；FinMind 外部交叉驗證 | `data_health.py` | 22:00 / 週六 09:00 |
| P3 結構治本 | 核心表 JSON Schema 驗證(warn)；備份可還原性驗證 | `apply_schema_validation.py` · `verify_backup.py` | 已套用 / 週日 04:00 |

> **升級檢視（2026-07）**：從「被動告警＋人工補」到「主動確保完整」再做一輪誠實檢視，補齊三個原缺的「錨」：
> **真相錨**（自適應門檻——measure「對照近期常態」而非「跟昨天一致」）、**正確錨**（值合理性——驗「值對」而非只驗「存在」）、**存活錨**（看門狗——確認守護機制自己活著）。三錨皆已上線。
> 殘留結構限制：看門狗自己也靠 cron，cron 全死則失效——已留 `HEALTHCHECK_URL` 掛勾可接離機 pinger（healthchecks.io）達成真·外部看門狗。

---

## 四、安全紅線（見 [架構特性](架構四面向詳解-2-架構特性.md)）
| # | 問題 | 風險 |
|---|------|------|
| S1 | API/Dashboard 無驗證 | 內網任何人可讀全部分析 |
| S2 | Dashboard 綁 0.0.0.0 + streamlit External URL 顯示公網 IP | 若對外未擋 → 網際網路暴露 |
| S3 | `.env` 明文密鑰 | 密鑰外洩面 |
| S4 | 無 TLS | 明文傳輸 |
| S5 | ~~FinMind token 寫死在 12 個檔案~~ ✅已清（推 GitHub 前掃出並清除、歷史重建）| ⚠️ **建議至 FinMind 後台輪替該 token**（曾明文存在磁碟/舊歷史）|

---

## 五、Backlog（優先級）

### ✅ 已完成（2026-07）
- [x] ~~完整度檢查修好（排 TAIEX，停擺偵測恢復）+ 時區守衛~~（P0）
- [x] ~~自癒機制上線 `--heal` + `backfill_by_date`~~（P1）
- [x] ~~主動監控 `data_health`（趨勢+FinMind 交叉）~~（P2）
- [x] ~~schema 驗證 + 備份可還原性驗證~~（P3）
- [x] ~~三錨補齊：自適應門檻（真相錨）+ 值合理性檢查（正確錨）+ 看門狗（存活錨）~~（P0 升級檢視）
- [x] ~~把 `.166` 新檔 pull 回本機（md5 對齊）~~
- [x] ~~財報頁統一改讀 `quarterly_earnings`~~
- [x] ~~修好 `/etc/timezone` 殘留（三來源一致）~~
- [x] ~~**導入 git 版控**（`.166` `git init`，681 檔初始快照）~~
- [x] ~~**config-as-code**：cron + systemd units 匯出進 `deploy/`（+ 災難復原 README）~~
- [x] ~~**修 runaway log**：`unified_downloader` pymongo DEBUG 灌爆日誌（1.1GB/時、35GB）→ 靜音 pymongo + 清 35GB，磁碟 44G→79G~~
- [x] ~~裝 pytest，測試套件（116 tests）可執行~~
- [x] ~~新增**主力/散戶籌碼研判**指標（`chip_score_scan.py`：法人×融資交叉，排除 ETF，量價共振）~~
- [x] ~~新增**量價×籌碼雙訊號共振**（`dual_signal_scan.py`：雙多/假突破陷阱/量升籌退/雙空/底部潛伏）~~
- [x] ~~加**法人連續買賣超天數**（連續性加權）+ **投信**標記~~
- [x] ~~**接 TDCC 集保股權分散**填 `shareholding` 空表（`tdcc_shareholding_sync.py`，免費、每週；千張大戶佔比整合進 chip）~~
- [x] ~~**接 TWSE 全市場外資持股比例**（`twse_foreign_holding_sync.py` → `foreign_holding`，免費每日；FinMind 免費版全市場被鎖，改走 TWSE MI_QFIIS `selectType=ALLBUT0999`；近5日變化整合進 chip）~~
- [x] ~~**量價補三因子**（`volume_factors`）：均額比 `atv_ratio`(成交金額÷筆數，大單/散單偵測)、周轉率 `turnover`(量÷流通股數)、成交值 `amount`；量價掃描標「均額×」區分主力大單 vs 散戶散單~~
- [x] ~~**修 `backfill_by_date` 漏存 amount/transaction**：P1 自癒經 MI_INDEX 補的日子會掉成交金額/筆數（均額因子失效）→ 已補存兩市場，07-13 回補~~

### P0（影響正確性/安全）
- [ ] **接遠端 repo**（內網 GitLab / GitHub private）+ push；本機 bundle 改 `git clone`（徹底消除人工 md5 同步）— 需決定 host
- [ ] 確認 Dashboard 8501 對外防火牆是否擋（S2）
- [ ] 檢視 `hourly_data_update.sh` 的舊 log 清理為何失效（`LOG_MAX_SIZE_MB=50` 未生效）+ 移除 macOS `/opt/homebrew` PATH 殘留
- [ ] 修 `scan_pku` risk（P5）— 每日選股的市場風控實際失效
- [ ] 分析名單排除下市股（理隆/興航等，虛增 unknown）

### P1（技術債/一致性）
- [ ] 值檢可延伸：把 OHLC 不變量擴到 stock_factors（如 RSI∈[0,100]）、加「單日漲跌逾 ±10% 且非除權息/新股」的可疑跳動計數（軟性、需排除例外）
- [ ] **統一 `margin_purchase_short_sale` 雙 schema**：舊(FinMind：`stock_id`/`MarginPurchaseTodayBalance`，16497 筆歷史) vs 新(TWSE：`code`/`margin_balance`，90121 筆、2026-04 起)。現由 `chip_score_scan` 的 normalizer 相容讀取，但屬「隱性 schema 契約」破裂，宜遷移統一欄位。
- [ ] **清理 stock_price 4,470 筆 2021 舊格式**（float close/字串 date/缺 stock_id）→ 之後 schema 可升 error（一之舊格式殘留）
- [ ] 統一 RSI 公式（P3）
- [ ] 移除死碼 `router.py`（P1）、修正 docstring（P2）
- [ ] 財報 drop 棄用的 `financial_reports`（收尾）

### P2（清理/優化）
- [ ] drop 空表與備份表（一）
- [ ] 回測費用模型加證交稅（P9）
- [ ] value factors 決策：寫回或刪除（P4）
- [ ] API/Dashboard 加基本驗證（S1）
