#!/usr/bin/env python3
"""
全市場量價掃描（每日）
=====================
讀取 stock_factors 已算好的量價因子（volume_ratio / vol_pct_60d / obv_slope /
vp_divergence，由 daily_senvision.sh [3/4] 每日為全市場計算），對「所有股票」做
量價分類與排名，輸出：
  1. 完整 CSV（results/volume_price/vp_scan_YYYYMMDD.csv）— 全部符合流動性的個股
  2. LINE 摘要 — 各分類 Top N

分類：
  🔴 爆量突破  量比≥2 或 量能百分位≥90，且當日收紅       （資金進場）
  💰 資金流入  OBV 斜率 > 0，依強度排名                   （持續吸籌）
  ⚠️ 空背警示  量價空頭背離（價漲量未跟）                  （漲勢轉弱）
  🟡 量縮待變  量比≤0.7 或 量能百分位≤20                   （低量整理，伺機變盤）
  📈 多頭背離  量價多頭背離且資金流入                       （底部承接）
  📉 資金流出  OBV 斜率 < 0（僅入 CSV）                     （資金退潮）

用法：
    python3 scripts/volume_price_scan.py                 # 跑 + 發 LINE
    python3 scripts/volume_price_scan.py --no-line       # 只輸出 CSV/終端
    python3 scripts/volume_price_scan.py --top 10 --min-volume 1000
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

from pymongo import MongoClient
from bson import Decimal128

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _tof(v):
    if isinstance(v, Decimal128):
        return float(v.to_decimal())
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def load_universe(db, min_volume_lots: int, min_price: float):
    """載入最新量價因子日的全市場量價資料（已濾流動性）。回傳 (date, list[dict])。"""
    fdoc = db.stock_factors.find_one({'volume_ratio': {'$ne': None}}, sort=[('date', -1)])
    if not fdoc:
        return None, []
    fd = fdoc['date']

    facs = list(db.stock_factors.find(
        {'date': fd, 'volume_ratio': {'$ne': None}},
        {'symbol': 1, 'volume_ratio': 1, 'vol_pct_60d': 1, 'obv_slope': 1, 'vp_divergence': 1},
    ))

    # 最近兩個交易日的股價（算當日漲跌幅）
    price_dates = sorted(db.stock_price.distinct('date', {'date': {'$lte': fd}}))[-2:]
    today_d = price_dates[-1]
    prev_d = price_dates[0] if len(price_dates) > 1 else today_d
    today = {p['symbol']: p for p in db.stock_price.find(
        {'date': today_d}, {'symbol': 1, 'close': 1, 'volume': 1, 'name': 1})}
    prev = {p['symbol']: _tof(p.get('close')) for p in db.stock_price.find(
        {'date': prev_d}, {'symbol': 1, 'close': 1})}

    # 三大法人淨買超（institutional_flow，key=stock_id 同碼，total_net 單位:股）
    inst_dates = sorted(db.institutional_flow.distinct('date', {'date': {'$lte': fd}}))
    inst = {}
    if inst_dates:
        inst = {x['stock_id']: _tof(x.get('total_net'))
                for x in db.institutional_flow.find(
                    {'date': inst_dates[-1]}, {'stock_id': 1, 'total_net': 1})}

    min_vol_shares = min_volume_lots * 1000
    rows = []
    for f in facs:
        sym = f['symbol']
        p = today.get(sym)
        if not p:
            continue
        close = _tof(p.get('close'))
        vol = _tof(p.get('volume'))
        if close is None or vol is None or close < min_price or vol < min_vol_shares:
            continue
        pc = prev.get(sym)
        chg = ((close - pc) / pc * 100) if pc and pc > 0 else None
        inet = inst.get(sym)
        rows.append({
            'symbol': sym,
            'name': p.get('name', ''),
            'close': close,
            'volume_lots': round(vol / 1000),
            'change_pct': round(chg, 2) if chg is not None else None,
            'volume_ratio': f.get('volume_ratio'),
            'vol_pct_60d': f.get('vol_pct_60d'),
            'obv_slope': f.get('obv_slope'),
            'vp_divergence': f.get('vp_divergence'),
            'inst_net_lots': round(inet / 1000) if inet is not None else None,
        })
    return fd, rows


def categorize(rows):
    """依量價因子分類；回傳各分類已排名的 list。"""
    def surge(r):
        return (r['volume_ratio'] or 0) >= 2.0 or (r['vol_pct_60d'] or 0) >= 90

    def shrink(r):
        return (r['volume_ratio'] or 99) <= 0.7 or (r['vol_pct_60d'] or 99) <= 20

    breakout = sorted(
        [r for r in rows if surge(r) and (r['change_pct'] or 0) > 0 and (r['obv_slope'] or 0) > 0],
        key=lambda r: -(r['volume_ratio'] or 0))
    inflow = sorted([r for r in rows if (r['obv_slope'] or 0) > 0],
                    key=lambda r: -(r['obv_slope'] or 0))
    outflow = sorted([r for r in rows if (r['obv_slope'] or 0) < 0],
                     key=lambda r: (r['obv_slope'] or 0))
    bear_div = sorted([r for r in rows if r['vp_divergence'] == -1],
                      key=lambda r: -r['volume_lots'])
    bull_div = sorted([r for r in rows if r['vp_divergence'] == 1 and (r['obv_slope'] or 0) > 0],
                      key=lambda r: -r['volume_lots'])
    consolidate = sorted([r for r in rows if shrink(r)],
                         key=lambda r: (r['vol_pct_60d'] if r['vol_pct_60d'] is not None else 99))
    return {
        'breakout': breakout, 'inflow': inflow, 'outflow': outflow,
        'bear_div': bear_div, 'bull_div': bull_div, 'consolidate': consolidate,
    }


def write_csv(fd, rows, cats, out_dir: Path) -> Path:
    import csv
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"vp_scan_{fd.strftime('%Y%m%d')}.csv"
    # 標記每檔所屬主分類（依優先序）
    tag = {}
    for r in cats['breakout']:   tag.setdefault(r['symbol'], '爆量突破')
    for r in cats['bear_div']:   tag.setdefault(r['symbol'], '空背警示')
    for r in cats['bull_div']:   tag.setdefault(r['symbol'], '多頭背離')
    for r in cats['consolidate']:tag.setdefault(r['symbol'], '量縮待變')
    for r in cats['inflow']:     tag.setdefault(r['symbol'], '資金流入')
    for r in cats['outflow']:    tag.setdefault(r['symbol'], '資金流出')
    cols = ['symbol', 'name', 'close', 'change_pct', 'volume_lots',
            'volume_ratio', 'vol_pct_60d', 'obv_slope', 'vp_divergence', 'category']
    header = ['代碼', '名稱', '收盤', '漲跌%', '量(張)', '量比', '量能百分位', 'OBV斜率', '量價背離', '分類']
    rank = sorted(rows, key=lambda r: -(r['obv_slope'] or -99))
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rank:
            w.writerow([r['symbol'], r['name'], r['close'], r['change_pct'], r['volume_lots'],
                        r['volume_ratio'], r['vol_pct_60d'], r['obv_slope'], r['vp_divergence'],
                        tag.get(r['symbol'], '')])
    return path


# 台股漲停約 +10%（含跳動取整 ~9.8%），>=此值視為已漲停
LIMIT_UP_PCT = 9.5


def build_line_message(fd, rows, cats, top: int, refined: bool = False) -> str:
    d = fd.strftime('%m/%d')

    def fmt(r):
        chg = f"{r['change_pct']:+.1f}%" if r['change_pct'] is not None else "—"
        return f"  {r['symbol']} {r['name']} {r['close']:.1f} {chg} 量比{r['volume_ratio']:.1f}"

    def inst_mark(r):
        n = r.get('inst_net_lots')
        return f" 法人{n:+d}張" if n else ""

    if not refined:
        # ── 版本 A：現行版 ──
        L = [f"📊 全市場量價掃描 ({d})", f"  共 {len(rows)} 檔（已濾流動性）\n"]
        L.append(f"🔴 爆量突破 ({len(cats['breakout'])})")
        L += [fmt(r) for r in cats['breakout'][:top]] or ["  無"]
    else:
        # ── 版本 B：精選版（爆量突破排除漲停 + 法人同步買超交叉）──
        breakout_started = [r for r in cats['breakout'] if (r['change_pct'] or 0) < LIMIT_UP_PCT]
        cross = sorted([r for r in breakout_started if (r.get('inst_net_lots') or 0) > 0],
                       key=lambda r: -(r['inst_net_lots'] or 0))
        L = [f"📊 全市場量價·精選版 ({d})",
             f"  共 {len(rows)} 檔；爆量突破排除漲停＋法人交叉\n"]
        L.append(f"🔥 爆量突破×法人買超 ({len(cross)})")
        L += [fmt(r) + inst_mark(r) for r in cross[:top]] or ["  無"]
        L.append(f"\n🔴 爆量突破·剛啟動 ({len(breakout_started)})")
        L += [fmt(r) + inst_mark(r) for r in breakout_started[:top]] or ["  無"]

    L.append(f"\n💰 資金流入榜 ({len(cats['inflow'])})")
    L += [f"  {r['symbol']} {r['name']} {r['close']:.1f} OBV{r['obv_slope']:+.2f}" + inst_mark(r)
          for r in cats['inflow'][:top]] or ["  無"]

    L.append(f"\n⚠️ 量價空背警示 ({len(cats['bear_div'])})")
    L += [fmt(r) + inst_mark(r) for r in cats['bear_div'][:top]] or ["  無"]

    L.append(f"\n🟡 量縮待變 ({len(cats['consolidate'])})")
    L += [f"  {r['symbol']} {r['name']} {r['close']:.1f} 量能{r['vol_pct_60d']:.0f}%"
          for r in cats['consolidate'][:top]] or ["  無"]

    # 市場量能廣度
    L.append(f"\n📈 資金流入 {len(cats['inflow'])} / 流出 {len(cats['outflow'])}")
    return '\n'.join(L)


def main():
    ap = argparse.ArgumentParser(description="全市場量價掃描（每日）")
    ap.add_argument('--top', type=int, default=8, help='各分類 LINE 顯示檔數')
    ap.add_argument('--min-volume', type=int, default=500, help='最低成交量（張）')
    ap.add_argument('--min-price', type=float, default=10.0, help='最低股價')
    ap.add_argument('--no-line', action='store_true', help='不發 LINE')
    ap.add_argument('--refined', action='store_true',
                    help='精選版：爆量突破排除漲停 + 法人同步買超交叉')
    ap.add_argument('--db-uri', default=os.getenv('MONGODB_URI', 'mongodb://localhost:27017'))
    args = ap.parse_args()

    db = MongoClient(args.db_uri)['tw_stock_analysis']
    fd, rows = load_universe(db, args.min_volume, args.min_price)
    if not rows:
        print("⚠️ 無量價因子資料，請先跑 parallel_factor_calculation.py")
        return

    cats = categorize(rows)
    path = write_csv(fd, rows, cats, ROOT / 'results' / 'volume_price')
    msg = build_line_message(fd, rows, cats, args.top, refined=args.refined)

    print(msg)
    print(f"\n完整 CSV：{path}")

    if not args.no_line:
        try:
            from dotenv import load_dotenv
            load_dotenv(ROOT / '.env')
            from src.alerts.line_notifier import LineNotifier
            ln = LineNotifier()
            if ln.enabled:
                ln.send(msg)
                print("✅ LINE 已發送")
            else:
                print("⚠️ LINE 未設定，略過")
        except Exception as e:
            print(f"⚠️ LINE 發送失敗: {e}")


if __name__ == '__main__':
    main()
