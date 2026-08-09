# 回測引擎與因子庫使用指南

## 📚 目錄

1. [回測引擎 (Backtesting Engine)](#回測引擎)
2. [因子庫 (Factor Library)](#因子庫)
3. [快速開始](#快速開始)
4. [進階用法](#進階用法)
5. [API 參考](#api-參考)

---

## 回測引擎

### 概述

回測引擎提供完整的策略回測功能，包含：
- **Portfolio**: 投資組合管理（持倉、現金、交易記錄）
- **Strategy**: 策略基類（可繼承實現自定義策略）
- **Backtest**: 回測執行引擎
- **PerformanceMetrics**: 績效指標計算

### 核心功能

#### 1. 績效指標
- 總報酬率、年化報酬率
- **夏普比率** (Sharpe Ratio)
- **最大回撤** (Maximum Drawdown)
- **Sortino Ratio**（下檔風險調整報酬）
- **Calmar Ratio**（年化報酬/最大回撤）
- 勝率、獲利因子

#### 2. 內建策略
- **MovingAverageCrossover**: 均線交叉策略
- **RSIMeanReversion**: RSI 均值回歸策略
- **ValueMomentum**: 價值-動能組合策略

### 快速範例

```python
from src.backtesting import Backtest
from src.backtesting.strategy import MovingAverageCrossover

# 建立策略
strategy = MovingAverageCrossover()
strategy.setup(short_window=5, long_window=20)

# 建立回測
backtest = Backtest(
    strategy=strategy,
    symbols=['2330', '2317'],  # 台積電、鴻海
    start_date='2024-01-01',
    end_date='2024-12-31',
    initial_cash=1_000_000
)

# 執行回測
results = backtest.run()

# 顯示績效
print(results['metrics'])

# 繪製權益曲線
backtest.plot_equity_curve(save_path='equity_curve.png')
```

---

## 因子庫

### 概述

因子庫提供系統化的量化因子計算和存儲功能，支援：
- **價值因子** (Value Factors)
- **動能因子** (Momentum Factors)
- **質量因子** (Quality Factors)

### 支援的因子

#### 價值因子
- `pe_ratio`: 本益比
- `pb_ratio`: 股價淨值比
- `dividend_yield`: 股息殖利率
- `earnings_yield`: 盈餘殖利率

#### 動能因子
- `return_1m`: 1 個月報酬率
- `return_3m`: 3 個月報酬率
- `return_6m`: 6 個月報酬率
- `return_12m`: 12 個月報酬率
- `rsi_14`: RSI (14日)
- `volatility_30d`: 30日波動率

#### 質量因子
- `roe`: 股東權益報酬率
- `roa`: 資產報酬率
- `profit_margin`: 淨利率
- `operating_margin`: 營益率
- `current_ratio`: 流動比率
- `debt_ratio`: 負債比率

### 快速範例

```python
from src.factors import FactorLibrary

# 建立因子庫
factor_lib = FactorLibrary()

# 計算並存儲因子
factor_lib.calculate_and_store(
    symbols=['2330', '2317', '2454'],
    start_date='2024-01-01',
    end_date='2024-12-31',
    factor_types=['value', 'momentum', 'quality']
)

# 查詢因子數據
factors = factor_lib.get_factors(
    symbol='2330',
    start_date='2024-01-01',
    end_date='2024-12-31'
)

# 取得橫斷面數據（某一天所有股票）
cross_section = factor_lib.get_cross_section(
    date='2024-12-31',
    factor_names=['pe_ratio', 'pb_ratio', 'roe']
)
```

---

## 快速開始

### 安裝依賴

```bash
# 基本依賴
pip install pymongo pandas numpy

# 繪圖功能（可選）
pip install matplotlib
```

### 範例腳本

系統提供三個完整的範例腳本：

#### 1. 回測引擎範例
```bash
python examples/backtest_example.py
```
展示如何使用回測引擎測試均線交叉策略。

#### 2. 因子庫範例
```bash
python examples/factor_example.py
```
展示如何計算、存儲和查詢量化因子。

#### 3. 多因子策略回測
```bash
python examples/multi_factor_backtest.py
```
結合因子庫與回測引擎，展示完整的量化投資工作流程。

---

## 進階用法

### 自定義策略

繼承 `Strategy` 基類實現自定義策略：

```python
from src.backtesting.strategy import Strategy
from datetime import datetime
from typing import Dict
import pandas as pd

class MyStrategy(Strategy):
    """我的自定義策略"""
    
    def __init__(self):
        super().__init__(name="My Custom Strategy")
    
    def setup(self, param1: int = 10, param2: float = 0.5):
        """設定策略參數"""
        self.param1 = param1
        self.param2 = param2
        self.params = {'param1': param1, 'param2': param2}
    
    def generate_signals(self, date: datetime, data: pd.DataFrame) -> Dict[str, str]:
        """
        生成交易信號
        
        Returns:
            {symbol: signal} 字典
            signal 可為: 'BUY', 'SELL', 'HOLD'
        """
        signals = {}
        
        # 實現您的策略邏輯
        for symbol in data['symbol'].unique():
            stock_data = data[data['symbol'] == symbol]
            # ... 分析邏輯 ...
            signals[symbol] = 'BUY'  # or 'SELL' or 'HOLD'
        
        return signals
```

### 多因子選股

結合因子庫實現多因子選股策略：

```python
from src.factors import FactorLibrary

class MultiFactorStrategy(Strategy):
    """多因子選股策略"""
    
    def setup(self):
        self.factor_lib = FactorLibrary()
    
    def generate_signals(self, date: datetime, data: pd.DataFrame):
        # 取得當日因子數據
        factors = self.factor_lib.get_cross_section(
            date=date.strftime('%Y-%m-%d'),
            factor_names=['pe_ratio', 'roe', 'return_3m']
        )
        
        # 根據因子評分選股
        # ... 選股邏輯 ...
        
        return signals
```

---

## API 參考

### Backtest 類

#### 初始化
```python
Backtest(
    strategy: Strategy,           # 策略物件
    symbols: List[str],           # 股票代碼列表
    start_date: str,              # 開始日期 (YYYY-MM-DD)
    end_date: str,                # 結束日期 (YYYY-MM-DD)
    initial_cash: float = 1000000,  # 初始資金
    position_size: float = 0.2,   # 單筆倉位（佔總資金比例）
    commission_rate: float = 0.003  # 手續費率
)
```

#### 主要方法
- `run()`: 執行回測，返回結果字典
- `summary()`: 列印回測摘要
- `plot_equity_curve(save_path)`: 繪製權益曲線

### FactorLibrary 類

#### 初始化
```python
FactorLibrary(
    mongo_uri: str = "mongodb://localhost:27017/",
    db_name: str = "tw_stock_analysis",
    collection_name: str = "stock_factors"
)
```

#### 主要方法
- `calculate_and_store(symbols, start_date, end_date, factor_types)`: 計算並存儲因子
- `get_factors(symbol, start_date, end_date)`: 查詢時間序列因子
- `get_cross_section(date, factor_names)`: 查詢橫斷面因子
- `calculate_factor_stats(factor_name, start_date, end_date)`: 計算因子統計量
- `list_available_factors()`: 列出所有可用因子

---

## 資料結構

### 績效指標 (PerformanceMetrics)

```python
{
    'total_return': 25.43,          # 總報酬率 (%)
    'annualized_return': 27.89,     # 年化報酬率 (%)
    'volatility': 18.52,            # 波動率 (%)
    'max_drawdown': -12.34,         # 最大回撤 (%)
    'sharpe_ratio': 1.45,           # 夏普比率
    'sortino_ratio': 2.01,          # Sortino Ratio
    'calmar_ratio': 2.26,           # Calmar Ratio
    'win_rate': 62.5,               # 勝率 (%)
    'profit_factor': 1.85,          # 獲利因子
    'total_trades': 40,             # 總交易次數
    'trading_days': 242             # 交易天數
}
```

### 因子數據

存儲在 `stock_factors` 集合：

```javascript
{
  symbol: "2330",
  date: ISODate("2024-12-31"),
  
  // 價值因子
  pe_ratio: 18.5,
  pb_ratio: 4.2,
  dividend_yield: 2.8,
  
  // 動能因子
  return_1m: 5.2,
  return_3m: 12.4,
  return_6m: 18.9,
  rsi_14: 55.3,
  
  // 質量因子
  roe: 25.3,
  roa: 12.8,
  profit_margin: 35.2
}
```

---

## 注意事項

1. **數據依賴**: 回測和因子計算依賴 MongoDB 中的 `stock_price` 和 `financial_reports` 數據
2. **計算效能**: 大量股票和長時間區間計算可能耗時，建議使用批次處理
3. **因子存儲**: 因子會存儲在 `stock_factors` 集合，避免重複計算
4. **手續費**: 台股實際交易成本約 0.3%（手續費 0.1425% × 2 + 證交稅 0.3%）

---

## 常見問題

### Q: 如何加速因子計算？
A: 使用 `batch_size` 參數調整批次大小，或平行處理多個股票。

### Q: 如何自定義評價指標？
A: 繼承 `PerformanceMetrics` 類，添加自定義指標計算方法。

### Q: 因子數據如何更新？
A: 定期執行 `calculate_and_store()`，使用 `upsert=True` 自動更新。

### Q: 回測結果如何匯出？
A: 使用 `results['equity_curve'].to_csv('output.csv')` 匯出 CSV。

---

## 相關文件

- [PROJECT_GUIDE.md](../PROJECT_GUIDE.md) - 專案整體架構
- [DATABASE_QUICK_REFERENCE.md](../DATABASE_QUICK_REFERENCE.md) - 資料庫結構
- [QUICK_START.md](../QUICK_START.md) - 快速開始指南

---

**開發時間**: 2026-02-22  
**版本**: 1.0.0  
**作者**: Claude & Ming
