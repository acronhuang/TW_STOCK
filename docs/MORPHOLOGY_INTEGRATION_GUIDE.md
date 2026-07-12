# 形態學模組整合指南 (v2.1)

**版本**: v2.1.0  
**創建日期**: 2026-02-23  
**適用對象**: 希望將形態學整合到現有量化系統的開發者

---

## 概述

本指南說明如何將蔡森形態學模組整合到 v2.0 量化交易系統中，實現 v2.1 升級。

**核心改變**:
```
v2.0: 17 因子綜合評分 → 直接選出 10 支
v2.1: 17 因子初選 30 支 → 形態過濾 → 最終 10 支
```

---

## 快速開始（5 分鐘）

### 1. 驗證模組可用性

```bash
cd /Users/ming/Desktop/Stock/tw-stock-analysis

# 快速測試（1 分鐘）
python3 scripts/quick_test_morphology.py

# 完整驗證（5-10 分鐘）
python3 scripts/validate_patterns.py
```

**預期輸出**:
```
✅ 所有測試通過！形態學模組運作正常。
```

---

### 2. 基本使用範例

```python
from src.morphology import PatternDetector
import pandas as pd

# 初始化偵測器
detector = PatternDetector()

# 假設你已有股價數據（從 MongoDB 讀取）
# df = get_stock_data("2330")  # 你的函數

# 執行偵測
results = detector.detect_all(df, stock_id="2330")

# 查看結果
print(detector.generate_summary(df, stock_id="2330"))

# 計算綜合評分
score = detector.calculate_overall_score(df, lookback_days=5)

if score >= 0.7:
    print(f"✓ 推薦進場！評分: {score:.3f}")
```

---

## 整合路徑

### 方案 1: 最小改動（推薦新手）

在現有 `multifactor_strategy_v2.py` 中加入形態檢查：

```python
# 在 src/strategy/multifactor_strategy_v2.py 的 select_stocks 方法中

def select_stocks(self, rebalance_date, top_n=10):
    """選股（v2.0 原始方法）"""
    
    # ... 原本的 17 因子計算 ...
    candidates = self.calculate_composite_scores(rebalance_date)
    
    # ====== 新增：形態過濾 ======
    from src.morphology import PatternDetector
    
    detector = PatternDetector()
    
    # 讀取候選股數據
    stocks_data = {}
    for stock_id, factor_score in candidates[:30]:  # 擴展到 30 支候選
        df = self.get_stock_data(stock_id, days=120)
        if df is not None:
            stocks_data[stock_id] = df
    
    # 形態過濾
    filtered = detector.filter_stocks(
        stocks_data,
        min_patterns=1,      # 至少 1 個形態
        min_score=0.5,       # 最低評分 0.5
        lookback_days=5
    )
    
    # 選出前 10 支
    final_stocks = [(stock_id, score) for stock_id, score, _ in filtered[:top_n]]
    
    return final_stocks
```

---

### 方案 2: 創建新策略檔（推薦進階）

創建 `src/strategy/integrated_strategy_v21.py`：

```python
"""
v2.1 整合策略：17 因子 + 形態學

整合蔡森形態學的量化選股策略。
"""

from src.strategy.multifactor_strategy_v2 import MultiFactorStrategy
from src.morphology import PatternDetector, calculate_position_weight


class IntegratedStrategyV21(MultiFactorStrategy):
    """v2.1 整合策略"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.pattern_detector = PatternDetector()
    
    def select_stocks(self, rebalance_date, candidate_n=30, final_n=10):
        """
        兩階段選股
        
        Args:
            rebalance_date: 調倉日期
            candidate_n: 候選股數量（17 因子選出）
            final_n: 最終持股數量（形態過濾後）
        
        Returns:
            List[(股票代碼, 倉位權重, 形態評分), ...]
        """
        
        # Step 1: 17 因子初選
        candidates = super().select_stocks(rebalance_date, top_n=candidate_n)
        print(f"✓ 17 因子選出 {len(candidates)} 支候選股")
        
        # Step 2: 讀取候選股數據
        stocks_data = {}
        for stock_id, factor_score in candidates:
            df = self.get_stock_data(stock_id, days=120)
            if df is not None:
                stocks_data[stock_id] = df
        
        # Step 3: 形態過濾
        filtered = self.pattern_detector.filter_stocks(
            stocks_data,
            min_patterns=1,
            min_score=0.5,
            lookback_days=5
        )
        print(f"✓ 形態過濾後剩 {len(filtered)} 支")
        
        # Step 4: 選出 final_n 支
        selected = filtered[:final_n]
        
        # Step 5: 計算倉位權重（根據形態評分調整）
        positions = []
        for stock_id, pattern_score, patterns in selected:
            base_weight = 1.0 / final_n
            adjusted_weight = calculate_position_weight(
                base_weight, pattern_score, max_boost=1.2
            )
            positions.append((stock_id, adjusted_weight, pattern_score))
        
        # Step 6: 歸一化權重
        total_weight = sum(w for _, w, _ in positions)
        positions = [(s, w/total_weight, p) for s, w, p in positions]
        
        return positions
    
    def check_exit_signals(self, holdings, current_date):
        """
        檢查出場訊號（形態破壞 + 原有邏輯）
        
        Args:
            holdings: {股票代碼: (持股數, 進場價, 進場日期)}
            current_date: 當前日期
        
        Returns:
            List[股票代碼]: 需要出場的股票
        """
        from src.morphology.bottom_reversal import check_pattern_breakdown
        from src.morphology.volume_analysis import detect_volume_price_divergence
        
        exit_signals = []
        
        for stock_id, (shares, entry_price, entry_date) in holdings.items():
            # 讀取數據
            df = self.get_stock_data(stock_id, days=60)
            if df is None:
                continue
            
            current_price = df['close'].iloc[-1]
            
            # 檢查形態破壞
            # 假設原本以破底翻進場，檢查是否跌破支撐線
            support_line = df['low'].rolling(20).min().iloc[-1]
            
            is_broken, reason = check_pattern_breakdown(
                current_price,
                support_line,
                entry_price,
                df['close'].tail(3),
                df['volume'].tail(3)
            )
            
            if is_broken:
                print(f"⚠️  {stock_id} 形態破壞: {reason}")
                exit_signals.append(stock_id)
                continue
            
            # 檢查量價背離（負背離，看跌）
            signal, _ = detect_volume_price_divergence(df)
            
            if signal.iloc[-1]:
                print(f"⚠️  {stock_id} 量價背離（減倉 50%）")
                exit_signals.append(stock_id)
        
        return exit_signals
```

