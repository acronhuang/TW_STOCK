#!/usr/bin/env python3
"""
系統驗證腳本 - 驗證回測引擎和因子庫功能

執行: python3 scripts/test_backtesting_factors.py
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_imports():
    """測試模組導入"""
    print("="*80)
    print("測試 1: 模組導入")
    print("="*80)
    
    try:
        from src.backtesting import Portfolio, Strategy, Backtest, PerformanceMetrics
        from src.backtesting.strategy import MovingAverageCrossover, RSIMeanReversion, ValueMomentum
        from src.factors import FactorLibrary, ValueFactors, MomentumFactors, QualityFactors
        
        print("✅ 所有模組導入成功")
        print()
        print("回測引擎:")
        print("  - Portfolio: 投資組合管理")
        print("  - Strategy: 策略基類")
        print("  - Backtest: 回測執行引擎")
        print("  - PerformanceMetrics: 績效指標")
        print()
        print("內建策略:")
        print("  - MovingAverageCrossover: 均線交叉")
        print("  - RSIMeanReversion: RSI 均值回歸")
        print("  - ValueMomentum: 價值-動能組合")
        print()
        print("因子庫:")
        print("  - FactorLibrary: 統一介面")
        print("  - ValueFactors: 價值因子")
        print("  - MomentumFactors: 動能因子")
        print("  - QualityFactors: 質量因子")
        print()
        return True
    except Exception as e:
        print(f"❌ 導入失敗: {e}")
        return False

def test_portfolio():
    """測試投資組合管理"""
    print("="*80)
    print("測試 2: Portfolio 功能")
    print("="*80)
    
    try:
        from src.backtesting import Portfolio
        from datetime import datetime
        
        # 建立組合
        portfolio = Portfolio(initial_cash=1_000_000, commission_rate=0.003)
        
        # 模擬交易
        date = datetime(2024, 1, 1)
        
        # 買入
        success = portfolio.buy(date, '2330', 1000, 500.0)
        assert success, "買入失敗"
        
        # 賣出
        success = portfolio.sell(date, '2330', 500, 520.0)
        assert success, "賣出失敗"
        
        # 記錄權益
        portfolio.record_equity(date, {'2330': 520.0})
        
        print("✅ Portfolio 功能正常")
        print()
        print(f"初始資金: {portfolio.initial_cash:,.0f}")
        print(f"剩餘現金: {portfolio.cash:,.2f}")
        print(f"持倉數量: {len(portfolio.positions)}")
        print(f"交易筆數: {len(portfolio.trades)}")
        print(f"權益記錄: {len(portfolio.equity_curve)}")
        print()
        return True
    except Exception as e:
        print(f"❌ Portfolio 測試失敗: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_strategy():
    """測試策略功能"""
    print("="*80)
    print("測試 3: Strategy 功能")
    print("="*80)
    
    try:
        from src.backtesting.strategy import MovingAverageCrossover
        import pandas as pd
        from datetime import datetime
        
        # 建立策略
        strategy = MovingAverageCrossover()
        strategy.setup(short_window=5, long_window=20)
        
        # 模擬數據
        dates = pd.date_range('2024-01-01', '2024-01-30')
        data = pd.DataFrame({
            'date': dates,
            'symbol': '2330',
            'adj_close': range(100, 100 + len(dates))
        })
        
        # 生成信號
        signals = strategy.generate_signals(dates[-1], data)
        
        print("✅ Strategy 功能正常")
        print()
        print(f"策略名稱: {strategy.name}")
        print(f"參數: {strategy.params}")
        print(f"信號數量: {len(signals)}")
        print()
        return True
    except Exception as e:
        print(f"❌ Strategy 測試失敗: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_factor_library():
    """測試因子庫功能"""
    print("="*80)
    print("測試 4: Factor Library 連接")
    print("="*80)
    
    try:
        from src.factors import FactorLibrary
        
        # 建立因子庫
        factor_lib = FactorLibrary()
        
        # 測試連接
        collection_name = factor_lib.collection.name
        
        # 列出現有因子
        available = factor_lib.list_available_factors()
        
        print("✅ Factor Library 連接成功")
        print()
        print(f"集合名稱: {collection_name}")
        print(f"現有因子數: {len(available)}")
        
        if available:
            print(f"可用因子:")
            for factor in available[:10]:
                print(f"  - {factor}")
        else:
            print("  (尚無因子數據，需執行計算)")
        
        print()
        return True
    except Exception as e:
        print(f"⚠️  Factor Library 連接失敗: {e}")
        print("  提示: 確保 MongoDB 正在運行")
        print()
        return False

def test_performance_metrics():
    """測試績效指標計算"""
    print("="*80)
    print("測試 5: Performance Metrics")
    print("="*80)
    
    try:
        from src.backtesting.performance import PerformanceCalculator
        from datetime import datetime, timedelta
        
        # 模擬權益曲線
        equity_curve = []
        base_date = datetime(2024, 1, 1)
        initial_cash = 1_000_000
        
        for i in range(252):  # 一年交易日
            equity = initial_cash * (1 + 0.0001 * i)  # 模擬增長
            equity_curve.append({
                'date': base_date + timedelta(days=i),
                'equity': equity
            })
        
        # 計算績效
        metrics = PerformanceCalculator.calculate(
            equity_curve=equity_curve,
            trades=[],
            initial_cash=initial_cash
        )
        
        print("✅ Performance Metrics 計算成功")
        print()
        print(f"總報酬率: {metrics.total_return:.2f}%")
        print(f"年化報酬率: {metrics.annualized_return:.2f}%")
        print(f"夏普比率: {metrics.sharpe_ratio:.3f}")
        print(f"最大回撤: {metrics.max_drawdown:.2f}%")
        print()
        return True
    except Exception as e:
        print(f"❌ Performance Metrics 測試失敗: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("\n")
    print("╔" + "="*78 + "╗")
    print("║" + " "*20 + "回測引擎與因子庫系統驗證" + " "*20 + "║")
    print("╚" + "="*78 + "╝")
    print()
    
    results = []
    
    # 執行測試
    results.append(("模組導入", test_imports()))
    results.append(("Portfolio", test_portfolio()))
    results.append(("Strategy", test_strategy()))
    results.append(("Factor Library", test_factor_library()))
    results.append(("Performance Metrics", test_performance_metrics()))
    
    # 總結
    print()
    print("="*80)
    print("測試總結")
    print("="*80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ 通過" if result else "❌ 失敗"
        print(f"{status:8s} {name}")
    
    print()
    print(f"通過率: {passed}/{total} ({passed/total*100:.1f}%)")
    print()
    
    if passed == total:
        print("🎉 所有測試通過！系統已準備就緒")
        print()
        print("下一步:")
        print("1. 執行回測範例: python3 examples/backtest_example.py")
        print("2. 計算因子: python3 examples/factor_example.py")
        print("3. 多因子策略: python3 examples/multi_factor_backtest.py")
    else:
        print("⚠️  部分測試失敗，請檢查錯誤訊息")
    
    print()
    print("="*80)

if __name__ == "__main__":
    main()
