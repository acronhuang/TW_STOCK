#!/usr/bin/env python3
"""
主力/散戶籌碼研判掃描（每日）
==============================
量價看得出「資金進出」，看不出「是誰在買」。本腳本交叉兩組籌碼足跡判斷主力 vs 散戶：

  主力  = 三大法人（institutional_flow：外資/投信/自營淨買超，單位 股 → 張）
  散戶  = 融資餘額變化（margin_purchase_short_sale：融資戶多為散戶，單位 張）

核心判準（法人 vs 融資「背離」）：
  ✅ 主力吸籌·散戶退   法人買 + 融資減   籌碼集中，最健康
  ⚠️ 主力出貨·散戶接   法人賣 + 融資增   籌碼渙散，見頂危險
  ➕ 法人散戶齊買       法人買 + 融資增   短多，留意融資過熱
  ➖ 法人散戶齊賣       法人賣 + 融資減   同步退場

另與量價因子（obv_slope / volume_ratio）交叉，標出「主力吸籌 + 量價共振」的最強組合 🔥。

輸出：
  1. CSV  results/chip/chip_scan_YYYYMMDD.csv（全市場，含 4 向研判與籌碼分數）
  2. LINE 摘要（主力吸籌榜 / 主力出貨警示 / 共振榜）

用法：
    python3 scripts/chip_score_scan.py                # 跑 + 發 LINE
    python3 scripts/chip_score_scan.py --no-line
    python3 scripts/chip_score_scan.py --top 10 --min-volume 1000
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from pathlib import Path

from bson import Decimal128
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 研判門檻（張）：低於此視為「不明顯」，避免 0 附近的雜訊被判成買/賣
INST_FLOOR = 100   # 法人淨買賣達此張數才算主力有動作
MGN_FLOOR = 50     # 融資增減達此張數才算散戶有動作


def _tof(v):
    if isinstance(v, Decimal128):
        return float(v.to_decimal())
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def read_institutional(db, ref_date):
    """{symbol: {foreign,trust,dealer,total}}（張）。法人 total_net 單位為股 → /1000。"""
    out = {}
    for x in db.institutional_flow.find(
            {'date': ref_date},
            {'stock_id': 1, 'foreign_net': 1, 'trust_net': 1, 'dealer_net': 1, 'total_net': 1}):
        sym = x.get('stock_id')
        if not sym:
            continue
        def lots(k):
            v = _tof(x.get(k))
            return round(v / 1000) if v is not None else 0
        out[sym] = {'foreign': lots('foreign_net'), 'trust': lots('trust_net'),
                    'dealer': lots('dealer_net'), 'total': lots('total_net')}
    return out


def read_margin(db, ref_date):
    """{symbol: {margin_chg, short_chg}}（張）。相容新舊兩種 schema。
    新（TWSE OpenAPI，2026-04 起）：code / margin_balance / margin_prev_balance / short_*
    舊（FinMind，歷史）：stock_id / MarginPurchaseTodayBalance / MarginPurchaseYesterdayBalance / ShortSale*
    """
    out = {}
    for d in db.margin_purchase_short_sale.find({'date': ref_date}):
        if 'margin_balance' in d:                      # 新 schema
            sym = d.get('code')
            mb, mp = _tof(d.get('margin_balance')), _tof(d.get('margin_prev_balance'))
            sb, sp = _tof(d.get('short_balance')), _tof(d.get('short_prev_balance'))
        else:                                          # 舊 schema
            sym = d.get('stock_id')
            mb, mp = _tof(d.get('MarginPurchaseTodayBalance')), _tof(d.get('MarginPurchaseYesterdayBalance'))
            sb, sp = _tof(d.get('ShortSaleTodayBalance')), _tof(d.get('ShortSaleYesterdayBalance'))
        if not sym or mb is None or mp is None:
            continue
        out[sym] = {'margin_chg': round(mb - mp),
                    'short_chg': round((sb - sp)) if sb is not None and sp is not None else 0}
    return out


def read_inst_streak(db, ref_date, lookback_days=12):
    """法人連續同向天數（連買 +N / 連賣 -N）。專業籌碼分析強調『連續性』——
    連續買超越多天，主力吸籌越確立；單日淨買可能只是雜訊。一次撈近 N 日全市場計算。"""
    dates = sorted(db.institutional_flow.distinct('date', {'date': {'$lte': ref_date}}))[-lookback_days:]
    if not dates:
        return {}
    series = defaultdict(dict)
    for x in db.institutional_flow.find(
            {'date': {'$in': dates}}, {'stock_id': 1, 'total_net': 1, 'date': 1}):
        series[x['stock_id']][x['date']] = _tof(x.get('total_net')) or 0.0
    streak = {}
    for sym, dm in series.items():
        vals = [dm.get(d, 0.0) for d in dates]        # 依日期升冪
        last = vals[-1]
        if last == 0:
            streak[sym] = 0
            continue
        sign = 1 if last > 0 else -1
        n = 0
        for v in reversed(vals):                       # 從最新往回數同號
            if (v > 0 and sign > 0) or (v < 0 and sign < 0):
                n += 1
            else:
                break
        streak[sym] = sign * n
    return streak


def read_holder_conc(db):
    """大戶集中度（集保股權分散，TDCC 每週）：{symbol: (big_pct, big_chg)}。
    big_pct = 千張大戶（級15）佔比；big_chg = 對比上一週快照的變化（≥2 週快照才有，否則 None）。
    大戶佔比週增 = 籌碼集中/主力吸籌的第三方確認（獨立於法人/融資）。"""
    dates = sorted(db.shareholding.distinct('date'))[-2:]
    if not dates:
        return {}
    latest = dates[-1]
    cur = {d['stock_id']: d.get('big_pct') for d in
           db.shareholding.find({'date': latest}, {'stock_id': 1, 'big_pct': 1})}
    pv = {}
    if len(dates) > 1:
        pv = {d['stock_id']: d.get('big_pct') for d in
              db.shareholding.find({'date': dates[0]}, {'stock_id': 1, 'big_pct': 1})}
    out = {}
    for sym, bp in cur.items():
        p = pv.get(sym)
        out[sym] = (bp, round(bp - p, 2) if (bp is not None and p is not None) else None)
    return out


def _is_etf(sym: str) -> bool:
    """台股 ETF 代碼以 00 開頭（0050/0056/00xxx/009xxx）。其法人流量為申贖/再平衡機械性
    流動，非『主力』情緒，主力散戶研判預設排除。"""
    return sym.startswith('00')


def load(db, min_volume_lots, min_price, include_etf=False):
    """彙整最新交易日的 法人 + 融資 + 股價 + 量價因子。回傳 (ref_date, rows, m_date)。"""
    idoc = db.institutional_flow.find_one({}, sort=[('date', -1)])
    if not idoc:
        return None, [], None
    ref = idoc['date']
    inst = read_institutional(db, ref)
    streak = read_inst_streak(db, ref)
    holders = read_holder_conc(db)

    # 融資：優先同日；若當日尚未更新則退回融資自己的最新日（並記錄落後）
    mdoc = db.margin_purchase_short_sale.find_one({'date': ref})
    m_date = ref if mdoc else (db.margin_purchase_short_sale.find_one({}, sort=[('date', -1)]) or {}).get('date')
    margin = read_margin(db, m_date) if m_date else {}

    # 股價（當日 + 前一交易日算漲跌）
    pdates = sorted(db.stock_price.distinct('date', {'date': {'$lte': ref}}))[-2:]
    today_d = pdates[-1]
    prev_d = pdates[0] if len(pdates) > 1 else today_d
    today = {p['symbol']: p for p in db.stock_price.find(
        {'date': today_d}, {'symbol': 1, 'close': 1, 'volume': 1, 'name': 1})}
    prev = {p['symbol']: _tof(p.get('close')) for p in db.stock_price.find(
        {'date': prev_d}, {'symbol': 1, 'close': 1})}

    # 量價因子（obv_slope / volume_ratio）供共振判斷
    fac = {f['symbol']: f for f in db.stock_factors.find(
        {'date': today_d}, {'symbol': 1, 'obv_slope': 1, 'volume_ratio': 1})}

    min_shares = min_volume_lots * 1000
    rows = []
    for sym, ins in inst.items():
        if not include_etf and _is_etf(sym):          # 排除 ETF（機械性申贖流動）
            continue
        p = today.get(sym)
        if not p:
            continue
        close, vol = _tof(p.get('close')), _tof(p.get('volume'))
        if close is None or vol is None or close < min_price or vol < min_shares:
            continue
        vol_lots = round(vol / 1000) or 1
        mg = margin.get(sym, {'margin_chg': 0, 'short_chg': 0})
        pc = prev.get(sym)
        chg = ((close - pc) / pc * 100) if pc and pc > 0 else None
        f = fac.get(sym, {})
        rows.append({
            'symbol': sym, 'name': p.get('name', ''), 'close': close,
            'change_pct': round(chg, 2) if chg is not None else None,
            'vol_lots': vol_lots,
            'inst_net': ins['total'], 'foreign': ins['foreign'],
            'trust': ins['trust'], 'dealer': ins['dealer'],
            'streak': streak.get(sym, 0),
            'big_pct': holders.get(sym, (None, None))[0],
            'big_chg': holders.get(sym, (None, None))[1],
            'margin_chg': mg['margin_chg'], 'short_chg': mg['short_chg'],
            'obv_slope': f.get('obv_slope'), 'volume_ratio': f.get('volume_ratio'),
        })
    return ref, rows, m_date


def judge(r):
    """回 (tag, score)。tag 為四向研判；score 為籌碼分數（法人佔量% − 融資佔量%，越正=主力越淨進）。"""
    idir = 1 if r['inst_net'] >= INST_FLOOR else (-1 if r['inst_net'] <= -INST_FLOOR else 0)
    mdir = 1 if r['margin_chg'] >= MGN_FLOOR else (-1 if r['margin_chg'] <= -MGN_FLOOR else 0)
    if idir > 0 and mdir < 0:
        tag = '主力吸籌·散戶退'
    elif idir < 0 and mdir > 0:
        tag = '主力出貨·散戶接'
    elif idir > 0 and mdir > 0:
        tag = '法人散戶齊買'
    elif idir < 0 and mdir < 0:
        tag = '法人散戶齊賣'
    else:
        tag = '中性/不明顯'
    v = r['vol_lots']
    score = round(r['inst_net'] / v * 100 - r['margin_chg'] / v * 100, 1)
    return tag, score


def resonance(r, tag):
    """主力吸籌 + 量價共振（OBV 正流入 + 溫和以上放量）→ 最強組合。
    主力吸籌常是溫和量，放量門檻用 1.2（非爆量 2.0）。"""
    return (tag == '主力吸籌·散戶退'
            and (r.get('obv_slope') or 0) > 0
            and (r.get('volume_ratio') or 0) >= 1.2)


def build(rows):
    for r in rows:
        r['tag'], r['score'] = judge(r)
        r['reson'] = resonance(r, r['tag'])
    # 排名把「連買天數」納入加權（連續性 = 主力吸籌確立度，專業籌碼分析共識）
    def w(r):
        return r['score'] + max(0, r.get('streak', 0)) * 8
    accum = sorted([r for r in rows if r['tag'] == '主力吸籌·散戶退'], key=lambda r: -w(r))
    distr = sorted([r for r in rows if r['tag'] == '主力出貨·散戶接'], key=lambda r: r['score'])
    reson = sorted([r for r in rows if r['reson']], key=lambda r: -w(r))
    return accum, distr, reson


def write_csv(ref, rows, out_dir):
    import csv
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"chip_scan_{ref.strftime('%Y%m%d')}.csv"
    cols = ['symbol', 'name', 'close', 'change_pct', 'vol_lots', 'inst_net',
            'foreign', 'trust', 'dealer', 'streak', 'big_pct', 'big_chg',
            'margin_chg', 'short_chg', 'score', 'tag', 'reson']
    header = ['代碼', '名稱', '收盤', '漲跌%', '量(張)', '法人淨(張)', '外資', '投信', '自營',
              '法人連續(+買/-賣)', '千張大戶%', '大戶週變化', '融資增減(張)', '融券增減',
              '籌碼分數', '研判', '量價共振']
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in sorted(rows, key=lambda r: -r['score']):
            w.writerow([r[c] for c in cols])
    return path


def line_msg(ref, m_date, rows, accum, distr, reson, top):
    d = ref.strftime('%m/%d')
    lag = '' if m_date == ref else f"（融資為 {m_date.strftime('%m/%d')}）"

    def f1(r):
        chg = f"{r['change_pct']:+.1f}%" if r['change_pct'] is not None else '—'
        s = r.get('streak', 0)
        streak = f" 連買{s}" if s >= 2 else (f" 連賣{-s}" if s <= -2 else "")
        trust = " 投信買" if r.get('trust', 0) >= 100 else ""
        bc = r.get('big_chg')
        big = f" 大戶{bc:+.1f}%" if bc is not None else (
            f" 大戶{r['big_pct']:.0f}%" if r.get('big_pct') is not None else "")
        return (f"  {r['symbol']} {r['name']} {r['close']:.1f} {chg} "
                f"法人{r['inst_net']:+d} 融資{r['margin_chg']:+d}{streak}{trust}{big}")

    L = [f"🎯 主力/散戶籌碼研判 ({d}){lag}", f"  共 {len(rows)} 檔（法人×融資交叉）\n"]
    L.append(f"🔥 主力吸籌×量價共振 ({len(reson)})")
    L += [f1(r) for r in reson[:top]] or ['  無']
    L.append(f"\n✅ 主力吸籌·散戶退 Top ({len(accum)})")
    L += [f1(r) for r in accum[:top]] or ['  無']
    L.append(f"\n⚠️ 主力出貨·散戶接 警示 ({len(distr)})")
    L += [f1(r) for r in distr[:top]] or ['  無']
    return '\n'.join(L)


def main():
    ap = argparse.ArgumentParser(description="主力/散戶籌碼研判掃描")
    ap.add_argument('--top', type=int, default=8)
    ap.add_argument('--min-volume', type=int, default=500, help='最低成交量（張）')
    ap.add_argument('--min-price', type=float, default=10.0)
    ap.add_argument('--no-line', action='store_true')
    ap.add_argument('--include-etf', action='store_true', help='納入 ETF（預設排除）')
    ap.add_argument('--db-uri', default=os.getenv('MONGODB_URI', 'mongodb://localhost:27017'))
    args = ap.parse_args()

    db = MongoClient(args.db_uri)['tw_stock_analysis']
    ref, rows, m_date = load(db, args.min_volume, args.min_price, include_etf=args.include_etf)
    if not rows:
        print("⚠️ 無法人/融資資料"); return
    accum, distr, reson = build(rows)
    path = write_csv(ref, rows, ROOT / 'results' / 'chip')
    msg = line_msg(ref, m_date, rows, accum, distr, reson, args.top)
    print(msg)
    print(f"\n完整 CSV：{path}")

    if not args.no_line:
        try:
            from dotenv import load_dotenv
            load_dotenv(ROOT / '.env')
            from src.alerts.line_notifier import LineNotifier
            ln = LineNotifier()
            if ln.enabled:
                ln.send(msg); print("✅ LINE 已發送")
            else:
                print("⚠️ LINE 未設定")
        except Exception as e:
            print(f"⚠️ LINE 發送失敗: {e}")


if __name__ == '__main__':
    main()
