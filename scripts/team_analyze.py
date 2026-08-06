#!/usr/bin/env python3
"""
7 人團隊一鍵完整分析

流程：
  1. 對每支股票預抓所有 API 數據（總經/財報/估值/風險/同業/籌碼/異常）
  2. 7 個專家依序分析（每個專家拿到對應數據 + 角色提示詞）
  3. investment-advisor 整合 6 份報告 → 最終建議
  4. 輸出彙總報告（Console + JSON 存檔，可選發 LINE）

使用：
    python scripts/team_analyze.py 1108
    python scripts/team_analyze.py 1108 2107 2706
    python scripts/team_analyze.py 1108 --line     # 完成後發 LINE
    python scripts/team_analyze.py 1108 --quick    # 跳過 advisor（省時間）
"""

from __future__ import annotations
import sys
import os
import json
import argparse
import time
from pathlib import Path
from datetime import datetime
import requests

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / '.env')

from src.moe.role_router import ask_role, ROLE_TO_MODEL

API = 'http://localhost:8888'

from pymongo import MongoClient as _MC
_CHIP_DB = None
def _chip_db():
    global _CHIP_DB
    if _CHIP_DB is None:
        _CHIP_DB = _MC('mongodb://localhost:27017/')['tw_stock_analysis']
    return _CHIP_DB

def _num(v):
    return int(v) if isinstance(v, (int, float)) else None

def _chip_context(symbol):
    """融資融券(含上檳)+大戶集保+借券;防呆不拋例外。"""
    try:
        db = _chip_db()
        out = {}
        mg = list(db.margin_purchase_short_sale.find({'code': symbol}).sort('date', -1).limit(2))
        if mg:
            c, pv = mg[0], (mg[1] if len(mg) > 1 else {})
            mb, sb = _num(c.get('margin_balance')), _num(c.get('short_balance'))
            pmb, psb = _num(pv.get('margin_balance')), _num(pv.get('short_balance'))
            out['margin'] = {'date': str(c.get('date'))[:10], 'margin_bal': mb,
                'margin_chg': (mb - pmb) if (mb is not None and pmb is not None) else None,
                'short_bal': sb, 'short_chg': (sb - psb) if (sb is not None and psb is not None) else None,
                'market': c.get('market', 'twse')}
        sh = list(db.shareholding.find({'stock_id': symbol}).sort('date', -1).limit(2))
        if sh:
            c, pv = sh[0], (sh[1] if len(sh) > 1 else {})
            th, pth = c.get('total_holders'), pv.get('total_holders')
            out['big_holder'] = {'date': str(c.get('date'))[:10], 'big400_pct': c.get('big400_pct'),
                'big1000_pct': c.get('big_pct'), 'total_holders': th,
                'holders_chg_pct': (round((th / pth - 1) * 100, 2) if (th and pth) else None)}
        sl = db.securities_lending.find_one({'stock_id': symbol}, sort=[('date', -1)])
        if sl:
            out['sbl'] = {'date': str(sl.get('date'))[:10], 'bal': _num(sl.get('balance')) or _num(sl.get('volume'))}
        try:
            from src.analysis.chip_signals import margin_signal
            mg0 = out.get("margin", {})
            mb, mchg = mg0.get("margin_bal"), mg0.get("margin_chg")
            sb, schg = mg0.get("short_bal"), mg0.get("short_chg")
            ratio = round(sb / mb * 100, 2) if (mb and sb is not None and mb > 0) else None
            def _cf(v):
                return float(v.to_decimal()) if hasattr(v, "to_decimal") else (float(v) if v is not None else None)
            sp = list(db.stock_price.find({"stock_id": symbol, "date": {"$type": "date"}},
                                          {"close": 1}).sort("date", -1).limit(6))
            pc5 = None
            if len(sp) >= 6:
                cn, c5 = _cf(sp[0].get("close")), _cf(sp[5].get("close"))
                if cn and c5:
                    pc5 = round((cn / c5 - 1) * 100, 1)
            lbl, emj, _t = margin_signal(mb, mchg, schg, ratio, pc5)
            if lbl and lbl not in ("-", "—"):
                out["籌碼訊號"] = f"{emj} {lbl}".strip()
                out["近5日股價%"] = pc5
        except Exception:
            pass
        return out or {'note': 'no_chip'}
    except Exception as e:
        return {'error': f'chip_context: {e}'}


