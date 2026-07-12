#!/usr/bin/env python3
"""蔡森底型態 × 年線位置 回測：底部型態在『站上年線(240MA)』vs『年線下』的前向報酬。
驗證長期趨勢是否影響底型態可靠度，以決定要不要進 score_signal。"""
import sys, os, warnings
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
warnings.filterwarnings('ignore')
import numpy as np
import pandas as pd
from pymongo import MongoClient
from src.utils.backtest import tof, dkey, HORIZONS, print_baseline, make_reporter
from src.senvision.analysis import analyze_timeframe

db = MongoClient('localhost', 27017)['tw_stock_analysis']
SIGNAL_DATES = ['2026-02-02', '2026-02-16', '2026-03-02', '2026-03-16',
                '2026-04-01', '2026-04-16', '2026-05-04', '2026-05-18']
MIN_VOL = 500 * 1000


def is_bottom(df_slice, sym):
    try:
        res = analyze_timeframe(df_slice, sym, 'D')
    except Exception:
        return False
    if not res:
        return False
    for p in res.get('patterns', []):
        pt = getattr(p, 'pattern_type', None)
        v = getattr(pt, 'value', None) or str(pt)
        if 'Bottom' in v or 'Failed-Breakdown' in v:   # 偏多反轉型態
            return True
    return False


syms = [s for s in db.stock_price.distinct('symbol') if s.isdigit() and len(s) == 4]
print(f"回測 {len(syms)} 檔 × {len(SIGNAL_DATES)} 日（底型態×年線）...")
samples = []
base = {h: [] for h in HORIZONS}

for sym in syms:
    docs = list(db.stock_price.find(
        {'symbol': sym}, {'date': 1, 'open': 1, 'high': 1, 'low': 1, 'close': 1, 'volume': 1}
    ).sort('date', 1))
    if len(docs) < 250:
        continue
    close = np.array([tof(d.get('close')) or np.nan for d in docs])
    vol = np.array([tof(d.get('volume')) or 0.0 for d in docs])
    if np.isnan(close).any():
        continue
    dates = [dkey(d['date']) for d in docs]
    dmap = {d: i for i, d in enumerate(dates)}

    for sd in SIGNAL_DATES:
        i = dmap.get(sd)
        if i is None or i < 240 or i + max(HORIZONS) >= len(close):
            continue
        if np.mean(vol[i-19:i+1]) < MIN_VOL:
            continue
        for h in HORIZONS:
            base[h].append(close[i+h]/close[i] - 1)
        lo = max(0, i - 249)
        sl = docs[lo:i+1]
        df = pd.DataFrame({
            'date': pd.to_datetime([dkey(x['date']) for x in sl]),
            'open': [tof(x.get('open')) for x in sl], 'high': [tof(x.get('high')) for x in sl],
            'low': [tof(x.get('low')) for x in sl], 'close': [tof(x.get('close')) for x in sl],
            'volume': [tof(x.get('volume')) or 0 for x in sl],
        })
        if not is_bottom(df, sym):
            continue
        ma240 = close[i-239:i+1].mean()
        samples.append({'above_year': bool(close[i] > ma240),
                        'rets': {h: close[i+h]/close[i] - 1 for h in HORIZONS}})

print()
bm = print_baseline(base)
nb = len(samples)
print(f"底型態訊號 {nb} 筆，其中站上年線 {sum(s['above_year'] for s in samples)} 筆\n")
rule = make_reporter(samples, bm)
rule("① 底型態(全部)", lambda s: True)
rule("② 底型態 + 站上年線", lambda s: s['above_year'])
rule("③ 底型態 + 年線下", lambda s: not s['above_year'])
