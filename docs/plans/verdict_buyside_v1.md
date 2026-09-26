# 可行性評估與架構規劃 — Verdict 買方選股改良 v1（影子模式）

> 範圍鎖定:本會期唯一的開放工程項 —— verdict **買進** call 追高反轉問題。
> 原則:**離線/影子模式,回測驗證前不動 live 判斷**（呼應 ADR「不宜逕改 live」)。

---

## 0. 問題陳述（證據導向,取自 verdict_detail 實測)

| verdict（前瞻 20 日) | n | 命中 | 事前 20 日動能 | 均超額 |
|---|--:|--:|--:|--:|
| 買進 | 1217 | **33.4%** | **+2.98%** | **−1.14%** ❌ |
| 賣出 | 2879 | 59.9% | −1.50% | +0.73% ✅ |

**根因**:買進系統性偏向「近期漲多」的股（事前動能 +2.98%),20 日內均值回歸 → 負超額。
**已排除**:反動能過濾(實測 33.4%→30.9%,更糟)、SLI 門檻(問題為真)、偏空/環境(賣出反而最佳)。

**目標(可量測)**:買進前瞻 20 日 **超額命中 ≥ 55%**、**均超額 ≥ +1.47%**(即現行 NFR-QUAL-002 門檻),
且**不劣化賣出**,全程**不改 live verdict**,以回測 out-of-sample 佐證後才提議切換。

---

## 1. 可行性評估報告（必含欄位)

| 模組/工項 | 技術難易度 | 風險係數 | 預估開發時程 | 相依 | 驗收訊號 |
|---|:--:|:--:|:--:|---|---|
| M1 特徵萃取器（動能+價值+品質) | 低 | 🟢 低 | 0.5 天 | stock_factors | 純函式,fixture 測試綠 |
| M2 買方再評分器 buy_rescore | 中 | 🟡 中 | 1 天 | M1 | 給定特徵→v2 決策,決定論可測 |
| M3 影子寫入器（shadow 欄位) | 低 | 🟢 低 | 0.5 天 | M2 | 只寫 shadow,永不覆蓋 live |
| M4 回測比較器（v1 vs v2) | 中 | 🟡 中 | 1 天 | verdict_detail + backtest | 產出 v1/v2 命中/超額對照 |
| M5 儀表板「買方改良對照」頁 | 中 | 🟡 中 | 1 天 | M4 | 趨勢圖 + 對照表,E2E 綠 |
| M6 E2E（Playwright)+ 截圖 | 中 | 🟡 中 | 0.5 天 | M5 + 安裝 | 重複腳本可跑、截圖產出 |
| **合計** | — | — | **~4.5 天** | — | 全模組驗收 + out-of-sample 佐證 |

**風險係數定義**:🟢 低=純離線/可回滾/不碰 live;🟡 中=需真實資料/回測不確定性;🔴 高=改 live 路徑。
本方案**刻意無 🔴**(影子模式)。

### 風險登錄（Top）
| 風險 | 影響 | 緩解 |
|---|---|---|
| 價值/品質 tilt 未必改善買方超額（核心假設可能不成立） | 專案目標達不到 | 影子模式:即使無效也零 live 損害;以回測快速證偽 |
| 小型股 stock_factors 稀疏（PE 僅 ~68% 覆蓋) | 特徵缺失→再評分退化 | M1 做缺值守衛 + 覆蓋率門檻,不足者維持原判 |
| 單一空頭 in-sample 過擬合（碼註解自警:34 獨立日/單區間) | 改善不外推 | 切分 train/holdout + walk-forward;報告標示樣本侷限 |

---

## 2. 架構選型分析（依環境與技能樹:Python / MongoDB / pytest / Streamlit / 既有 verdict_detail + 回測 harness / 離線分析強項)

