#!/usr/bin/env python3
"""Robustness harness for the value factor. Isolates factor sleeves via
update_config presets and runs the PURE multi-factor path (v2.0, no pattern/chip
stages) so results reflect the factor alone. Uses the corrected pe/pb/EY data."""
import sys, argparse, json
sys.path.append('/home/mdsadmin/Stock/tw-stock-analysis/src')
sys.path.append('/home/mdsadmin/Stock/tw-stock-analysis/scripts')
from pymongo import MongoClient
from backtest_integrated_v21 import BacktestV21

PRESETS = {
    'full':          {},                                  # momentum+value(+quality per source)
    'value_only':    {'momentum': None, 'quality': None}, # value = 100%
    'momentum_only': {'value': None, 'quality': None},    # momentum = 100%
    'quality_only':  {'momentum': None, 'value': None},   # quality = 100% (needs --quality-source fundamental)
}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--start-date', required=True)
    ap.add_argument('--end-date', required=True)
    ap.add_argument('--preset', default='value_only', choices=list(PRESETS))
    ap.add_argument('--quality-source', default='none', choices=['none','fundamental','legacy'])
    ap.add_argument('--output', required=True)
    a = ap.parse_args()

    db = MongoClient('mongodb://localhost:27017/')['tw_stock_analysis']
    bt = BacktestV21(db, initial_capital=10_000_000, rebalance_frequency='monthly',
                     quality_source=a.quality_source)
    cfg = PRESETS[a.preset]
    if cfg:
        for strat in (bt.strategy_v21.factor_strategy, bt.strategy_v20):
            strat.update_config(cfg)
    print("PRESET=%s  v2.0 config=%s" % (
        a.preset, {k: round(v['weight'], 3) for k, v in bt.strategy_v20.factor_config.items()}))

    res = bt.run(a.start_date, a.end_date, strategy_version='v2.0')
    m = res['metrics']
    print("RESULT preset=%s period=%s..%s q=%s :: annual=%.2f%% sharpe=%.3f mdd=%.2f%% win=%.1f%% trades=%d" % (
        a.preset, a.start_date, a.end_date, a.quality_source,
        m['annual_return']*100, m['sharpe_ratio'], m['max_drawdown']*100,
        m['win_rate']*100, m['completed_trades']))
    json.dump(res, open(a.output, 'w'), ensure_ascii=False, indent=2, default=str)
    print("saved", a.output)

if __name__ == '__main__':
    main()
