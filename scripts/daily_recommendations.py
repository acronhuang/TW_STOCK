#!/usr/bin/env python3
"""
每日自動推薦腳本（4 大選股法整合版）
======================================
流程：
 1. 因子排行篩選 Top 候選
 2. 蔡森 SenVision 型態突破篩選
 3. 謝富旭深度價值存股篩選
 4. 北大法則風控 + 市場週期
 5. 交叉比對 → 多策略共同推薦
 6. 發 LINE 通知（含各策略個別結果 + 整合推薦）

由 com.twstock.daily_recommendations.plist 在每日 17:30 執行
"""
from __future__ import annotations
import sys
import os
import json
import csv
import warnings
from pathlib import Path
from datetime import datetime

warnings.filterwarnings('ignore')
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / '.env')

from src.analysis.stock_ranker import StockRanker
from src.analysis.risk_manager import RiskAnalyzer
from src.analysis.valuation_models import ValuationAnalyzer
from src.analysis.financial_health import FinancialHealthAnalyzer


def scan_factor_ranking(pool_size=60):
    """策略一：因子排行"""
    sr, ra, va, fh = StockRanker(), RiskAnalyzer(), ValuationAnalyzer(), FinancialHealthAnalyzer()
    top = sr.rank(limit=pool_size)
    results = []
    for s in top:
        sym = s['symbol']
        risk = ra.analyze(sym)
        if risk.get('error'): continue
        val = va.analyze(sym)
        if val.get('error'): continue
        eps = va._get_trailing_eps(sym)
        health = fh.analyze_stock(sym)
        if 'error' in health: continue
        real_pe = s['price'] / eps if eps and eps > 0 else None
        upside = val['composite'].get('upside_pct', 0) or 0
        if (s['total_score'] >= 70 and
            risk['risk_level']['level'] in ('低風險', '中風險') and
            upside > 0 and health['total_score'] >= 60 and
            real_pe and 3 < real_pe < 25):
            results.append({
                'sym': sym, 'name': s['name'], 'price': s['price'],
                'pe': round(real_pe, 1), 'upside': round(upside, 1),
                'sharpe': round(risk['ratios']['sharpe'], 3),
                'dy': round(s['metrics'].get('dividend_yield') or 0, 1),
                'fs_grade': health['grade'][:6],
                'source': '因子',
            })
    return sorted(results, key=lambda x: (x['sharpe'] <= 0, -x['upside']))


