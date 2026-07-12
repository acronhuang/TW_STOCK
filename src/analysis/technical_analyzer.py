#!/usr/bin/env python3
"""
多空判斷系統
===========
根據技術指標綜合判斷股票多空態勢
"""

from pymongo import MongoClient
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import statistics

MONGODB_URI = 'mongodb://localhost:27017/'
DB_NAME = 'tw_stock_analysis'


class TechnicalAnalyzer:
    """技術分析多空判斷"""
    
    def __init__(self):
        self.client = MongoClient(MONGODB_URI)
        self.db = self.client[DB_NAME]
        
    def analyze_stock(self, symbol: str, date: str = None) -> Dict:
        """
        分析單一股票的多空態勢
        
        Args:
            symbol: 股票代碼
            date: 分析日期 (None = 最新)
            
        Returns:
            {
                'symbol': 股票代碼,
                'date': 分析日期,
                'score': 多空分數 (-100~100),
                'signal': '強多'/'多'/'中性'/'空'/'強空',
                'trend_score': 趨勢分數,
                'momentum_score': 動能分數,
                'volume_score': 量能分數,
                'details': 各指標詳細資訊
            }
        """
        # 取得技術指標
        if date:
            indicator = self.db.technical_indicators.find_one({
                'symbol': symbol,
                'date': date
            })
        else:
            indicator = self.db.technical_indicators.find_one(
                {'symbol': symbol},
                sort=[('date', -1)]
            )
            
        if not indicator:
            return {
                'symbol': symbol,
                'error': '找不到技術指標資料'
            }
        
        # 取得股價資料 (處理日期格式差異)
        indicator_date = indicator['date']
        if isinstance(indicator_date, str):
            # technical_indicators 用字串,需轉換為 datetime 來查詢 stock_price
            from datetime import datetime
            date_obj = datetime.strptime(indicator_date, '%Y-%m-%d')
        else:
            date_obj = indicator_date
            
        price = self.db.stock_price.find_one({
            'symbol': symbol,
            'date': date_obj
        })
        
        if not price:
            return {
                'symbol': symbol,
                'error': '找不到股價資料'
            }
        
        # 計算各項分數
        trend_score = self._analyze_trend(indicator, price)
        momentum_score = self._analyze_momentum(indicator)
        volume_score = self._analyze_volume(indicator, price)
        
        # 綜合分數 (加權平均)
        total_score = (
            trend_score * 0.4 +      # 趨勢 40%
            momentum_score * 0.35 +   # 動能 35%
            volume_score * 0.25       # 量能 25%
        )
        
        # 判斷信號
        signal = self._get_signal(total_score)
        
        return {
            'symbol': symbol,
            'date': indicator['date'],
            'close': price['close'],
            'score': round(total_score, 2),
            'signal': signal,
            'trend_score': round(trend_score, 2),
            'momentum_score': round(momentum_score, 2),
            'volume_score': round(volume_score, 2),
            'details': {
                'trend': self._get_trend_details(indicator, price),
                'momentum': self._get_momentum_details(indicator),
                'volume': self._get_volume_details(indicator, price)
            }
        }
    
    def _analyze_trend(self, indicator: Dict, price: Dict) -> float:
        """分析趨勢 (-100~100)"""
        score = 0
        close = price['close']
        
        # 1. 均線多頭排列 (30分)
        ma_score = 0
        if all(k in indicator for k in ['MA5', 'MA10', 'MA20', 'MA60']):
            if indicator['MA5'] > indicator['MA10'] > indicator['MA20'] > indicator['MA60']:
                ma_score = 30
            elif indicator['MA5'] < indicator['MA10'] < indicator['MA20'] < indicator['MA60']:
                ma_score = -30
            else:
                # 部分排列
                above_count = sum([
                    1 if indicator['MA5'] > indicator['MA10'] else 0,
                    1 if indicator['MA10'] > indicator['MA20'] else 0,
                    1 if indicator['MA20'] > indicator['MA60'] else 0
                ])
                ma_score = (above_count - 1.5) * 20
        
        # 2. 價格相對均線位置 (20分)
        price_ma_score = 0
        if 'MA20' in indicator:
            ma20_diff = (close - indicator['MA20']) / indicator['MA20'] * 100
            if ma20_diff > 10:
                price_ma_score = 20
            elif ma20_diff > 5:
                price_ma_score = 15
            elif ma20_diff > 0:
                price_ma_score = 10
            elif ma20_diff > -5:
                price_ma_score = -10
            elif ma20_diff > -10:
                price_ma_score = -15
            else:
                price_ma_score = -20
        
        # 3. ADX 趨勢強度 (20分)
        adx_score = 0
        if 'ADX' in indicator:
            adx = indicator['ADX']
            dmi_plus = indicator.get('DMI_plus', 0)
            dmi_minus = indicator.get('DMI_minus', 0)
            
            if adx > 25:  # 強趨勢
                if dmi_plus > dmi_minus:
                    adx_score = 20
                else:
                    adx_score = -20
            elif adx > 20:  # 中等趨勢
                if dmi_plus > dmi_minus:
                    adx_score = 10
                else:
                    adx_score = -10
        
        # 4. 布林通道位置 (30分)
        bb_score = 0
        if all(k in indicator for k in ['BB_upper', 'BB_middle', 'BB_lower']):
            bb_upper = indicator['BB_upper']
            bb_middle = indicator['BB_middle']
            bb_lower = indicator['BB_lower']
            
            if close > bb_upper:
                bb_score = 30
            elif close > bb_middle:
                bb_score = 15
            elif close > bb_lower:
                bb_score = 0
            elif close > bb_lower * 0.98:
                bb_score = -15
            else:
                bb_score = -30
        
        score = ma_score + price_ma_score + adx_score + bb_score
        return max(-100, min(100, score))
    
    def _analyze_momentum(self, indicator: Dict) -> float:
        """分析動能 (-100~100)"""
        score = 0
        
        # 1. RSI (30分)
        rsi_score = 0
        if 'RSI' in indicator:
            rsi = indicator['RSI']
            if rsi > 70:
                rsi_score = 30
            elif rsi > 60:
                rsi_score = 20
            elif rsi > 50:
                rsi_score = 10
            elif rsi > 40:
                rsi_score = -10
            elif rsi > 30:
                rsi_score = -20
            else:
                rsi_score = -30
        
        # 2. MACD (35分)
        macd_score = 0
        if all(k in indicator for k in ['MACD', 'MACD_signal']):
            macd = indicator['MACD']
            signal = indicator['MACD_signal']
            diff = macd - signal
            
            if macd > 0 and signal > 0 and diff > 0:
                macd_score = 35
            elif macd > 0 and diff > 0:
                macd_score = 25
            elif diff > 0:
                macd_score = 15
            elif macd < 0 and signal < 0 and diff < 0:
                macd_score = -35
            elif macd < 0 and diff < 0:
                macd_score = -25
            elif diff < 0:
                macd_score = -15
        
        # 3. KD (35分)
        kd_score = 0
        if all(k in indicator for k in ['KD_K', 'KD_D']):
            k = indicator['KD_K']
            d = indicator['KD_D']
            
            if k > 80 and d > 80:
                kd_score = 30
            elif k > d and k > 50:
                kd_score = 20
            elif k > d:
                kd_score = 10
            elif k < 20 and d < 20:
                kd_score = -30
            elif k < d and k < 50:
                kd_score = -20
            elif k < d:
                kd_score = -10
        
        score = rsi_score + macd_score + kd_score
        return max(-100, min(100, score))
    
    def _analyze_volume(self, indicator: Dict, price: Dict) -> float:
        """分析量能 (-100~100)"""
        score = 0
        
        # 1. 成交量比率 (40分)
        vol_ratio_score = 0
        if 'volume_ratio' in indicator:
            vol_ratio = indicator['volume_ratio']
            if vol_ratio > 2.0:
                vol_ratio_score = 40
            elif vol_ratio > 1.5:
                vol_ratio_score = 30
            elif vol_ratio > 1.2:
                vol_ratio_score = 20
            elif vol_ratio > 1.0:
                vol_ratio_score = 10
            elif vol_ratio > 0.8:
                vol_ratio_score = -10
            elif vol_ratio > 0.5:
                vol_ratio_score = -20
            else:
                vol_ratio_score = -30
        
        # 2. OBV (30分)
        obv_score = 0
        if 'OBV' in indicator and 'OBV_MA' in indicator:
            obv = indicator['OBV']
            obv_ma = indicator.get('OBV_MA', obv)
            
            if obv > obv_ma * 1.1:
                obv_score = 30
            elif obv > obv_ma:
                obv_score = 15
            elif obv < obv_ma * 0.9:
                obv_score = -30
            elif obv < obv_ma:
                obv_score = -15
        
        # 3. MFI (30分)
        mfi_score = 0
        if 'MFI' in indicator:
            mfi = indicator['MFI']
            if mfi > 80:
                mfi_score = 30
            elif mfi > 60:
                mfi_score = 20
            elif mfi > 50:
                mfi_score = 10
            elif mfi > 40:
                mfi_score = -10
            elif mfi > 20:
                mfi_score = -20
            else:
                mfi_score = -30
        
        score = vol_ratio_score + obv_score + mfi_score
        return max(-100, min(100, score))
    
    def _get_signal(self, score: float) -> str:
        """根據分數判斷信號"""
        if score >= 60:
            return '強多'
        elif score >= 30:
            return '多'
        elif score >= -30:
            return '中性'
        elif score >= -60:
            return '空'
        else:
            return '強空'
    
    def _get_trend_details(self, indicator: Dict, price: Dict) -> Dict:
        """趨勢詳細資訊"""
        close = price['close']
        details = {}
        
        # 均線排列
        if all(k in indicator for k in ['MA5', 'MA10', 'MA20', 'MA60']):
            ma5, ma10, ma20, ma60 = indicator['MA5'], indicator['MA10'], indicator['MA20'], indicator['MA60']
            if ma5 > ma10 > ma20 > ma60:
                details['均線'] = '多頭排列 ⬆️'
            elif ma5 < ma10 < ma20 < ma60:
                details['均線'] = '空頭排列 ⬇️'
            else:
                details['均線'] = '盤整'
        
        # 價格位置
        if 'MA20' in indicator:
            diff = (close - indicator['MA20']) / indicator['MA20'] * 100
            details['價格位置'] = f"距MA20: {diff:+.2f}%"
        
        # ADX
        if 'ADX' in indicator:
            adx = indicator['ADX']
            if adx > 25:
                details['趨勢強度'] = f'強趨勢 (ADX={adx:.1f})'
            elif adx > 20:
                details['趨勢強度'] = f'中等趨勢 (ADX={adx:.1f})'
            else:
                details['趨勢強度'] = f'弱趨勢 (ADX={adx:.1f})'
        
        return details
    
    def _get_momentum_details(self, indicator: Dict) -> Dict:
        """動能詳細資訊"""
        details = {}
        
        if 'RSI' in indicator:
            rsi = indicator['RSI']
            if rsi > 70:
                details['RSI'] = f'{rsi:.1f} (超買)'
            elif rsi < 30:
                details['RSI'] = f'{rsi:.1f} (超賣)'
            else:
                details['RSI'] = f'{rsi:.1f}'
        
        if all(k in indicator for k in ['MACD', 'MACD_signal']):
            macd = indicator['MACD']
            signal = indicator['MACD_signal']
            if macd > signal:
                details['MACD'] = '黃金交叉 ⬆️'
            else:
                details['MACD'] = '死亡交叉 ⬇️'
        
        if all(k in indicator for k in ['KD_K', 'KD_D']):
            k = indicator['KD_K']
            d = indicator['KD_D']
            if k > 80 and d > 80:
                details['KD'] = f'K={k:.1f}, D={d:.1f} (超買)'
            elif k < 20 and d < 20:
                details['KD'] = f'K={k:.1f}, D={d:.1f} (超賣)'
            elif k > d:
                details['KD'] = f'K={k:.1f} > D={d:.1f} (黃金交叉)'
            else:
                details['KD'] = f'K={k:.1f} < D={d:.1f} (死亡交叉)'
        
        return details
    
    def _get_volume_details(self, indicator: Dict, price: Dict) -> Dict:
        """量能詳細資訊"""
        details = {}
        
        if 'volume_ratio' in indicator:
            ratio = indicator['volume_ratio']
            details['量比'] = f'{ratio:.2f}倍'
        
        if 'MFI' in indicator:
            mfi = indicator['MFI']
            if mfi > 80:
                details['MFI'] = f'{mfi:.1f} (資金充裕)'
            elif mfi < 20:
                details['MFI'] = f'{mfi:.1f} (資金不足)'
            else:
                details['MFI'] = f'{mfi:.1f}'
        
        return details
    
    def scan_market(self, signal_filter: str = None, limit: int = 50) -> List[Dict]:
        """
        掃描市場找出符合條件的股票
        
        Args:
            signal_filter: '強多'/'多'/'中性'/'空'/'強空' (None=全部)
            limit: 返回數量限制
            
        Returns:
            排序後的股票分析結果列表
        """
        # 取得最新日期
        latest = self.db.technical_indicators.find_one(
            {},
            sort=[('date', -1)]
        )
        
        if not latest:
            return []
        
        latest_date = latest['date']
        
        # 取得該日期所有有技術指標的股票
        symbols = self.db.technical_indicators.distinct('symbol', {'date': latest_date})
        
        results = []
        for symbol in symbols:
            try:
                analysis = self.analyze_stock(symbol, latest_date)
                if 'error' not in analysis:
                    if signal_filter is None or analysis['signal'] == signal_filter:
                        results.append(analysis)
            except Exception as e:
                continue
        
        # 按分數排序
        results.sort(key=lambda x: x['score'], reverse=True)
        
        return results[:limit]


