#!/usr/bin/env python3
"""
Backfill pe_ratio / pb_ratio / earnings_yield into stock_factors from
quarterly_earnings. Point-in-time: only reports whose statutory filing deadline
(publish date) <= the price date are used for EPS/equity -> no look-ahead.

  PE  = close / TTM_EPS         (TTM = sum trailing 4 single-quarter income.eps)
  EY  = TTM_EPS / close         (earnings yield; keeps negative for loss-makers)
  PB  = close / BVPS            (BVPS = equity_pit / shares ; shares = cap/10)

Shares: capital_stock is one current snapshot per symbol (season-1 only), used
for all historical dates (shares ~static; standard fallback). EPS/equity stay
point-in-time. Guards: PE in (0,2000], PB in (0,50], EY in [-5,5]. Self-clearing:
$unset stale values when a metric computes None. Updates existing stock_factors
docs by (symbol,date); never creates docs.

Usage:
  python backfill_pe_pb_factors.py --dry-run --symbols 2303,6182
  python backfill_pe_pb_factors.py
"""
import argparse, bisect, datetime as dt
from collections import defaultdict
from pymongo import MongoClient, UpdateOne
from bson.decimal128 import Decimal128

PAR = 10.0
PE_MAX = 2000.0
PB_MAX = 50.0
EY_ABS = 5.0

def f(v):
    if v is None: return None
    if isinstance(v, Decimal128): return float(v.to_decimal())
    if isinstance(v, (int, float)): return float(v)
    try: return float(v)
    except Exception: return None

def publish_date(year, season):
    if season == 1: return dt.datetime(year, 5, 15)
    if season == 2: return dt.datetime(year, 8, 14)
    if season == 3: return dt.datetime(year, 11, 14)
    if season == 4: return dt.datetime(year + 1, 3, 31)
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--symbols', default=None)
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--batch', type=int, default=5000)
    a = ap.parse_args()

    db = MongoClient('mongodb://localhost:27017/')['tw_stock_analysis']

    qe = defaultdict(list)
    proj = {'symbol':1,'year':1,'season':1,'income.eps':1,
            'balance.total_equity':1,'balance.equity_parent':1,'balance.capital_stock':1}
    for d in db.quarterly_earnings.find({}, proj):
        y, s = d.get('year'), d.get('season')
        if y is None or s is None: continue
        pub = publish_date(int(y), int(s))
        if pub is None: continue
        inc = d.get('income') or {}; bal = d.get('balance') or {}
        eq = bal.get('equity_parent')
        eq = f(eq) if eq is not None else f(bal.get('total_equity'))
        qe[d['symbol']].append({'y':int(y),'s':int(s),'pub':pub,
                                'eps':f(inc.get('eps')),'eq':eq,'cap':f(bal.get('capital_stock'))})

    targets = set(a.symbols.split(',')) if a.symbols else None
    syms = sorted(qe.keys())
    if targets is not None: syms = [s for s in syms if s in targets]
    if a.limit: syms = syms[:a.limit]

    n_sym = n_docs = n_pe = n_pb = n_ey = 0
    ops = []
    samples = {}
    for sym in syms:
        ql = sorted(qe[sym], key=lambda x: x['pub'])
        pub_dates = [q['pub'] for q in ql]
        cap_sym = None
        for q in ql:
            if q['cap'] and q['cap'] > 0: cap_sym = q['cap']
        shares = cap_sym/PAR if cap_sym else None

        prices = {}
        for p in db.stock_price.find({'symbol':sym}, {'date':1,'close':1}):
            c = f(p.get('close'))
            if c and c > 0: prices[p['date']] = c
        if not prices: continue
        fdates = [fd['date'] for fd in db.stock_factors.find({'symbol':sym}, {'date':1})]
        if not fdates: continue
        n_sym += 1

        for D in fdates:
            close = prices.get(D)
            if close is None: continue
            i = bisect.bisect_right(pub_dates, D) - 1
            if i < 0: continue
            avail = sorted(ql[:i+1], key=lambda x: (x['y'], x['s']))

            pe = pb = ey = None
            last4 = avail[-4:]
            if len(last4) == 4 and all(q['eps'] is not None for q in last4):
                ttm = sum(q['eps'] for q in last4)
                if ttm > 0:
                    v = round(close/ttm, 2)
                    if 0 < v <= PE_MAX: pe = v
                eyv = round(ttm/close, 6)      # earnings yield keeps losses (negative)
                if -EY_ABS <= eyv <= EY_ABS: ey = eyv

            if shares and shares > 0:
                eq = None
                for q in reversed(avail):
                    if q['eq'] and q['eq'] > 0: eq = q['eq']; break
                if eq:
                    bvps = eq/shares
                    if bvps > 0:
                        v = round(close/bvps, 2)
                        if 0 < v <= PB_MAX: pb = v

            setd = {}; unsetd = {}
            if pe is not None: setd['pe_ratio'] = pe; n_pe += 1
            else: unsetd['pe_ratio'] = ''
            if pb is not None: setd['pb_ratio'] = pb; n_pb += 1
            else: unsetd['pb_ratio'] = ''
            if ey is not None: setd['earnings_yield'] = ey; n_ey += 1
            else: unsetd['earnings_yield'] = ''
            upd = {}
            if setd: upd['$set'] = setd
            if unsetd: upd['$unset'] = unsetd
            n_docs += 1
            ops.append(UpdateOne({'symbol':sym,'date':D}, upd))
            if targets and sym in targets:
                cur = samples.get(sym)
                if cur is None or D > cur['date']:
                    samples[sym] = {'date':D,'close':close,'pe':pe,'pb':pb,'ey':ey}
            if len(ops) >= a.batch and not a.dry_run:
                db.stock_factors.bulk_write(ops, ordered=False); ops = []

    if ops and not a.dry_run:
        db.stock_factors.bulk_write(ops, ordered=False)

    for sym in sorted(samples):
        s = samples[sym]
        print(f"  {sym}: date={s['date']:%Y-%m-%d} close={s['close']} pe={s['pe']} pb={s['pb']} ey={s['ey']}")
    print(f"symbols={n_sym} docs_touched={n_docs} pe_set={n_pe} pb_set={n_pb} ey_set={n_ey} dry_run={a.dry_run}")

if __name__ == '__main__':
    main()
