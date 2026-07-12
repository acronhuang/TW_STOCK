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

from typing import Dict, List, Tuple, Optional
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dataclasses import dataclass


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
        self.holdings_col = self.db['institutional_holdings']
        self.trading_col = self.db['institutional_trading']
    
    def analyze_institutional_holdings(
        self,
        stock_id: str,
        end_date: str,
        lookback_weeks: int = 4
    ) -> Dict:
        """
        分析大戶持股趨勢
        
        Args:
            stock_id: 股票代碼
            end_date: 截止日期
            lookback_weeks: 回溯週數
        
        Returns:
            大戶持股分析結果
        """
        lookback_date = (pd.to_datetime(end_date) - timedelta(weeks=lookback_weeks)).strftime('%Y-%m-%d')
        
        # 獲取持股數據
        data = list(self.holdings_col.find({
            'stock_id': stock_id,
            'date': {'$gte': lookback_date, '$lte': end_date}
        }).sort('date', 1))
        
        if not data:
            return {
                'holding_400_plus': 0,
                'holding_change_4w': 0,
                'trend': 'unknown'
            }
        
        df = pd.DataFrame(data)
        
        # 計算 400 張以上持股比例
        holding_400_plus = df[df['level'] >= 400]['percent'].sum() if len(df) > 0 else 0
        
        # 計算變化率
        if len(df) >= 2:
            latest = df[df['date'] == end_date]['percent'].sum()
            earliest = df[df['date'] == lookback_date]['percent'].sum()
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
    ) -> Dict:
        """
        分析法人買賣動向
        
        Args:
            stock_id: 股票代碼
            end_date: 截止日期
            lookback_days: 回溯天數
        
        Returns:
            法人買賣分析結果
        """
        lookback_date = (pd.to_datetime(end_date) - timedelta(days=lookback_days)).strftime('%Y-%m-%d')
        
        # 獲取法人買賣數據
        data = list(self.trading_col.find({
            'stock_id': stock_id,
            'date': {'$gte': lookback_date, '$lte': end_date}
        }).sort('date', 1))
        
        if not data:
            return {
                'foreign_net_buy': 0,
                'foreign_continuous_days': 0,
                'trust_net_buy': 0,
                'dealer_net_buy': 0
            }
        
        df = pd.DataFrame(data)
        
        # 計算淨買超
        foreign_net_buy = df['Foreign_Investor_Net'].sum() if 'Foreign_Investor_Net' in df.columns else 0
        trust_net_buy = df['Investment_Trust_Net'].sum() if 'Investment_Trust_Net' in df.columns else 0
        dealer_net_buy = df['Dealer_Net'].sum() if 'Dealer_Net' in df.columns else 0
        
        # 計算外資連續買超天數
        foreign_continuous_days = 0
        if 'Foreign_Investor_Net' in df.columns:
            for i in range(len(df) - 1, -1, -1):
                if df.iloc[i]['Foreign_Investor_Net'] > 0:
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
        holdings_analysis: Dict,
        trading_analysis: Dict
    ) -> Tuple[str, float]:
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
        holdings_analysis: Dict,
        trading_analysis: Dict,
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
        stock_ids: List[str],
        date: str
    ) -> List[ChipSignal]:
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
        signals: List[ChipSignal],
        min_score: float = 0.6
    ) -> List[ChipSignal]:
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
    
    print(f"\n台積電籌碼分析（2024-12-31）:")
    print(f"  大戶持股（400張+）: {signal.holding_400_plus:.1%}")
    print(f"  4週變化: {signal.holding_change_4w:+.2%}")
    print(f"  持股趨勢: {signal.holding_trend}")
    print(f"  外資淨買超: {signal.foreign_net_buy:,} 張")
    print(f"  連續買超: {signal.foreign_continuous_days} 天")
    print(f"  投信淨買超: {signal.trust_net_buy:,} 張")
    print(f"  主力訊號: {signal.main_force_signal}")
    print(f"  主力強度: {signal.main_force_strength:.3f}")
    print(f"  籌碼評分: {signal.chip_score:.3f}")
