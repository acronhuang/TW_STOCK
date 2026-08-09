"""
籌碼分析模組

功能：
1. 大戶持股趨勢分析（400/600/800/1000 張）
2. 法人買賣動向分析（外資、投信、自營商）
3. 主力進出訊號生成
4. 籌碼面評分系統

作者: Ming
創建日期: 2026-02-23
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


def _to_utc_midnight(d) -> datetime:
    """日期（字串或 datetime）→ UTC 午夜 datetime。

    本專案 shareholding / institutional_investors_wide / stock_price 的 date
    一律存 UTC 午夜 Date 型別，用字串查詢會查不到任何資料且不會報錯
    （見記憶 date-field-three-representations）。
    """
    if isinstance(d, datetime):
        return datetime(d.year, d.month, d.day, tzinfo=UTC)
    ts = pd.to_datetime(d)
    return datetime(ts.year, ts.month, ts.day, tzinfo=UTC)


@dataclass
class ChipSignal:
    """籌碼訊號"""
    stock_id: str
    date: str
    
    # 大戶持股
    holding_400_plus: float       # 400張以上持股比例
    holding_change_4w: float      # 4週變化率
    holding_trend: str            # 'increasing' / 'stable' / 'decreasing'
    
    # 法人買賣
    foreign_net_buy: int          # 外資淨買超（張）
    foreign_continuous_days: int  # 連續買超天數
    trust_net_buy: int            # 投信淨買超
    dealer_net_buy: int           # 自營商淨買超
    
    # 主力動向
    main_force_signal: str        # 'accumulating' / 'neutral' / 'distributing'
    main_force_strength: float    # 主力強度（0-1）
    
    # 綜合評分
    chip_score: float             # 籌碼綜合評分（0-1）
    
    def __repr__(self):
        return (f"ChipSignal({self.stock_id}, {self.date}, "
                f"score={self.chip_score:.3f}, signal={self.main_force_signal})")


class ChipAnalyzer:
    """籌碼分析器"""
    
    def __init__(self, db_connection):
        """
        初始化
        
        Args:
            db_connection: MongoDB 連接
        """
        self.db = db_connection
        # 2026-07-19 修正資料源。原本指向 institutional_holdings（0 筆）與
        # institutional_trading（470 檔殘骸，且欄位名為 buy/sell/name，
        # 與本模組期待的 Foreign_Investor_Net 等欄位完全不符）→ 兩個 analyze
        # 方法無論輸入什麼股票都恆回 0，且被 `if ... in df.columns else 0` 靜默吞掉。
        self.holdings_col = self.db['shareholding']                    # TDCC 集保大戶
        self.trading_col = self.db['institutional_investors_wide']     # 重建的法人買賣寬表
    
    def analyze_institutional_holdings(
        self,
        stock_id: str,
        end_date: str,
        lookback_weeks: int = 4
    ) -> dict:
        """
        分析大戶持股趨勢
        
        Args:
            stock_id: 股票代碼
            end_date: 截止日期
            lookback_weeks: 回溯週數
        
        Returns:
            大戶持股分析結果
        """
        # shareholding.date 為 UTC 午夜 Date 型別，須用 datetime 查詢（字串查不到）
        end_dt = _to_utc_midnight(end_date)
        start_dt = end_dt - timedelta(weeks=lookback_weeks)

        # 獲取持股數據（TDCC 每週一期）
        data = list(self.holdings_col.find({
            'stock_id': stock_id,
            'date': {'$gte': start_dt, '$lte': end_dt}
        }).sort('date', 1))

        if not data:
            return {
                'holding_400_plus': 0,
                'holding_change_4w': 0,
                'trend': 'unknown'
            }

        # big400_pct 即「400 張以上持股比例」，不需再依 level 彙總
        pcts = [float(d['big400_pct']) for d in data if d.get('big400_pct') is not None]
        if not pcts:
            return {
                'holding_400_plus': 0,
                'holding_change_4w': 0,
                'trend': 'unknown'
            }

        holding_400_plus = pcts[-1]          # 最新一期

        # 計算變化率（維持原本的「相對變化」定義，門檻語意不變）
        if len(pcts) >= 2:
            latest, earliest = pcts[-1], pcts[0]
            change_4w = (latest - earliest) / earliest if earliest > 0 else 0
        else:
            change_4w = 0
        
        # 判斷趨勢
        if change_4w > 0.03:
            trend = 'increasing'
        elif change_4w < -0.03:
            trend = 'decreasing'
        else:
            trend = 'stable'
        
        return {
            'holding_400_plus': holding_400_plus,
            'holding_change_4w': change_4w,
            'trend': trend
        }
    
    def analyze_institutional_trading(
        self,
        stock_id: str,
        end_date: str,
        lookback_days: int = 20
    ) -> dict:
        """
        分析法人買賣動向
        
        Args:
            stock_id: 股票代碼
            end_date: 截止日期
            lookback_days: 回溯天數
        
        Returns:
            法人買賣分析結果
        """
        # institutional_investors_wide.date 為 UTC 午夜 Date 型別
        end_dt = _to_utc_midnight(end_date)
        start_dt = end_dt - timedelta(days=lookback_days)

        # 獲取法人買賣數據（欄位：foreign_net / trust_net / dealer_net，單位為股數）
        data = list(self.trading_col.find(
            {'stock_id': stock_id, 'date': {'$gte': start_dt, '$lte': end_dt}},
            {'date': 1, 'foreign_net': 1, 'trust_net': 1, 'dealer_net': 1}
        ).sort('date', 1))

        if not data:
            return {
                'foreign_net_buy': 0,
                'foreign_continuous_days': 0,
                'trust_net_buy': 0,
                'dealer_net_buy': 0
            }

        def _n(d, k):
            v = d.get(k)
            return 0 if v is None else float(v)

        # institutional_investors_wide 的單位是「股」，但 ChipSignal 宣告的是「張」
        # （見本檔 ChipSignal.foreign_net_buy 註解，及 scripts/chip_score_scan.py 的
        # read_institutional：「法人 total_net 單位為股 → /1000」）。
        # 未換算會讓 detect_main_force 的 >1000 / >500 門檻恆成立 → 外資項恆滿分。
        SHARES_PER_LOT = 1000

        foreign_series = [_n(d, 'foreign_net') for d in data]
        foreign_net_buy = sum(foreign_series) / SHARES_PER_LOT
        trust_net_buy = sum(_n(d, 'trust_net') for d in data) / SHARES_PER_LOT
        dealer_net_buy = sum(_n(d, 'dealer_net') for d in data) / SHARES_PER_LOT

        # 計算外資連續買超天數（由最新往回數）
        foreign_continuous_days = 0
        for v in reversed(foreign_series):
            if v > 0:
                foreign_continuous_days += 1
            else:
                break

        return {
            'foreign_net_buy': int(foreign_net_buy),
            'foreign_continuous_days': foreign_continuous_days,
            'trust_net_buy': int(trust_net_buy),
            'dealer_net_buy': int(dealer_net_buy)
        }
    
    def detect_main_force(
        self,
        holdings_analysis: dict,
        trading_analysis: dict
    ) -> tuple[str, float]:
        """
        偵測主力動向
        
        Args:
            holdings_analysis: 大戶持股分析
            trading_analysis: 法人買賣分析
        
        Returns:
            (主力訊號, 強度)
        """
        # 主力累積訊號
        accumulating_score = 0.0
        
        # 1. 大戶持股增加
        if holdings_analysis['holding_change_4w'] > 0.05:
            accumulating_score += 0.4
        elif holdings_analysis['holding_change_4w'] > 0.03:
            accumulating_score += 0.2
        
        # 2. 外資買超
        if trading_analysis['foreign_net_buy'] > 1000:
            accumulating_score += 0.3
        elif trading_analysis['foreign_net_buy'] > 500:
            accumulating_score += 0.15
        
        # 3. 外資連續買超
        if trading_analysis['foreign_continuous_days'] >= 5:
            accumulating_score += 0.2
        elif trading_analysis['foreign_continuous_days'] >= 3:
            accumulating_score += 0.1
        
        # 4. 投信買超
        if trading_analysis['trust_net_buy'] > 500:
            accumulating_score += 0.1
        
        # 判斷訊號
        if accumulating_score >= 0.6:
            signal = 'accumulating'
        elif accumulating_score <= 0.2:
            signal = 'distributing'
        else:
            signal = 'neutral'
        
        strength = min(accumulating_score, 1.0)
        
        return signal, strength
    
    def calculate_chip_score(
        self,
        holdings_analysis: dict,
        trading_analysis: dict,
        main_force_signal: str,
        main_force_strength: float
    ) -> float:
        """
        計算籌碼綜合評分
        
        Args:
            holdings_analysis: 大戶持股分析
            trading_analysis: 法人買賣分析
            main_force_signal: 主力訊號
            main_force_strength: 主力強度
        
        Returns:
            籌碼評分（0-1）
        """
        score = 0.0
        
        # 1. 大戶持股趨勢（30%）
        if holdings_analysis['trend'] == 'increasing':
            score += 0.30
        elif holdings_analysis['trend'] == 'stable':
            score += 0.15
        
        # 2. 外資動向（30%）
        if trading_analysis['foreign_net_buy'] > 1000:
            score += 0.30
        elif trading_analysis['foreign_net_buy'] > 500:
            score += 0.20
        elif trading_analysis['foreign_net_buy'] > 0:
            score += 0.10
        
        # 3. 投信動向（20%）
        if trading_analysis['trust_net_buy'] > 500:
            score += 0.20
        elif trading_analysis['trust_net_buy'] > 200:
            score += 0.10
        
        # 4. 主力強度（20%）
        score += main_force_strength * 0.20
        
        return min(score, 1.0)
    
    def analyze(
        self,
        stock_id: str,
        date: str,
        lookback_weeks: int = 4,
        lookback_days: int = 20
    ) -> ChipSignal:
        """
        完整籌碼分析
        
        Args:
            stock_id: 股票代碼
            date: 分析日期
            lookback_weeks: 持股回溯週數
            lookback_days: 交易回溯天數
        
        Returns:
            ChipSignal 物件
        """
        # 1. 分析大戶持股
        holdings = self.analyze_institutional_holdings(
            stock_id, date, lookback_weeks
        )
        
        # 2. 分析法人買賣
        trading = self.analyze_institutional_trading(
            stock_id, date, lookback_days
        )
        
        # 3. 偵測主力動向
        main_signal, main_strength = self.detect_main_force(holdings, trading)
        
        # 4. 計算綜合評分
        chip_score = self.calculate_chip_score(
            holdings, trading, main_signal, main_strength
        )
        
        # 5. 生成訊號
        signal = ChipSignal(
            stock_id=stock_id,
            date=date,
            holding_400_plus=holdings['holding_400_plus'],
            holding_change_4w=holdings['holding_change_4w'],
            holding_trend=holdings['trend'],
            foreign_net_buy=trading['foreign_net_buy'],
            foreign_continuous_days=trading['foreign_continuous_days'],
            trust_net_buy=trading['trust_net_buy'],
            dealer_net_buy=trading['dealer_net_buy'],
            main_force_signal=main_signal,
            main_force_strength=main_strength,
            chip_score=chip_score
        )
        
        return signal
    
    def batch_analyze(
        self,
        stock_ids: list[str],
        date: str
    ) -> list[ChipSignal]:
        """
        批量分析多支股票
        
        Args:
            stock_ids: 股票代碼列表
            date: 分析日期
        
        Returns:
            ChipSignal 列表
        """
        signals = []
        
        for stock_id in stock_ids:
            try:
                signal = self.analyze(stock_id, date)
                signals.append(signal)
            except Exception as e:
                print(f"⚠️  {stock_id} 籌碼分析失敗: {e}")
                continue
        
        return signals
    
    def filter_by_chip_score(
        self,
        signals: list[ChipSignal],
        min_score: float = 0.6
    ) -> list[ChipSignal]:
        """
        根據籌碼評分過濾
        
        Args:
            signals: ChipSignal 列表
            min_score: 最低評分
        
        Returns:
            過濾後的 ChipSignal 列表
        """
        return [s for s in signals if s.chip_score >= min_score]
    
    def integrate_with_pattern_score(
        self,
        pattern_score: float,
        chip_signal: ChipSignal
    ) -> float:
        """
        整合形態評分與籌碼評分
        
        Args:
            pattern_score: 形態評分（0-1）
            chip_signal: 籌碼訊號
        
        Returns:
            整合後評分（0-1）
        """
        # 基礎權重：形態 70%、籌碼 30%
        base_score = pattern_score * 0.7 + chip_signal.chip_score * 0.3
        
        # 強化邏輯
        boost = 1.0
        
        # 主力累積 + 形態良好 → 加權 1.2
        if chip_signal.main_force_signal == 'accumulating' and pattern_score >= 0.7:
            boost = 1.2
        
        # 主力出貨 → 降權 0.7
        elif chip_signal.main_force_signal == 'distributing':
            boost = 0.7
        
        # 外資強勁買超 → 加權 1.15
        if chip_signal.foreign_continuous_days >= 5 and chip_signal.foreign_net_buy > 1000:
            boost *= 1.15
        
        final_score = min(base_score * boost, 1.0)
        
        return final_score


# 便捷函數
def analyze_chip(db_connection, stock_id: str, date: str) -> ChipSignal:
    """
    快速籌碼分析
    
    Args:
        db_connection: MongoDB 連接
        stock_id: 股票代碼
        date: 分析日期
    
    Returns:
        ChipSignal 物件
    """
    analyzer = ChipAnalyzer(db_connection)
    return analyzer.analyze(stock_id, date)


if __name__ == "__main__":
    """測試範例"""
    from pymongo import MongoClient
    
    # 連接資料庫
    client = MongoClient('mongodb://localhost:27017/')
    db = client['tw_stock_analysis']
    
    # 初始化分析器
    analyzer = ChipAnalyzer(db)
    
    # 分析台積電
    signal = analyzer.analyze('2330', '2024-12-31')
    
    print("\n台積電籌碼分析（2024-12-31）:")
    print(f"  大戶持股（400張+）: {signal.holding_400_plus:.1%}")
    print(f"  4週變化: {signal.holding_change_4w:+.2%}")
    print(f"  持股趨勢: {signal.holding_trend}")
    print(f"  外資淨買超: {signal.foreign_net_buy:,} 張")
    print(f"  連續買超: {signal.foreign_continuous_days} 天")
    print(f"  投信淨買超: {signal.trust_net_buy:,} 張")
    print(f"  主力訊號: {signal.main_force_signal}")
    print(f"  主力強度: {signal.main_force_strength:.3f}")
    print(f"  籌碼評分: {signal.chip_score:.3f}")
