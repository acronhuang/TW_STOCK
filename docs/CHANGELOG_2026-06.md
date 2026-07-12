# 異動清單 — 2026-06（量價分析 + 角色資料稽核 + E2E）

本次 session 的所有改動。分：新增 scripts、修改檔案、排程、一次性資料操作、模型、memory。

---

## 【2026-06-19 增補】OBV 真底背離 + 三重共振選股

- **偵測升級**：`src/factors/volume_factors.py` `vp_divergence` 由「頭尾淨變化」改為**真擺動低/高點背離**
  (`detect_obv_divergence`：60日窗 pivot 比對，價更低低點+OBV抬高低點+現價區間下半；obv_hl 以視窗振幅正規化)。
  掃描多背/空背標籤、score_signal、團隊量價顯示自動變準(下次因子計算生效)。
- **回測驗證**(`scripts/backtest_obv_divergence.py`)：單一底背離當買進**無 edge**(跑輸基準)；
  唯「**OBV底背離 ∩ 蔡森底型態 ∩ 尚未反彈**」三重共振有 edge → 20日超額+3%、勝率74%(n=27偏小)。
- **每日掃描**：`scripts/obv_bottom_divergence_scan.py` + 排程 `com.twstock.daily_obv_divergence`(週一~五 18:05)→LINE。
- **排程清理**：修復 `weekly_outstanding_shares`(plist `&` 未跳脫→無法載入,已修+立即補抓股數,原停在3/22)；
  移除一次性 `backfill_331`(3/31已補齊,移到 `_disabled/`)。目前 18 個 com.twstock.* 排程。
- **量價框架狀態(絕望量/窒息量/鎖籌)**：依使用者量價框架補 `VolumeFactors.detect_capitulation/detect_choke/`
  `detect_chip_lock/volume_state`，存數值碼 `vol_state` 並串入 scanner `_volume_state_label`。
  回測(`backtest_volume_states.py`)三者單獨買進**皆無 edge**(絕望量20日-5.4%超額)→ 僅作**情境標籤**,
  不接評分/不單獨選股(呼應框架「背離須等確認+多重驗證」)。「鎖籌誤殺」風險經 OBV 位置守衛已解。
  注意：框架『絕望量(價跌量增)』與 OBV 底背離(價跌量縮、賣壓衰竭)是**相反**的兩種落底機制。

## 【2026-06-19 增補】資料缺口稽核 + 補齊(A) + 查證層治本(B)

- **稽核**(活躍1980檔)：發行股數56%、PE73%、殖利率89%、月營收53%、法人54%、財報9%。
  **關鍵認知**：法人缺892檔多為**興櫃無三大法人申報**(歷史0筆)、財報受**FinMind免費版上限~200檔**、虧損股無PE
  → **這些本來就補不了**，非管線缺失。真可補的只有發行股數、月營收。
- **B 查證層治本**(`team_daily_verified.py`)：團隊分析 `ℹ️未查證` 痛點根因是**50檔即時打FinMind爆配額**(非DB缺)。
  改**本地DB優先 + FinMind節流抽查**(`_FM_AUDIT_QUOTA=25`/run)；查不到標 `📁本地`(非警示)。
  `_evidence_ok` 改顯示**資料完整度**(本地有值=「佐齊」)。驗證：50檔中 46 檔「齊」(原本半數未查證)。
- **A master 補齊**(`scripts/master_backfill.sh`，背景節流)：[1]發行股數 `--all`(真缺~850檔) [2]月營收近3月。
  各工具自帶 600/hr 節流，跑數小時自動完成。發行股數已 1128→1217 進展中。
  注意：補不了的(法人興櫃/財報FinMind上限/虧損股無PE)不在此列。
- **上櫃(tpex)三大法人修復**：稽核更正——缺法人 882 檔**不是興櫃(只31檔)，是上櫃**！根因：
  `twse_daily_update.py fetch_tpex_institutional` 的 TPEX 端點 `tpex_buysell_sec_date` **已失效(302轉址)**。
  改用新端點 `https://www.tpex.org.tw/openapi/v1/tpex_3insti_daily_trading`(需瀏覽器UA;民國日期;
  欄位 `...-Difference`/`TotalDifference`)。**上櫃法人覆蓋 0%→90%**(當日818/902)。
  每日17:00 daily_senvision→twse_daily_update 自動續抓。**限制**：新端點僅最新日,歷史日需另用FinMind回補。