def main():
    """測試多空判斷系統"""
    analyzer = TechnicalAnalyzer()
    
    # 測試單一股票
    print("=" * 80)
    print("🎯 多空判斷系統測試")
    print("=" * 80)
    
    test_symbols = ['2330', '2317', '2454', '2881', '2882']
    
    for symbol in test_symbols:
        print(f"\n【{symbol}】")
        result = analyzer.analyze_stock(symbol)
        
        if 'error' in result:
            print(f"  ❌ {result['error']}")
            continue
        
        print(f"  日期: {result['date']}")
        print(f"  收盤: {result['close']:.2f}")
        print(f"  綜合分數: {result['score']:.2f}")
        print(f"  信號: {result['signal']}")
        print(f"  ├─ 趨勢分數: {result['trend_score']:.2f}")
        print(f"  ├─ 動能分數: {result['momentum_score']:.2f}")
        print(f"  └─ 量能分數: {result['volume_score']:.2f}")
        
        print(f"\n  📊 趨勢:")
        for key, value in result['details']['trend'].items():
            print(f"     • {key}: {value}")
        
        print(f"\n  ⚡ 動能:")
        for key, value in result['details']['momentum'].items():
            print(f"     • {key}: {value}")
        
        print(f"\n  💰 量能:")
        for key, value in result['details']['volume'].items():
            print(f"     • {key}: {value}")
    
    # 市場掃描
    print("\n" + "=" * 80)
    print("🔍 市場掃描 - 強多股票 TOP 10")
    print("=" * 80)
    
    strong_bulls = analyzer.scan_market(signal_filter='強多', limit=10)
    
    for i, stock in enumerate(strong_bulls, 1):
        print(f"{i:2d}. {stock['symbol']:6s} | 分數:{stock['score']:6.2f} | "
              f"收盤:{stock['close']:7.2f} | {stock['signal']}")


if __name__ == "__main__":
    main()
