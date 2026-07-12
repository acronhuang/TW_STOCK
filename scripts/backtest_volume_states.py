#!/usr/bin/env python3
"""框架量價狀態回測：絕望量/鎖籌/窒息量 訊號後 5/10/20 日報酬 vs 基準。"""
import sys, os, warnings
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
warnings.filterwarnings('ignore')
import numpy as np
from pymongo import MongoClient
from src.factors.volume_factors import VolumeFactors
from src.utils.backtest import tof, HORIZONS, print_baseline, make_reporter

db = MongoClient('localhost', 27017)['tw_stock_analysis']
vf = VolumeFactors(db)

SIGNAL_DATES = ['2026-02-02', '2026-02-16', '2026-03-02', '2026-03-16', '2026-04-01',
                '2026-04-16', '2026-05-04', '2026-05-18']
MIN_VOL = 500 * 1000

syms = [s for s in db.stock_price.distinct('symbol') if s.isdigit() and len(s) == 4]
print(f"回測 {len(syms)} 檔 × {len(SIGNAL_DATES)} 日 ...")

samples = []
base_ret = {h: [] for h in HORIZONS}

for sym in syms:
    docs = list(db.stock_price.find({'symbol': sym}, {'date': 1, 'close': 1, 'volume': 1}).sort('date', 1))
    if len(docs) < 80:
        continue
    dk = lambda d: d.strftime('%Y-%m-%d') if hasattr(d, 'strftime') else str(d)[:10]
    closes = np.array([tof(d.get('close')) or np.nan for d in docs])
    vols = np.array([tof(d.get('volume')) or 0.0 for d in docs])
    if np.isnan(closes).any():
        continue
    dmap = {dk(d['date']): i for i, d in enumerate(docs)}
    for sd in SIGNAL_DATES:
        i = dmap.get(sd)
        if i is None or i < 60 or i + max(HORIZONS) >= len(closes):
            continue
        if np.mean(vols[i-19:i+1]) < MIN_VOL:
            continue
        for h in HORIZONS:
            base_ret[h].append(closes[i + h] / closes[i] - 1)
        c, v = closes[:i+1], vols[:i+1]
        samples.append({
            'cap': vf.detect_capitulation(c, v),
            'lock': vf.detect_chip_lock(c, v),
            'choke': vf.detect_choke(v),
            'rets': {h: closes[i + h] / closes[i] - 1 for h in HORIZONS},
        })

print()
bm = print_baseline(base_ret)
evalrule = make_reporter(samples, bm)

evalrule("① 絕望量(價跌量增)", lambda s: s['cap'])
evalrule("② 鎖籌(量縮上漲)", lambda s: s['lock'])
evalrule("③ 窒息量", lambda s: s['choke'])
evalrule("②+ 鎖籌 但非絕望量", lambda s: s['lock'] and not s['cap'])
