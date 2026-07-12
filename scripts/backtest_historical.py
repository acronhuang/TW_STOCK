#!/usr/bin/env python3
"""
歷史回測（2022-2024）

使用優化後的參數進行多年回測，驗證策略穩健性
"""

import sys
from pathlib import Path
from datetime import datetime
import json
import argparse
import pandas as pd

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from examples.multifactor_strategy import MultiFactorStrategy
from examples.backtest_multifactor import MultiFactorBacktest


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


def parse_percent(s):
    """解析百分比字符串"""
    if isinstance(s, str):
        return float(s.replace('%', '').replace(',', ''))
    return float(s) if s else 0.0


def parse_number(s):
    """解析數字字符串"""
    if isinstance(s, str):
        return float(s.replace(',', ''))
    return float(s) if s else 0.0


def backtest_year(strategy, params, year):
    """回測單一年度"""
    print(f"\n執行 {year} 年回測...")
    print("-" * 80)
    
    start_date = datetime(year, 1, 1)
    end_date = datetime(year, 12, 31)
    
    # 生成信號
    signals = strategy.generate_signals(
        start_date=start_date,
        end_date=end_date,
        rebalance_freq=params['rebalance_freq'],
        top_n=params['top_n']
    )
    
    if signals.empty:
        print(f"❌ {year} 年無法生成信號")
        return None
    
    print(f"✅ 生成 {len(signals)} 條交易信號")
    
    # 回測
    backtest = MultiFactorBacktest()
    results = backtest.run(signals_df=signals)
    
    metrics = results['metrics']
    
    # 解析指標
    parsed_metrics = {
        'year': year,
        'annual_return': parse_percent(metrics.get('年化報酬率', '0%')),
        'sharpe_ratio': parse_number(metrics.get('夏普比率', '0')),
        'max_drawdown': parse_percent(metrics.get('最大回撤', '0%')),
        'total_return': parse_percent(metrics.get('總報酬率', '0%')),
        'volatility': parse_percent(metrics.get('波動率', '0%')),
        'win_rate': parse_percent(metrics.get('勝率', '0%')),
        'trades': int(metrics.get('交易次數', 0))
    }
    
    # 顯示結果
    print(f"\n{year} 年績效:")
    print(f"  年化報酬率: {parsed_metrics['annual_return']:.2f}%")
    print(f"  總報酬率:   {parsed_metrics['total_return']:.2f}%")
    print(f"  夏普比率:   {parsed_metrics['sharpe_ratio']:.3f}")
    print(f"  最大回撤:   {parsed_metrics['max_drawdown']:.2f}%")
    print(f"  波動率:     {parsed_metrics['volatility']:.2f}%")
    print(f"  勝率:       {parsed_metrics['win_rate']:.2f}%")
    print(f"  交易次數:   {parsed_metrics['trades']}")
    
    return parsed_metrics