**使用新策略**:

```python
from src.strategy.integrated_strategy_v21 import IntegratedStrategyV21

strategy = IntegratedStrategyV21()

# 執行回測
backtest_engine = BacktestEngine(strategy)
backtest_engine.run(start_date='2023-01-01', end_date='2024-06-30')
```

---

### 方案 3: 完整 FinMind 整合（終極版）

參考 [PRD v2.1](../PRD_v2.1_FinMind_Morphology.md) 第 9 章「實施路徑」：

**Week 1-2**: FinMind 數據對接
**Week 3-4**: 形態辨識引擎（已完成）
**Week 5-6**: 籌碼分析整合
**Week 7-8**: 策略整合與回測
**Week 9-10**: 參數優化
**Week 11-12**: 風控升級

---

## 關鍵整合點

### 1. 選股流程整合

```python
def integrated_selection_v21(rebalance_date):
    """v2.1 選股流程"""
    
    # 1. 17 因子初選（30 支）
    candidates = select_by_17_factors(rebalance_date, top_n=30)
    
    # 2. 形態過濾（10 支）
    detector = PatternDetector()
    final_stocks = detector.filter_stocks(
        candidates,
        min_patterns=1,
        min_score=0.6
    )
    
    # 3. 倉位分配（根據形態評分調整）
    positions = calculate_positions_with_pattern_score(final_stocks)
    
    return positions
```

---

### 2. 出場邏輯整合

```python
def check_exit_with_pattern(stock_id, entry_price, current_price, df):
    """整合形態破壞的出場判斷"""
    
    # 原有的固定停損
    if current_price / entry_price - 1 <= -0.08:
        return True, "固定停損 -8%"
    
    # 新增：形態破壞
    from src.morphology.bottom_reversal import check_pattern_breakdown
    
    support_line = df['low'].rolling(20).min().iloc[-1]
    is_broken, reason = check_pattern_breakdown(
        current_price,
        support_line,
        entry_price,
        df['close'].tail(3),
        df['volume'].tail(3)
    )
    
    if is_broken:
        return True, f"形態破壞: {reason}"
    
    # 新增：量價背離
    from src.morphology.volume_analysis import detect_volume_price_divergence
    
    signal, _ = detect_volume_price_divergence(df)
    if signal.iloc[-1]:
        return True, "量價背離（減倉 50%）"
    
    return False, None
```

---

### 3. 數據結構整合

如需將形態特徵存入資料庫（PostgreSQL）：

```sql
-- 擴展 daily_market_data 表
ALTER TABLE daily_market_data
ADD COLUMN is_bottom_reversal BOOLEAN DEFAULT FALSE,
ADD COLUMN is_w_bottom BOOLEAN DEFAULT FALSE,
ADD COLUMN is_neckline_breakout BOOLEAN DEFAULT FALSE,
ADD COLUMN pattern_score NUMERIC(3, 2),
ADD COLUMN pattern_details JSONB;
```

```python
# 每日計算並存儲形態
def daily_pattern_calculation():
    from src.morphology import PatternDetector
    
    detector = PatternDetector()
    
    for stock_id in get_all_stocks():
        df = get_stock_data(stock_id, days=120)
        results = detector.detect_all(df)
        
        # 存入資料庫
        for pattern_name, result in results.items():
            if result['detected']:
                update_database(
                    stock_id,
                    pattern_name,
                    result['score'],
                    result['latest']
                )
```