- **月營收+發行股數改用免費官方 OpenAPI(取代FinMind配額瓶頸)**：FinMind 免費版整批回補跑不動(實測月營收0進展)。
  改抓官方 OpenAPI(整批全市場、不耗配額)：
  - `sync_revenue_openapi.py`：上市 `t187ap05_L` + 上櫃 `mopsfin_t187ap05_O` → monthly_revenue。月營收 **53%→99%**(1972筆)。
  - `sync_shares_openapi.py`：上市 `t187ap03_L`(已發行普通股數) + 上櫃 `mopsfin_t187ap03_O`(IssueShares)÷1000(千股)
    → taiwan_stock_info.outstanding_shares。發行股數 **59%→99%**(1980檔)。
  - **驗證正確**：2330月營收與FinMind吻合(千元)且更新更快(有5月)；發行股數 API/DB=1000 單位一致;1240茂生244093千元精準對上。
  - 排程改指 OpenAPI：`monthly_revenue_sync`→sync_revenue_openapi；`weekly_outstanding_shares`→sync_shares_openapi。
  - **教訓**：能用免費官方 OpenAPI(TWSE/TPEX/MOPS)整批抓的,就別用 FinMind 逐股(配額限制+慢)。需UA、民國日期、欄位中英混。
- **財報資產負債表+ROE 改用 OpenAPI**：真缺口是 `quarterly_earnings.balance` **全空**(income齊但無權益→ROE 0%)。
  `sync_balance_openapi.py` 抓 `t187ap07_L_*`(上市)+`mopsfin_t187ap07_O_*`(上櫃) 各行業變體(ci/ins/bd/fh/basi/mim)，
  fallback 涵蓋「資產總額/總計」「權益總額/總計/歸屬母公司權益合計」(代號 公司代號/SecuritiesCompanyCode)，
  灌 balance(權益/資產/負債,千元→元) + 算 **ROE=淨利×(4/季)/權益×100**(年化)。寫進 quarterly_earnings.balance。
  - **驗證正確**：台積電 ROE **38.62%**(對上既有38.28)、富邦金12.97%(金控)、環球晶8.12%(上櫃)。**ROE 0%→99%**(1968檔)。
  - quality_factors.calculate_roe 直接讀到；接進 `quarterly_earnings_sync.sh`(income後)。stock_factors.roe 待下次因子計算補。
  - 註：income 仍走 FinMind 季報(已99%可用)；如要更快可日後改 t187ap06 OpenAPI。
- **「silent gap」系統稽核（消費端有讀但欄位空）**：
  - 🔴 `monthly_revenue.yoy_growth`(蔡森評分/因子排行讀)：OpenAPI 同步漏存「去年同月增減」→ 補後 0%→99%(`sync_revenue_openapi` 加 yoy_growth/last_year_revenue)。
  - 🔴 `income.gross_margin`(financial_health/謝富旭讀)：季報來源(t187ap14)無毛利欄→ `sync_balance_openapi` 加抓損益表 t187ap06_ci 算毛利率 0%→97%。
    **坑：TPEX 損益表用英文 `Year`/`Season`，資產負債表卻用中文「年度/季別」**(同站不一致)→fallback。
  - 🟢 `cashflow.*`/`stock_factors.beta`：空但無消費端(beta由risk_manager即時自算)→無害。
  - 🟢 PE 73%/殖利率 89% 缺口**確認合法**：缺PE 515檔中503檔有BWIBBU殖利率/PB(PE因TTM EPS負而空白)、12檔ETF；
    缺殖利率twse 196檔中190檔真不配息。`dividend_detail` 健康(最新除息2026-08、欄位有值、填息邏輯用EPS非此表)。
  - 教訓：凡「消費端 .get(巢狀欄位)」都要查 population，常見空欄=來源該欄沒同步進來。

## 【2026-06-20 增補】團隊LINE可用性：RRR失真 + 判定矛盾 + PE極端
- 🔴 **RRR 失真修正**(最影響判讀)：`pattern_detector.calculate_(short_)risk_reward_ratio` 與 `pattern_bridge`
  原用 **current_price** 當進場 → 成型中型態現價貼停損→風險趨近0→RRR 爆成 90/77。**改用頸線(進場點)**算。
  驗證：長榮 19.1→0.78、永豐餘 90.48→0.78、台積電 77.57→0.78（反轉型態真實 RRR 多 0.7~0.85，目標僅1倍height）。
  連帶校準：`daily_senvision.sh --min-rrr 1.5→0.5`、scanner/market_scan 預設 1.5/2.0→0.5(避免型態被濾光)、
  評分門檻 analysis.py/pattern_detector RRR 加分 3.0/2.0→1.5/1.0(配合新尺度)。**下次掃描17:00生效**。
