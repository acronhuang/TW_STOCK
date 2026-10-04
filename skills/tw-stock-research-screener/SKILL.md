---
name: tw-stock-research-screener
description: >-
  台股全市場「研究篩選」工作流：從 2000+ 檔股票，依序取清單→抓期間資料→算技術指標→
  分析價格結構→辨識突破型態→檢查量能→基本面→籌碼面→多因子評分→產出 🟢🟡🔴 研究候選名單。
  重用既有 tw-stock-analysis 模組（daily_recommendations / stock_ranker / senvision /
  morphology / financial_health / chip_signals），不重算、不重寫。輸出為「研究名單」而非
  「買進名單」。WHEN：使用者要求「全市場選股/研究篩選」、「幫我找值得研究的股票」、
  「跑選股」、「產生候選名單」、「台股研究清單」、「篩選 2000 檔」、「研究名單分級」、
  「哪些股票值得深入研究」。DO NOT USE FOR：單純問「某一檔怎麼樣」(用 cli/query.py 或
  team_analyze.py)、資料回補(用停機回補流程)、即時下單或買賣建議(本 skill 不給買賣指令)。
---

# 台股研究篩選器（TW Stock Research Screener）

## ⚠️ 硬性原則（每次輸出都要遵守）

1. **「研究名單」≠「買進名單」**；「技術型態」≠「未來一定上漲」；「AI 篩選」≠「投資保證」。
2. 本 skill 只做：找資料、找特徵、算指標、建立分類、整理研究結果。**最終投資判斷由人決定。**
3. 每一筆結論**都要標資料日期**，且**先檢查資料新鮮度**（見步驟 0）。資料過期就先說明，不要在舊資料上給名單。
4. 不輸出「買進價/張數/停損」這類下單指令（那是使用者自行決定；若要個股深度，改用 `team_analyze.py`）。

## 執行環境

- 正式機 `.166` = `mdsadmin@172.16.9.166`；程式 `/home/mdsadmin/Stock/tw-stock-analysis`；venv `/home/mdsadmin/Stock/.venv`。
- MongoDB `tw_stock_analysis`（localhost:27017）。
- 所有指令在專案根目錄下、用 venv python 執行。

## 步驟 0 — 前置檢查（必做）

先確認資料是最新再跑篩選，否則名單無意義：

```bash
cd /home/mdsadmin/Stock/tw-stock-analysis
/home/mdsadmin/Stock/.venv/bin/python3 scripts/data_freshness_audit.py | tail -5
```

- 若結尾為「✅ 無任何表超出其更新頻率的落後門檻」→ 繼續。
- 若有 🔴 核心表（stock_price / stock_factors / institutional_flow）落後 → **先停下**，回報落後項，建議先補資料（見停機回補流程），不要硬跑。

## 步驟 1–10 — 篩選流程（重用既有模組）

這 10 步在系統內已各自實作；**單一入口是 `daily_recommendations.py`**，它已整合因子排行＋蔡森型態＋財報篩檢＋北大風控。優先用它一次跑完，再用其餘模組補齊分級所需欄位。

| 步驟 | 動作 | 指令 / 模組 |
|---|---|---|
| ① 股票清單 | 取全市場（排除 ETF/權證） | `senvision/scanner.py get_stock_list()` |
| ② 期間資料 | 取近 N 日還原價 | `src/cli/query.py price <sym> --days 60` |
| ③ 技術指標 | RSI/KD/MACD/BB/OBV | `src/indicators/`（已於 stock_factors 落地） |
| ④ 價格結構 | 支撐壓力/趨勢線 | `senvision/support_resistance.py` |
| ⑤ 突破型態 | W底/VCP/頸線/蔡森 | `scripts/daily_senvision.sh` → `results/scan_auto_*.csv` |
| ⑥ 量能 | 量價型態/OBV 背離 | `analysis/volprice_pattern.py` |
| ⑦ 基本面 | 6 維財報健康 A~F | `src/cli/query.py health <sym>`（`financial_health.py`） |
| ⑧ 籌碼 | 三大法人/融資券 9 訊號 | `analysis/chip_signals.py` / `scripts/chip_score_scan.py` |
| ⑨ 多因子評分 | 綜合分 0–100 | `analysis/stock_ranker.py`（value .25/quality .20/momentum .15/safety .15/chip .15/growth .10） |
| ⑩ 候選名單 | 一鍵整合輸出 | `make scan`（= `python scripts/daily_recommendations.py`）→ `results/daily_picks_*.json` |

