#!/usr/bin/env python3
"""
診斷回測問題
"""

import sys
from pathlib import Path
from datetime import datetime
import pandas as pd

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from examples.multifactor_strategy import MultiFactorStrategy
from examples.backtest_multifactor import MultiFactorBacktest

# 測試：生成信號並回測
strategy = MultiFactorStrategy()

start_date = datetime(2024, 1, 1)
end_date = datetime(2024, 12, 31)

print("生成交易信號...")
signals = strategy.generate_signals(
    start_date=start_date,
    end_date=end_date,
    rebalance_freq='ME',
    top_n=20
)

print(f"\n信號數量: {len(signals)}")
print(f"信號樣本:\n{signals.head(10)}")
print(f"\n信號 dtypes:\n{signals.dtypes}")

if not signals.empty:
    print("\n執行回測...")
    backtest = MultiFactorBacktest()
    
    try:
        metrics = backtest.run(signals_df=signals)
        print(f"\n回測指標:")
        print(f"類型: {type(metrics)}")
        for key, value in metrics.items():
            print(f"  {key}: {value} (type: {type(value)})")
    except Exception as e:
        print(f"\n回測失敗: {e}")
        import traceback
        traceback.print_exc()
else:
    print("\n無法生成信號")
