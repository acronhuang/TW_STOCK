#!/usr/bin/env python3
"""
台股資料庫 CLI 查詢工具 — 供 OpenClaw 直接呼叫
==============================================
不經 API，直接連 MongoDB 查詢。

Usage:
    twstock factors 2330
    twstock price 2330 --days 20
    twstock valuation 2330
    twstock risk 2330
    twstock ranking --limit 20
    twstock scan --limit 20
    twstock peer 2330
    twstock macro
    twstock institutional 2330
    twstock revenue 2330
    twstock dividend 2330
    twstock sentiment 2330
    twstock predict 2330
    twstock anomaly 2330
    twstock advisor --capital 5000000
    twstock health
"""

import sys
import os
import json
import warnings
from pathlib import Path

warnings.filterwarnings('ignore')

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / '.env')

from pymongo import MongoClient
from bson import Decimal128
from datetime import datetime, timedelta

client = MongoClient(os.getenv('MONGODB_URI', 'mongodb://localhost:27017'))
db = client['tw_stock_analysis']


def tof(v):
    if isinstance(v, Decimal128): return float(v.to_decimal())
    try: return float(v)
    except: return None


def out(data):
    print(json.dumps(data, ensure_ascii=False, default=str, indent=2))


# ──────────────────────────────────────────────
def cmd_health():
    latest = db.stock_price.find_one({}, {'date':1}, sort=[('date',-1)])
    out({
        "status": "ok",
        "latest_price_date": str(latest['date'])[:10] if latest else None,
        "collections": {name: db[name].estimated_document_count()
                        for name in ['stock_price','stock_factors','quarterly_earnings','dividend_detail','monthly_revenue']},
    })


def cmd_factors(symbol):
    f = db.stock_factors.find_one({'symbol': symbol}, {'_id':0}, sort=[('date',-1)])
    if not f:
        out({"error": "not found"})
        return
    out({k: tof(v) if isinstance(v, Decimal128) else v for k, v in f.items()})


def cmd_price(symbol, days=20):
    prices = list(db.stock_price.find(
        {'symbol': symbol}, {'_id':0,'date':1,'open':1,'high':1,'low':1,'close':1,'volume':1}
    ).sort('date',-1).limit(days))
    out([{'date':str(p['date'])[:10],'open':tof(p.get('open')),'high':tof(p.get('high')),
          'low':tof(p.get('low')),'close':tof(p.get('close')),'volume':tof(p.get('volume'))} for p in reversed(prices)])


def cmd_valuation(symbol):
    from src.analysis.valuation_models import ValuationAnalyzer
    out(ValuationAnalyzer().analyze(symbol))


def cmd_risk(symbol):
    from src.analysis.risk_manager import RiskAnalyzer
    out(RiskAnalyzer().analyze(symbol))


def cmd_ranking(limit=20):
    from src.analysis.stock_ranker import StockRanker
    out(StockRanker().rank(limit=limit))


def cmd_scan(limit=20):
    from src.analysis.stock_ranker import StockRanker
    from src.analysis.risk_manager import RiskAnalyzer
    sr, ra = StockRanker(), RiskAnalyzer()
    ranking = sr.rank(limit=limit*2)
    results = []
    for s in ranking:
        risk = ra.analyze(s['symbol'])
        if risk.get('error'): continue
        results.append({
            'symbol': s['symbol'], 'name': s['name'], 'price': s['price'],
            'score': s['total_score'], 'grade': s['grade'],
            'risk_level': risk['risk_level']['level'],
            'sharpe': risk['ratios']['sharpe'],
            'max_drawdown': risk['drawdown']['max_drawdown'],
            'pe': s['metrics'].get('pe_ratio'),
            'dividend_yield': s['metrics'].get('dividend_yield'),
        })
    results.sort(key=lambda x: x['score'], reverse=True)
    out({"total": len(results), "results": results[:limit]})


