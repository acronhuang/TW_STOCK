"""
交易規則引擎（參考北大炒股教材）
==========================================

四大法則：
  1. 倉位管理 > 選股能力（334 倉位法）
  2. 止損紀律 > 分析預測（5% 無條件止損 / 破 60 日線清倉）
  3. 邏輯驗證 > 消息內幕（買入三問）
  4. 等待 > 操作（80% 收益來自 20% 時間）

市場週期：春播（觀察）→ 夏長（重倉）→ 秋收（減倉）→ 冬藏（空倉）
主力行為：建倉 → 洗盤 → 試盤 → 拉升 → 出貨
"""

from __future__ import annotations
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from pymongo import MongoClient
from bson import Decimal128
import numpy as np


def _tof(v) -> Optional[float]:
    if isinstance(v, Decimal128):
        return float(v.to_decimal())
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class TradingRules:
    """北大四大法則 + 主力行為偵測"""

    def __init__(self,
                 mongo_uri: str = "mongodb://localhost:27017/",
                 db_name: str = "tw_stock_analysis"):
        self.db = MongoClient(mongo_uri)[db_name]

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  法則一：334 倉位法
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def position_334(self, capital: float, cycle: str = 'normal') -> Dict:
        """334 倉位管理：30% 底倉 + 30% 機動 + 40% 現金

        市場週期會調整比例：
          春播（觀察）→ 20/20/60
          夏長（重倉）→ 40/30/30
          秋收（減倉）→ 20/10/70
          冬藏（空倉）→ 0/0/100
        """
        ratios = {
            'spring': (0.20, 0.20, 0.60),  # 春播：觀察待機
            'summer': (0.40, 0.30, 0.30),  # 夏長：重倉介入
            'autumn': (0.20, 0.10, 0.70),  # 秋收：逐步減倉
            'winter': (0.00, 0.00, 1.00),  # 冬藏：空倉休息
            'normal': (0.30, 0.30, 0.40),  # 正常：334 標準
        }
        core, tactical, cash = ratios.get(cycle, ratios['normal'])
        return {
            'cycle': cycle,
            'core_position': round(capital * core),
            'tactical_position': round(capital * tactical),
            'cash_reserve': round(capital * cash),
            'core_pct': core * 100,
            'tactical_pct': tactical * 100,
            'cash_pct': cash * 100,
            'rule': '首次開倉永遠不滿倉，永遠有預備隊',
        }

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  法則二：止損紀律（5% 無條件 + 破 60 日線清倉）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def check_stop_loss(self, symbol: str, cost: float) -> Dict:
        """檢查止損：5% 無條件 + 破 60 日線清倉"""
        prices = list(self.db.stock_price.find(
            {'symbol': symbol}, {'close': 1, 'date': 1}
        ).sort('date', -1).limit(60))

        if not prices:
            return {'symbol': symbol, 'error': '無價格資料'}

        current = _tof(prices[0]['close'])
        pnl_pct = (current - cost) / cost * 100

        # 5% 無條件止損
        stop_5pct = cost * 0.95
        hit_5pct = current < stop_5pct

        # 60 日線（MA60）
        closes = [_tof(p['close']) for p in prices if _tof(p.get('close'))]
        ma60 = np.mean(closes[:60]) if len(closes) >= 60 else None
        below_ma60 = current < ma60 if ma60 else None

        # 趨勢判斷：均線多頭/空頭排列
        ma5 = np.mean(closes[:5]) if len(closes) >= 5 else None
        ma10 = np.mean(closes[:10]) if len(closes) >= 10 else None
        ma20 = np.mean(closes[:20]) if len(closes) >= 20 else None

        if ma5 and ma10 and ma20:
            if ma5 > ma10 > ma20:
                ma_trend = '多頭排列'
            elif ma5 < ma10 < ma20:
                ma_trend = '空頭排列'
            else:
                ma_trend = '糾結'
        else:
            ma_trend = '資料不足'

        signals = []
        if hit_5pct:
            signals.append('🛑 跌破成本 5%，無條件止損')
        if below_ma60:
            signals.append('🛑 跌破 60 日線，清倉出場')
        if ma_trend == '空頭排列':
            signals.append('⚠️ 均線空頭排列，趨勢向下')

        # 判斷行動（分層嚴格度）
        loss_pct = pnl_pct  # 負值代表虧損
        action = '持有'
        if hit_5pct and below_ma60:
            action = '止損出場'       # 虧超過 5% + 跌破 MA60 = 最嚴重
        elif hit_5pct:
            action = '止損出場'       # 虧超過 5% = 無條件止損
        elif below_ma60 and loss_pct < -3:
            action = '減碼觀察'       # 跌破 MA60 + 虧 3% = 要注意
        elif below_ma60 and loss_pct >= 0:
            action = '留意趨勢'       # 跌破 MA60 但獲利中 = 只留意
        elif ma_trend == '空頭排列' and loss_pct < -3:
            action = '減碼觀察'       # 空頭排列 + 虧損
        elif ma_trend == '空頭排列':
            action = '留意趨勢'       # 空頭排列但虧損小

        return {
            'symbol': symbol,
            'current': current,
            'cost': cost,
            'pnl_pct': round(pnl_pct, 2),
            'stop_5pct': round(stop_5pct, 2),
            'hit_5pct': hit_5pct,
            'ma60': round(ma60, 2) if ma60 else None,
            'below_ma60': below_ma60,
            'ma_trend': ma_trend,
            'signals': signals,
            'action': action,
        }

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  法則三：買入三問
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def buy_three_questions(self, symbol: str) -> Dict:
        """買入前三問：為什麼漲？誰在買？還能漲嗎？"""
        # Q1: 為什麼漲？（邏輯）
        factors = self.db.stock_factors.find_one(
            {'symbol': symbol}, sort=[('date', -1)])
        prices = list(self.db.stock_price.find(
            {'symbol': symbol}, {'close': 1, 'volume': 1, 'date': 1}
        ).sort('date', -1).limit(20))

        if not prices or not factors:
            return {'symbol': symbol, 'error': '資料不足'}

        current = _tof(prices[0]['close'])
        prev = _tof(prices[1]['close']) if len(prices) > 1 else current
        daily_change = (current - prev) / prev * 100 if prev else 0

        ret_1m = _tof(factors.get('return_1m')) or 0
        rsi = _tof(factors.get('rsi_14')) or 50

        if ret_1m > 10:
            q1_reason = '月漲幅 > 10%，可能有基本面或題材驅動'
        elif ret_1m > 0:
            q1_reason = '溫和上漲，走勢健康'
        else:
            q1_reason = '近月下跌，需確認是否止跌'
        q1_pass = ret_1m > -5

        # Q2: 誰在買？（資金）
        flows = list(self.db.institutional_flow.find(
            {'stock_id': symbol}, {'foreign_net': 1, 'trust_net': 1}
        ).sort('date', -1).limit(5))
        total_fn = sum(_tof(f.get('foreign_net', 0)) or 0 for f in flows)
        total_tn = sum(_tof(f.get('trust_net', 0)) or 0 for f in flows)

        if total_fn > 0 and total_tn >= 0:
            q2_who = f'外資買超 {total_fn/1000:+.0f}千張（主力進場）'
            q2_pass = True
        elif total_fn > 0:
            q2_who = f'外資買但投信賣（分歧）'
            q2_pass = True
        else:
            q2_who = f'法人賣超（缺乏資金支撐）'
            q2_pass = False

        # Q3: 還能漲嗎？（空間）
        if rsi > 80:
            q3_space = f'RSI {rsi:.0f}（嚴重超買，不宜追）'
            q3_pass = False
        elif rsi > 70:
            q3_space = f'RSI {rsi:.0f}（超買，謹慎）'
            q3_pass = False
        elif rsi < 30:
            q3_space = f'RSI {rsi:.0f}（超賣，有反彈空間）'
            q3_pass = True
        else:
            q3_space = f'RSI {rsi:.0f}（中性，有空間）'
            q3_pass = True

        all_pass = q1_pass and q2_pass and q3_pass
        return {
            'symbol': symbol,
            'current': current,
            'q1_why': {'answer': q1_reason, 'pass': q1_pass},
            'q2_who': {'answer': q2_who, 'pass': q2_pass},
            'q3_space': {'answer': q3_space, 'pass': q3_pass},
            'verdict': '✅ 三問通過，可考慮買入' if all_pass else '❌ 未通過三問，暫不宜買',
            'pass_count': sum([q1_pass, q2_pass, q3_pass]),
        }

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  市場週期判斷（春夏秋冬）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def market_cycle(self) -> Dict:
        """判斷目前市場處於春夏秋冬哪個階段

        春播期：小範圍漲停，溫和放量，普遍忽視 → 觀察待機
        夏長期：全面漲停潮，成交量放大，開始關注 → 重倉介入
        秋收期：補漲瘋狂，天量成交，全民鼓吹 → 逐步減倉
        冬藏期：炸板增多，量能萎縮，負面報道 → 空倉休息
        """
        # 用 0050 近 60 日走勢判斷
        prices = list(self.db.stock_price.find(
            {'symbol': '0050'}, {'close': 1, 'volume': 1, 'date': 1}
        ).sort('date', -1).limit(60))

        if len(prices) < 20:
            return {'cycle': 'unknown', 'reason': '資料不足'}

        closes = [_tof(p['close']) for p in prices]
        volumes = [_tof(p.get('volume', 0)) or 0 for p in prices]

        # 近期漲跌
        ret_5d = (closes[0] - closes[4]) / closes[4] * 100 if len(closes) > 4 else 0
        ret_20d = (closes[0] - closes[19]) / closes[19] * 100 if len(closes) > 19 else 0

        # 量能比較
        vol_5d = np.mean(volumes[:5])
        vol_20d = np.mean(volumes[:20])
        vol_ratio = vol_5d / vol_20d if vol_20d > 0 else 1

        # MA 趨勢
        ma5 = np.mean(closes[:5])
        ma20 = np.mean(closes[:20])
        ma60 = np.mean(closes[:60]) if len(closes) >= 60 else ma20

        if ma5 < ma20 < ma60 and ret_20d < -5:
            cycle = 'winter'
            desc = '冬藏期（量縮下跌，空頭排列）→ 空倉休息'
            position = '0-10%'
        elif ma5 > ma60 and ret_20d < 3 and vol_ratio < 1.2:
            cycle = 'spring'
            desc = '春播期（溫和放量，剛站上均線）→ 觀察待機'
            position = '20-30%'
        elif ma5 > ma20 > ma60 and ret_20d > 5 and vol_ratio > 1.3:
            cycle = 'autumn'
            desc = '秋收期（量大加速，可能見頂）→ 逐步減倉'
            position = '20-30%'
        elif ma5 > ma20 and ret_20d > 0:
            cycle = 'summer'
            desc = '夏長期（穩步上升，量能配合）→ 重倉介入'
            position = '50-70%'
        else:
            cycle = 'spring'
            desc = '春播期（趨勢不明，觀望為主）→ 觀察待機'
            position = '20-30%'

        return {
            'cycle': cycle,
            'description': desc,
            'suggested_position': position,
            'indicators': {
                'ret_5d': round(ret_5d, 2),
                'ret_20d': round(ret_20d, 2),
                'vol_ratio': round(vol_ratio, 2),
                'ma5': round(ma5, 2),
                'ma20': round(ma20, 2),
                'ma60': round(ma60, 2),
            },
        }

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  主力行為偵測（建倉→洗盤→拉升→出貨）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def detect_institution_phase(self, symbol: str) -> Dict:
        """偵測主力目前在哪個階段"""
        prices = list(self.db.stock_price.find(
            {'symbol': symbol}, {'close': 1, 'volume': 1, 'high': 1, 'low': 1, 'date': 1}
        ).sort('date', -1).limit(60))

        if len(prices) < 20:
            return {'symbol': symbol, 'error': '資料不足'}

        closes = [_tof(p['close']) for p in prices]
        volumes = [_tof(p.get('volume', 0)) or 0 for p in prices]
        highs = [_tof(p.get('high', 0)) or 0 for p in prices]
        lows = [_tof(p.get('low', 0)) or 0 for p in prices]

        vol_5d = np.mean(volumes[:5])
        vol_20d = np.mean(volumes[:20])
        vol_ratio = vol_5d / vol_20d if vol_20d > 0 else 1

        ret_5d = (closes[0] - closes[4]) / closes[4] * 100 if len(closes) > 4 else 0
        ret_20d = (closes[0] - closes[19]) / closes[19] * 100 if len(closes) > 19 else 0

        # 振幅
        amplitude_5d = np.mean([(h - l) / l * 100 for h, l in zip(highs[:5], lows[:5]) if l > 0])

        # 判斷階段
        if vol_ratio < 0.8 and abs(ret_5d) < 2 and amplitude_5d < 3:
            phase = '建倉'
            desc = '量縮盤整、價格波動小（主力偷偷吃貨）'
            action = '可分批佈局'
        elif vol_ratio > 1.5 and ret_5d < -3:
            phase = '洗盤'
            desc = '放量下殺（主力震出散戶，製造恐慌）'
            action = '不要賣，等洗盤結束'
        elif vol_ratio > 1.3 and ret_5d > 5:
            phase = '拉升'
            desc = '量增價漲（主力啟動主升浪）'
            action = '跟隨持有，不要下車'
        elif vol_ratio > 2 and ret_5d > 0 and amplitude_5d > 5:
            phase = '出貨'
            desc = '巨量高振幅（主力邊拉邊出）'
            action = '獲利了結，不要貪'
        elif ret_20d < -10 and vol_ratio < 0.7:
            phase = '徹底出貨'
            desc = '陰跌量縮（主力已走完）'
            action = '不要接刀'
        else:
            phase = '觀望'
            desc = '無明確主力訊號'
            action = '繼續觀察'

        return {
            'symbol': symbol,
            'phase': phase,
            'description': desc,
            'action': action,
            'indicators': {
                'vol_ratio': round(vol_ratio, 2),
                'ret_5d': round(ret_5d, 2),
                'ret_20d': round(ret_20d, 2),
                'amplitude_5d': round(amplitude_5d, 2),
            },
        }

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  綜合診斷（法則一～四全檢）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def full_diagnosis(self, symbol: str, cost: float, capital: float = 1000000) -> Dict:
        """對單一持股做北大四大法則全面檢查"""
        cycle = self.market_cycle()
        stop = self.check_stop_loss(symbol, cost)
        three_q = self.buy_three_questions(symbol)
        phase = self.detect_institution_phase(symbol)
        position = self.position_334(capital, cycle['cycle'])

        return {
            'symbol': symbol,
            'market_cycle': cycle,
            'stop_loss': stop,
            'buy_three_questions': three_q,
            'institution_phase': phase,
            'position_334': position,
        }


