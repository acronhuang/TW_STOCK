#!/usr/bin/env python3
"""
台股分析 REST API — 供 OpenClaw / 外部系統查詢
=============================================
啟動: python3 src/api/server.py
URL:  http://localhost:8888

供 OpenClaw Ollama agents 透過 HTTP 取得即時分析數據。
"""

import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / '.env')

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from bson import Decimal128

app = FastAPI(title="台股智能分析 API", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

client = MongoClient(os.getenv('MONGODB_URI', 'mongodb://localhost:27017'))
db = client['tw_stock_analysis']


def tof(v):
    if isinstance(v, Decimal128): return float(v.to_decimal())
    try: return float(v)
    except: return None


# ──────────────────────────────────────────────
#  股價
# ──────────────────────────────────────────────
@app.get("/api/price/{symbol}")
def get_price(symbol: str, days: int = 20):
    """取得個股近 N 日股價"""
    prices = list(db.stock_price.find(
        {'symbol': symbol}, {'_id':0, 'date':1, 'open':1, 'high':1, 'low':1, 'close':1, 'volume':1}
    ).sort('date', -1).limit(days))
    return [{
        'date': str(p['date'])[:10],
        'open': tof(p.get('open')),
        'high': tof(p.get('high')),
        'low': tof(p.get('low')),
        'close': tof(p.get('close')),
        'volume': tof(p.get('volume')),
    } for p in reversed(prices)]


# ──────────────────────────────────────────────
#  因子
# ──────────────────────────────────────────────
@app.get("/api/factors/{symbol}")
def get_factors(symbol: str):
    """取得個股最新因子（PE/PB/殖利率/ROE/RSI 等）。
    注意：stock_factors 多來源(TWSE寫pe/pb/殖利率；factor_calc寫roe/rsi且最新筆常無pe)，
    故取『近30筆每欄首個非null』而非 naive 最新筆，否則 pe/dy/roe 會是 None。"""
    recs = list(db.stock_factors.find({'symbol': symbol}, {'_id': 0}).sort('date', -1).limit(30))
    if not recs:
        return {"error": "not found"}
    merged = {}
    for r in recs:                       # 新→舊，每欄取首個非 null
        for k, v in r.items():
            if v is not None and merged.get(k) is None:
                merged[k] = v
    merged['date'] = recs[0].get('date')  # date 用最新
    return {k: tof(v) if isinstance(v, Decimal128) else v for k, v in merged.items()}


# ──────────────────────────────────────────────
#  估值
# ──────────────────────────────────────────────
@app.get("/api/valuation/{symbol}")
def get_valuation(symbol: str):
    """DCF + DDM + PE Band 估值分析"""
    from src.analysis.valuation_models import ValuationAnalyzer
    va = ValuationAnalyzer()
    return va.analyze(symbol)


# ──────────────────────────────────────────────
#  風險
# ──────────────────────────────────────────────
@app.get("/api/risk/{symbol}")
def get_risk(symbol: str):
    """個股風險分析（VaR/Sharpe/MDD）"""
    from src.analysis.risk_manager import RiskAnalyzer
    ra = RiskAnalyzer()
    return ra.analyze(symbol)


@app.get("/api/risk/portfolio")
def get_portfolio_risk(symbols: str = Query(..., description="逗號分隔，如 2330,2317,0056"),
                       weights: Optional[str] = None):
    """投組風險分析"""
    from src.analysis.risk_manager import RiskAnalyzer
    ra = RiskAnalyzer()
    sym_list = [s.strip() for s in symbols.split(',')]
    w_list = [float(w) for w in weights.split(',')] if weights else None
    return ra.portfolio_risk(sym_list, w_list)


# ──────────────────────────────────────────────
#  同業比較
# ──────────────────────────────────────────────
@app.get("/api/peer/{symbol}")
def get_peer(symbol: str):
    """同業比較分析"""
    from src.analysis.peer_comparison import PeerComparison
    pc = PeerComparison()
    return pc.analyze(symbol)


@app.get("/api/industry/{industry}")
def get_industry_ranking(industry: str, limit: int = 20):
    """產業排名"""
    from src.analysis.peer_comparison import PeerComparison
    pc = PeerComparison()
    return pc.industry_ranking(industry, limit=limit)


# ──────────────────────────────────────────────
#  綜合選股
# ──────────────────────────────────────────────
@app.get("/api/ranking")
def get_ranking(limit: int = 20):
    """綜合選股排行"""
    from src.analysis.stock_ranker import StockRanker
    sr = StockRanker()
    return sr.rank(limit=limit)


@app.get("/api/score/{symbol}")
def get_score(symbol: str):
    """單股綜合評分"""
    from src.analysis.stock_ranker import StockRanker
    sr = StockRanker()
    return sr.score_stock(symbol)


# ──────────────────────────────────────────────
#  總經
# ──────────────────────────────────────────────
@app.get("/api/macro")
def get_macro():
    """總經環境與市場訊號"""
    from src.analysis.macro_indicators import MacroAnalyzer
    ma = MacroAnalyzer()
    return {"overview": ma.overview(), "signal": ma.market_signal()}


# ──────────────────────────────────────────────
#  情緒
# ──────────────────────────────────────────────
@app.get("/api/sentiment/{symbol}")
def get_sentiment(symbol: str):
    """情緒分析（新聞/PTT/內部人）"""
    from src.sentiment.analyzer import SentimentAnalyzer
    sa = SentimentAnalyzer()
    return sa.analyze(symbol)


# ──────────────────────────────────────────────
#  ML 預測
# ──────────────────────────────────────────────
@app.get("/api/predict/{symbol}")
def get_prediction(symbol: str):
    """XGBoost 5 日方向預測"""
    from src.ml.predictor import StockPredictor
    sp = StockPredictor()
    sp.train(symbol)
    return sp.predict(symbol)


# ──────────────────────────────────────────────
#  異常偵測
# ──────────────────────────────────────────────
@app.get("/api/anomaly/{symbol}")
def get_anomaly(symbol: str, days: int = 30):
    """異常偵測"""
    from src.ml.anomaly_detector import AnomalyDetector
    ad = AnomalyDetector()
    return ad.detect(symbol, lookback=days)


# ──────────────────────────────────────────────
#  法人籌碼
# ──────────────────────────────────────────────
@app.get("/api/institutional/{symbol}")
def get_institutional(symbol: str, days: int = 10):
    """法人買賣超"""
    flows = list(db.institutional_flow.find(
        {'stock_id': symbol},
        {'_id':0, 'date':1, 'foreign_net':1, 'trust_net':1, 'dealer_net':1, 'total_net':1}
    ).sort('date', -1).limit(days))
    result = []
    for f in reversed(flows):
        result.append({
            'date': str(f['date'])[:10],
            'foreign_net': tof(f.get('foreign_net')),   # 外資
            'trust_net': tof(f.get('trust_net')),        # 投信
            'dealer_net': tof(f.get('dealer_net')),      # 自營商
            'total_net': tof(f.get('total_net')),
        })
    return result


# ──────────────────────────────────────────────
#  月營收
# ──────────────────────────────────────────────
@app.get("/api/revenue/{symbol}")
def get_revenue(symbol: str, months: int = 6):
    """月營收"""
    revs = list(db.monthly_revenue.find(
        {'symbol': symbol}, {'_id':0, 'year_month':1, 'revenue':1, 'yoy_growth':1, 'mom_growth':1}
    ).sort('year_month', -1).limit(months))
    return list(reversed(revs))


# ──────────────────────────────────────────────
#  股利
# ──────────────────────────────────────────────
@app.get("/api/dividend/{symbol}")
def get_dividend(symbol: str, years: int = 5):
    """股利明細"""
    divs = list(db.dividend_detail.find(
        {'stock_id': symbol}, {'_id':0}
    ).sort('date', -1).limit(years * 3))
    for d in divs:
        for k, v in d.items():
            if isinstance(v, Decimal128):
                d[k] = float(v.to_decimal())
    return list(reversed(divs))


# ──────────────────────────────────────────────
#  交易建議
# ──────────────────────────────────────────────
@app.get("/api/pku")
def pku_rules(symbol: str = None, cost: float = None):
    """北大四大法則（市場週期 + 止損 + 買入三問 + 主力階段）"""
    from src.strategy.trading_rules import TradingRules
    tr = TradingRules()
    result = {'market_cycle': tr.market_cycle()}
    if symbol:
        if cost:
            result['stop_loss'] = tr.check_stop_loss(symbol, cost)
        result['buy_three_questions'] = tr.buy_three_questions(symbol)
        result['institution_phase'] = tr.detect_institution_phase(symbol)
    return result


@app.get("/api/hsieh/research/{symbol}")
def hsieh_research(symbol: str):
    """謝富旭研究分析法（財報驚喜/EPS推演/成長性/填息/配股效應）"""
    from src.strategy.hsieh_analysis import HsiehAnalysis
    return HsiehAnalysis().full_research(symbol)


@app.get("/api/hsieh")
def hsieh_scan(limit: int = 20):
    """謝富旭存股選股法"""
    from src.strategy.hsieh_dividend import HsiehDividendStrategy
    return HsiehDividendStrategy().scan(limit=limit)


@app.get("/api/advisor")
def get_advisor(capital: float = 5000000):
    """策略交易建議"""
    from src.strategy.live_advisor import LiveAdvisor
    la = LiveAdvisor(capital=capital)
    return la.generate_suggestions()


# ──────────────────────────────────────────────
#  財報分析
# ──────────────────────────────────────────────
@app.get("/api/financial/{symbol}")
def get_financial(symbol: str):
    """個股完整財報健康分析（6 維評分 + 杜邦 + 警示）"""
    from src.analysis.financial_health import FinancialHealthAnalyzer
    return FinancialHealthAnalyzer().analyze_stock(symbol)


# ──────────────────────────────────────────────
#  全市場掃描
# ──────────────────────────────────────────────
@app.get("/api/scan")
def scan_market(limit: int = 20):
    """全市場綜合分析：排行 + 風險篩選 + 最終推薦"""
    from src.analysis.stock_ranker import StockRanker
    from src.analysis.risk_manager import RiskAnalyzer
    sr = StockRanker()
    ra = RiskAnalyzer()

    ranking = sr.rank(limit=limit * 2)
    results = []
    for s in ranking:
        risk = ra.analyze(s['symbol'])
        if risk.get('error'):
            continue
        rl = risk['risk_level']['level']
        results.append({
            'symbol': s['symbol'],
            'name': s['name'],
            'price': s['price'],
            'score': s['total_score'],
            'grade': s['grade'],
            'risk_level': rl,
            'sharpe': risk['ratios']['sharpe'],
            'max_drawdown': risk['drawdown']['max_drawdown'],
            'annual_return': risk['returns']['annual_return'],
            'annual_volatility': risk['returns']['annual_volatility'],
            'pe': s['metrics'].get('pe_ratio'),
            'dividend_yield': s['metrics'].get('dividend_yield'),
            'scores': s['scores'],
        })
    results.sort(key=lambda x: x['score'], reverse=True)
    return {
        'total_scanned': len(ranking),
        'total_with_risk': len(results),
        'results': results[:limit],
    }


@app.get("/api/stocks")
def list_stocks(limit: int = 50):
    """列出所有有數據的股票代號和名稱"""
    symbols = db.stock_factors.distinct('symbol')
    stocks = []
    for sym in sorted(symbols):
        name_rec = db.stock_price.find_one({'symbol': sym}, {'name': 1})
        name = name_rec.get('name', '') if name_rec else ''
        stocks.append({'symbol': sym, 'name': name})
    return {'total': len(stocks), 'stocks': stocks[:limit]}


# ──────────────────────────────────────────────
#  團隊分析（7 角色 + .27 合議）
# ──────────────────────────────────────────────
def _clean(doc):
    """移除 _id，datetime → 字串。"""
    if not doc:
        return doc
    doc.pop('_id', None)
    for k in ('date', 'created_at', 'updated_at'):
        if k in doc and doc[k] is not None:
            doc[k] = str(doc[k])[:19]
    v = doc.get('verify')
    if isinstance(v, dict) and v.get('checked_at') is not None:
        v['checked_at'] = str(v['checked_at'])[:19]
    return doc


@app.get("/api/team/{symbol}")
def team_symbol(symbol: str, date: Optional[str] = None):
    """個股團隊分析：6 角色報告 + 佐證 + 顧問整合 + .27 合議定案 + 復驗狀態。
    date=YYYYMMDD 指定日期；預設回最新一日。"""
    q = {'symbol': symbol}
    if date:
        q['date'] = datetime.strptime(date, '%Y%m%d')
    doc = db.team_analysis.find_one(q, sort=[('date', -1)])
    if not doc:
        return {'error': f'查無 {symbol} 的團隊分析', 'symbol': symbol}
    return _clean(doc)


@app.get("/api/team")
def team_verdicts(date: Optional[str] = None, verdict: Optional[str] = None,
                  status: Optional[str] = None, limit: int = 3000):
    """全市場定案彙總（供 dashboard 表格）。可依 date / verdict / verify 狀態篩選。
    預設回最新一個有資料的日期。"""
    if date:
        d = datetime.strptime(date, '%Y%m%d')
    else:
        latest = db.team_analysis.find_one({}, {'date': 1}, sort=[('date', -1)])
        if not latest:
            return {'date': None, 'total': 0, 'rows': []}
        d = latest['date']
    q = {'date': d}
    if verdict:
        q['final_verdict'] = verdict
    if status:
        q['verify.status'] = status
    proj = {'symbol': 1, 'name': 1, 'final_verdict': 1, 'consensus.tally': 1,
            'price_at_analysis': 1, 'verify.status': 1, 'verify.truth_close': 1, '_id': 0}
    rows = list(db.team_analysis.find(q, proj).limit(limit))
    tally = {}
    for r in rows:
        tally[r.get('final_verdict')] = tally.get(r.get('final_verdict'), 0) + 1
    return {'date': str(d)[:10], 'total': len(rows), 'verdict_tally': tally, 'rows': rows}


# ──────────────────────────────────────────────
#  健康檢查
# ──────────────────────────────────────────────
@app.get("/api/health")
def health():
    latest = db.stock_price.find_one({}, {'date':1}, sort=[('date',-1)])
    return {
        "status": "ok",
        "latest_price_date": str(latest['date'])[:10] if latest else None,
        "collections": {name: db[name].estimated_document_count() for name in
                        ['stock_price', 'stock_factors', 'quarterly_earnings', 'dividend_detail', 'monthly_revenue']},
    }


if __name__ == '__main__':
    import uvicorn
    print("🚀 台股分析 API 啟動中...")
    print("📊 http://localhost:8888/docs  (Swagger UI)")
    print("📊 http://localhost:8888/api/health")
    uvicorn.run(app, host="127.0.0.1", port=8888)