def scan_senvision():
    """策略二：蔡森 SenVision 型態突破"""
    results_dir = ROOT / 'results'
    csvs = sorted([f for f in os.listdir(results_dir) if f.startswith('scan_auto_') and f.endswith('.csv')], reverse=True)
    if not csvs:
        return []

    bullish = {'W-Bottom', 'HS-Bottom', 'Triple-Bottom', 'Triangle-Up', 'Flag-Rising'}
    breakouts = {}
    with open(results_dir / csvs[0], encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get('狀態') == '剛突破' and row.get('形態') in bullish:
                sym = row.get('股票代碼', '').strip()
                score = float(row.get('評分', '0') or '0')
                if sym not in breakouts or score > breakouts[sym]['score']:
                    breakouts[sym] = {
                        'pattern': row['形態'], 'timeframe': row.get('時框', ''),
                        'score': score, 'ma': row.get('均線排列', ''),
                        'vp_state': row.get('量價狀態', ''),
                    }

    # 基本面交叉驗證
    fh = FinancialHealthAnalyzer()
    ra = RiskAnalyzer()
    results = []
    for sym, info in breakouts.items():
        health = fh.analyze_stock(sym)
        if 'error' in health or health['total_score'] < 60: continue
        risk = ra.analyze(sym)
        if risk.get('error') or risk['risk_level']['level'] == '極高風險': continue

        from pymongo import MongoClient
        db = MongoClient(os.getenv('MONGODB_URI'))['tw_stock_analysis']
        from bson import Decimal128
        p = db.stock_price.find_one({'symbol': sym}, sort=[('date', -1)])
        price = float(p['close'].to_decimal()) if p and isinstance(p['close'], Decimal128) else (float(p['close']) if p else 0)
        name = p.get('name', '') if p else ''

        results.append({
            'sym': sym, 'name': name, 'price': price,
            'pattern': info['pattern'], 'tf': info['timeframe'],
            'pat_score': info['score'], 'vp_state': info.get('vp_state', ''),
            'sharpe': round(risk['ratios']['sharpe'], 3),
            'source': '蔡森',
        })
    return sorted(results, key=lambda x: -x['pat_score'])[:15]


def scan_hsieh():
    """策略三：謝富旭存股法（全市場演算法篩選，取代手選清單）"""
    from pymongo import MongoClient
    from src.strategy.hsieh_value import HsiehValueScreen
    sc = HsiehValueScreen(MongoClient('localhost', 27017)['tw_stock_analysis'])
    return [{
        'sym': r['symbol'], 'name': r['name'], 'price': r['price'],
        'dy': r['dividend_yield'], 'debt_ratio': r['debt_ratio'],
        'current_ratio': r['current_ratio'], 'retained_x': r['retained_x'],
        'payout_years': r['payout_years'], 'source': '謝富旭',
    } for r in sc.screen(top=15)]


def scan_pku():
    """策略四：北大法則（市場週期 + 風控）"""
    from src.strategy.trading_rules import TradingRules
    tr = TradingRules()
    return {
        'cycle': tr.market_cycle(),
        'risk': tr.market_risk_level() if hasattr(tr, 'market_risk_level') else None,
    }


def cross_reference(factor_list, senvision_list, hsieh_list):
    """交叉比對：找出多策略共同推薦"""
    all_syms = {}

    for r in factor_list:
        sym = r['sym']
        if sym not in all_syms:
            all_syms[sym] = {'name': r['name'], 'price': r['price'], 'sources': [], 'details': {}}
        all_syms[sym]['sources'].append('因子')
        all_syms[sym]['details']['factor'] = r

    for r in senvision_list:
        sym = r['sym']
        if sym not in all_syms:
            all_syms[sym] = {'name': r['name'], 'price': r['price'], 'sources': [], 'details': {}}
        all_syms[sym]['sources'].append('蔡森')
        all_syms[sym]['details']['senvision'] = r

    for r in hsieh_list:
        sym = r['sym']
        if sym not in all_syms:
            all_syms[sym] = {'name': r['name'], 'price': r['price'], 'sources': [], 'details': {}}
        all_syms[sym]['sources'].append('謝富旭')
        all_syms[sym]['details']['hsieh'] = r

    # 依命中策略數排序
    ranked = sorted(all_syms.items(), key=lambda x: (-len(x[1]['sources']), x[0]))
    return ranked


def format_line_message(factor_list, senvision_list, hsieh_list, pku, cross):
    """格式化 LINE 訊息"""
    d = datetime.now().strftime('%m/%d %H:%M')
    lines = [f"🏛️ 每日選股推薦 ({d})\n"]

    # 北大法則
    cycle = pku.get('cycle', {})
    lines.append(f"🌡️ {cycle.get('description', '?')}")
    lines.append(f"   倉位: {cycle.get('suggested_position', '?')}\n")

    # 策略一：因子
    lines.append("━━━ 📊 因子排行 ━━━")
    for r in factor_list[:5]:
        star = '⭐' if r['sharpe'] > 0 else '  '
        lines.append(f"{star}{r['sym']} {r['name']} {r['price']} PE{r['pe']} +{r['upside']}% 殖{r['dy']}%")
    if not factor_list:
        lines.append("  無符合標的")

    # 策略二：蔡森
    lines.append("\n━━━ 📈 蔡森型態 ━━━")
    for r in senvision_list[:5]:
        vp = f" 📊{r['vp_state']}" if r.get('vp_state') else ''
        lines.append(f"{r['sym']} {r['name']} {r['pattern']}({r['tf']}) Sharpe{r['sharpe']:+.2f}{vp}")
    if not senvision_list:
        lines.append("  無突破信號")

    # 策略三：謝富旭存股法篩選（全市場演算法，取代手選清單）
    lines.append("\n━━━ 📕 謝富旭存股法（高殖利率優質股）━━━")
    for r in hsieh_list[:5]:
        lines.append(f"🔴 {r['sym']} {r['name']} {r['price']:g} 殖{r['dy']:.1f}% "
                     f"負債{r['debt_ratio']:.0f}% 連配{r['payout_years']}年")
    if not hsieh_list:
        lines.append("  目前無符合存股法標的")

    # 交叉推薦
    multi = [(sym, info) for sym, info in cross if len(info['sources']) >= 2]
    if multi:
        lines.append(f"\n━━━ 🏆 多策略共同推薦 ━━━")
        for sym, info in multi[:5]:
            sources = '+'.join(info['sources'])
            lines.append(f"🏆 {sym} {info['name']} {info['price']} [{sources}]")

    # 整合建議（即使無交叉也給結論）
    lines.append(f"\n━━━ 💡 整合建議 ━━━")
    if multi:
        lines.append(f"✅ {len(multi)} 支多策略確認，優先佈局")
    else:
        lines.append("各策略選股分散（互補不衝突）")
    # 波段推薦
    if senvision_list:
        top_sv = senvision_list[0]
        lines.append(f"📈 波段: {top_sv['sym']} {top_sv['name']}（{top_sv['pattern']}突破）")
    # 存股推薦（存股法篩選首檔，依殖利率）
    if hsieh_list:
        top_hs = hsieh_list[0]
        lines.append(f"📕 存股: {top_hs['sym']} {top_hs['name']}（殖{top_hs['dy']:.1f}% 連配{top_hs['payout_years']}年 存股法）")
    # 因子推薦
    if factor_list:
        top_f = factor_list[0]
        lines.append(f"📊 綜合: {top_f['sym']} {top_f['name']}（PE{top_f['pe']} Sharpe{top_f['sharpe']:+.2f}）")

    return '\n'.join(lines)


def save_report(data):
    out_dir = ROOT / 'results' / 'daily_picks'
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    path = out_dir / f"picks_{ts}.json"
    with open(path, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    return str(path)


def main():
    no_line = '--no-line' in sys.argv      # 測試用：不發 LINE
    print(f"📊 每日推薦掃描（4 大選股法）{datetime.now()}")

    # 四大策略各自跑
    print("  [1/5] 因子排行...")
    factor_list = scan_factor_ranking()
    print(f"        通過: {len(factor_list)} 支")

    print("  [2/5] 蔡森 SenVision...")
    senvision_list = scan_senvision()
    print(f"        突破: {len(senvision_list)} 支")

    print("  [3/4] 北大法則...")
    pku = scan_pku()
    print(f"        週期: {pku.get('cycle', {}).get('cycle', '?')}")

    print("  [4/4] 謝富旭老師清單主動分析...")
    from pymongo import MongoClient
    from src.strategy.hsieh_value import HsiehValueScreen
    from src.strategy.agan import AganMoatScreen
    screen = HsiehValueScreen(MongoClient('localhost', 27017)['tw_stock_analysis'])
    hsieh_list = scan_hsieh()                  # 存股法篩選(全市場演算法)
    hsieh_watchlist_msg = screen.line_message()  # 主動分析 LINE = 存股法清單
    growth_msg = screen.growth_line_message()  # 存股成長精選 = 存股法 ∩ EPS年增≥10% ∩ 月/季營收
    from src.strategy.quality_growth import QualityGrowthScreen
    quality_msg = QualityGrowthScreen(MongoClient('localhost', 27017)['tw_stock_analysis']).line_message()
    print(f"        存股法通過: {len(hsieh_list)} 支(前15)；成長精選: {len(screen.growth_picks())} 支")

    cross = cross_reference(factor_list, senvision_list, hsieh_list)
    multi_count = sum(1 for _, info in cross if len(info['sources']) >= 2)
    print(f"\n  🏆 多策略共同推薦: {multi_count} 支")

    # 存檔
    report = {
        'date': datetime.now().isoformat(),
        'factor': factor_list,
        'senvision': senvision_list,
        'hsieh': hsieh_list,
        'pku': pku,
        'cross_reference': [(sym, info) for sym, info in cross if len(info['sources']) >= 2],
    }
    path = save_report(report)
    print(f"  已存檔: {path}")

    # 發 LINE（兩則：策略整合 + 謝富旭清單）
    msg = format_line_message(factor_list, senvision_list, hsieh_list, pku, cross)
    agan_msg = AganMoatScreen(MongoClient('localhost', 27017)['tw_stock_analysis']).line_message()
    if no_line:
        print("  [--no-line] 略過發送。訊息預覽：\n" + "─" * 40)
        print("\n".join([msg, "─" * 40, hsieh_watchlist_msg, "─" * 40,
                         growth_msg, "─" * 40, quality_msg, "─" * 40, agan_msg]))
        return
    try:
        from src.alerts.line_notifier import LineNotifier
        ln = LineNotifier()
        ln.send(msg)
        ln.send(hsieh_watchlist_msg)
        ln.send(growth_msg)
        ln.send(quality_msg)
        ln.send(agan_msg)
        print("  ✅ LINE 已發送（5 則）")
    except Exception as e:
        print(f"  ⚠️ LINE 失敗: {e}")


if __name__ == '__main__':
    main()
