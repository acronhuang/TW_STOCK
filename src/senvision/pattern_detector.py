"""
SenVision 形態識別引擎（薄殼 — 相容層）

實作已於 Phase 3「上帝模組拆分」拆至 `senvision.patterns` 子套件：
- types.py        : PatternType / PatternStatus / Pattern
- base.py         : PatternDetector（共用邏輯：信心度/風報比/量能確認）
- w_bottom.py     : WBottomDetector（W 底）
- m_top.py        : MTopDetector（M 頭）
- triple_bottom.py: TripleBottomDetector（三重底）
- triple_top.py   : TripleTopDetector（三重頂）

本檔保留原 import 介面（`from senvision.pattern_detector import ...` 一律有效），
避免破壞既有呼叫端（analysis / scanner / chart_visualizer / __init__ 等）。

Author: SenVision Team
Date: 2026-02-24
"""

from .patterns import (
    MTopDetector,
    Pattern,
    PatternDetector,
    PatternStatus,
    PatternType,
    TripleBottomDetector,
    TripleTopDetector,
    WBottomDetector,
)

__all__ = [
    "PatternType", "PatternStatus", "Pattern", "PatternDetector",
    "WBottomDetector", "MTopDetector", "TripleBottomDetector", "TripleTopDetector",
]


if __name__ == '__main__':
    import sys
    from pathlib import Path

    import numpy as np
    import pandas as pd
    
    # 添加項目路徑
    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root / 'src'))
    
    print("="*80)
    print("形態識別引擎測試")
    print("="*80)
    
    # 生成測試數據 - W底形態
    np.random.seed(42)
    dates = pd.date_range('2024-01-01', periods=100, freq='D')
    
    # 創建 W 底形態
    prices = np.concatenate([
        np.linspace(100, 85, 20),   # 下跌至 L1
        np.linspace(85, 95, 15),    # 反彈至 H（頸線）
        np.linspace(95, 87, 20),    # 下跌至 L2
        np.linspace(87, 105, 45)    # 突破上漲
    ])
    
    df_test = pd.DataFrame({
        'date': dates,
        'open': prices,
        'high': prices + np.random.rand(100) * 2,
        'low': prices - np.random.rand(100) * 2,
        'close': prices,
        'volume': np.random.randint(1000000, 10000000, 100)
    })
    
    # 測試 W 底識別
    print("\n【測試 W 底識別】")
    detector_w = WBottomDetector()
    patterns_w = detector_w.detect(df_test, '2330')
    
    print(f"\n找到 {len(patterns_w)} 個 W 底形態:\n")
    for pattern in patterns_w:
        print(pattern)
        print(f"  關鍵點: {list(pattern.key_points.keys())}")
        print(f"  信心度: {pattern.confidence:.2%}")
        print()
    
    # 測試 M 頭識別
    print("\n【測試 M 頭識別】")
    # 創建 M 頭形態數據
    prices_m = np.concatenate([
        np.linspace(100, 120, 20),  # 上漲至 H1
        np.linspace(120, 105, 15),  # 下跌至 L（頸線）
        np.linspace(105, 118, 20),  # 上漲至 H2
        np.linspace(118, 95, 45)    # 跌破頸線
    ])
    
    df_test_m = pd.DataFrame({
        'date': dates,
        'open': prices_m,
        'high': prices_m + np.random.rand(100) * 2,
        'low': prices_m - np.random.rand(100) * 2,
        'close': prices_m,
        'volume': np.random.randint(1000000, 10000000, 100)
    })
    
    detector_m = MTopDetector()
    patterns_m = detector_m.detect(df_test_m, '2454')
    
    print(f"找到 {len(patterns_m)} 個 M 頭形態:\n")
    for pattern in patterns_m:
        print(pattern)
        print(f"  關鍵點: {list(pattern.key_points.keys())}")
        print(f"  信心度: {pattern.confidence:.2%}")
        print()
    
    print("✅ 測試完成")

