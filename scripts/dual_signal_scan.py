#!/usr/bin/env python3
"""
量價 × 籌碼 雙訊號共振掃描（每日）
==================================
把兩個各自獨立的訊號交叉，找出「資金方向」與「是誰在買」互相印證（或互相打臉）的個股：

  量價（資金方向，來自 stock_factors）:  obv_slope / volume_ratio / vol_pct_60d / vp_divergence
  籌碼（是誰在買，法人×融資）:            institutional_flow 淨買  vs  margin 融資增減

四種共振結論：
  🚀 雙多共振    量價多(OBV+/爆量) + 主力吸籌(法人買·融資減)   → 資金進『且』是主力進，最強做多
  🎭 假突破陷阱  量價爆量突破(看似強) + 主力在賣/散戶在追       → 量價騙線，散戶追高主力倒貨（隔日沖常見）
  🕳️ 雙空警示    量價空(OBV-/頂背離) + 主力出貨·散戶接         → 資金退『且』主力倒給散戶，最強看空
  🌱 底部潛伏    量價量縮 + 主力吸籌·散戶退                     → 主力默默吸底、散戶還沒發現

「假突破陷阱」是量價單獨看不出、必須靠籌碼才揭穿的——這正是雙訊號的價值。

輸出：CSV results/dual/dual_scan_YYYYMMDD.csv + LINE 摘要。
用法：python3 scripts/dual_signal_scan.py [--top N] [--no-line] [--min-volume 500]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from pymongo import MongoClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))   # 匯入 sibling script
from chip_score_scan import (_tof, read_institutional, read_margin, read_inst_streak,
                             _is_etf, judge, INST_FLOOR, MGN_FLOOR, _last_complete_date)


def vp_signal(r):
    """量價訊號 → (方向 多/空/中, 型態)。"""
    obv = r['obv_slope'] or 0
    vr = r['volume_ratio'] or 0
    vpct = r['vol_pct_60d'] or 0
    vpd = r['vp_divergence']
    chg = r['change_pct'] or 0
    surge = vr >= 2.0 or vpct >= 90
    if vpd == -1:
        return '空', '頂背離'
    if surge and chg > 0 and obv > 0:
        return '多', '爆量突破'
    if vpd == 1 and obv > 0:
        return '多', '底背離'
    if obv > 0:
        return '多', '資金流入'
    if obv < 0:
        return '空', '資金流出'
    if vr <= 0.7 or vpct <= 20:
        return '中', '量縮'
    return '中', ''


def chip_dir(r):
    """籌碼方向 → (主力進/退/中, 研判標籤)。"""
    tag, _ = judge(r)
    if tag == '主力吸籌·散戶退':
        return '進', tag
    if tag == '法人散戶齊買':
        return '進弱', tag
    if tag == '主力出貨·散戶接':
        return '退', tag
    if tag == '法人散戶齊賣':
        return '退弱', tag
    return '中', tag


def combine(r):
    """交叉量價與籌碼 → (共振碼, 說明)。碼供優先排序與 CSV 標記。"""
    vpd, vpt = vp_signal(r)
    cd, ctag = chip_dir(r)
    r['vp_dir'], r['vp_type'], r['chip_tag'] = vpd, vpt, ctag
    sells = r['inst_net'] <= -INST_FLOOR
    # 假突破陷阱：當日『爆量突破』看似強，但主力在賣 → 散戶追高、主力倒貨（隔日沖常見）
    if vpt == '爆量突破' and sells:
        return 'TRAP', '🎭 假突破陷阱'
    # 雙多共振：量價多 + 主力進
    if vpd == '多' and cd in ('進', '進弱'):
        return 'BULL', '🚀 雙多共振'
    # 量升籌退：OBV/資金流入趨勢仍多，但主力今日已在賣（非爆量）→ 主力偷跑、趨勢轉弱前兆
    if vpd == '多' and sells:
        return 'DIVERGE', '⚡ 量升籌退'
    # 雙空警示：量價空 + 主力退
    if vpd == '空' and cd in ('退', '退弱'):
        return 'BEAR', '🕳️ 雙空警示'
    # 底部潛伏：量縮 + 主力吸籌
    if vpt == '量縮' and cd == '進':
        return 'STEALTH', '🌱 底部潛伏'
    return 'NA', ''


def load(db, min_volume_lots, min_price, include_etf=False):
    # 法人：取最後完整日（跳過 T+1 未齊的最新日），與股價日解耦
    ref = _last_complete_date(db, 'institutional_flow')
    if not ref:
        return None, [], None
    inst = read_institutional(db, ref)
    streak = read_inst_streak(db, ref)
    mdoc = db.margin_purchase_short_sale.find_one({'date': ref})
    m_date = ref if mdoc else (db.margin_purchase_short_sale.find_one({}, sort=[('date', -1)]) or {}).get('date')
    margin = read_margin(db, m_date) if m_date else {}

    # 股價：用自己的最新日（不受法人 ref 牽制，避免被拉回 T-1）
    # $type:date 濾掉 stock_price 中混入的 str 型別髒日期，避免 distinct 排序型別衝突
    pdates = sorted(db.stock_price.distinct('date', {'date': {'$type': 'date'}}))[-2:]
    today_d = pdates[-1]
    prev_d = pdates[0] if len(pdates) > 1 else today_d
    today = {p['symbol']: p for p in db.stock_price.find(
        {'date': today_d}, {'symbol': 1, 'close': 1, 'volume': 1, 'name': 1})}
    prev = {p['symbol']: _tof(p.get('close')) for p in db.stock_price.find(
        {'date': prev_d}, {'symbol': 1, 'close': 1})}
    fac = {f['symbol']: f for f in db.stock_factors.find(
        {'date': today_d},
        {'symbol': 1, 'obv_slope': 1, 'volume_ratio': 1, 'vol_pct_60d': 1, 'vp_divergence': 1})}

    min_shares = min_volume_lots * 1000
    rows = []
    for sym, ins in inst.items():
        if not include_etf and _is_etf(sym):
            continue
        p = today.get(sym)
        if not p:
            continue
        close, vol = _tof(p.get('close')), _tof(p.get('volume'))
        if close is None or vol is None or close < min_price or vol < min_shares:
            continue
        pc = prev.get(sym)
        f = fac.get(sym, {})
        mg = margin.get(sym, {'margin_chg': 0, 'short_chg': 0})
        rows.append({
            'symbol': sym, 'name': p.get('name', ''), 'close': close,
            'change_pct': round((close - pc) / pc * 100, 2) if pc and pc > 0 else None,
            'vol_lots': round(vol / 1000) or 1,
            'inst_net': ins['total'], 'trust': ins['trust'], 'streak': streak.get(sym, 0),
            'margin_chg': mg['margin_chg'],
            'obv_slope': f.get('obv_slope'), 'volume_ratio': f.get('volume_ratio'),
            'vol_pct_60d': f.get('vol_pct_60d'), 'vp_divergence': f.get('vp_divergence'),
        })
    return ref, rows, m_date


def build(rows):
    buckets = {'BULL': [], 'TRAP': [], 'DIVERGE': [], 'BEAR': [], 'STEALTH': []}
    for r in rows:
        code, label = combine(r)
        r['signal'], r['signal_label'] = code, label
        if code in buckets:
            buckets[code].append(r)
    buckets['BULL'].sort(key=lambda r: -(r['inst_net'] - r['margin_chg'] + max(0, r.get('streak', 0)) * 200))
    buckets['TRAP'].sort(key=lambda r: (r['inst_net']))              # 法人賣最多在前
    buckets['DIVERGE'].sort(key=lambda r: (r['inst_net']))
    buckets['BEAR'].sort(key=lambda r: (r['inst_net']))
    buckets['STEALTH'].sort(key=lambda r: -(r['inst_net'] - r['margin_chg']))
    return buckets


def write_csv(ref, rows, out_dir):
    import csv
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"dual_scan_{ref.strftime('%Y%m%d')}.csv"
    cols = ['symbol', 'name', 'close', 'change_pct', 'vol_lots', 'inst_net', 'streak', 'margin_chg',
            'vp_dir', 'vp_type', 'chip_tag', 'signal_label']
    header = ['代碼', '名稱', '收盤', '漲跌%', '量(張)', '法人淨(張)', '法人連續', '融資增減(張)',
              '量價方向', '量價型態', '籌碼研判', '雙訊號結論']
    order = {'TRAP': 0, 'DIVERGE': 1, 'BULL': 2, 'BEAR': 3, 'STEALTH': 4, 'NA': 5}
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in sorted(rows, key=lambda r: (order.get(r.get('signal', 'NA'), 9), -r['inst_net'])):
            w.writerow([r.get(c) for c in cols])
    return path


def line_msg(ref, m_date, rows, b, top):
    d = ref.strftime('%m/%d')
    lag = '' if m_date == ref else f"（融資{m_date.strftime('%m/%d')}）"

    def f1(r):
        chg = f"{r['change_pct']:+.1f}%" if r['change_pct'] is not None else '—'
        s = r.get('streak', 0)
        streak = f" 連買{s}" if s >= 2 else (f" 連賣{-s}" if s <= -2 else "")
        return (f"  {r['symbol']} {r['name']} {r['close']:.1f} {chg} "
                f"法人{r['inst_net']:+d} 融資{r['margin_chg']:+d}{streak}")

    L = [f"🔀 量價×籌碼 雙訊號 ({d}){lag}", f"  掃 {len(rows)} 檔\n"]
    L.append(f"🚀 雙多共振 ({len(b['BULL'])})")
    L += [f1(r) for r in b['BULL'][:top]] or ['  無']
    L.append(f"\n🎭 假突破陷阱 ({len(b['TRAP'])})  ← 爆量但主力賣")
    L += [f1(r) for r in b['TRAP'][:top]] or ['  無']
    L.append(f"\n⚡ 量升籌退 ({len(b['DIVERGE'])})  ← 主力偷跑")
    L += [f1(r) for r in b['DIVERGE'][:top]] or ['  無']
    L.append(f"\n🕳️ 雙空警示 ({len(b['BEAR'])})")
    L += [f1(r) for r in b['BEAR'][:top]] or ['  無']
    L.append(f"\n🌱 底部潛伏 {len(b['STEALTH'])} 檔（詳見 CSV）")
    return '\n'.join(L)


def main():
    ap = argparse.ArgumentParser(description="量價×籌碼 雙訊號共振掃描")
    ap.add_argument('--top', type=int, default=6)
    ap.add_argument('--min-volume', type=int, default=500)
    ap.add_argument('--min-price', type=float, default=10.0)
    ap.add_argument('--no-line', action='store_true')
    ap.add_argument('--include-etf', action='store_true')
    ap.add_argument('--db-uri', default=os.getenv('MONGODB_URI', 'mongodb://localhost:27017'))
    args = ap.parse_args()

    db = MongoClient(args.db_uri)['tw_stock_analysis']
    ref, rows, m_date = load(db, args.min_volume, args.min_price, include_etf=args.include_etf)
    if not rows:
        print("⚠️ 無資料"); return
    b = build(rows)
    path = write_csv(ref, rows, ROOT / 'results' / 'dual')
    msg = line_msg(ref, m_date, rows, b, args.top)
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
