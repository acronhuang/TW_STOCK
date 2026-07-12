# v2.1 系統執行指南

**生成時間**: 2026-02-23  
**狀態**: 核心模組已完成，等待執行

---

## ✅ 已完成任務

### 1. 核心模組創建
- ✅ 12 週執行計劃（[docs/FINMIND_INTEGRATION_12_WEEK_PLAN.md](docs/FINMIND_INTEGRATION_12_WEEK_PLAN.md)）
- ✅ FinMind 數據同步腳本（[scripts/finmind_full_sync.py](scripts/finmind_full_sync.py)）
- ✅ 數據驗證腳本（[scripts/validate_finmind_data.py](scripts/validate_finmind_data.py)）
- ✅ 每日自動更新腳本（[scripts/finmind_daily_update.py](scripts/finmind_daily_update.py)）
- ✅ 籌碼分析模組（[src/chip_analysis/__init__.py](src/chip_analysis/__init__.py)）
- ✅ v2.1 整合策略（[src/strategy/integrated_strategy_v21.py](src/strategy/integrated_strategy_v21.py)）
- ✅ v2.1 回測腳本（[scripts/backtest_integrated_v21.py](scripts/backtest_integrated_v21.py)）
- ✅ Week 9-10 參數優化腳本（[scripts/optimize_v21_params.py](scripts/optimize_v21_params.py)）
- ✅ 參數敏感性分析腳本（[scripts/analyze_parameter_sensitivity.py](scripts/analyze_parameter_sensitivity.py)）
- ✅ Cron Job 設置腳本（[scripts/setup_daily_cron.sh](scripts/setup_daily_cron.sh)、[scripts/daily_update_cron.sh](scripts/daily_update_cron.sh)）

---

## 🚀 立即執行任務（按優先級）

### 任務 1: 完成 FinMind 首次完整同步（高優先級）⏰

**當前狀態**: 腳本正在運行，等待用戶確認

**步驟**:
```bash
# FinMind 同步腳本已在後台運行，正在等待確認
# 請在 Terminal ID: 71b1e582-255f-4581-bdf6-c4787fb053b0 中輸入 "yes"

# 或者重新啟動同步（如果上一個已終止）：
cd /Users/ming/Desktop/Stock/tw-stock-analysis
export FINMIND_API_TOKEN=""

# 執行完整同步（預計 2-4 小時）
python3 scripts/finmind_full_sync.py --initial 2>&1 | tee logs/finmind_full_sync_$(date +%Y%m%d_%H%M%S).log
```

**預計時間**: 2-4 小時  
**注意事項**:
- 將下載 3,065 支股票 × 5 年的數據
- 6 個數據集：stock_price, financial, holdings, per, dividend, institutional_trading
- 建議在網路穩定時執行
- 可以在背景執行，不影響其他操作

**驗證**:
```bash
# 完成後驗證數據品質
python3 scripts/validate_finmind_data.py
```

---

### 任務 2: 設置每日自動更新（中優先級）📅

**步驟**:
```bash
cd /Users/ming/Desktop/Stock/tw-stock-analysis

# 方法 1: 手動設置 crontab
crontab -e

# 加入以下行（每週一至週五 15:30 執行）：
# FinMind 每日自動更新（週一至週五 15:30）
30 15 * * 1-5 /Users/ming/Desktop/Stock/tw-stock-analysis/scripts/daily_update_cron.sh

# 方法 2: 使用命令直接設置
(crontab -l 2>/dev/null | grep -v "daily_update_cron.sh"; \
 echo "# FinMind 每日自動更新"; \
 echo "30 15 * * 1-5 /Users/ming/Desktop/Stock/tw-stock-analysis/scripts/daily_update_cron.sh") | crontab -
```

**驗證**:
```bash
# 查看 crontab
crontab -l | grep finmind

# 測試執行
/Users/ming/Desktop/Stock/tw-stock-analysis/scripts/daily_update_cron.sh

# 查看日誌
ls -lt logs/daily_updates/ | head -5
```