- 🟡 **判定尊重型態方向**：顧問 prompt(team_analyze) 改對稱要求——偏多型態不給賣出/偏空不給買進，相反須首句說明壓過技術的關鍵因素。
  (原只規範頭部不給買進，漏了底部不給賣出→豐泰 W-Bottom→賣出 那種矛盾)。
- 🟢 **PE 極端標註**：team `_enrich_line` PE>80 顯示「PE高」(低獲利股 PE 數值無意義,如群創585/台泥282/聯亞321)。

## 【2026-06-20】新增因子：MA乖離度 + 法人連續買賣超
- `MomentumFactors` 加 `calculate_ma_bias`(ma_bias_20/60 = (收盤-MA)/MA×100) + `calculate_inst_streak`
  (foreign_streak/trust_streak：外資/投信同號連續天數,+買/-賣) → 併入 calculate_all_momentum_factors → stock_factors。
- **回測(`backtest_ma_inst.py`)推翻直覺**：多頭 regime 下「超賣反彈」是錯的——超賣只 5日短彈、20日超額-2%，深超賣(-15)更-7.5%(接刀)；
  反而超買(乖離≥15)是動能續強(+6%)但 regime 依賴危險。**唯一乾淨可接評分的是「外資連買≥3」(+2.5%、勝60%)**。
- **評分**：score_signal 加 `foreign_streak` 參數，僅「外資連買≥3 → +0.05」(已驗證)；乖離/超買超賣**只顯示不評分**。
- **顯示**：team `_enrich_line` 過度延伸(|乖離|≥15)標「乖離60+74%⚠超買/超賣」、法人連續≥3標「外資連4賣」；
  scanner `_FACTOR_FIELDS`+CSV+score_signal 全接。下次因子計算/掃描生效。

## 【2026-06-20】整潔程式碼重構（去重複,依使用者五原則）
- **`src/utils/twstock_openapi.py`**(共用)：集中政府 OpenAPI 的 UA/`fetch_openapi`/`field`(中英欄名fallback)/
  `to_float`/`roc_to_year`/`roc_year_month`。三支 `sync_*_openapi.py`(revenue/shares/balance) 改用 → 各自複製的
  UA/fetch/民國轉換歸零；`sync_shares` 兩 fetch 併成 `fetch_shares(url,code,shares)`+SOURCES 表。
  **重測輸出不變**(revenue1972/shares1980/balance1969+1924/台積ROE38.62)。排程腳本路徑未變→不需動排程。
- **`src/utils/backtest.py`**(共用)：集中回測 harness `tof`/`dkey`/`print_baseline`/`report`/`make_reporter`。
  4 支 `backtest_*.py` 改用 → 去除各自複製的 tof/baseline/show。**重跑驗證數字一致**(基準n=61082、外資連買≥3超額+2.49%)。
- 動機：這些是排程正式碼+驗證工具，共通的是 OpenAPI 規則/回測機制；集中後 API 改版或調回測只需改一處(避免持續維護折磨)。

## 【2026-06-20】謝富旭手選清單 → 存股法演算法篩選 + 極端 yoy 截斷
- **極端 yoy 截斷**：`stock_ranker._get_revenue_growth` 對 >500% 截斷為 500(建案完工認列致 +87447% 等基期效應,
  官方數值正確但會汙染排名；已查證 1808 與 TWSE OpenAPI 逐位元相符,官方備註「完工建案過戶交屋認列」)。
  score_signal 用 yoy 是門檻式(≥20/≤-10)本就不受影響。