def main():
    parser = argparse.ArgumentParser(description='歷史回測（2022-2024）')
    parser.add_argument('--start-date', type=str, default='2022-01-01',
                        help='開始日期 (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, default='2024-12-31',
                        help='結束日期 (YYYY-MM-DD)')
    parser.add_argument('--params', type=str, 
                        default='results/optimization_results_v2.json',
                        help='參數文件路徑')
    parser.add_argument('--output', type=str,
                        default='reports/historical_backtest.json',
                        help='輸出文件路徑')
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("歷史回測（2022-2024）")
    print("=" * 80)
    
    # 載入參數
    params_file = project_root / args.params
    if not params_file.exists():
        print(f"\n❌ 參數文件不存在: {params_file}")
        return
    
    with open(params_file, 'r', encoding='utf-8') as f:
        optimization_results = json.load(f)
    
    params = optimization_results['params']
    
    print(f"\n參數來源: {args.params}")
    print(f"回測期間: {args.start_date} ~ {args.end_date}")
    print(f"\n策略配置:")
    print(f"  持股數量:   {params['top_n']}")
    print(f"  調倉頻率:   {params['rebalance_freq']}")
    print(f"  最少因子數: {params['min_factors']}")
    print(f"  動能權重:   {params['momentum_weight']:.1%}")
    print(f"  價值權重:   {params['value_weight']:.1%}")
    print(f"  質量權重:   {params['quality_weight']:.1%}")
    
    # 創建策略
    strategy = MultiFactorStrategy()
    apply_params_to_strategy(strategy, params)
    
    # 確定要回測的年份
    start_year = int(args.start_date.split('-')[0])
    end_year = int(args.end_date.split('-')[0])
    years = list(range(start_year, end_year + 1))
    
    print("\n" + "=" * 80)
    print(f"開始逐年回測（{len(years)} 年）")
    print("=" * 80)
    
    # 逐年回測
    yearly_results = []
    for year in years:
        result = backtest_year(strategy, params, year)
        if result:
            yearly_results.append(result)
    
    if not yearly_results:
        print("\n❌ 所有年份回測失敗")
        return
    
    # 計算多年統計
    print("\n" + "=" * 80)
    print("多年統計分析")
    print("=" * 80)
    
    df = pd.DataFrame(yearly_results)
    
    print("\n【逐年績效】")
    print("-" * 80)
    print(f"{'年份':<10} {'年化報酬':<12} {'夏普比率':<12} {'最大回撤':<12} {'勝率':<12}")
    print("-" * 80)
    for _, row in df.iterrows():
        print(f"{int(row['year']):<10} {row['annual_return']:>10.2f}%  "
              f"{row['sharpe_ratio']:>10.3f}  {row['max_drawdown']:>10.2f}%  "
              f"{row['win_rate']:>10.2f}%")
    
    # 多年平均
    print("\n【多年平均】")
    print("-" * 80)
    print(f"平均年化報酬:   {df['annual_return'].mean():.2f}%")
    print(f"平均夏普比率:   {df['sharpe_ratio'].mean():.3f}")
    print(f"平均最大回撤:   {df['max_drawdown'].mean():.2f}%")
    print(f"平均勝率:       {df['win_rate'].mean():.2f}%")
    
    # 穩定性指標
    print("\n【穩定性指標】")
    print("-" * 80)
    positive_years = (df['annual_return'] > 0).sum()
    print(f"正報酬年數:     {positive_years}/{len(df)} ({positive_years/len(df)*100:.1f}%)")
    print(f"報酬標準差:     {df['annual_return'].std():.2f}%")
    print(f"最佳年份:       {df.loc[df['annual_return'].idxmax(), 'year']:.0f} "
          f"({df['annual_return'].max():.2f}%)")
    print(f"最差年份:       {df.loc[df['annual_return'].idxmin(), 'year']:.0f} "
          f"({df['annual_return'].min():.2f}%)")
    
    # 風險調整報酬
    print("\n【風險調整報酬】")
    print("-" * 80)
    for _, row in df.iterrows():
        if row['max_drawdown'] != 0:
            risk_adj = row['annual_return'] / abs(row['max_drawdown'])
            print(f"{int(row['year'])} 年: {risk_adj:.2f}")
    
    avg_risk_adj = df['annual_return'].mean() / abs(df['max_drawdown'].mean())
    print(f"\n平均風險調整報酬: {avg_risk_adj:.2f}")
    
    # 評估結果
    print("\n" + "=" * 80)
    print("穩健性評估")
    print("=" * 80)
    
    success_criteria = {
        '正報酬年數 ≥ 2/3': positive_years >= len(df) * 2/3,
        '平均年化 > 20%': df['annual_return'].mean() > 20,
        '平均夏普 > 1.5': df['sharpe_ratio'].mean() > 1.5,
        '最大年度回撤 < -20%': df['max_drawdown'].min() > -20
    }
    
    print("\n【成功指標】")
    print("-" * 80)
    for criterion, passed in success_criteria.items():
        status = '✅' if passed else '❌'
        print(f"{status} {criterion}")
    
    all_passed = all(success_criteria.values())
    if all_passed:
        print("\n✅ 策略通過所有穩健性測試")
    else:
        failed_count = sum(1 for v in success_criteria.values() if not v)
        print(f"\n⚠️  策略未通過 {failed_count}/{len(success_criteria)} 項測試")
    
    # 風險警示
    print("\n【風險警示】")
    print("-" * 80)
    
    if df['annual_return'].std() > 20:
        print("⚠️  年度報酬波動較大（標準差 > 20%）")
    
    if positive_years < len(df):
        negative_years = df[df['annual_return'] < 0]
        print(f"⚠️  發現 {len(negative_years)} 個負報酬年份:")
        for _, row in negative_years.iterrows():
            print(f"    {int(row['year'])} 年: {row['annual_return']:.2f}%")
    
    worst_drawdown = df['max_drawdown'].min()
    if worst_drawdown < -15:
        worst_year = df.loc[df['max_drawdown'].idxmin(), 'year']
        print(f"⚠️  最大年度回撤 {worst_drawdown:.2f}% ({int(worst_year)} 年)")
    
    # 保存結果
    output_file = project_root / args.output
    output_file.parent.mkdir(exist_ok=True)
    
    report = {
        'backtest_period': {
            'start': args.start_date,
            'end': args.end_date
        },
        'params': params,
        'yearly_results': yearly_results,
        'summary': {
            'avg_annual_return': float(df['annual_return'].mean()),
            'avg_sharpe_ratio': float(df['sharpe_ratio'].mean()),
            'avg_max_drawdown': float(df['max_drawdown'].mean()),
            'avg_win_rate': float(df['win_rate'].mean()),
            'return_std': float(df['annual_return'].std()),
            'positive_years': int(positive_years),
            'total_years': len(df),
            'best_year': int(df.loc[df['annual_return'].idxmax(), 'year']),
            'best_return': float(df['annual_return'].max()),
            'worst_year': int(df.loc[df['annual_return'].idxmin(), 'year']),
            'worst_return': float(df['annual_return'].min()),
            'avg_risk_adjusted_return': float(avg_risk_adj)
        },
        'success_criteria': {k: bool(v) for k, v in success_criteria.items()},
        'all_tests_passed': all_passed,
        'generated_at': datetime.now().isoformat()
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 回測報告已保存: {output_file}")
    
    # 生成 Markdown 報告
    md_file = output_file.with_suffix('.md')
    with open(md_file, 'w', encoding='utf-8') as f:
        f.write(f"# 歷史回測報告（{args.start_date} ~ {args.end_date}）\n\n")
        f.write(f"**生成時間**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"## 策略配置\n\n")
        f.write(f"- 持股數量: {params['top_n']}\n")
        f.write(f"- 調倉頻率: {params['rebalance_freq']}\n")
        f.write(f"- 最少因子數: {params['min_factors']}\n")
        f.write(f"- 動能權重: {params['momentum_weight']:.1%}\n")
        f.write(f"- 價值權重: {params['value_weight']:.1%}\n")
        f.write(f"- 質量權重: {params['quality_weight']:.1%}\n\n")
        
        f.write(f"## 逐年績效\n\n")
        f.write(f"| 年份 | 年化報酬 | 夏普比率 | 最大回撤 | 勝率 |\n")
        f.write(f"|------|---------|---------|---------|------|\n")
        for _, row in df.iterrows():
            f.write(f"| {int(row['year'])} | {row['annual_return']:.2f}% | "
                   f"{row['sharpe_ratio']:.3f} | {row['max_drawdown']:.2f}% | "
                   f"{row['win_rate']:.2f}% |\n")
        
        f.write(f"\n## 多年統計\n\n")
        f.write(f"- 平均年化報酬: {df['annual_return'].mean():.2f}%\n")
        f.write(f"- 平均夏普比率: {df['sharpe_ratio'].mean():.3f}\n")
        f.write(f"- 平均最大回撤: {df['max_drawdown'].mean():.2f}%\n")
        f.write(f"- 正報酬年數: {positive_years}/{len(df)}\n")
        f.write(f"- 平均風險調整報酬: {avg_risk_adj:.2f}\n\n")
        
        f.write(f"## 穩健性評估\n\n")
        for criterion, passed in success_criteria.items():
            status = '✅' if passed else '❌'
            f.write(f"{status} {criterion}\n")
        
        f.write(f"\n**最終結論**: {'✅ 通過所有測試' if all_passed else '⚠️ 部分測試未通過'}\n")
    
    print(f"📄 Markdown 報告已保存: {md_file}")
    
    print("\n" + "=" * 80)
    print("✅ 歷史回測完成！")
    print("=" * 80)


if __name__ == '__main__':
    main()
