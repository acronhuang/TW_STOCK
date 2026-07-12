#!/usr/bin/env python3
"""絕望量 + 確認(A/B) + 多重驗證 回測。
進場點 = 確認日(絕望量後1~3日,量縮未破底)，量測該日起前向報酬 vs 全體基準。
連續掃描日期窗以增大稀疏訊號樣本。"""
import sys, os, warnings
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
warnings.filterwarnings('ignore')
import numpy as np
from pymongo import MongoClient
from src.factors.volume_factors import VolumeFactors
from src.utils.backtest import tof, HORIZONS, print_baseline, report, make_reporter

db = MongoClient('localhost', 27017)['tw_stock_analysis']
vf = VolumeFactors(db)

WIN_START, WIN_END = '2026-01-15', '2026-05-18'   # 評估日窗(需 +20 前向)
MIN_VOL = 500 * 1000
CAP_LOW_W, CAP_VOL_PCT = 20, 88

def vol_pct_at(vols, j):
    seg = vols[max(0, j-59):j+1]
    return (seg <= vols[j]).mean() * 100

def is_cap(closes, lows, vols, j):
    if j < CAP_LOW_W:
        return False
    new_low = closes[j] <= closes[j-CAP_LOW_W+1:j+1].min() * 1.003
    return bool(new_low and vol_pct_at(vols, j) >= CAP_VOL_PCT)

def stoch_k(closes, highs, lows, i, n=9, span=30):
    """遞迴 %K(K=2/3前+1/3RSV)，自 i-span 起 seed=50。回 (K_i, K_prev)。"""
    s = max(n, i-span)
    K = 50.0; Kprev = 50.0
    for t in range(s, i+1):
        ll = lows[t-n+1:t+1].min(); hh = highs[t-n+1:t+1].max()
        rsv = (closes[t]-ll)/(hh-ll)*100 if hh > ll else 50.0
        Kprev = K
        K = K*2/3 + rsv/3
    return K, Kprev

syms = [s for s in db.stock_price.distinct('symbol') if s.isdigit() and len(s) == 4]
print(f"回測 {len(syms)} 檔，評估窗 {WIN_START}~{WIN_END} ...")

samples = []
base_ret = {h: [] for h in HORIZONS}
cap_naked = {h: [] for h in HORIZONS}   # 裸絕望量(進場=絕望量當日)

for sym in syms:
    docs = list(db.stock_price.find(
        {'symbol': sym}, {'date': 1, 'high': 1, 'low': 1, 'close': 1, 'volume': 1}).sort('date', 1))
    if len(docs) < 90:
        continue
    dk = lambda d: d.strftime('%Y-%m-%d') if hasattr(d, 'strftime') else str(d)[:10]
    ds = [dk(d['date']) for d in docs]
    close = np.array([tof(d.get('close')) or np.nan for d in docs])
    high = np.array([tof(d.get('high')) or np.nan for d in docs])
    low = np.array([tof(d.get('low')) or np.nan for d in docs])
    vol = np.array([tof(d.get('volume')) or 0.0 for d in docs])
    if np.isnan(close).any() or np.isnan(low).any():
        continue
    n = len(close)
    for i in range(60, n - max(HORIZONS)):
        if not (WIN_START <= ds[i] <= WIN_END):
            continue
        if np.mean(vol[i-19:i+1]) < MIN_VOL:
            continue
        for h in HORIZONS:
            base_ret[h].append(close[i+h]/close[i]-1)
        if is_cap(close, low, vol, i):
            for h in HORIZONS:
                cap_naked[h].append(close[i+h]/close[i]-1)
        # 找最近 1~3 日的絕望量 D
        D = next((j for j in (i-1, i-2, i-3) if is_cap(close, low, vol, j)), None)
        if D is None:
            continue
        qcut = vol[i] <= vol[D]*0.5                      # 確認A-量縮
        held = low[D+1:i+1].min() >= low[D]*0.99         # 確認A-未破底
        if not (qcut and held):
            continue
        ma5 = close[i] > close[i-4:i+1].mean()           # 確認B-站回MA5
        obv = (vf.calculate_obv_slope(close[:i+1], vol[:i+1]) or 0) > 0
        K, Kp = stoch_k(close, high, low, i)
        kd = (K < 35 and K > Kp)                          # KD低檔回升
        samples.append({'ma5': ma5, 'obv': obv, 'kd': kd,
                        'rets': {h: close[i+h]/close[i]-1 for h in HORIZONS}})

print()
bm = print_baseline(base_ret)
print()
report("V0 裸絕望量(進場=當日)", cap_naked, bm)

sub = make_reporter(samples, bm)
print(f"\n確認日總數(絕望量+確認A) = {len(samples)}")
sub("V1 +確認A(量縮未破底)", lambda s: True)
sub("V2 +A+B(站回MA5)", lambda s: s['ma5'])
sub("V3 +A+OBV流入", lambda s: s['obv'])
sub("V4 +A+KD低檔回升", lambda s: s['kd'])
sub("V5 +A+多重驗證≥1", lambda s: (s['ma5']+s['obv']+s['kd']) >= 1)
sub("V6 +A+多重驗證≥2", lambda s: (s['ma5']+s['obv']+s['kd']) >= 2)
sub("V7 +A+B+驗證≥2", lambda s: s['ma5'] and (s['obv']+s['kd']) >= 1)