- **存股法篩選取代手選清單**(`src/strategy/hsieh_value.py` HsiehValueScreen)：依謝富旭受訪整理的可量化條件全市場篩選——
  ①負債比<60% ②流動比>100%(速動比代理,官方摘要無存貨) ③未分配盈餘(保留盈餘)≥2倍股本 ④營益率衰退<營收衰退(核心競爭力)
  ⑤殖利率≥4% ⑥連續配息≥3年。資料 quarterly_earnings.balance/income + stock_factors + dividend_detail。
  - 先驗資料：毛利率 YoY 僅9%可比(歷史稀疏)→ 核心改用**營益率**(91%可比)；其餘條件 89~99%覆蓋。
  - 結果 81 檔通過(麗豐-KY/金洲/中菲行/新麥…全是低負債高流動連配12年的真存股)。
  - `sync_balance_openapi` 加存 保留盈餘/股本。daily_recommendations(便宜區+主動分析+多策略+整合) 與 team tier 全改用 HsiehValueScreen。
  - 硬編碼 `hsieh_watchlist.HSIEH_PICKS`(13檔)徹底脫鉤(無外部引用)，已標棄用可刪。

## 【2026-06-21】加入季線/半年線/年線(長期均線)
- `MomentumFactors`：①`calculate_ma_bias` 乖離窗擴為 20/60(季線)/120(半年線)/240(年線)
  ②新增 `calculate_ma_long_trend`：`ma_above_long`(現價站上幾條長均0~3) + `ma_long_trend`(60>120>240長多=1/長空=-1/糾結=0)。
  → stock_factors(96~99%)、scanner `_FACTOR_FIELDS`+CSV、team `_enrich_line`(乖離年/⚠年線下)。
- 用途：年線=台股多空分界，底部型態在年線上方(多頭回檔)較可靠、年線下(空頭弱反彈)接刀風險。群創乖離年+210% 印證 PE585 極端超漲。
- **回測驗證 + 接入評分**(`backtest_pattern_yearline.py`)：底型態+站上年線 20日 **+6.1%** vs 年線下 **+2.9%**(差~3.15%)，
  年線位置強烈 discriminate 底型態品質(年線下=空頭弱反彈接刀)。兩者皆<基準(多頭抄底輸動能)，故當**相對品質濾網**：
  score_signal 加 `ma_above_long` 參數——`is_bottom`+年線下(0)→**-0.06**、+站上年線(≥2)→**+0.04**。scanner 已傳入。

## 【2026-06-21】闕又上「阿甘投資法」(`src/strategy/agan.py`)
- **A.景氣燈號擇時**：`agan_market_signal` 讀 macro_indicators(indicator='leading').data.signal_score(國發會景氣對策信號,月更)→
  燈號+進出場(藍/黃藍燈分批進場、綠燈持有、黃紅/紅燈減碼出場)。現況 39分紅燈→出場(景氣過熱)。
- **B.護城河龍頭選股**：`AganMoatScreen`——市值前200大型龍頭 + ROE≥15% + 負債<50% + 連配≥5年，依ROE排序。
  - **ROE 用 TTM(近4單季淨利加總/權益)**：原 stored.roe 是單季×4年化,Q1強會爆值(宜鼎149%失真)→ TTM 才是真實年ROE(宜鼎49%/聯發科25%/台積電32%)。覆蓋91%。
  - 結果27檔(創見51%/宜鼎49%/力旺46%/群聯31%…真高ROE龍頭)。
- 接入 daily_recommendations 第3則 LINE(景氣燈號訊號 + 護城河龍頭)。景氣燈號需月更(macro_sync --set-signal)。
- 教訓：ROE 單季×4 年化對 Q1 強/弱季失真,品質型篩選應用 **TTM ROE**(同 PE/yoy 極端值之鑑)。

## 【2026-06-21】全資料健檢 + stored ROE 系統性改 TTM
- **健檢**：覆蓋率 96~99%(除合法缺口 PE73%虧損股/殖利率89%不配息)；問題掃描——
  PE>200(73檔,已標PE高)、yoy>500%(35檔,已截斷)、毛利率YoY僅9%可比(已用營益率繞)、景氣燈號停2026-04(需月更)。
- **🔴 stored ROE 年化失真(系統性修正)**：`sync_balance_openapi` 的 `balance.roe` 原用 `淨利×(4/季)` 單季年化，
  Q1強會爆值(群聯82%/宜鼎149%失真)，而**團隊/掃描/quality_factors 全讀此值**。改 **TTM(近4單季淨利加總/權益)**。
  驗證:群聯82→30.7%、宜鼎149→48.8%、台積電32.5%、聯發科25.3%；ROE>60%失真 29→6檔。
  覆蓋 1968→1816(TTM需4季,新股略缺,屬正常)。AganMoatScreen 本就用 TTM(一致)。

