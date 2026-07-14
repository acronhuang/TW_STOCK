#!/usr/bin/env python3
"""
合議 A/B 命中率報告 —— 盲投 vs 討論+主持人，對照實際後續報酬
============================================================
資料由 consensus.discuss() 每檔自動並存(blind_final=round0盲投、final=討論+主持人)，
零額外呼叫。累積數週後跑此報告，即可用「後續 N 交易日報酬」回答「討論有沒有比盲投準」。

判準：買進→後續漲(>+1%)算對；賣出→跌(<-1%)算對；持有→小幅(|ret|≤2%)算對。
關鍵看「兩者定案不同」的那組——一致的股票無從比較。

用法：
    consensus_ab_report.py            # 後續 5 交易日報酬為判準
    consensus_ab_report.py --days 10
"""
import argparse
from bson import Decimal128
from pymongo import MongoClient


def _tof(v):
    if isinstance(v, Decimal128):
        return float(v.to_decimal())
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fwd_close(db, sym, dt, days):
    """analysis 日之後第 days 個交易日的收盤（不足則 None）。"""
    dates = sorted(db.stock_price.distinct('date', {'symbol': sym, 'date': {'$gt': dt}}))
    if len(dates) < days:
        return None
    d = db.stock_price.find_one({'symbol': sym, 'date': dates[days - 1]}, {'close': 1})
    return _tof(d['close']) if d else None


def _correct(verdict, ret_pct):
    if verdict == '買進':
        return ret_pct > 1.0
    if verdict == '賣出':
        return ret_pct < -1.0
    if verdict == '持有':
        return abs(ret_pct) <= 2.0
    return None


def main():
    ap = argparse.ArgumentParser(description='合議 A/B 命中率報告')
    ap.add_argument('--days', type=int, default=5, help='後續幾個交易日報酬為判準')
    args = ap.parse_args()
    db = MongoClient('localhost', 27017)['tw_stock_analysis']

    docs = list(db.team_analysis.find(
        {'consensus.blind_final': {'$exists': True}, 'consensus.final': {'$exists': True}}))
    if not docs:
        print("尚無雙定案記錄（需 discuss() 跑過的股票）。等 daily/週批跑幾天後再來。")
        return
    agree = sum(1 for d in docs if d['consensus']['blind_final'] == d['consensus']['final'])
    diff = [d for d in docs if d['consensus']['blind_final'] != d['consensus']['final']]
    print(f"雙定案記錄：{len(docs)} 檔　一致 {agree} / 不同 {len(diff)}"
          f"（討論改變定案 {len(diff)} 檔 = {len(diff)/len(docs)*100:.0f}%）")

    b_hit = b_n = f_hit = f_n = 0
    d_bhit = d_fhit = d_n = 0
    for d in docs:
        c = d['consensus']
        p0 = _tof(d.get('price_at_analysis'))
        pN = _fwd_close(db, d['symbol'], d['date'], args.days)
        if not p0 or not pN or p0 <= 0:
            continue
        ret = (pN - p0) / p0 * 100
        cb, cf = _correct(c['blind_final'], ret), _correct(c['final'], ret)
        if cb is not None:
            b_n += 1; b_hit += int(cb)
        if cf is not None:
            f_n += 1; f_hit += int(cf)
        if c['blind_final'] != c['final'] and cb is not None and cf is not None:
            d_n += 1; d_bhit += int(cb); d_fhit += int(cf)

    print(f"\n後續 {args.days} 交易日報酬評判（可評：盲 {b_n} / 討 {f_n} 檔）")
    if b_n:
        print(f"  盲投 命中率 {b_hit/b_n*100:.0f}%  ({b_hit}/{b_n})")
    if f_n:
        print(f"  討論 命中率 {f_hit/f_n*100:.0f}%  ({f_hit}/{f_n})")
    if d_n:
        print(f"\n★ 關鍵對照（兩者定案不同的 {d_n} 檔）：")
        print(f"    盲投命中 {d_bhit/d_n*100:.0f}%  vs  討論命中 {d_fhit/d_n*100:.0f}%")
        verdict = ("討論較準" if d_fhit > d_bhit else "盲投較準" if d_bhit > d_fhit else "打平")
        print(f"    → {verdict}（樣本 {d_n} 檔；越多越可信）")
    else:
        print("\n（定案不同的股票尚無足夠後續報酬，再等幾個交易日）")


if __name__ == '__main__':
    main()