---

## 回測驗證

### 1. 驗證形態有效性

```bash
# 驗證形態偵測準確性
python3 scripts/validate_patterns.py
```

### 2. 完整回測

```bash
# 回測形態策略
python3 scripts/backtest_patterns.py
```

### 3. 對比回測（v2.0 vs v2.1）

創建 `scripts/compare_v20_v21.py`：

```python
from src.strategy.multifactor_strategy_v2 import MultiFactorStrategy
from src.strategy.integrated_strategy_v21 import IntegratedStrategyV21

# 回測 v2.0
strategy_v20 = MultiFactorStrategy()
result_v20 = backtest(strategy_v20, '2023-01-01', '2024-06-30')

# 回測 v2.1
strategy_v21 = IntegratedStrategyV21()
result_v21 = backtest(strategy_v21, '2023-01-01', '2024-06-30')

# 對比
print(f"v2.0 年化報酬: {result_v20['annual_return']:.2%}")
print(f"v2.1 年化報酬: {result_v21['annual_return']:.2%}")
print(f"v2.0 夏普比率: {result_v20['sharpe']:.3f}")
print(f"v2.1 夏普比率: {result_v21['sharpe']:.3f}")
```

---

## 參數調優建議

### 形態靈敏度調整

**嚴格模式**（減少假訊號）：
```python
detector = PatternDetector()

# 破底翻：更嚴格
signal, details = detect_bottom_reversal(
    df,
    recovery_days=3,      # 縮短到 3 天
    volume_ratio=2.0,     # 提高到 2 倍
    recovery_threshold=1.03  # +3%
)
```

**寬鬆模式**（增加機會）：
```python
# 破底翻：更寬鬆
signal, details = detect_bottom_reversal(
    df,
    recovery_days=7,      # 延長到 7 天
    volume_ratio=1.2,     # 降低到 1.2 倍
    recovery_threshold=1.01  # +1%
)
```

### 權重優化

根據回測結果調整形態權重：

```python
detector = PatternDetector(
    custom_weights={
        'bottom_reversal': 0.40,      # 若勝率最高，提高權重
        'w_bottom': 0.25,
        'neckline_breakout': 0.25,
        'volume_surge': 0.10
    }
)
```

---

## 常見問題

### Q1: 形態偵測太敏感，出現很多訊號？

**A**: 提高閾值：

```python
# 提高最低評分
filtered = detector.filter_stocks(
    stocks_data,
    min_patterns=2,      # 至少 2 個形態
    min_score=0.7        # 提高到 0.7
)
```

### Q2: 形態偵測太保守，幾乎沒有訊號？

**A**: 降低閾值或放寬參數：

```python
# 降低最低評分
filtered = detector.filter_stocks(
    stocks_data,
    min_patterns=1,
    min_score=0.4        # 降低到 0.4
)

# 或放寬形態參數（參考「參數調優建議」）
```

### Q3: 整合後績效沒有提升？

**A**: 可能原因：
1. 參數未調優（需針對歷史數據調整）
2. 形態權重不合理（根據回測調整）
3. 樣本期間特殊（Walk-forward 測試）
4. 過擬合風險（Out-of-sample 驗證）

**建議**: 執行 Walk-forward 測試：

```python
# 分段回測
periods = [
    ('2022-01-01', '2022-06-30'),  # In-sample（調參）
    ('2022-07-01', '2022-12-31'),  # Out-of-sample（驗證）
    ('2023-01-01', '2023-06-30'),  # In-sample
    ('2023-07-01', '2023-12-31'),  # Out-of-sample
]

for start, end, type in periods:
    result = backtest(strategy, start, end)
    print(f"{type} ({start}~{end}): {result['return']:.2%}")
```

---

## 下一步

1. **測試基本功能**:
   ```bash
   python3 scripts/quick_test_morphology.py
   ```

2. **閱讀使用手冊**:
   ```bash
   open docs/MORPHOLOGY_MANUAL.md
   ```

3. **執行回測驗證**:
   ```bash
   python3 scripts/backtest_patterns.py
   ```

4. **整合到系統**:
   - 方案 1: 最小改動（修改現有策略）
   - 方案 2: 創建新策略（`integrated_strategy_v21.py`）
   - 方案 3: 完整 FinMind 整合（參考 PRD v2.1）

5. **調優與驗證**:
   - Walk-forward 測試
   - Out-of-sample 驗證
   - 參數敏感性分析

---

**相關文件**:
- [PRD v2.1](../PRD_v2.1_FinMind_Morphology.md) - 完整產品需求文件
- [使用手冊](MORPHOLOGY_MANUAL.md) - 形態學詳細說明
- [驗證腳本](../scripts/validate_patterns.py) - 形態驗證
- [回測腳本](../scripts/backtest_patterns.py) - 策略回測

---

**結束** | 有任何問題請查閱 [使用手冊](MORPHOLOGY_MANUAL.md)
