#!/usr/bin/env python3
"""MA乖離 + 法人連續 評分假設回測：各條件訊號後 5/10/20 日報酬 vs 基準。"""
import sys, os, warnings
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
warnings.filterwarnings('ignore')
import numpy as np
from pymongo import MongoClient
from src.utils.backtest import tof, dkey as dk, HORIZONS, print_baseline, make_reporter

db = MongoClient('localhost', 27017)['tw_stock_analysis']
WIN_START, WIN_END = '2026-01-15', '2026-05-18'
MIN_VOL = 500 * 1000

syms = [s for s in db.stock_price.distinct('symbol') if s.isdigit() and len(s) == 4]
print(f"回測 {len(syms)} 檔，窗 {WIN_START}~{WIN_END} ...")
samples = []; base = {h: [] for h in HORIZONS}

for sym in syms:
    px = list(db.stock_price.find({'symbol': sym}, {'date':1,'close':1,'volume':1}).sort('date',1))
    if len(px) < 80: continue
    closes = np.array([tof(p.get('close')) or np.nan for p in px])
    vols = np.array([tof(p.get('volume')) or 0.0 for p in px])
    if np.isnan(closes).any(): continue
    dates = [dk(p['date']) for p in px]
    dmap = {d: i for i, d in enumerate(dates)}
    # 法人(外資)序列: {date_str: foreign_net}
    inst = {}
    for d in db.institutional_flow.find({'stock_id': sym}, {'date':1,'foreign_net':1}).sort('date',1):
        inst[dk(d['date'])] = tof(d.get('foreign_net'))
    inst_dates = sorted(inst.keys())

    def fstreak(sigdate):
        ds = [d for d in inst_dates if d <= sigdate]
        n, sign = 0, 0
        for d in reversed(ds):
            v = inst.get(d)
            if v is None or v == 0: break
            s = 1 if v > 0 else -1
            if sign == 0: sign = s
            elif s != sign: break
            n += 1
            if n >= 15: break
        return sign * n

    for i in range(60, len(closes) - max(HORIZONS)):
        if not (WIN_START <= dates[i] <= WIN_END): continue
        if np.mean(vols[i-19:i+1]) < MIN_VOL: continue
        for h in HORIZONS: base[h].append(closes[i+h]/closes[i]-1)
        ma20 = closes[i-19:i+1].mean()
        bias20 = (closes[i]-ma20)/ma20*100 if ma20 else 0
        fs = fstreak(dates[i])
        samples.append({'bias20': bias20, 'fs': fs,
                        'rets': {h: closes[i+h]/closes[i]-1 for h in HORIZONS}})

print()
bm = print_baseline(base)
show = make_reporter(samples, bm)

show("① 超賣 乖離20≤-10", lambda s: s['bias20'] <= -10)
show("② 超賣+外資轉買", lambda s: s['bias20'] <= -10 and s['fs'] >= 1)
show("③ 超買 乖離20≥15", lambda s: s['bias20'] >= 15)
show("④ 超買+外資連賣≥2", lambda s: s['bias20'] >= 15 and s['fs'] <= -2)
show("⑤ 外資連買≥3", lambda s: s['fs'] >= 3)
show("⑥ 外資連買≥5", lambda s: s['fs'] >= 5)
show("⑦ 外資連賣≥3", lambda s: s['fs'] <= -3)
show("⑧ 乖離20≤-15(深超賣)", lambda s: s['bias20'] <= -15)
