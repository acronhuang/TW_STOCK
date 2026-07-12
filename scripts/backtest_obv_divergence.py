#!/usr/bin/env python3
"""OBV 底背離 × 蔡森底型態 交叉驗證回測。
對每個底背離訊號(股,日)額外跑 SenVision 型態，分組比較前向報酬 vs 基準。"""
import sys, os, warnings
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
warnings.filterwarnings('ignore')
import numpy as np
import pandas as pd
from pymongo import MongoClient
from src.factors.volume_factors import VolumeFactors
from src.senvision.analysis import analyze_timeframe

from src.utils.backtest import tof, HORIZONS, print_baseline, make_reporter

db = MongoClient('localhost', 27017)['tw_stock_analysis']
vf = VolumeFactors(db)

SIGNAL_DATES = ['2026-02-16', '2026-03-02', '2026-03-16', '2026-04-01',
                '2026-04-16', '2026-05-04', '2026-05-18']
MIN_VOL = 500 * 1000

syms = [s for s in db.stock_price.distinct('symbol') if s.isdigit() and len(s) == 4]
print(f"交叉驗證 {len(syms)} 檔 × {len(SIGNAL_DATES)} 日 ...")

samples = []                       # 底背離訊號 + 是否含蔡森底型態 + 前向報酬
base_ret = {h: [] for h in HORIZONS}

def has_senvision_bottom(df_slice, sym):
    try:
        res = analyze_timeframe(df_slice, sym, 'D')
    except Exception:
        return False
    if not res:
        return False
    for p in res.get('patterns', []):
        pt = getattr(p, 'pattern_type', None)
        ptv = getattr(pt, 'value', None) or str(pt)
        if 'Bottom' in ptv:
            return True
    return False

for sym in syms:
    docs = list(db.stock_price.find(
        {'symbol': sym}, {'date': 1, 'open': 1, 'high': 1, 'low': 1, 'close': 1, 'volume': 1}
    ).sort('date', 1))
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
        if i is None or i < 40 or i + max(HORIZONS) >= len(closes):
            continue
        if np.mean(vols[i-19:i+1]) < MIN_VOL:
            continue
        for h in HORIZONS:
            base_ret[h].append(closes[i + h] / closes[i] - 1)
        b = vf.detect_obv_divergence(closes[:i+1], vols[:i+1])['bottom']
        if not b:
            continue
        # 蔡森型態：用截至訊號日的近 180 根 OHLCV
        lo = max(0, i - 179)
        sl = docs[lo:i+1]
        df = pd.DataFrame({
            'date': pd.to_datetime([dk(d['date']) for d in sl]),
            'open': [tof(d.get('open')) for d in sl],
            'high': [tof(d.get('high')) for d in sl],
            'low': [tof(d.get('low')) for d in sl],
            'close': [tof(d.get('close')) for d in sl],
            'volume': [tof(d.get('volume')) or 0 for d in sl],
        })
        senv = has_senvision_bottom(df, sym)
        rets = {h: closes[i + h] / closes[i] - 1 for h in HORIZONS}
        samples.append({**b, 'senv_bottom': senv, 'rets': rets})

print()
bm = print_baseline(base_ret)
print(f"底背離訊號 {len(samples)} 筆，其中含蔡森底型態 {sum(s['senv_bottom'] for s in samples)} 筆\n")
evalrule = make_reporter(samples, bm)

evalrule("① 底背離(全部)", lambda s: True)
evalrule("② 底背離 ∩ 蔡森底型態", lambda s: s['senv_bottom'])
evalrule("③ 底背離 但無蔡森型態", lambda s: not s['senv_bottom'])
evalrule("④ 兩者 + OBV斜率濾後未反彈", lambda s: s['senv_bottom'] and not s['rebound'])
evalrule("⑤ 兩者 + 已反彈(確認轉折)", lambda s: s['senv_bottom'] and s['rebound'])