## 【2026-06-21】選股加流動性門檻(過濾買不到的冷門股)
- 回饋：推薦清單出現勝品(12張/日)、鼎翰(56張)等冷門股「買不到/掛單墊高成本」，非好標的。
- 抽共用 `src/strategy/screen_liquidity.py`(`avg_volume_lots`/`is_liquid`,門檻近20日均量≥300張)，
  套進 `HsiehValueScreen`+`AganMoatScreen`。謝富旭 81→40檔(濾掉勝品)、阿甘 27檔。
- 阿甘護城河每日清單已固定(daily_recommendations 第3則LINE)：景氣燈號訊號 + 護城河龍頭(高ROE·站上年線·流動性足)。
- 教訓：選股(尤其存股長抱)要列「買得到」的——多策略技術交集易選到打底冷門股,品質龍頭(高ROE+站上年線)才是好標的。

---

## 一、新增 scripts（7 支 + 1 模組）

| 檔案 | 用途 |
|---|---|
| `src/factors/volume_factors.py` | **新模組** VolumeFactors：量比/量能百分位/OBV斜率/量價背離 |
| `scripts/backfill_recent_gaps.py` | 隔日自動回補缺漏交易日（法人/PE-PB），被 daily_senvision [1.5/4] 呼叫 |
| `scripts/volume_price_scan.py` | 全市場量價掃描（爆量/資金流入/空背/量縮）→ CSV+LINE；`--refined` 精選版(法人交叉) |
| `scripts/team_daily_verified.py` | 每日已查證角色團隊分析（6角色+顧問，DB vs FinMind即時佐證，技術角色吃蔡森型態） |
| `scripts/macro_sync.py` | 總經指標同步（匯率台銀自動 + CPI/利率/M1B-M2/景氣存值月更 + **TAIEX**）|
| `scripts/fix_quarterly_units.py` | **一次性** 修季報千元/累計 bug（3916筆） |
| `scripts/backfill_gross_margin.py` | **一次性** 從 financial_statements 回補毛利率（2710筆） |
| `scripts/backfill_price_history.py` | **一次性** FinMind 回補被截斷的歷史股價（207檔/184,551筆） |

## 二、修改的既有檔案

**量價分析接入**
- `src/factors/factor_calculator.py` — 接 volume 因子類別
- `scripts/parallel_factor_calculation.py` — factor_types 加 `'volume'`
- `src/senvision/analysis.py` — `score_signal()` 加量價評分（量比/OBV/量價背離±）
- `src/senvision/scanner.py` — 量價因子快取/評分傳入/`_volume_state_label`
- `scripts/senvision_market_scan.py` — CSV 加 量比/量能百分位/OBV斜率/量價背離/量價狀態
- `src/strategy/hsieh_watchlist.py` — `volume_tag` + `_recommend_action` 量價否決(強模式)
- `scripts/daily_recommendations.py` — 蔡森/存股區塊加量價狀態 + 加 `--no-line`

**完整度檢查重構**
- `scripts/twse_openapi_sync.py` — 日期+筆數雙驗、**交易日**落後(非日曆天)、pipeline停擺偵測
- `scripts/daily_senvision.sh` — [3/4] factor `--end-date 今天`(含當日)；[1.5/4] 改呼叫 backfill_recent_gaps

**LLM 角色模型升級 + 蔡森接入**
- `src/moe/role_router.py` — ROLE_TO_MODEL：advisor/orchestrator→**qwen3.6:27b**、vision→移除
- `src/moe/router.py` — EXPERTS 更新、移除 vision 路由
- `scripts/team_analyze.py` — 硬編碼模型字串改動態讀 ROLE_TO_MODEL
- `ARCHITECTURE.md` / `INSTALL.md` — 模型名稱同步

**角色資料稽核修正（5+1）**
- `scripts/twse_quarterly_sync.py` — `normalize_income()`：千元×1000 + 反累計(YTD→單季)
- `src/analysis/risk_manager.py` — beta 按日期對齊 + 過濾分割假跳動 + market proxy 0050→**TAIEX**
- `src/api/server.py` — institutional 補 `dealer_net`；`get_factors` 改「首個非null」(pe=None修正)
- `src/analysis/stock_ranker.py` — `_load_candidates` 改「首個非null」(因子排行0檔修正)
- `src/analysis/peer_comparison.py` — aggregation 改「首個非null」(同業排名null修正)

