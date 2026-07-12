# Priority 1-3 執行指南

**創建日期**: 2026-02-23  
**目的**: 快速執行 Priority 1-3 任務

---

## Priority 1 🔴 v2 參數驗證（立即執行，5-10 分鐘）

### 1.1 驗證 v2 參數

```bash
cd /Users/ming/Desktop/Stock/tw-stock-analysis
python3 scripts/validate_best_params_v2.py
```

**目標**：
- ✅ 確認 74.51% 年化報酬可重現
- ✅ 檢查 min_factors = 3 是否解決選股失敗
- ✅ 確認涵蓋全年 12 個月（vs v1 的 159 天）

**輸出**：
- `results/best_params_v2_validated.json` - 驗證結果

**預期結果**：
- 年化報酬：74.51% ± 2%
- 夏普比率：2.338 ± 0.1
- 涵蓋月份：12 個月（vs v1 的 159 天/~5 個月）

---

### 1.2 對比 v1 vs v2

```bash
python3 scripts/compare_v1_v2_params.py
```

**目標**：
- 參數配置詳細對比
- 績效指標多維度對比
- 演化過程分析

**輸出**：
- `reports/v1_vs_v2_comparison.txt` - 對比報告

**關鍵發現**：
- v2 年化報酬 +37.5%（54.18% → 74.51%）
- 持股數量 -44%（18 → 10，極度集中）
- 價值因子 +4%（28.7% → 32.7%）
- min_factors -25%（4 → 3，解決數據問題）

---

## Priority 2 🟡 歷史回測 2022-2024（本週執行，2-3 小時）

### 2.1 使用 v2 參數回測 2022-2024

```bash
python3 scripts/backtest_historical.py \
  --start-date 2022-01-01 \
  --end-date 2024-12-31 \
  --params results/optimization_results_v2.json \
  --output reports/historical_backtest_v2.json
```

**目標**：
- 驗證 v2 策略穩健性
- 識別過擬合風險
- 分析不同市場環境表現

**輸出**：
- `reports/historical_backtest_v2.json` - 完整回測數據
- `reports/historical_backtest_v2.md` - Markdown 報告

**預期結果**：
- 2022 年（熊市）：預期較差
- 2023 年（復甦）：預期良好
- 2024 年（牛市）：74.51%（已知）
- 多年平均：>30% 年化
- 正報酬年數：2/3 年

**成功指標**：
- ✅ 正報酬年數 ≥ 2/3
- ✅ 平均年化 > 20%
- ✅ 平均夏普 > 1.5
- ✅ 最大年度回撤 < -20%

---

### 2.2 對比不同參數版本（可選）

```bash
# v1 歷史回測
python3 scripts/backtest_historical.py \
  --start-date 2022-01-01 \
  --end-date 2024-12-31 \
  --params results/optimization_results.json \
  --output reports/historical_backtest_v1.json

# 原始策略回測（需要創建原始參數文件）
# ...
```

---

## Priority 3 🟡 實盤準備（本月執行，1-2 週開發 + 3-6 個月測試）

### 3.1 風控模組開發（待開發）

**功能需求**：
- 單股止損：-5%
- 組合止損：-10%
- 倉位管理：最大 10% 單股
- 再平衡容忍度：5%

**參考代碼**：
```python
# src/trading/risk_manager.py
class RiskManager:
    def __init__(self):
        self.single_stock_stop_loss = -0.05
        self.portfolio_stop_loss = -0.10
        self.position_size_limit = 0.10
        self.max_turnover = 1.00
        self.rebalance_tolerance = 0.05
    
    def check_stop_loss(self, portfolio):
        # 檢查止損觸發
        pass
    
    def calculate_position_size(self, signal, capital):
        # 計算倉位大小
        pass
```

---

### 3.2 自動交易模組（待開發）

**功能需求**：
- 下單介面：富邦證券 API / 元大證券 API
- 監控預警：Line Notify / Telegram Bot
- 績效追蹤：每日更新
- 異常處理：網路斷線、API 錯誤

---

### 3.3 實盤測試流程

**階段 1：紙上交易（1 個月）**
- 使用即時數據模擬交易
- 驗證系統穩定性
- 記錄滑價、流動性問題

**階段 2：小資金測試（3 個月）**
- 資金：10-30 萬
- 配置：30% v2 策略 + 70% 現金
- 目標：年化 >20%，回撤 <-15%

**階段 3：逐步加碼（3-6 個月）**
- 每月檢視績效
- 績效良好：加碼 10-20%
- 績效不佳：減碼或停止

---

## 快速檢查清單

### Priority 1 完成檢查 ✅
- [ ] v2 參數驗證通過（74.51% ± 2%）
- [ ] 涵蓋全年 12 個月（vs v1 的 159 天）
- [ ] v1 vs v2 對比報告生成
- [ ] 策略代碼更新為 v2 參數（可選）

### Priority 2 完成檢查 ✅
- [ ] 2022 年回測完成
- [ ] 2023 年回測完成
- [ ] 2024 年回測完成
- [ ] 多年平均年化 >30%
- [ ] 正報酬年數 ≥ 2/3
- [ ] 回測報告生成（JSON + Markdown）

### Priority 3 完成檢查 ✅
- [ ] 風控模組開發完成
- [ ] 自動交易模組開發完成
- [ ] 紙上交易測試通過
- [ ] 小資金實盤測試（3 個月）
- [ ] 績效監控系統建立

---

## 常見問題

### Q1: validate_best_params_v2.py 驗證失敗怎麼辦？

**A1**: 檢查以下項目：
1. MongoDB 是否運行中：`mongosh --eval "db.version()"`
2. 因子數據是否完整：`python3 scripts/check_factor_data.py`
3. 價格數據是否最新：`mongosh tw_stock_analysis --eval "db.stock_price.find().sort({date:-1}).limit(1)"`

如果數據不完整，執行：
```bash
python3 scripts/parallel_factor_calculation.py --workers 4 --start-date 2024-01-01 --end-date 2024-12-31
```

---

### Q2: backtest_historical.py 執行時間過長？

**A2**: 正常執行時間：
- 單年回測：20-30 分鐘
- 三年回測：60-90 分鐘

加速方法：
1. 確保因子數據已預先計算
2. 使用 SSD 硬碟
3. 增加 MongoDB 記憶體配置

---

### Q3: 如何選擇 v1 還是 v2？

**A3**: 建議決策樹：
```
風險承受度高 + 追求高報酬？
  → 是：採用 v2（74.51% 年化，10 支）
  → 否：採用 v1（54.18% 年化，18 支）或混合策略
```

**混合策略配置**：
- 50% v1（保守，18 支）
- 50% v2（進取，10 支）
- 預期年化：(54.18% + 74.51%) / 2 = 64.35%

---

### Q4: 歷史回測發現 2022 年負報酬怎麼辦？

**A4**: 正常現象：
- 2022 年台股下跌約 -20%
- 量化策略可能跑輸大盤
- 關鍵在於：
  1. 回撤是否控制在 -20% 內 ✅
  2. 2023-2024 是否快速恢復 ✅
  3. 多年平均是否 >20% ✅

---

## 聯絡資訊

**專案路徑**: `/Users/ming/Desktop/Stock/tw-stock-analysis`  
**文檔路徑**: `docs/chat_history.md`  
**報告路徑**: `reports/`  
**結果路徑**: `results/`

---

**最後更新**: 2026-02-23