| 方案 | 說明 | 技術難易度 | 風險 | 時程 | live 影響 | 適配度 |
|---|---|:--:|:--:|:--:|---|:--:|
| **A. 影子再評分器（post-hoc overlay)** ⭐ | 讀既有 team_analysis 買進 + 特徵→算 buy_v2_score,寫 shadow 欄,回測對照 v1/v2 | 中 | 🟢🟡 | ~4.5 天 | **零**（永不覆蓋) | ★★★★★ |
| B. 判斷時 feature-gate（旗標關閉) | 在 pipeline 買進條件加價值/品質 gate,feature flag 預設 off | 中高 | 🟡（碰 pipeline) | ~6 天 | 旗標 off 時零,on 有風險 | ★★★☆ |
| C. 買方多因子模型重構 | 以多因子模型取代買進訊號 | 高 | 🔴 | ~15 天+ | 大 | ★★ |

**選定:A（影子再評分器)**。理由:
- 完全複用既有 `verdict_detail`(已含 excess/prior_20d/hit)+ `verdict_orthogonality_backtest` harness → 最短路徑
- **零 live 風險**:只寫 shadow 欄,回測 out-of-sample 佐證後,才由團隊決定是否升級為 B 的 feature-gate
- 契合離線分析強項與 pytest/mongomock 可測性;E2E 面向既有 Streamlit dashboard

### 規格拆解（Option A,附驗收標準)

- **M1 `features.py::extract_buy_features(doc, factors)`**
  - 輸出 `{prior_20d, pe_pctile, pb_pctile, roe, coverage_ok}`;缺值→`coverage_ok=False`
  - ✅ 驗收:給定 fixture 因子→正確百分位;缺 PE/PB→`coverage_ok=False` 且不拋錯
- **M2 `buy_rescore.py::rescore(features) -> {'v2': '買進'|'降級持有', 'score': float, 'reason': str}`**
  - 規則:高動能(prior_20d>閾) 且 (價值差 pe_pctile 高 或 品質差 roe 低) → 降級持有;否則維持買進
  - ✅ 驗收:決定論;高動能+高PE→降級;低動能+高ROE→維持;`coverage_ok=False`→維持原判(不亂動)
- **M3 `shadow_writer.py`**:寫 `verdict_detail.buy_v2`（不動 `verdict`/`final_verdict`)
  - ✅ 驗收:live 欄位位元不變;僅新增 shadow 欄;可 `--dry-run`
- **M4 `backtest_compare.py`**:對同一 verdict_detail 集算 v1 vs v2 的買方命中/均超額
  - ✅ 驗收:輸出 `{v1:{hit,excess,n}, v2:{...}, delta}`;holdout 切分;v2 命中 ≥ v1（否則報告如實標示未達標)
- **M5 dashboard 頁 `buyside_compare.py`**:v1/v2 命中率趨勢 + 對照表 + 樣本侷限註記
  - ✅ 驗收:空資料→st.info 不報錯;有資料→line_chart + metric（v2−v1 delta)
- **M6 Playwright E2E**:開頁→等待渲染→截圖→斷言頁面含「買方改良對照」與兩條趨勢
  - ✅ 驗收:腳本可重複執行、產出截圖檔、關鍵字斷言綠

---

## 3. 最沒把握的 3 件事（誠實)

1. **核心假設本身**——「加價值/品質 tilt 能改善買方 20 日超額」未經證實。買進追高反轉可能源自更深層(選股訊號本身,而非動能疊加),tilt 也許無效甚至更糟(反動能過濾就前車之鑑)。→ **影子模式讓證偽零成本,但成敗未知**。
2. **樣本外泛化**——現有 verdict_detail 僅涵蓋單一(偏空)區間、34 個獨立分析日,in-sample。任何改善都可能是過擬合,walk-forward/holdout 後可能消失。**「回測變好」不等於「未來變好」**。
3. **小型股特徵稀疏**——出問題最多的正是小型股(1256/1301…),而它們的 stock_factors(PE/PB/ROE)覆蓋最差(PE ~68%)。再評分最需要特徵的地方,恰恰最缺特徵 → 對這批可能退化成「維持原判」,改善打折。

---

## 交付與切換準則
- 全程**影子**:`verdict`/`final_verdict` 位元不變,可隨時移除 shadow 欄回滾。
- **升級到 live（Option B feature-gate)之門檻**:out-of-sample 買方超額命中 ≥55% 且均超額 ≥ 門檻、賣出不劣化、跨 ≥2 個市場區間穩健 —— 由團隊審查回測後決定,**非本專案自動切換**。