> **根因教訓**：stock_factors 多來源，最新一筆常是 factor_calc(無PE)。凡讀 pe/pb/殖利率/roe
> 一律取「近30天首個非null」，不可用 naive `$first`/`find_one(sort date)`。

## 三、新增排程（launchd，全部已載入）

| Label | 時間 | 執行 |
|---|---|---|
| `com.twstock.daily_macro_sync` | 週一~五 17:10 | macro_sync.py（TAIEX/匯率/總經） |
| `com.twstock.daily_volume_price` | 週一~五 18:00 | volume_price_scan.py |
| `com.twstock.daily_team_verified` | 週一~五 18:30 | **team_daily_50.sh**（50檔兩階段） |

**每日管線總覽**：17:00 senvision → 17:10 macro_sync → 17:30 recommendations → 18:00 volume_price → 18:30 team_verified(50檔兩階段) → 21:00 integrity_check

### team_daily_verified.py 擴充為「50檔×兩階段」（2026-06）
- **選股**：`select_universe_50(50)` = 各行業龍頭（市值=發行股數×最新收盤，每股取最新收盤避免當日半盤；排除 ETF/指數/受益/存託）+ 成交額(收盤×量)補滿 50，重複跳過。
- **兩階段**（`scripts/team_daily_50.sh` 串接，`&&` 確保 Phase2 在 Phase1 完成後才跑，避免搶寫同檔）：
  - Phase1 `--universe industry50 --quick`：6 角色 + 資料佐證，**省顧問整合**(~2h)→ LINE 摘要。逐檔存 `results/team_analysis/team_YYYYMMDD.json`。
  - Phase2 `--universe industry50 --phase2`：讀今日存檔，**只補跑投資顧問整合**(重用已存 6 角色報告)→ LINE 摘要。
- **LINE 自適應**：>8 檔自動切 `build_line_summary`（一檔一行，依顧問判定排序，顯示 🎩判定/(待整合)、🔷蔡森型態、佐證 n/m✅）；>4500 字自動分段發送。
- 既有 `--universe tier`(預設 Tier1/2)、`--symbols`、`--top` 仍保留供手動使用。

#### 全量 E2E 測試結果（2026-06-17 21:03 → 06-18 04:08，`--no-line`）
- **總耗時 ~7h**：Phase1 1h55m（50檔×6角色，暖機後 ~90–100s/檔）；Phase2 5h10m（50檔顧問整合，~6.2 分/檔，首檔冷載）。
- **完整度 50/50**：兩階段皆無遺漏；逐檔存檔→phase2 成功重用 phase1 報告。**全程 0 Traceback / 0 timeout / 0 崩潰**。
- 顧問判定分布：買進27 / 強力買進1 / 觀望21 / 賣出1。兩版 LINE 摘要(精簡「待整合」/完整「🎩判定」)渲染正確、依判定排序。
- **佐證 187 筆**：✅83、📊法人37、⚠️背離14、ℹ️未查證50、⚠️DB缺2、—無資料1。
  - `ℹ️未查證`(50) 分散收盤/PE/殖利率(各16–17檔)、`live=None`：**50檔×3指標即時查證打滿 FinMind 免費配額(600/hr)** → 約1/3個股當下查不到，佐證層優雅標「未查證」(不誤報)。要提升覆蓋率可在佐證層加節流或只對前N大檔即時查證。
- 觀察(非bug)：偶有「蔡森偏空型態 vs 顧問偏多」張力(如晟德 HS-Top vs 強力買進)，屬分析品質面，日後可讓顧問更尊重蔡森型態方向。
- 正式排程意義：18:30 起跑 → Phase1 ~20:25 出精簡版 LINE → Phase2 ~凌晨03–04 出完整版 LINE。

#### LINE 摘要改版：加料行 + 分組（2026-06-18，因「看不出資料」回饋）
- 舊版每行只有 `代號 名 行業 (待整合) 🔷型態 佐證n/m` → 精簡版 50 行全 `(待整合)`，無決策資訊。
- `_enrich_line()` 加料行：`現價 PEx 殖x% 🔷型態方向·狀態 RRRx 📊量價 佐n/m✅`，資料全取自既有
  evidence(收盤/PE/殖利率 DB值) + senvision(pattern/status/rrr/vp)。
