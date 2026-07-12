#!/usr/bin/env python3
"""
資產負債表同步（免費官方 OpenAPI）→ 補 quarterly_earnings.balance + 算 ROE
==========================================================================
缺口：quarterly_earnings 有 income(營收/淨利/利潤率) 但 balance 全空 → 全市場 0% ROE。
本腳本抓官方資產負債表(t187ap07)，灌 權益/資產/負債 進 balance，並用既有 income.net_income 算 ROE。

來源(各行業變體；TWSE中文/TPEX代號英文，財務欄位皆中文，用 fallback 涵蓋「總額」/「總計」)：
  上市 TWSE: openapi.twse.com.tw/v1/opendata/t187ap07_L_{ci,ins,bd,fh,basi,mim}
  上櫃 TPEX: tpex.org.tw/openapi/v1/mopsfin_t187ap07_O_{ci,ins,bd,fh,basi,mim}
單位：API 千元 → 存元(×1000，對齊 income)。ROE=淨利×(4/季)/權益×100(年化)。

用法： python scripts/sync_balance_openapi.py [--dry-run]
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import datetime
from pymongo import MongoClient, UpdateOne
from src.utils.twstock_openapi import fetch_openapi, field, to_float

VARIANTS = ['ci', 'ins', 'bd', 'fh', 'basi', 'mim']
TWSE = 'https://openapi.twse.com.tw/v1/opendata/t187ap07_L_{}'
TPEX = 'https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap07_O_{}'
# 損益表(一般業)算毛利率；金融/保險無毛利概念故僅 ci
INC_TWSE = 'https://openapi.twse.com.tw/v1/opendata/t187ap06_L_ci'
INC_TPEX = 'https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap06_O_ci'


def _yuan(v):
    """財報數值 千元 → 元（對齊 quarterly_earnings.income 單位）。"""
    f = to_float(v)
    return f * 1000.0 if f is not None else None


def fetch_all():
    """回 {(symbol,year,season): balance_dict}。"""
    out = {}
    for tmpl in (TWSE, TPEX):
        for v in VARIANTS:
            for row in fetch_openapi(tmpl.format(v)):
                code = str(field(row, '公司代號', 'SecuritiesCompanyCode') or '').strip()
                roc = str(field(row, '年度', 'Year') or '').strip()
                season = field(row, '季別', 'Season')
                if not (code.isdigit() and roc.isdigit() and season):
                    continue
                year = int(roc) + 1911
                eq = _yuan(field(row, '權益總額', '權益總計'))
                eq_parent = _yuan(field(row, '歸屬於母公司業主之權益合計', '歸屬於母公司業主之權益'))
                out[(code, year, int(season))] = {
                    'total_equity': eq or eq_parent,
                    'equity_parent': eq_parent,
                    'total_assets': _yuan(field(row, '資產總額', '資產總計')),
                    'total_liabilities': _yuan(field(row, '負債總額', '負債總計')),
                    'current_assets': _yuan(field(row, '流動資產')),
                    'current_liabilities': _yuan(field(row, '流動負債')),
                    'retained_earnings': _yuan(field(row, '保留盈餘')),   # 存股法:未分配盈餘倍數
                    'capital_stock': _yuan(field(row, '股本')),
                }
    return out


def fetch_gross():
    """回 {(symbol,year,season): gross_margin%}（毛利率，僅一般業）。"""
    out = {}
    for url in (INC_TWSE, INC_TPEX):
        for row in fetch_openapi(url):
            code = str(field(row, '公司代號', 'SecuritiesCompanyCode') or '').strip()
            roc = str(field(row, '年度', 'Year') or '').strip()
            season = field(row, '季別', 'Season')
            rev = _yuan(field(row, '營業收入'))
            gp = _yuan(field(row, '營業毛利（毛損）淨額', '營業毛利（毛損）'))
            if code.isdigit() and roc.isdigit() and season and rev and gp is not None:
                out[(code, int(roc) + 1911, int(season))] = round(gp / rev * 100, 2)
    return out


def main():
    dry = '--dry-run' in sys.argv
    db = MongoClient('localhost', 27017)['tw_stock_analysis']
    bals = fetch_all()
    gross = fetch_gross()
    print(f"抓到 {len(bals)} 筆資產負債、{len(gross)} 筆毛利率")

    ops, computed = [], 0
    for (sym, year, season), b in bals.items():
        # ROE 用 TTM(近4單季淨利加總/權益)，非單季×4年化(Q1強會爆值,如宜鼎149%失真)
        roe = None
        if b.get('total_equity'):
            qs = list(db.quarterly_earnings.find(
                {'symbol': sym}, {'income.net_income': 1}
            ).sort([('year', -1), ('season', -1)]).limit(4))
            nis = [(q.get('income') or {}).get('net_income') for q in qs]
            nis = [x for x in nis if x is not None]
            if len(nis) == 4:
                roe = round(sum(nis) / b['total_equity'] * 100, 2)   # TTM ROE
                computed += 1
        rec = {**b, 'roe': roe, 'unit_fixed': True, 'source': 'OpenAPI'}
        gm = gross.get((sym, year, season))
        if dry:
            if sym in ('2330', '2881', '6488'):
                print(f"  {sym} {year}Q{season}: 權益={b['total_equity']:.0f} ROE={roe} 毛利率={gm}")
            continue
        setdoc = {'balance': rec}
        if gm is not None:
            setdoc['income.gross_margin'] = gm   # 補回毛利率(financial_health/謝富旭讀)
        ops.append(UpdateOne({'symbol': sym, 'year': year, 'season': season},
                             {'$set': setdoc}, upsert=False))
    if dry:
        print(f"(dry-run) 可算 ROE {computed} 檔")
        return
    res = db.quarterly_earnings.bulk_write(ops, ordered=False)
    print(f"✅ 更新 balance：matched {res.matched_count} modified {res.modified_count}；算出 ROE {computed} 檔")


if __name__ == '__main__':
    main()
