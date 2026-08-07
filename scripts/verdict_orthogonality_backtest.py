#!/usr/bin/env python3
"""
verdict 命中率 × 委員正交性回測 —— NFR-QUAL-001 常態 SLI（月度）

用法:
  verdict_orthogonality_backtest.py                 算 + 印 + 寫 verdict_performance 快照
  verdict_orthogonality_backtest.py --dry-run       只算 + 印，不寫 DB
  verdict_orthogonality_backtest.py --alert         破 NFR-QUAL 門檻才寫 schedule_alerts
  verdict_orthogonality_backtest.py --window 20     前瞻交易日數（預設 20）

純讀 team_analysis / stock_price；寫入僅 verdict_performance（快照）與可選 schedule_alerts。
NFR-QUAL-001 門檻：買進 方向命中 ≥ 55% 且 均超額 ≥ +1.5%。
"""
import sys, bisect, math, argparse, datetime
from collections import defaultdict, Counter
from pymongo import MongoClient

DB = MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]
QUAL_HIT = 0.55      # NFR-QUAL-001 命中率門檻
QUAL_EXCESS = 0.015  # NFR-QUAL-001 超額門檻
MIN_N = 30           # 樣本過小不告警（避免雜訊誤報）

SYN = [('賣出', ('賣出', '賣', '減碼', '出場', '看空')),
       ('買進', ('買進', '買', '加碼', '進場', '看多')),
       ('持有', ('持有', '觀望', '中立', '不動', '續抱'))]


def to_f(x):
    try:
        return float(str(x))   # 處理 Decimal128（float(Decimal128) 會拋例外）
    except Exception:
        return None


def load_verdicts():
    docs = []
    for d in DB.team_analysis.find({}, {'symbol': 1, 'date': 1, 'final_verdict': 1,
                                        'consensus': 1}):
        if d.get('final_verdict') and d.get('symbol') and isinstance(d.get('date'), datetime.datetime):
            docs.append(d)
    return docs


def price_series(symbols):
    ser = {}
    for s in symbols:
        rows = [(r['date'], to_f(r.get('adj_close'))) for r in
                DB.stock_price.find({'symbol': s, 'adj_close': {'$ne': None}},
                                    {'date': 1, 'adj_close': 1}).sort('date', 1)]
        ser[s] = [(dt, px) for dt, px in rows if px]
    return ser


def fwd_return(ser, sym, vdate, fwd):
    s = ser.get(sym)
    if not s or len(s) < 2:
        return None, None
    ds = [x[0] for x in s]
    i = bisect.bisect_right(ds, vdate) - 1
    if i < 0 or i + fwd >= len(s):
        return None, None
    p0, pN = s[i][1], s[i + fwd][1]
    return (pN / p0 - 1.0, s[i][0]) if p0 else (None, None)