**時間選項**:
- 每天 16:00: `0 16 * * *`
- 每天 20:00: `0 20 * * *`
- 每 4 小時: `0 */4 * * *`

---

### 任務 3: 執行 v2.0 vs v2.1 回測對比（高優先級）📊

**前置條件**: 完成 FinMind 數據同步

**步驟**:
```bash
cd /Users/ming/Desktop/Stock/tw-stock-analysis

# 執行完整回測（2022-2024，3 年）
python3 scripts/backtest_integrated_v21.py \
    --start-date 2022-01-01 \
    --end-date 2024-12-31 \
    --initial-capital 10000000 \
    --rebalance-frequency monthly \
    --output results/backtest_v21_results_$(date +%Y%m%d).json

# 預計時間：30-60 分鐘
```

**輸出範例**:
```
========================================
績效對比報告
========================================
指標                v2.0           v2.1         改善
----------------------------------------
總報酬            95.32%        120.45%       +26.3%
年化報酬          39.32%         45.67%       +16.1%
夏普比率           1.305          1.825       +39.8%
最大回撤         -14.37%        -11.25%       +21.7%
勝率              62.5%          71.3%        +14.1%
```

**結果分析**:
```bash
# 查看詳細結果
cat results/backtest_v21_results_*.json | jq '.v2.1.metrics'

# 查看交易記錄
cat results/backtest_v21_results_*.json | jq '.v2.1.trades[] | select(.action == "sell")' | head -20
```

---

### 任務 4: 執行參數優化（可選，耗時較長）🔬

**前置條件**: 完成回測驗證

**步驟**:
```bash
cd /Users/ming/Desktop/Stock/tw-stock-analysis

# 執行參數優化（預計 12-24 小時）
python3 scripts/optimize_v21_params.py \
    --start-date 2023-01-01 \
    --end-date 2024-12-31 \
    --population 50 \
    --generations 50 \
    --workers 4 \
    --mutation-rate 0.1 \
    --crossover-rate 0.7 \
    --output results/v21_optimization_$(date +%Y%m%d).json \
    2>&1 | tee logs/optimization_v21_$(date +%Y%m%d_%H%M%S).log &

# 查看進度
tail -f logs/optimization_v21_*.log

# 完成後進行敏感性分析
python3 scripts/analyze_parameter_sensitivity.py \
    --params results/v21_optimization_*.json \
    --start-date 2023-01-01 \
    --end-date 2024-12-31 \
    --test-points 10 \
    --output results/parameter_sensitivity_$(date +%Y%m%d).json \
    --plot
```

**優化配置**:
- 人口大小: 50（建議範圍 30-100）
- 世代數: 50（建議範圍 30-100）
- 並行工作數: 4（根據 CPU 核心數調整）
- 突變率: 0.1（建議範圍 0.05-0.2）
- 交叉率: 0.7（建議範圍 0.6-0.8）

---

## 📊 系統架構總覽

```
v2.1 整合策略系統
│
├─ 數據層
│  ├─ FinMind API（股價、財報、籌碼）
│  ├─ MongoDB（數據存儲）
│  └─ 每日自動更新（cron job）
│
├─ 分析層
│  ├─ 17 因子分析（v2.0 基礎）
│  ├─ 形態學分析（5 個形態偵測器）
│  └─ 籌碼分析（大戶持股 + 法人買賣 + 主力偵測）
│
├─ 策略層
│  ├─ Stage 1: 17 因子初選（30 支）
│  ├─ Stage 2: 形態過濾（15-20 支）
│  ├─ Stage 3: 籌碼確認（10-15 支）
│  └─ Stage 4: 綜合排名與倉位配置（10 支）
│
├─ 風控層
│  ├─ 固定停損 -8%
│  ├─ 形態破壞出場
│  ├─ 量價背離出場
│  └─ 主力出貨出場
│
└─ 優化層
   ├─ 遺傳算法參數優化（40+ 參數）
   └─ 敏感性分析
```