if __name__ == '__main__':
    tr = TradingRules()

    # 測試市場週期
    print("▏市場週期判斷")
    c = tr.market_cycle()
    print(f"  {c['description']}")
    print(f"  建議倉位: {c['suggested_position']}")

    # 測試持股
    print("\n▏持股檢查")
    for sym, cost in [('2603', 213), ('7705', 53.75), ('5871', 127.96)]:
        s = tr.check_stop_loss(sym, cost)
        print(f"  {sym} 成本{cost} 現{s['current']} {s['action']} {s['ma_trend']}")
        for sig in s['signals']:
            print(f"    {sig}")

    # 測試買入三問
    print("\n▏買入三問（2603 長榮）")
    q = tr.buy_three_questions('2603')
    print(f"  Q1 為什麼漲: {q['q1_why']['answer']} {'✅' if q['q1_why']['pass'] else '❌'}")
    print(f"  Q2 誰在買: {q['q2_who']['answer']} {'✅' if q['q2_who']['pass'] else '❌'}")
    print(f"  Q3 還能漲嗎: {q['q3_space']['answer']} {'✅' if q['q3_space']['pass'] else '❌'}")
    print(f"  結論: {q['verdict']}")

    # 測試主力階段
    print("\n▏主力階段偵測")
    for sym in ['2603', '7705', '5871', '1229']:
        p = tr.detect_institution_phase(sym)
        print(f"  {sym}: {p['phase']} → {p['action']}")
