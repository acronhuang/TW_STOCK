#!/usr/bin/env python3
"""
提取優化歷史中的最佳參數並驗證

從優化日誌中提取第 13 代的最佳參數，進行完整回測驗證
"""

import sys
from pathlib import Path
from datetime import datetime
import json

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from examples.multifactor_strategy import MultiFactorStrategy
from examples.backtest_multifactor import MultiFactorBacktest


# 第 13 代最佳參數（從 JSON 文件和日誌中提取）
BEST_PARAMS = {
    'momentum_weight': 0.43260319680636905,
    'value_weight': 0.28675915381450523,
    'quality_weight': 0.2806376493791256,
    'return_3m_weight': 0.3612357250838026,
    'return_6m_weight': 0.12532924028765596,
    'return_12m_weight': 0.2841923208527021,
    'volatility_weight': 0.19211147580097268,
    'rsi_weight': 0.03713123797486659,
    'pe_weight': 0.3432030008718905,
    'pb_weight': 0.332585390224506,
    'earnings_yield_weight': 0.3242116089036035,
    'roe_weight': 0.3553974875162489,
    'roa_weight': 0.3339829812922358,
    'profit_margin_weight': 0.15282771897955666,
    'debt_ratio_weight': 0.15779181221195857,
    'top_n': 18,
    'min_factors': 4,
    'rebalance_freq': '2ME'
}

EXPECTED_METRICS = {
    'annual_return': 54.18,
    'sharpe_ratio': 2.392,
    'max_drawdown': -7.46
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
    print("驗證優化後的最佳參數")
    print("=" * 80)
    
    # 顯示參數
    print("\n【最佳參數】（第 13 代）")
    print("-" * 80)
    print(f"\n因子大類權重:")
    print(f"  動能因子: {BEST_PARAMS['momentum_weight']:.1%}")
    print(f"  價值因子: {BEST_PARAMS['value_weight']:.1%}")
    print(f"  質量因子: {BEST_PARAMS['quality_weight']:.1%}")
    
    print(f"\n動能子因子權重:")
    print(f"  return_3m:   {BEST_PARAMS['return_3m_weight']:.1%}")
    print(f"  return_6m:   {BEST_PARAMS['return_6m_weight']:.1%}")
    print(f"  return_12m:  {BEST_PARAMS['return_12m_weight']:.1%}")
    print(f"  volatility:  {BEST_PARAMS['volatility_weight']:.1%}")
    print(f"  RSI:         {BEST_PARAMS['rsi_weight']:.1%}")
    
    print(f"\n價值子因子權重:")
    print(f"  PE:              {BEST_PARAMS['pe_weight']:.1%}")
    print(f"  PB:              {BEST_PARAMS['pb_weight']:.1%}")
    print(f"  earnings_yield:  {BEST_PARAMS['earnings_yield_weight']:.1%}")
    
    print(f"\n質量子因子權重:")
    print(f"  ROE:            {BEST_PARAMS['roe_weight']:.1%}")
    print(f"  ROA:            {BEST_PARAMS['roa_weight']:.1%}")
    print(f"  profit_margin:  {BEST_PARAMS['profit_margin_weight']:.1%}")
    print(f"  debt_ratio:     {BEST_PARAMS['debt_ratio_weight']:.1%}")
    
    print(f"\n交易參數:")
    print(f"  持股數量:    {BEST_PARAMS['top_n']}")
    print(f"  調倉頻率:    {BEST_PARAMS['rebalance_freq']}")
    print(f"  最少因子數:  {BEST_PARAMS['min_factors']}")
    
    print(f"\n【預期指標】（第 13 代）")
    print("-" * 80)
    print(f"  年化報酬率: {EXPECTED_METRICS['annual_return']:.2f}%")
    print(f"  夏普比率:   {EXPECTED_METRICS['sharpe_ratio']:.3f}")
    print(f"  最大回撤:   {EXPECTED_METRICS['max_drawdown']:.2f}%")
    
    # 創建策略
    print("\n" + "=" * 80)
    print("執行驗證回測")
    print("=" * 80)
    
    strategy = MultiFactorStrategy()
    apply_params_to_strategy(strategy, BEST_PARAMS)
    
    # 生成信號
    start_date = datetime(2024, 1, 1)
    end_date = datetime(2024, 12, 31)
    
    print(f"\n生成交易信號...")
    signals = strategy.generate_signals(
        start_date=start_date,
        end_date=end_date,
        rebalance_freq=BEST_PARAMS['rebalance_freq'],
        top_n=BEST_PARAMS['top_n']
    )
    
    if signals.empty:
        print("\n❌ 無法生成信號")
        return
    
    print(f"✅ 生成 {len(signals)} 條交易信號")
    
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
    
    annual_diff = actual_metrics['annual_return'] - EXPECTED_METRICS['annual_return']
    sharpe_diff = actual_metrics['sharpe_ratio'] - EXPECTED_METRICS['sharpe_ratio']
    drawdown_diff = actual_metrics['max_drawdown'] - EXPECTED_METRICS['max_drawdown']
    
    print(f"{'年化報酬率':<20} {EXPECTED_METRICS['annual_return']:>12.2f}%  {actual_metrics['annual_return']:>12.2f}%  {annual_diff:>+12.2f}%")
    print(f"{'夏普比率':<20} {EXPECTED_METRICS['sharpe_ratio']:>14.3f}  {actual_metrics['sharpe_ratio']:>14.3f}  {sharpe_diff:>+14.3f}")
    print(f"{'最大回撤':<20} {EXPECTED_METRICS['max_drawdown']:>12.2f}%  {actual_metrics['max_drawdown']:>12.2f}%  {drawdown_diff:>+12.2f}%")
    
    print("\n【其他指標】")
    print("-" * 80)
    print(f"總報酬率:     {actual_metrics['total_return']:.2f}%")
    print(f"波動率:       {actual_metrics['volatility']:.2f}%")
    print(f"勝率:         {actual_metrics['win_rate']:.2f}%")
    print(f"交易次數:     {actual_metrics['trades']}")
    
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
    
    # 保存完整結果
    output_file = project_root / 'results' / 'best_params_validated.json'
    output_file.parent.mkdir(exist_ok=True)
    
    validation_results = {
        'params': BEST_PARAMS,
        'expected_metrics': EXPECTED_METRICS,
        'actual_metrics': actual_metrics,
        'validation_date': datetime.now().isoformat(),
        'backtest_period': {
            'start': start_date.isoformat(),
            'end': end_date.isoformat()
        },
        'signals_count': len(signals),
        'validation_passed': annual_match and sharpe_match
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(validation_results, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 驗證結果已保存: {output_file}")
    print("\n" + "=" * 80)
    print("✅ 驗證完成！")
    print("=" * 80)


if __name__ == '__main__':
    main()