---

## 🎯 預期績效目標（v2.1）

| 指標 | v2.0 | v2.1 目標 | 改善 |
|------|------|----------|------|
| **年化報酬** | 39.32% | **45%+** | +15% |
| **夏普比率** | 1.305 | **1.8+** | +38% |
| **勝率** | 62.5% | **70%+** | +12% |
| **最大回撤** | -14.37% | **-12%** | -16% |

---

## 📝 檢查清單

### 數據準備
- [ ] 完成 FinMind 首次完整同步（2-4 小時）
- [ ] 驗證數據品質（覆蓋率 > 95%）
- [ ] 設置每日自動更新

### 策略驗證
- [ ] 執行 v2.0 vs v2.1 回測對比（30-60 分鐘）
- [ ] 分析績效差異
- [ ] 檢查選股邏輯與出場邏輯

### 參數優化（可選）
- [ ] 執行遺傳算法優化（12-24 小時）
- [ ] 進行敏感性分析
- [ ] 更新最佳參數配置

### 監控與維護
- [ ] 驗證 cron job 運行
- [ ] 檢查每日更新日誌
- [ ] 設置告警機制（可選）

---

## 🔧 常見問題

### Q1: FinMind API 限制怎麼辦？
**A**: 
- 免費版：每日 1,000 次調用
- Premium 版：$99/月，無限次調用
- 建議：首次同步時升級 Premium，或分多日完成

### Q2: 回測時間過長怎麼辦？
**A**:
- 縮短回測期間（如 1 年 instead of 3 年）
- 減少再平衡頻率（如 quarterly instead of monthly）
- 使用更少股票數（調整 stage1_top_n）

### Q3: 參數優化需要多久？
**A**:
- 人口 50，世代 50：約 12-24 小時
- 人口 30，世代 30：約 6-12 小時
- 人口 20，世代 20：約 3-6 小時
- 建議：先用小規模測試，再執行完整優化

### Q4: 如何查看系統狀態？
**A**:
```bash
# 數據狀態
python3 scripts/validate_finmind_data.py

# Cron job 狀態
crontab -l | grep finmind
ls -lt logs/daily_updates/ | head -5

# MongoDB 狀態
mongosh tw_stock_analysis --quiet --eval "
print('stock_price:', db.stock_price.countDocuments({}));
print('institutional_holdings:', db.institutional_holdings.countDocuments({}));
print('institutional_trading:', db.institutional_trading.countDocuments({}));
"
```

---

## 📚 相關文檔

- **12 週執行計劃**: [docs/FINMIND_INTEGRATION_12_WEEK_PLAN.md](docs/FINMIND_INTEGRATION_12_WEEK_PLAN.md)
- **完成報告**: [FINMIND_INTEGRATION_COMPLETE_REPORT.md](FINMIND_INTEGRATION_COMPLETE_REPORT.md)
- **形態學手冊**: [docs/MORPHOLOGY_MANUAL.md](docs/MORPHOLOGY_MANUAL.md)
- **形態學整合指南**: [docs/MORPHOLOGY_INTEGRATION_GUIDE.md](docs/MORPHOLOGY_INTEGRATION_GUIDE.md)
- **PRD v2.1**: [PRD_v2.1_FinMind_Morphology.md](PRD_v2.1_FinMind_Morphology.md)

---

## 🎉 總結

所有核心模組已完成！現在可以：

1. **立即執行**:
   - ✅ 確認 FinMind 數據同步（輸入 "yes"）
   - ✅ 設置 cron job 每日更新
   - ⏳ 等待數據同步完成（2-4 小時）

2. **數據同步完成後**:
   - 執行 v2.0 vs v2.1 回測對比
   - 驗證策略績效

3. **可選**:
   - 執行參數優化（12-24 小時）
   - 進行敏感性分析

**從 v2.0（74.51%）到 v2.1（45%+ 目標）的完整系統已建立！** 🚀

---

**最後更新**: 2026-02-23  
**狀態**: 等待執行