def fetch_all_data(symbol: str) -> dict:
    """一次抓齊所有需要的 API 資料"""
    print(f"  📥 抓取 {symbol} 完整資料...")
    data = {}
    endpoints = {
        'factors':       f'/api/factors/{symbol}',
        'financial':     f'/api/financial/{symbol}',
        'valuation':     f'/api/valuation/{symbol}',
        'risk':          f'/api/risk/{symbol}',
        'peer':          f'/api/peer/{symbol}',
        'institutional': f'/api/institutional/{symbol}?days=10',
        'anomaly':       f'/api/anomaly/{symbol}',
        'revenue':       f'/api/revenue/{symbol}?months=6',
        'macro':         f'/api/macro',
    }
    for key, ep in endpoints.items():
        try:
            r = requests.get(API + ep, timeout=30)
            data[key] = r.json() if r.status_code == 200 else {'error': r.status_code}
        except Exception as e:
            data[key] = {'error': str(e)}
    data['chip'] = _chip_context(symbol)
    try:
        from src.analysis.news_evidence import news_evidence as _news_ev
        data['news'] = _news_ev(symbol) or ''
    except Exception:
        data['news'] = ''
    data['news_sentiment'] = _news_sentiment(data.get('news', ''))
    return data


def _position_hint(price, capital: int = 100_000, weight: float = 0.15) -> str:
    """程式端算好部位張數,避免 LLM 自行心算算錯(台股 1 張=1000 股)。"""
    try:
        price = float(price)
    except (TypeError, ValueError):
        price = 0.0
    if price <= 0:
        return "【部位試算】無現價,無法試算張數。"
    cost_per_lot = price * 1000
    max_lots    = int(capital // cost_per_lot)              # 全押上限
    target_lots = int((capital * weight) // cost_per_lot)   # 單檔 15% 權重
    if max_lots < 1:
        return (f"【部位試算(程式,勿改算)】現價約{price:.1f}元,一張需{cost_per_lot:,.0f}元;"
                f"10萬資金買不起 1 張(<1 張)→建議零股或跳過。")
    return (f"【部位試算(程式,勿改算)】現價約{price:.1f}元,一張{cost_per_lot:,.0f}元;"
            f"10萬資金單檔 15% 權重約 {target_lots} 張(全押最多 {max_lots} 張)。")


def _intl_context() -> dict:
    """國際隔夜:費半/美股/VIX 最新收盤與漲跌%(台股開盤前領先訊號)。防呆。"""
    try:
        db = _chip_db()
        out = {}
        for r in db.intl_index.aggregate([
                {"$sort": {"date": -1}},
                {"$group": {"_id": "$name", "close": {"$first": "$close"},
                            "chg_pct": {"$first": "$chg_pct"}, "date": {"$first": "$date"}}}]):
            out[r["_id"]] = {"close": r["close"], "chg%": r["chg_pct"], "date": str(r["date"])[:10]}
        try:
            gl = db.gold_price.find_one(sort=[("date", -1)])
            if gl:
                from datetime import datetime as _dt, timedelta as _td2
                cur_p = float(gl["Price"])
                _bnd = (_dt.strptime(str(gl["date"])[:10], "%Y-%m-%d") - _td2(days=1)).strftime("%Y-%m-%d") + " 23:59:59"
                pg = db.gold_price.find_one({"date": {"$lte": _bnd}}, sort=[("date", -1)])
                _chg = round((cur_p / float(pg["Price"]) - 1) * 100, 2) if pg and pg.get("Price") else None
                out["黃金"] = {"close": round(cur_p, 1), "chg%": _chg, "date": str(gl["date"])[:10]}
        except Exception:
            pass
        return out or {"note": "no_intl"}
    except Exception as e:
        return {"error": f"intl: {e}"}


_POS_WORDS = ["漲停","大漲","飆","買超","調升","上修","創新高","填息","獲利成長","擴產",
              "增產","接單","訂單","看好","利多","突破","強勢","回補","增持","買進","受惠",
              "轉盈","營收創高","題材","樂觀","調高目標價","法人買"]
_NEG_WORDS = ["跌停","大跌","重挫","崩跌","賣超","調降","下修","創新低","貼息","虧損","衰退",
              "減產","看壞","利空","跌破","弱勢","出貨","減持","賣出","示警","踩雷","違約",
              "轉虧","摜壓","悲觀","調降目標價","法人賣","停損"]

def _news_sentiment(text: str) -> dict:
    """規則式新聞情緒:利多/利空詞計分(決定性,不靠模型)。score>0 偏多、<0 偏空。"""
    if not text:
        return {"score": 0, "label": "無新聞", "pos": 0, "neg": 0}
    pos = sum(text.count(w) for w in _POS_WORDS)
    neg = sum(text.count(w) for w in _NEG_WORDS)
    net = pos - neg
    label = "偏多" if net > 0 else ("偏空" if net < 0 else "中性")
    return {"score": net, "label": label, "pos": pos, "neg": neg}


def _fib_context(symbol, lookback_days=180):
    """費波納契反彈計算器:原始價、自動抓 swing(近N日最高→之後最低)、算三檔反彈目標+判定現況。
    弱勢×0.382/中級×0.5/強勢×0.618;破 0.618 上緣=回升(趨勢反轉)。防呆不拋例外。"""
    try:
        from datetime import timedelta
        db = _chip_db()
        def g(v):
            return float(v.to_decimal()) if hasattr(v, "to_decimal") else (float(v) if v is not None else None)
        lat = db.stock_price.find_one({"stock_id": symbol, "date": {"$type": "date"}}, sort=[("date", -1)])
        if not lat:
            return {"note": "no_price"}
        end = lat["date"]; start = end - timedelta(days=lookback_days)
        rows = []
        for r in db.stock_price.find({"stock_id": symbol, "date": {"$gte": start, "$lte": end, "$type": "date"}},
                                     {"date": 1, "close": 1, "high": 1, "low": 1}).sort("date", 1):
            c = g(r.get("close"))
            if c:
                rows.append((c, g(r.get("high")) or c, g(r.get("low")) or c))
        if len(rows) < 20:
            return {"note": "資料不足"}
        hi = max(r[1] for r in rows)
        hi_i = max(i for i, r in enumerate(rows) if r[1] == hi)   # 取最後一次高點後才算回檔
        lo = min(r[2] for r in rows[hi_i:])
        cur = rows[-1][0]
        drop = hi - lo
        if drop <= 0:
            return {"note": "無有效回檔(仍在創高)"}
        t382, t5, t618 = (round(lo + drop * k, 1) for k in (0.382, 0.5, 0.618))
        if cur <= lo * 1.005:
            zone = "仍在低點/反彈未發動"
        elif cur < t382:
            zone = "反彈初起(未達弱勢0.382)"
        elif cur < t5:
            zone = "弱勢反彈區(0.382~0.5)"
        elif cur < t618:
            zone = "中級反彈區(0.5~0.618)"
        elif cur < hi:
            zone = "強勢反彈區(>0.618,逼近回升)"
        else:
            zone = "已破前高=回升(趨勢反轉)"
        return {"高": round(hi, 1), "低": round(lo, 1), "現價": round(cur, 1), "跌幅": round(drop, 1),
                "弱勢0.382": t382, "中級0.5": t5, "強勢0.618": t618, "現況": zone,
                "note": f"原始價;swing=近{lookback_days}日最高→之後最低"}
    except Exception as e:
        return {"error": f"fib:{e}"}


def _sr_context(symbol, window=120):
    """支撐壓力線(SenVision find_support_resistance):現價附近的壓力/支撐位+強度+觸碰次數。
    技術委員據此把費波納契反彈目標對照實際壓力/支撐(有無共振)。防呆。"""
    try:
        import pandas as pd
        from src.senvision.support_resistance import find_support_resistance
        db = _chip_db()
        def g(v):
            return float(v.to_decimal()) if hasattr(v, "to_decimal") else (float(v) if v is not None else None)
        rows = []
        for r in db.stock_price.find({"stock_id": symbol, "date": {"$type": "date"}},
                                     {"close": 1, "high": 1, "low": 1}).sort("date", -1).limit(window):
            c = g(r.get("close"))
            if c:
                rows.append({"high": g(r.get("high")) or c, "low": g(r.get("low")) or c, "close": c})
        if len(rows) < 30:
            return {"note": "資料不足"}
        rows.reverse()
        lv = find_support_resistance(pd.DataFrame(rows))
        res = sorted([l for l in lv if l.type == "resistance"], key=lambda l: l.price)
        sup = sorted([l for l in lv if l.type == "support"], key=lambda l: -l.price)
        fmt = lambda l: {"價": l.price, "強度": l.strength, "觸碰": l.touches}
        return {"壓力線(近到遠)": [fmt(l) for l in res[:3]],
                "支撐線(近到遠)": [fmt(l) for l in sup[:3]]}
    except Exception as e:
        return {"error": f"sr:{e}"}


def _tech_sig(symbol):
    """技術訊號(規則式:蔡森頸線 → 現價 vs 支撐壓力 + fib 反彈位置)。回標籤字串。"""
    try:
        from src.analysis.tech_lines import price_series, fib_rebound, sr_levels, tech_signal, neckline_ctx
        db = _chip_db()
        df = price_series(db, symbol)
        fib = fib_rebound(df)
        lbl, emj, _t = tech_signal(fib, sr_levels(df), pattern=neckline_ctx(symbol))
        return f"{emj} {lbl}".strip() if (lbl and lbl != "—") else ""
    except Exception:
        return ""


def _pattern_line(symbol):
    """蔡森型態頸線(讀 scan_auto CSV,與 dailypicks 同源)。回一行字串或空。"""
    try:
        from src.analysis.tech_lines import neckline_ctx
        p = neckline_ctx(symbol)
        if not p:
            return ""
        d = "多方" if p["dir"] == "bull" else "空方"
        return (f"{p['tf']}{p['pattern']} {p['status']} 頸線={p['neckline']} "
                f"目標={p['target']} 風報比={p['rrr']} 方向={d}")
    except Exception:
        return ""


def _stock_name(symbol):
    """取股名(taiwan_stock_info→stock_price),供 prompt 標示避免代號被誤讀為年份。"""
    try:
        db = _chip_db()
        d = db.taiwan_stock_info.find_one({"stock_id": symbol}, {"stock_name": 1})
        if d and d.get("stock_name"):
            return d["stock_name"]
        d = db.stock_price.find_one({"stock_id": symbol, "name": {"$nin": ["", None]}},
                                    sort=[("date", -1)])
        return d.get("name", "") if d else ""
    except Exception:
        return ""


def _volprice_context(symbol):
    """多時框量價型態(七句口訣+位置),餵技術委員。回精簡字串。"""
    try:
        from datetime import timedelta
        from src.analysis.volprice_pattern import TIMEFRAMES, classify_tf
        db = _chip_db()
        lat = db.stock_price.find_one({"stock_id": symbol, "date": {"$type": "date"}}, sort=[("date", -1)])
        if not lat:
            return ""
        closes, vols = [], []
        for r in db.stock_price.find(
                {"stock_id": symbol, "date": {"$gte": lat["date"] - timedelta(days=760), "$type": "date"}},
                {"close": 1, "adj_close": 1, "volume": 1}).sort("date", 1):
            c = r.get("adj_close") or r.get("close")
            c = float(c.to_decimal()) if hasattr(c, "to_decimal") else (float(c) if c is not None else None)
            v = r.get("volume")
            v = float(v.to_decimal()) if hasattr(v, "to_decimal") else (float(v) if v is not None else None)
            if c and v is not None:
                closes.append(c); vols.append(v)
        parts = []
        for tf in TIMEFRAMES:
            rr = classify_tf(closes, vols, tf)
            if rr:
                parts.append(f"{tf}={rr['label']}(位階{rr['位階%']}%)")
        return " / ".join(parts)
    except Exception:
        return ""


def _fin_deep(symbol):
    """財報深度摘要(逐季三率/現金流品質/負債),餵基本面委員。"""
    try:
        from src.analysis.financial_statements import committee_summary
        return committee_summary(_chip_db(), symbol)
    except Exception:
        return ""


def _s2560_context(symbol):
    """2560戰法訊號(MA25向上+踩線起動+量能情境),餵技術委員。"""
    try:
        from datetime import timedelta
        from src.analysis.strategy_2560 import classify_2560
        db = _chip_db()
        lat = db.stock_price.find_one({"stock_id": symbol, "date": {"$type": "date"}}, sort=[("date", -1)])
        if not lat:
            return ""
        closes, vols = [], []
        for r in db.stock_price.find(
                {"stock_id": symbol, "date": {"$gte": lat["date"] - timedelta(days=160), "$type": "date"}},
                {"close": 1, "adj_close": 1, "volume": 1}).sort("date", 1):
            c = r.get("adj_close") or r.get("close")
            c = float(c.to_decimal()) if hasattr(c, "to_decimal") else (float(c) if c is not None else None)
            v = r.get("volume")
            v = float(v.to_decimal()) if hasattr(v, "to_decimal") else (float(v) if v is not None else None)
            if c and v is not None:
                closes.append(c); vols.append(v)
        res = classify_2560(closes, vols)
        if not res:
            return ""
        return f"{res['label']}(MA25{'向上' if res['ma25_rising'] else '走平'}、離25線{res['dist%']:+.1f}%、量比5/60={res['vol5_60']})"
    except Exception:
        return ""


def _rebound_ctx(symbol):
    """跌深反彈:套牢量壓力 + 反彈潛力(跌深股自救),餵技術委員。"""
    try:
        from src.analysis.tech_lines import price_series, trapped_volume_zones, rebound_potential
        db = _chip_db()
        df = price_series(db, symbol, 200)
        tz = trapped_volume_zones(df)
        rp = rebound_potential(db, symbol)
        parts = []
        if tz:
            parts.append("套牢量壓力區(下跌爆量處=反彈解套賣壓):" + ", ".join(f"{z['price']:.0f}(+{z['dist%']:.0f}%)" for z in tz))
        if rp:
            parts.append(f"跌深反彈潛力={rp['verdict']}({';'.join(rp['reasons'][:3])})")
        return " | ".join(parts)
    except Exception:
        return ""


def build_expert_prompt(role: str, symbol: str, data: dict) -> str:
    """為每個專家準備專屬提示詞 + 數據"""
    if role == 'macro-analyst':
        nm = _stock_name(symbol)
        verdict = (data.get("macro") or {}).get("signal", {}).get("verdict", "")
        _rule = ("規則：(1) 只可引用上方 JSON 實際出現的欄位、其確切名稱與數值(含正負號)，"
                 "嚴禁自創或改名指標(例如 VIX 的 chg% 就是 VIX 當日漲跌幅，不得改稱『券資報酬率』等)；"
                 "(2) 你的多空結論方向須與上方 signal.verdict「" + verdict + "」一致，不得相反。")
        _parts = [
            f"用台股總經背景判斷對個股 {symbol} {nm} 的影響：",
            json.dumps(data['macro'], ensure_ascii=False),
            "國際隔夜(費半/美股/VIX；chg%=該指數當日漲跌幅): " + json.dumps(_intl_context(), ensure_ascii=False),
            "",
            _rule,
            f"用 5 行內回答：大盤是否適合佈局？對 {symbol} {nm} 利或不利？",
        ]
        return chr(10).join(_parts)

    if role == 'fundamental-analyst':
        f = data['financial']
        rev = data.get('revenue') or []
        _parts = [
            f"分析 {symbol} 財報健康狀況：",
            json.dumps({k: v for k, v in f.items()}, ensure_ascii=False),
            "近6月月營收動能(revenue=當月營收千元, yoy_growth=年增%, mom_growth=月增%): " + json.dumps(rev, ensure_ascii=False),
            "財報深度(逐季三率/現金流品質/負債): " + _fin_deep(symbol),
            "",
            "用 5 行內回答：財報健康嗎？三率(毛利/營益/淨利)趨勢向上或向下？獲利含金量(營運現金流/淨利)夠不夠？月營收動能是否加速？關鍵警示？",
        ]
        return chr(10).join(_parts)

    if role == 'value-analyst':
        v = data['valuation']
        return f"判斷 {symbol} 估值：\n{json.dumps(v, ensure_ascii=False)}\n\n用 3 行回答：低估還是高估？合理價多少？"

    if role == 'technical-analyst':
        return f"分析 {symbol} 技術面：\n因子: {json.dumps(data['factors'], ensure_ascii=False)}\n異常: {json.dumps(data['anomaly'], ensure_ascii=False)}" + chr(10) + f"費波納契反彈: {json.dumps(_fib_context(symbol), ensure_ascii=False)}" + chr(10) + f"支撐壓力線: {json.dumps(_sr_context(symbol), ensure_ascii=False)}" + chr(10) + f"技術訊號: {_tech_sig(symbol)}" + chr(10) + f"蔡森型態頸線: {_pattern_line(symbol)}" + chr(10) + f"量價型態(七句口訣·多時框): {_volprice_context(symbol)}" + chr(10) + f"2560戰法(安德烈布殊·踩25線+量能): {_s2560_context(symbol)}" + chr(10) + f"跌深反彈(套牢量壓力/反彈潛力): {_rebound_ctx(symbol)}\n\n用 5 行內回答：趨勢方向?進出場訊號?費波納契反彈目標與支撐壓力線是否共振(共振=更強的關卡)?多時框量價型態是否同向(短長期一致=更強訊號)?"

    if role == 'chip-analyst':
        return f"分析 {symbol} 籌碼：\n近10日法人: {json.dumps(data['institutional'], ensure_ascii=False)}" + chr(10) + f"chip(融券/大戶/借券): {json.dumps(data.get('chip', {}), ensure_ascii=False)}\n\n用 4 行內回答：法人買賣?融資融券增減與大戶集保透露的主力意圖?借券是否偏空?(可直接引用上方chip的『籌碼訊號』標籤,如主力吃貨/斷頭風險/軋空候選)"

    if role == 'risk-manager':
        _price = (data.get('factors') or {}).get('close') or (data.get('valuation') or {}).get('current_price')
        _hint  = _position_hint(_price)
        return (f"評估 {symbol} 風險：\n{json.dumps(data['risk'], ensure_ascii=False)}\n{_hint}\n\n"
                "用 5 行內回答：風險等級？建議部位/張數(務必採用上方【部位試算】的數字,不得自行重算)/停損？")

    if role == 'investment-advisor':
        # 把前 6 個專家的報告當輸入
        return f"""你是投資顧問，整合以下 6 份報告，給 {symbol} 最終建議：

【總經】{data.get('reports', {}).get('macro-analyst', '無')}

【基本面】{data.get('reports', {}).get('fundamental-analyst', '無')}

【估值】{data.get('reports', {}).get('value-analyst', '無')}

【技術】{data.get('reports', {}).get('technical-analyst', '無')}

【籌碼】{data.get('reports', {}).get('chip-analyst', '無')}

【風險】{data.get('reports', {}).get('risk-manager', '無')}

【近期新聞/事件｜情緒{data.get('news_sentiment', {}).get('label', '?')}(利多{data.get('news_sentiment', {}).get('pos', 0)}/利空{data.get('news_sentiment', {}).get('neg', 0)})】{data.get('news') or '無新聞'}

⚠️ 輸出規則（務必遵守）：
第一行只輸出評級標籤，固定格式：`評級：<X>`，X 五選一【強力買進 / 買進 / 觀望 / 減碼 / 賣出】，不得加註其他字。
第二行起才寫理由與具體操作（張數/進場價/停損價/目標價/持有期）。張數務必沿用【風險】報告中「部位試算」的程式數字,嚴禁自行心算(台股 1 張=1000 股)。
評級需呼應蔡森技術型態方向（一致性要求）：
  • 偏空型態(M-Top/HS-Top/Triple-Top/Failed-Breakout)且無強力利多催化 → 不給買進/強力買進。
  • 偏多型態(W-Bottom/HS-Bottom/Triple-Bottom/Failed-Breakdown)且無強烈利空 → 不給賣出/減碼。
  • 若你的評級與型態方向相反(例如型態偏多卻給賣出)，**必須在理由首句明確說明壓過技術面的關鍵因素**
    (如基本面急轉直下、估值極端、籌碼大量出貨)；否則請改回與型態方向一致的評級。"""

    return f"分析 {symbol}"


def analyze_one(symbol: str, quick: bool = False) -> dict:
    """完整分析單一股票"""
    print(f"\n{'═'*70}")
    print(f"  🏛️  7 人團隊分析：{symbol}")
    print(f"{'═'*70}")
    t_start = time.time()

    # Step 1: 抓資料
    data = fetch_all_data(symbol)
    name = data['factors'].get('symbol', symbol)
    price = data['factors'].get('close') or data['valuation'].get('current_price')

    # Step 2: 6 個專家依序分析
    expert_order = [
        'macro-analyst',
        'fundamental-analyst',
        'value-analyst',
        'technical-analyst',
        'chip-analyst',
        'risk-manager',
    ]
    reports = {}
    for role in expert_order:
        print(f"\n  🤖 {role} ({ROLE_TO_MODEL[role]})")
        prompt = build_expert_prompt(role, symbol, data)
        r = ask_role(role, prompt, include_role_prompt=True, timeout=180)
        if 'error' in r:
            print(f"     ❌ {r['error']}")
            reports[role] = f"分析失敗: {r['error']}"
        else:
            text = r['response'].strip()
            # 去掉 <think>...</think>
            if '<think>' in text:
                text = text.split('</think>', 1)[-1].strip()
            reports[role] = text
            preview = text[:120].replace('\n', ' ')
            print(f"     ⏱  {r['elapsed_sec']}s  💬 {preview}...")

    # Step 3: investment-advisor 整合
    if not quick:
        print(f"\n  🎩 investment-advisor ({ROLE_TO_MODEL['investment-advisor']})  整合中...")
        data['reports'] = reports
        prompt = build_expert_prompt('investment-advisor', symbol, data)
        r = ask_role('investment-advisor', prompt, include_role_prompt=True, timeout=300)
        if 'error' in r:
            final = f"整合失敗: {r['error']}"
        else:
            final = r['response'].strip()
            if '<think>' in final:
                final = final.split('</think>', 1)[-1].strip()
            print(f"     ⏱  {r['elapsed_sec']}s")
    else:
        final = '(--quick 模式跳過 advisor)'

    elapsed_total = time.time() - t_start

    return {
        'symbol': symbol,
        'price': price,
        'reports': reports,
        'final_advice': final,
        'total_seconds': round(elapsed_total, 1),
        'analyzed_at': datetime.now().isoformat(),
    }


def print_report(result: dict):
    """漂亮印出分析結果"""
    print(f"\n{'═'*70}")
    print(f"  📊 {result['symbol']}  最終分析報告  (總耗時 {result['total_seconds']}s)")
    print(f"{'═'*70}")

    titles = {
        'macro-analyst':       '🎯 總經分析',
        'fundamental-analyst': '💰 基本面',
        'value-analyst':       '💎 估值',
        'technical-analyst':   '📈 技術面',
        'chip-analyst':        '🏦 籌碼',
        'risk-manager':        '🛡️ 風險',
    }
    for role, title in titles.items():
        report = result['reports'].get(role, '')
        print(f"\n  ── {title} ──")
        print(f"  {report[:500]}")

    print(f"\n{'═'*70}")
    print(f"  🎩 投資顧問最終建議")
    print(f"{'═'*70}")
    print(f"  {result['final_advice']}")
    print(f"{'═'*70}\n")


def save_report(results: list, output_dir: str = None):
    output_dir = output_dir or str(ROOT / 'results' / 'team_analysis')
    os.makedirs(output_dir, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    path = f"{output_dir}/team_{ts}.json"
    with open(path, 'w') as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    print(f"  💾 報告已存至: {path}")
    return path


def send_line(results: list):
    from src.alerts.line_notifier import LineNotifier
    ln = LineNotifier()
    msg = "🏛️ 7人團隊分析報告\n\n"
    for r in results:
        advice = r['final_advice'][:300] if r['final_advice'] else '(無)'
        msg += f"📊 {r['symbol']} ({r['price']})\n{advice}\n\n"
    ln.send(msg[:4500])
    print(f"  ✅ LINE 已發送")


def main():
    parser = argparse.ArgumentParser(description='7 人團隊股票一鍵分析')
    parser.add_argument('symbols', nargs='+', help='股票代號（可多個）')
    parser.add_argument('--quick', action='store_true', help='跳過 advisor 整合（省時間）')
    parser.add_argument('--line', action='store_true', help='完成後發 LINE')
    parser.add_argument('--no-save', action='store_true', help='不存檔')
    args = parser.parse_args()

    results = []
    for sym in args.symbols:
        r = analyze_one(sym, quick=args.quick)
        print_report(r)
        results.append(r)

    if not args.no_save:
        save_report(results)

    if args.line:
        send_line(results)


if __name__ == '__main__':
    main()