- `_pat_dir()` 方向以 **target vs stop** 判定(target>stop=偏多↗/<=偏空↘)，不受 Failed-Breakdown 命名干擾；退而看型態名。
- `build_line_summary` 分組：**精簡版**(無顧問)依蔡森方向分 📈偏多/📉偏空/➖無型態(偏多在前=可留意 setup)；
  **完整版**(有顧問)依🎩判定分 🔥強力買進/🟢買進/🟡觀望/🟠減碼/🔴賣出。組內依風報比(RRR)排序。
- 已用 06/18 真實存檔驗證兩版渲染。**注意**：改檔不影響當下已在記憶體執行的 phase2，新格式自下個排程起生效。

#### 🔴 顧問評級解析 bug（2026-06-19，致 34/50 假「買進」）
- 症狀：完整版 LINE 顯示 強力買進1/買進33/觀望16，68% 買進、0 賣出 → 無鑑別力、無法判斷。
- **根因**：`_verdict()` 在**整篇**顧問文字裡依序找『強力買進→買進→觀望→減碼→賣出』第一個命中。
  但內文充斥「條件式買進/逢高佈局買進」等字，『買進』永遠先被掃到 → 不管最終建議是賣出或觀望全判成買進。
  顧問本身分析正確(如 2330『最終建議：賣出』、2308『賣出』、1717『賣出』)，是解析糟蹋了結論。
- **修法(兩段)**：
  - 解析改三層：① 讀結構標籤『評級：X』→ ② 明確「最終(投資)建議：X」窗格、取**出現位置最前**的評級詞
    (非關鍵字優先序，避免條件式詞蓋過)→ ③ 顧問多在開頭下結論，前160字位置法補漏。前160法與明確建議行
    交叉比對 **0 衝突**，50/50 全解析。
  - prompt 加固定輸出規則(`team_analyze.py` investment-advisor)：第一行只輸出『評級：<五選一>』，
    且「頭部型態(M-Top/HS-Top/Triple-Top)無強催化不應給買進」→ 根除未來歧義。
- 修正後 06/19 真實分布：**買進11(↗偏多型態為主)/觀望31/賣出8(↘頭部型態為主)** — 與蔡森方向一致、可判斷。

## 四、一次性資料操作（已執行）

- 補下載 2026-06-05、06-08 缺漏（股價/法人/PE-PB/因子）
- `fix_quarterly_units.py`：季報 2025Q4+2026Q1 單位/累計修正 — **3,916 筆**
- `backfill_gross_margin.py`：毛利率回補 — **2,710 筆**
- `backfill_price_history.py`：截斷歷史股價回補 — **207 檔 / 184,551 筆**
- macro_sync seed：利率2.0%/CPI2.2%/M1B8.25%/M2 6.45%/景氣39紅燈
- TAIEX 灌入 stock_price(symbol='TAIEX') — **1,078 筆**（2022~今）

## 五、Ollama 模型

**升級後保留（7）**：qwen3.6:27b、qwen3-vl:8b、deepseek-r1:14b、qwen3:8b、qwen2.5-coder:7b、nomic-embed-text、llama-3-taiwan:8b
**已刪（釋37GB）**：qwen3:30b、llama3.2-vision:11b、gemma4:e4b、gemma3:4b
**⚠️ 孤兒可刪**：`qwen3-vl:8b`(6.1GB) — vision 角色已移除後沒程式引用，可 `ollama rm qwen3-vl:8b` 回收

## 六、memory（供跨 session 參考）

- `integrity_check.md` — 完整度檢查雙驗 + 交易日落後 + end_date 修正
- `volume_factors.md` — 量價因子 + 掃描/清單接入
- `llm_team_analysis.md` — MoE 模型 + 每日已查證團隊分析 + macro 修復
- `data_quality_fixes.md` — 季報單位/beta/dealer/毛利/歷史價/TAIEX/多來源$first 共8項

## 七、待辦（未做，已記錄）

- 季報單位 code 修正需待 7月Q2 申報季實際驗證
- gross_margin 僅涵蓋 192 檔（financial_statements 限制）
- 新聞/事件質化查證（佐證層 v2）、團隊法人即時交叉、beta 除息還原
- 謝富旭清單強力買進在「買進/佈局」區重複列（line_analysis 字串包含，可選修）