def compute(fwd):
    docs = load_verdicts()
    ser = price_series(sorted({d['symbol'] for d in docs}))
    for d in docs:
        r, p0d = fwd_return(ser, d['symbol'], d['date'], fwd)
        d['_fwd'], d['_p0'] = r, p0d
    usable = [d for d in docs if d['_fwd'] is not None]

    # 橫斷面基準（同 P0 日、分析池平均）
    by_date = defaultdict(list)
    for d in usable:
        by_date[d['_p0']].append(d['_fwd'])
    bench = {dt: sum(v) / len(v) for dt, v in by_date.items()}
    for d in usable:
        d['_ex'] = d['_fwd'] - bench[d['_p0']]

    def cls(v, hit_fn):
        rows = [d for d in usable if d['final_verdict'] == v]
        n = len(rows)
        if not n:
            return {'n': 0}
        fwds = [d['_fwd'] for d in rows]
        exs = [d['_ex'] for d in rows]
        return {'n': n,
                'mean_ret': sum(fwds) / n, 'median_ret': sorted(fwds)[n // 2],
                'hit': sum(1 for d in rows if hit_fn(d)) / n,
                'mean_excess': sum(exs) / n,
                'excess_pos': sum(1 for x in exs if x > 0) / n,
                'excess_ge_1p5': sum(1 for x in exs if x >= QUAL_EXCESS) / n}

    buy = cls('買進', lambda d: d['_fwd'] > 0)
    sell = cls('賣出', lambda d: d['_fwd'] < 0)
    spread = (buy.get('mean_ret', 0) - sell.get('mean_ret', 0)) if buy['n'] and sell['n'] else None

    # 委員正交性
    V = {'買進': 1, '持有': 0, '賣出': -1}
    mv = defaultdict(dict)
    for d in docs:
        for v in (d.get('consensus') or {}).get('votes') or []:
            if v.get('model') and v.get('vote') in V:
                mv[str(d['_id'])][v['model']] = V[v['vote']]
    models = sorted({m for x in mv.values() for m in x})
    pairs = []
    for i in range(len(models)):
        for j in range(i + 1, len(models)):
            xs, ys = [], []
            for x in mv.values():
                if models[i] in x and models[j] in x:
                    xs.append(x[models[i]]); ys.append(x[models[j]])
            if len(xs) >= 5:
                n = len(xs)
                agree = sum(1 for k in range(n) if xs[k] == ys[k]) / n
                mx, my = sum(xs) / n, sum(ys) / n
                cov = sum((xs[k] - mx) * (ys[k] - my) for k in range(n))
                sx = math.sqrt(sum((x - mx) ** 2 for x in xs)); sy = math.sqrt(sum((y - my) ** 2 for y in ys))
                corr = cov / (sx * sy) if sx and sy else None
                pairs.append({'a': models[i], 'b': models[j], 'n': n,
                              'agree': round(agree, 3), 'corr': round(corr, 3) if corr is not None else None})
    max_pair = max((p for p in pairs if p['corr'] is not None), key=lambda p: p['corr'], default=None)
    bias = {}
    for m in models:
        cnt = Counter(); tot = 0
        for x in mv.values():
            if m in x:
                cnt[x[m]] += 1; tot += 1
        if tot:
            bias[m] = {'buy%': round(cnt[1] * 100 / tot, 1), 'hold%': round(cnt[0] * 100 / tot, 1),
                       'sell%': round(cnt[-1] * 100 / tot, 1)}

    return {'window': fwd, 'n_usable': len(usable), 'buy': buy, 'sell': sell,
            'buy_sell_spread_pp': round(spread * 100, 2) if spread is not None else None,
            'committee': {'models': models, 'pairs': pairs, 'max_corr_pair': max_pair, 'bias': bias}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--window', type=int, default=20)
    ap.add_argument('--dry-run', action='store_true', help='只算不寫 DB')
    ap.add_argument('--alert', action='store_true', help='破 NFR-QUAL 門檻才寫 schedule_alerts')
    a = ap.parse_args()

    r = compute(a.window)
    b = r['buy']
    print(f"=== verdict SLI (前瞻 {r['window']} 交易日) ===")
    print(f"完整視窗樣本 N={r['n_usable']}")
    if b['n']:
        print(f"買進 N={b['n']} 方向命中={b['hit']*100:.1f}% 均超額={b['mean_excess']*100:+.2f}% "
              f"超額≥1.5%={b['excess_ge_1p5']*100:.1f}%")
    if r['sell']['n']:
        s = r['sell']
        print(f"賣出 N={s['n']} 方向命中={s['hit']*100:.1f}% 均報酬={s['mean_ret']*100:+.2f}%")
    print(f"買-賣 spread = {r['buy_sell_spread_pp']} pp")
    mp = r['committee']['max_corr_pair']
    if mp:
        print(f"委員最高相關: {mp['a']} × {mp['b']} 同票{mp['agree']*100:.1f}% corr={mp['corr']:+.2f}")

    # NFR-QUAL 判定
    qual_pass = None
    if b['n'] >= MIN_N:
        qual_pass = (b['hit'] >= QUAL_HIT) and (b['mean_excess'] >= QUAL_EXCESS)
        print(f"NFR-QUAL-001: {'✅ 達標' if qual_pass else '🔴 未達標'} "
              f"(門檻 命中≥{QUAL_HIT*100:.0f}% 且 均超額≥{QUAL_EXCESS*100:.1f}%)")
    else:
        print(f"NFR-QUAL-001: 樣本 <{MIN_N}，不判定")

    snapshot = {'ts': datetime.datetime.now(), 'source': 'verdict_sli', **r, 'nfr_qual_pass': qual_pass}
    if a.dry_run:
        print("[dry-run] 未寫 DB")
    else:
        DB.verdict_performance.create_index([('ts', -1)])
        DB.verdict_performance.insert_one(dict(snapshot))
        print("[ok] 已寫 verdict_performance 快照")

    if a.alert and qual_pass is False:
        DB.schedule_alerts.create_index([('ts', -1)])
        DB.schedule_alerts.insert_one({
            'ts': datetime.datetime.now(), 'level': 'warning', 'source': 'verdict_sli',
            'message': f"⚠️ NFR-QUAL-001 未達標: 買進方向命中 {b['hit']*100:.1f}%(需≥55%) "
                       f"均超額 {b['mean_excess']*100:+.2f}%(需≥1.5%), N={b['n']}",
            'resolved': False})
        print("[alert] 已寫 schedule_alerts")
    return 0


if __name__ == '__main__':
    sys.exit(main())
