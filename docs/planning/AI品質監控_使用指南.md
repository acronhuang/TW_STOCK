# AI 品質監控與 verdict 優化 使用指南

> 一套「量化 AI 判斷準不準 → 診斷病因 → 前瞻驗證優化」的閉環工具。
> 全部唯讀主資料（除 A/B 記錄），純函式核心皆有單元測試。

## 背景與發現
上線後以真實資料歸因發現：AI 的「買進」判斷 20 日命中率僅 18%（≈市場基準），且
**持有期越長超額越差**（60 日買進落後大盤 −6.62%）；多窗回測顯示**上漲與下跌市買進皆落後**，
傾向「逆勢/結構性偏弱」，但 verdict 僅 ~2.5 個月，**資料不足以定論** → 採前瞻 A/B 邊收邊驗。

---

## 工具地圖

| 階段 | 工具 | 用途 | 寫入 |
|---|---|---|---|
| 監控 | `scripts/verdict_attribution.py` | 每日命中率/校準 → `verdict_metrics` | verdict_metrics |
| 診斷 | `scripts/verdict_horizon_sweep.py` | 各持有期(5~120日)絕對+超額表現 | 無（唯讀） |
| 診斷 | `scripts/verdict_multiwindow_backtest.py` | 跨情境驗證是否結構性做反 | 無（唯讀） |
| 驗證 | `scripts/verdict_ab_record.py` | 記錄三臂決策 | verdict_ab |
| 驗證 | `scripts/verdict_ab_eval.py` | 比三臂超額 + Ollama vs 規則差異 | 無（唯讀） |
| 呈現 | Dashboard 總覽 → 🩺 系統健康 | 命中率 + 資料健康面板 | 無 |

核心模組：`src/audit/verdict_tracker.py`（命中/超額）、`src/audit/ab_verdict.py`（趨勢/閘門/比對）。

---

## 三臂 A/B（回答「Ollama 分析 vs 我的規則分析 差在哪」）

| 臂 | 決策方式 | 代表 |
|---|---|---|
| **base** | 現行 pipeline 最終 verdict | Ollama MoE 合議（多角色+委員+主持人） |
| **rule_gate** | 規則式動能閘門 | 買進但非上升趨勢(價>MA20>MA60) → 降為持有 |
| **ollama** | Ollama 帶動能情境「重新判斷」 | 把趨勢/均線餵回 technical-analyst 讓 LLM 再決策 |

### 為什麼要比 Ollama vs 規則
- **規則閘門**：透明、可解釋、零成本、穩定；但死板（無法權衡個案）。
- **Ollama 重判**：能綜合情境與例外；但慢、有成本、可能不穩定/幻覺。
- **兩者可能分歧** —— `verdict_ab_eval.py` 量化：
  - **一致率**：多少比例兩者判一樣（越高代表規則已抓到 Ollama 的多數判斷 → 可用便宜規則替代）。
  - **分歧矩陣**：規則說「持有」但 Ollama 說「買進」有幾檔 → 看分歧處**誰的超額報酬較好**，決定該信誰。
- **決策準則**：
  - 若 rule_gate 超額 ≈ ollama 且一致率高 → **用規則**（便宜穩定）。
  - 若 ollama 在分歧處明顯較準 → **保留 Ollama 重判**（值得成本）。
  - 若三臂差不多 → 病不在此，回頭查選股因子/prompt。

### 執行流程
```bash
# 1) 每日記錄三臂（在 .166，Ollama 臂連 .28；--limit 控成本）
python3 scripts/verdict_ab_record.py --limit 60      # → verdict_ab

# 2) 等 N 日後評估（唯讀）
python3 scripts/verdict_ab_eval.py --horizon-days 20
```
輸出範例：
```
臂          n   超額均值  相對命中
base       60   -1.2%     28%
rule_gate  60   +0.4%     35%     ← 規則閘門改善
ollama     60   +0.9%     38%     ← Ollama 重判更佳？
Ollama vs 規則：一致率 72%（分歧 17 檔）
  分歧矩陣：規則 持有 → Ollama 買進: 11   （這 11 檔誰對，看超額）
```

---

## 診斷工具速用

**持有期掃描**（判斷是否尺度錯配）
```bash
python3 scripts/verdict_horizon_sweep.py
# 讀法：買進超額若隨持有期變好→價值系統(改評估期即可)；越久越差→結構性弱
```

**多窗回測**（判斷結構性 vs 情境）
```bash
python3 scripts/verdict_multiwindow_backtest.py --horizon 20 --points 8
# 讀法：買進超額在【所有情境】皆負→結構性；僅上漲情境負→太保守/逆勢(加情境濾網)
# 注意：verdict 資料量須足(多個評估點皆有 n)，否則勿定論
```

---

## 建議節奏
1. **現在**：每日跑 `verdict_ab_record.py` 累積三臂資料（已可加入 cron）。
2. **1 個月後**：`verdict_ab_eval.py` 看三臂超額 + Ollama/規則差異，決定採規則或 Ollama。
3. **1-2 個月後**：`verdict_multiwindow_backtest.py` 有更多情境窗，確認買進是否結構性弱。
4. 若確診 → 正式在 pipeline 導入勝出臂（規則閘門或 Ollama 動能重判）。

## 設計原則
- 純函式核心 + 注入（`ask_role_fn` 可 mock）→ 離線可測、CI 不依賴 Ollama/Mongo。
- 前瞻 A/B 而非只回測 → 避免在 2.5 個月歷史上過擬合。
- 唯讀主資料；只寫 `verdict_metrics`/`verdict_ab` 監控集合。