**快速路徑（最常用）：**
```bash
make scan            # 全市場 → results/daily_picks_*.json
make update          # 需要先重算當日因子/型態時先跑這個（daily_senvision）
```
取綜合分與排行也可走 API（若 `twstock-api.service` 在跑）：
```bash
curl -s localhost:8888/api/ranking?limit=30
curl -s localhost:8888/api/score/2330
```

**互動檢視**：Dashboard 已有「📊 策略研究 → 🔬 研究篩選」頁，直接呈現 🟢🟡🔴 分級、
六維拆解與可調門檻，並可下載 CSV（`dashboard/pages/research_screener.py`）。

## 🟢🟡🔴 分級規則（在既有輸出上做分類，不另算）

把 `daily_recommendations` / `stock_ranker` 綜合分、`financial_health` 等級、型態旗標、籌碼訊號組合成三燈。**預設門檻（可依使用者指定調整）：**

- 🟢 **值得深入研究**：綜合分 **≥ 70** 且 財報健康 **≥ B** 且（型態已確認：`is_vcp` 或 頸線突破）且 籌碼**無** 🔴 斷頭風險。
- 🟡 **條件部分符合**：綜合分 **50–69**，或上述條件只成立一部分、但無重大警訊。
- 🔴 **暫不納入研究**：綜合分 **< 50**，或 財報 **D–F**，或 型態未收斂，或 籌碼出現 🔴 斷頭/融資過熱。

遇到資料缺漏（某檔無因子/無財報）→ 標 🟡 並註明「資料不足，無法分級」，不要猜。

## 步驟 11 — 驗證與報告（標準流程，必做）

產出 🟢🟡🔴 名單**之後**，標準流程必須再跑一層驗證，確認這套因子/評分的優勢不是
樣本巧合或前視洩漏，否則 🟢 名單不可信。三件事都要做並附在報告：

1. **多因子評分報告** — 輸出綜合分的維度拆解（估值/品質/動能/安全/籌碼/成長）與分佈，
   讓使用者看到每檔 🟢 是靠哪些維度得分。
   `/home/mdsadmin/Stock/.venv/bin/python3 scripts/factor_ic_analysis.py`（因子 IC / 衰減）。
2. **回測 + Walk-Forward** — 用同一套評分在歷史上滾動驗證（樣本內/外對比），報告
   年化報酬、夏普、最大回撤、勝率。
   `scripts/backtest_integrated_v21.py --start-date 2022-01-01`（內含 6 月滾動 Walk-Forward）。
   績效指標模組：`src/backtesting/performance.py`。
3. **前視洩漏 / A-B 穩健性閘門** — 確認品質因子沒有偷看未來財報；覆蓋率 <85% 應拒跑。
   `scripts/run_ab_robust.py` → 結論寫入 `ab_verdict.txt`（PASS/FAIL）。

**判讀規則：** 若回測 Walk-Forward 樣本外績效崩壞，或 A-B 判定 FAIL（疑前視洩漏），
則**在報告開頭明確警告**「本期評分優勢可能不穩健／疑似前視」，🟢 名單降級為僅供觀察，
不可當成可信研究結論。IC 與回測同向才算站得住。

## 輸出格式（固定模板）

```
台股研究候選名單 · 資料日期 <YYYY-MM-DD> · 篩選門檻 <預設/自訂>

🟢 值得深入研究（N 檔）
  <代號 名稱> 綜合分<xx> 財報<等級> 型態<名稱> 籌碼<訊號>
  ...
🟡 條件部分符合（N 檔）
  ...
🔴 暫不納入研究（摘要：N 檔，列前幾名或略）

⚠️ 研究名單 ≠ 買進名單；型態 ≠ 未來上漲；AI 篩選 ≠ 投資保證。
   本清單僅供研究起點，投資決策請自行確認。
```

## 進階模組（使用者要求再跑）

- 單檔 7 角色深度：`python scripts/team_analyze.py <代號>`
- 每日自動候選（排程）：`evening_pipeline.sh` 已含選股/合議，產出每日 picks。

## 常見陷阱

- 先 `make update` 再 `make scan`：型態/因子要先在最新價上重算，否則掃到舊值。
- SSH 下中文/括號會被 PowerShell 吃掉引號 → 遠端 grep 用 `-e PATTERN`，mongosh 用 `--file`。
- 綜合分欄位來自 `stock_factors`；該表落後時分數不可信（回步驟 0）。
