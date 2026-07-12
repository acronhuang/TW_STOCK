#!/usr/bin/env python3
"""
驗證 v2 優化的最佳參數

從 optimization_results_v2.json 中提取第 25 代的最佳參數，進行完整回測驗證
"""

import sys
from pathlib import Path
from datetime import datetime
import json

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from examples.multifactor_strategy import MultiFactorStrategy
from examples.backtest_multifactor import MultiFactorBacktest


# v2 第 25 代最佳參數
BEST_PARAMS_V2 = {
    'momentum_weight': 0.46616470870580645,
    'value_weight': 0.3271613464744718,
    'quality_weight': 0.2066739448197218,
    'return_3m_weight': 0.240608572516088,
    'return_6m_weight': 0.12113801956601614,
    'return_12m_weight': 0.3261032851896994,
    'volatility_weight': 0.1922152285327366,
    'rsi_weight': 0.11993489419545983,
    'pe_weight': 0.3337240403776484,
    'pb_weight': 0.39742745539862817,
    'earnings_yield_weight': 0.2688485042237236,
    'roe_weight': 0.24078228013642022,
    'roa_weight': 0.35628513932548495,
    'profit_margin_weight': 0.206461415156578,
    'debt_ratio_weight': 0.19647116538151685,
    'top_n': 10,
    'min_factors': 3,
    'rebalance_freq': '2ME'
}

EXPECTED_METRICS_V2 = {
    'annual_return': 74.51,
    'sharpe_ratio': 2.338,
    'max_drawdown': -9.33,
    'win_rate': 83.33
}


def apply_params_to_strategy(strategy: MultiFactorStrategy, params: dict):
    """將參數應用到策略"""
    strategy.factor_config = {
        'momentum': {
            'weight': params['momentum_weight'],
            'factors': {
                'return_3m': {'weight': params['return_3m_weight'], 'direction': 1},
                'return_6m': {'weight': params['return_6m_weight'], 'direction': 1},
                'return_12m': {'weight': params['return_12m_weight'], 'direction': 1},
                'volatility_30d': {'weight': params['volatility_weight'], 'direction': -1},
                'rsi_14': {'weight': params['rsi_weight'], 'direction': 0}
            }
        },
        'value': {
            'weight': params['value_weight'],
            'factors': {
                'pe_ratio': {'weight': params['pe_weight'], 'direction': -1},
                'pb_ratio': {'weight': params['pb_weight'], 'direction': -1},
                'earnings_yield': {'weight': params['earnings_yield_weight'], 'direction': 1}
            }
        },
        'quality': {
            'weight': params['quality_weight'],
            'factors': {
                'roe': {'weight': params['roe_weight'], 'direction': 1},
                'roa': {'weight': params['roa_weight'], 'direction': 1},
                'profit_margin': {'weight': params['profit_margin_weight'], 'direction': 1},
                'debt_ratio': {'weight': params['debt_ratio_weight'], 'direction': -1}
            }
        }
    }


