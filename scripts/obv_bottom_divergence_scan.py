#!/usr/bin/env python3
"""
OBV 底背離 × 蔡森底型態 × 尚未反彈 —— 每日三重共振底部掃描
============================================================
回測驗證(2026 Q1-Q2, 7訊號日)：此三重組合 20日 +10.9% vs 基準 +7.9%(超額+3%)、勝率74%。
單一底背離無 edge；「已反彈」會追死貓跳變負 → 必須三條件同時成立。

條件(逐股當日)：
  1. OBV 真底背離：價格更低低點 + OBV 抬高低點 + 現價在區間下半 (detect_obv_divergence)
  2. 尚未反彈：現價 ≤ 第二低點之上一點點(rebound=False) → 在轉折前進場
  3. 蔡森底型態：SenVision 偵測到 W-Bottom / Triple-Bottom / HS-Bottom 等

用法：
  python scripts/obv_bottom_divergence_scan.py            # 掃 + 發 LINE
  python scripts/obv_bottom_divergence_scan.py --no-line  # 只印不發
"""
import sys, os, warnings
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
warnings.filterwarnings('ignore')
import numpy as np
import pandas as pd
from datetime import datetime
from pymongo import MongoClient
from src.factors.volume_factors import VolumeFactors
from src.senvision.analysis import analyze_timeframe

MIN_VOL = 500 * 1000   # 近20日均量(股)門檻


def tof(v):
    try:
        return float(v.to_decimal()) if hasattr(v, 'to_decimal') else float(v)
    except Exception:
        return None


def senvision_bottom(df, sym):
    """回傳蔡森底型態名稱(找到第一個)或 None。"""
    try:
        res = analyze_timeframe(df, sym, 'D')
    except Exception:
        return None
    if not res:
        return None
    for p in res.get('patterns', []):
        pt = getattr(p, 'pattern_type', None)
        ptv = getattr(pt, 'value', None) or str(pt)
        if 'Bottom' in ptv:
            return ptv
    return None


def scan(db):
    vf = VolumeFactors(db)
    latest = db.stock_price.find_one(sort=[('date', -1)])['date']
    syms = [s for s in db.stock_price.distinct('symbol') if s.isdigit() and len(s) == 4]
    hits = []
    for sym in syms:
        closes, vols = vf._load_series(sym, latest)
        if closes is None or len(closes) < 40:
            continue
        if np.mean(vols[-20:]) < MIN_VOL:
            continue
        d = vf.detect_obv_divergence(closes, vols)
        b = d['bottom']
        if not b or b['rebound']:          # 需底背離 且 尚未反彈
            continue
        # 候選 → 跑蔡森型態(近180根 OHLCV)
        docs = list(db.stock_price.find(
            {'symbol': sym},
            {'date': 1, 'open': 1, 'high': 1, 'low': 1, 'close': 1, 'volume': 1, 'name': 1}
        ).sort('date', -1).limit(180))
        docs = docs[::-1]
        dk = lambda x: x.strftime('%Y-%m-%d') if hasattr(x, 'strftime') else str(x)[:10]
        df = pd.DataFrame({
            'date': pd.to_datetime([dk(x['date']) for x in docs]),
            'open': [tof(x.get('open')) for x in docs],
            'high': [tof(x.get('high')) for x in docs],
            'low': [tof(x.get('low')) for x in docs],
            'close': [tof(x.get('close')) for x in docs],
            'volume': [tof(x.get('volume')) or 0 for x in docs],
        })
        pat = senvision_bottom(df, sym)
        if not pat:
            continue
        nm = next((x.get('name') for x in reversed(docs) if x.get('name')), '') or ''
        hits.append({
            'symbol': sym, 'name': nm, 'close': float(closes[-1]), 'pattern': pat,
            'price_ll': b['price_ll'], 'obv_hl': b['obv_hl'], 'pos': b['pos'], 'recent': b['recent'],
        })
    # 排序：OBV 抬高幅度(背離清晰度) desc
    hits.sort(key=lambda h: -(h['obv_hl'] + h['price_ll']))
    return latest, hits


def build_line(latest, hits, top=15):
    d = latest.strftime('%m/%d') if hasattr(latest, 'strftime') else str(latest)[:10]
    L = [f"🔵 OBV底背離×蔡森底型態 ({d})",
         f"  三重共振·底部承接(未反彈) 共{len(hits)}檔",
         "  〔回測:20日超額+3%·勝74%,n小〕\n"]
    if not hits:
        L.append("  今日無符合(嚴格訊號,常0~5檔)")
    for h in hits[:top]:
        L.append(f"{h['symbol']} {h['name']} {h['close']:g} 🔷{h['pattern']} "
                 f"價低{-h['price_ll']*100:.1f}%/OBV抬{h['obv_hl']*100:.0f}% 區間位{h['pos']*100:.0f}%")
    return '\n'.join(L)


def main():
    no_line = '--no-line' in sys.argv
    db = MongoClient('localhost', 27017)['tw_stock_analysis']
    latest, hits = scan(db)
    msg = build_line(latest, hits)
    print(msg)
    if not no_line:
        try:
            from src.alerts.line_notifier import LineNotifier
            ln = LineNotifier()
            if ln.enabled:
                ln.send(msg); print("\n✅ LINE 已發送")
            else:
                print("\n⚠️ LINE 未設定")
        except Exception as e:
            print(f"\n⚠️ LINE 失敗: {e}")


if __name__ == '__main__':
    main()