def cmd_peer(symbol):
    from src.analysis.peer_comparison import PeerComparison
    out(PeerComparison().analyze(symbol))


def cmd_macro():
    from src.analysis.macro_indicators import MacroAnalyzer
    ma = MacroAnalyzer()
    out({"overview": ma.overview(), "signal": ma.market_signal()})


def cmd_institutional(symbol, days=10):
    flows = list(db.institutional_flow.find(
        {'stock_id': symbol}, {'_id':0,'date':1,'foreign_net':1,'trust_net':1,'total_net':1}
    ).sort('date',-1).limit(days))
    out([{'date':str(f['date'])[:10],'foreign_net':tof(f.get('foreign_net')),
          'trust_net':tof(f.get('trust_net')),'total_net':tof(f.get('total_net'))} for f in reversed(flows)])


def cmd_revenue(symbol, months=6):
    revs = list(db.monthly_revenue.find(
        {'symbol': symbol}, {'_id':0,'year_month':1,'revenue':1,'yoy_growth':1,'mom_growth':1}
    ).sort('year_month',-1).limit(months))
    out(list(reversed(revs)))


def cmd_dividend(symbol):
    divs = list(db.dividend_detail.find({'stock_id': symbol}, {'_id':0}).sort('date',-1).limit(10))
    for d in divs:
        for k, v in d.items():
            if isinstance(v, Decimal128): d[k] = float(v.to_decimal())
    out(list(reversed(divs)))


def cmd_sentiment(symbol):
    from src.sentiment.analyzer import SentimentAnalyzer
    out(SentimentAnalyzer().analyze(symbol))


def cmd_predict(symbol):
    from src.ml.predictor import StockPredictor
    sp = StockPredictor()
    sp.train(symbol)
    out(sp.predict(symbol))


def cmd_anomaly(symbol, days=30):
    from src.ml.anomaly_detector import AnomalyDetector
    out(AnomalyDetector().detect(symbol, lookback=days))


def cmd_advisor(capital=5000000):
    from src.strategy.live_advisor import LiveAdvisor
    out(LiveAdvisor(capital=capital).generate_suggestions())


# ──────────────────────────────────────────────
def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return

    cmd = args[0]
    symbol = args[1] if len(args) > 1 else None

    # 解析 --key value 參數
    params = {}
    i = 1
    while i < len(args):
        if args[i].startswith('--') and i+1 < len(args):
            params[args[i][2:]] = args[i+1]
            i += 2
        else:
            i += 1

    if cmd == 'health':
        cmd_health()
    elif cmd == 'factors' and symbol:
        cmd_factors(symbol)
    elif cmd == 'price' and symbol:
        cmd_price(symbol, int(params.get('days', 20)))
    elif cmd == 'valuation' and symbol:
        cmd_valuation(symbol)
    elif cmd == 'risk' and symbol:
        cmd_risk(symbol)
    elif cmd == 'ranking':
        cmd_ranking(int(params.get('limit', 20)))
    elif cmd == 'scan':
        cmd_scan(int(params.get('limit', 20)))
    elif cmd == 'peer' and symbol:
        cmd_peer(symbol)
    elif cmd == 'macro':
        cmd_macro()
    elif cmd == 'institutional' and symbol:
        cmd_institutional(symbol, int(params.get('days', 10)))
    elif cmd == 'revenue' and symbol:
        cmd_revenue(symbol, int(params.get('months', 6)))
    elif cmd == 'dividend' and symbol:
        cmd_dividend(symbol)
    elif cmd == 'sentiment' and symbol:
        cmd_sentiment(symbol)
    elif cmd == 'predict' and symbol:
        cmd_predict(symbol)
    elif cmd == 'anomaly' and symbol:
        cmd_anomaly(symbol, int(params.get('days', 30)))
    elif cmd == 'advisor':
        cmd_advisor(float(params.get('capital', 5000000)))
    else:
        print(f"未知指令: {cmd}")
        print(__doc__)


if __name__ == '__main__':
    main()