def main():
    print("=" * 80)
    print("驗證 v2 優化後的最佳參數")
    print("=" * 80)
    
    # 顯示參數
    print("\n【v2 最佳參數】（第 25 代）")
    print("-" * 80)
    print(f"\n因子大類權重:")
    print(f"  動能因子: {BEST_PARAMS_V2['momentum_weight']:.1%}")
    print(f"  價值因子: {BEST_PARAMS_V2['value_weight']:.1%} 🎯 (vs v1 28.7%)")
    print(f"  質量因子: {BEST_PARAMS_V2['quality_weight']:.1%}")
    
    print(f"\n動能子因子權重:")
    print(f"  return_3m:   {BEST_PARAMS_V2['return_3m_weight']:.1%}")
    print(f"  return_6m:   {BEST_PARAMS_V2['return_6m_weight']:.1%}")
    print(f"  return_12m:  {BEST_PARAMS_V2['return_12m_weight']:.1%} 🎯 強化長期趨勢")
    print(f"  volatility:  {BEST_PARAMS_V2['volatility_weight']:.1%}")
    print(f"  RSI:         {BEST_PARAMS_V2['rsi_weight']:.1%} (vs v1 3.7%)")
    
    print(f"\n價值子因子權重:")
    print(f"  PE:              {BEST_PARAMS_V2['pe_weight']:.1%}")
    print(f"  PB:              {BEST_PARAMS_V2['pb_weight']:.1%}")
    print(f"  earnings_yield:  {BEST_PARAMS_V2['earnings_yield_weight']:.1%}")
    
    print(f"\n質量子因子權重:")
    print(f"  ROE:            {BEST_PARAMS_V2['roe_weight']:.1%}")
    print(f"  ROA:            {BEST_PARAMS_V2['roa_weight']:.1%}")
    print(f"  profit_margin:  {BEST_PARAMS_V2['profit_margin_weight']:.1%}")
    print(f"  debt_ratio:     {BEST_PARAMS_V2['debt_ratio_weight']:.1%}")
    
    print(f"\n交易參數:")
    print(f"  持股數量:    {BEST_PARAMS_V2['top_n']} 🎯 (vs v1 18 支，極度集中)")
    print(f"  調倉頻率:    {BEST_PARAMS_V2['rebalance_freq']}")
    print(f"  最少因子數:  {BEST_PARAMS_V2['min_factors']} (vs v1 4，解決數據問題)")
    
    print(f"\n【預期指標】（第 25 代）")
    print("-" * 80)
    print(f"  年化報酬率: {EXPECTED_METRICS_V2['annual_return']:.2f}%")
    print(f"  夏普比率:   {EXPECTED_METRICS_V2['sharpe_ratio']:.3f}")
    print(f"  最大回撤:   {EXPECTED_METRICS_V2['max_drawdown']:.2f}%")
    print(f"  勝率:       {EXPECTED_METRICS_V2['win_rate']:.2f}%")
    
    # 創建策略
    print("\n" + "=" * 80)
    print("執行驗證回測")
    print("=" * 80)
    
    strategy = MultiFactorStrategy()
    apply_params_to_strategy(strategy, BEST_PARAMS_V2)
    
    # 生成信號
    start_date = datetime(2024, 1, 1)
    end_date = datetime(2024, 12, 31)
    
    print(f"\n生成交易信號...")
    signals = strategy.generate_signals(
        start_date=start_date,
        end_date=end_date,
        rebalance_freq=BEST_PARAMS_V2['rebalance_freq'],
        top_n=BEST_PARAMS_V2['top_n']
    )
    
    if signals.empty:
        print("\n❌ 無法生成信號")
        return
    
    print(f"✅ 生成 {len(signals)} 條交易信號")
    
    # 檢查調倉月份
    unique_months = signals['date'].dt.to_period('M').unique()
    print(f"\n調倉月份: {len(unique_months)} 個月")
    print(f"涵蓋月份: {', '.join(str(m) for m in sorted(unique_months))}")
    
    if len(unique_months) < 12:
        missing_months = set(range(1, 13)) - set(m.month for m in unique_months)
        if missing_months:
            print(f"⚠️  缺少月份: {sorted(missing_months)}")
    else:
        print("✅ 涵蓋全年 12 個月！（vs v1 的 159 天問題已解決）")
    
    # 回測
    print(f"\n執行回測...")
    backtest = MultiFactorBacktest()
    results = backtest.run(signals_df=signals)
    
    metrics = results['metrics']
    
    # 解析指標
    def parse_percent(s):
        if isinstance(s, str):
            return float(s.replace('%', '').replace(',', ''))
        return float(s) if s else 0.0
    
    def parse_number(s):
        if isinstance(s, str):
            return float(s.replace(',', ''))
        return float(s) if s else 0.0
    
    actual_metrics = {
        'annual_return': parse_percent(metrics.get('年化報酬率', '0%')),
        'sharpe_ratio': parse_number(metrics.get('夏普比率', '0')),
        'max_drawdown': parse_percent(metrics.get('最大回撤', '0%')),
        'total_return': parse_percent(metrics.get('總報酬率', '0%')),
        'volatility': parse_percent(metrics.get('波動率', '0%')),
        'win_rate': parse_percent(metrics.get('勝率', '0%')),
        'trades': int(metrics.get('交易次數', 0))
    }
    
    # 對比結果
    print("\n" + "=" * 80)
    print("驗證結果")
    print("=" * 80)
    
    print("\n【指標對比】")
    print("-" * 80)
    print(f"{'指標':<20} {'預期':<15} {'實際':<15} {'差異':<15}")
    print("-" * 80)
    
    annual_diff = actual_metrics['annual_return'] - EXPECTED_METRICS_V2['annual_return']
    sharpe_diff = actual_metrics['sharpe_ratio'] - EXPECTED_METRICS_V2['sharpe_ratio']
    drawdown_diff = actual_metrics['max_drawdown'] - EXPECTED_METRICS_V2['max_drawdown']
    
    print(f"{'年化報酬率':<20} {EXPECTED_METRICS_V2['annual_return']:>12.2f}%  {actual_metrics['annual_return']:>12.2f}%  {annual_diff:>+12.2f}%")
    print(f"{'夏普比率':<20} {EXPECTED_METRICS_V2['sharpe_ratio']:>14.3f}  {actual_metrics['sharpe_ratio']:>14.3f}  {sharpe_diff:>+14.3f}")
    print(f"{'最大回撤':<20} {EXPECTED_METRICS_V2['max_drawdown']:>12.2f}%  {actual_metrics['max_drawdown']:>12.2f}%  {drawdown_diff:>+12.2f}%")
    
    print("\n【其他指標】")
    print("-" * 80)
    print(f"總報酬率:     {actual_metrics['total_return']:.2f}%")
    print(f"波動率:       {actual_metrics['volatility']:.2f}%")
    print(f"勝率:         {actual_metrics['win_rate']:.2f}%")
    print(f"交易次數:     {actual_metrics['trades']}")
    
    # 計算風險調整報酬
    if actual_metrics['max_drawdown'] != 0:
        risk_adjusted_return = actual_metrics['annual_return'] / abs(actual_metrics['max_drawdown'])
        print(f"\n風險調整報酬: {risk_adjusted_return:.2f} (年化報酬 / 最大回撤)")
    
    # 判斷驗證結果
    print("\n" + "=" * 80)
    print("驗證結論")
    print("=" * 80)
    
    # 容許誤差：±2% 年化報酬，±0.1 夏普
    annual_match = abs(annual_diff) < 2.0
    sharpe_match = abs(sharpe_diff) < 0.1
    
    if annual_match and sharpe_match:
        print("\n✅ 驗證成功！實際結果與預期一致")
    elif abs(annual_diff) < 5.0 and abs(sharpe_diff) < 0.2:
        print("\n⚠️  驗證通過，但有輕微差異（可接受範圍內）")
    else:
        print("\n❌ 驗證失敗，實際結果與預期有較大差異")
    
    print(f"\n說明:")
    print(f"  - 年化報酬差異: {annual_diff:+.2f}% {'✅' if annual_match else '⚠️'}")
    print(f"  - 夏普比率差異: {sharpe_diff:+.3f} {'✅' if sharpe_match else '⚠️'}")
    
    # 檢查 min_factors = 3 是否解決問題
    if len(unique_months) >= 10:
        print(f"  - min_factors = 3 效果: ✅ 涵蓋 {len(unique_months)} 個月（vs v1 僅 159 天）")
    else:
        print(f"  - min_factors = 3 效果: ⚠️ 仍有數據缺失問題")
    
    # 保存完整結果
    output_file = project_root / 'results' / 'best_params_v2_validated.json'
    output_file.parent.mkdir(exist_ok=True)
    
    validation_results = {
        'version': 'v2',
        'params': BEST_PARAMS_V2,
        'expected_metrics': EXPECTED_METRICS_V2,
        'actual_metrics': actual_metrics,
        'validation_date': datetime.now().isoformat(),
        'backtest_period': {
            'start': start_date.isoformat(),
            'end': end_date.isoformat()
        },
        'signals_count': len(signals),
        'rebalance_months': len(unique_months),
        'validation_passed': annual_match and sharpe_match,
        'improvements_vs_v1': {
            'min_factors_reduced': '4 → 3 (解決數據問題)',
            'holdings_reduced': '18 → 10 (極度集中)',
            'value_weight_increased': '28.7% → 32.7% (估值紀律)',
            'return_12m_increased': '28.4% → 32.6% (長期趨勢)'
        }
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(validation_results, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 驗證結果已保存: {output_file}")
    print("\n" + "=" * 80)
    print("✅ v2 驗證完成！")
    print("=" * 80)


if __name__ == '__main__':
    main()
