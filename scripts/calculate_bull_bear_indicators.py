#!/usr/bin/env python3
"""
多空指標計算系統
整合技術面、籌碼面、資券面進行綜合評分
評分範圍: -100 (極空) 到 +100 (極多)
"""

import pymongo
from datetime import datetime, timedelta
import numpy as np
from typing import Dict, List, Optional

class BullBearCalculator:
    def __init__(self):
        self.db = pymongo.MongoClient('mongodb://localhost:27017/')['tw_stock_analysis']
        
    def calculate_bull_bear_score(self, stock_id: str, date: str = None) -> Dict:
        """
        計算股票的多空評分
        
        參數:
            stock_id: 股票代碼
            date: 計算日期 (預設為最新)
            
        返回:
            {
                'stock_id': 股票代碼,
                'date': 計算日期,
                'total_score': 總分 (-100 ~ +100),
                'grade': 等級 (A+/A/B/C/D/F),
                'signal': 訊號 (極多/偏多/中性/偏空/極空),
                'technical_score': 技術面分數 (40%權重),
                'institutional_score': 籌碼面分數 (30%權重),
                'margin_score': 資券面分數 (30%權重),
                'details': 詳細指標
            }
        """
        if not date:
            date = datetime.now().strftime('%Y-%m-%d')
        
        # 計算各面向分數
        technical_score = self._calculate_technical_score(stock_id, date)
        institutional_score = self._calculate_institutional_score(stock_id, date)
        margin_score = self._calculate_margin_score(stock_id, date)
        
        # 加權計算總分
        total_score = (
            technical_score['score'] * 0.4 +
            institutional_score['score'] * 0.3 +
            margin_score['score'] * 0.3
        )
        
        # 評級與訊號
        grade = self._get_grade(total_score)
        signal = self._get_signal(total_score)
        
        return {
            'stock_id': stock_id,
            'date': date,
            'total_score': round(total_score, 2),
            'grade': grade,
            'signal': signal,
            'technical_score': technical_score,
            'institutional_score': institutional_score,
            'margin_score': margin_score,
            'timestamp': datetime.now().isoformat()
        }
    
    def _calculate_technical_score(self, stock_id: str, date: str) -> Dict:
        """
        計算技術面分數 (40%權重)
        評估項目: MA趨勢、MACD、RSI、KD
        """
        tech = self.db['technical_indicators'].find_one(
            {'symbol': stock_id},
            sort=[('date', -1)]
        )
        
        if not tech:
            return {'score': 0, 'details': '無技術指標資料'}
        
        score = 0
        details = {}
        
        # 1. MA 趨勢 (25分)
        try:
            ma5 = tech.get('MA_5', 0)
            ma10 = tech.get('MA_10', 0)
            ma20 = tech.get('MA_20', 0)
            ma60 = tech.get('MA_60', 0)
            close = tech.get('close', 0)
            
            ma_score = 0
            if close > ma5 > ma10 > ma20 > ma60:
                ma_score = 25  # 完美多頭排列
                details['MA_趨勢'] = '完美多頭排列 ✅'
            elif close > ma5 > ma10 > ma20:
                ma_score = 18
                details['MA_趨勢'] = '多頭排列'
            elif close > ma5 > ma10:
                ma_score = 10
                details['MA_趨勢'] = '短期多頭'
            elif ma60 > ma20 > ma10 > ma5 > close:
                ma_score = -25  # 完美空頭排列
                details['MA_趨勢'] = '完美空頭排列 ⚠️'
            elif ma20 > ma10 > ma5 > close:
                ma_score = -18
                details['MA_趨勢'] = '空頭排列'
            elif ma10 > ma5 > close:
                ma_score = -10
                details['MA_趨勢'] = '短期空頭'
            else:
                ma_score = 0
                details['MA_趨勢'] = '盤整'
            
            score += ma_score
        except:
            details['MA_趨勢'] = '資料不足'
        
        # 2. MACD (25分)
        try:
            macd = tech.get('MACD', 0)
            macd_signal = tech.get('MACD_signal', 0)
            macd_hist = tech.get('MACD_histogram', 0)
            
            macd_score = 0
            if macd > 0 and macd_signal > 0 and macd > macd_signal:
                macd_score = 25  # 黃金交叉且在零軸上
                details['MACD'] = '強力多方 ✅'
            elif macd > macd_signal and macd_hist > 0:
                macd_score = 15  # 黃金交叉
                details['MACD'] = '多方訊號'
            elif macd < 0 and macd_signal < 0 and macd < macd_signal:
                macd_score = -25  # 死亡交叉且在零軸下
                details['MACD'] = '強力空方 ⚠️'
            elif macd < macd_signal and macd_hist < 0:
                macd_score = -15  # 死亡交叉
                details['MACD'] = '空方訊號'
            else:
                macd_score = 0
                details['MACD'] = '中性'
            
            score += macd_score
        except:
            details['MACD'] = '資料不足'
        
        # 3. RSI (25分)
        try:
            rsi = tech.get('RSI', 50)
            
            rsi_score = 0
            if rsi >= 70:
                rsi_score = -15  # 超買
                details['RSI'] = f'{rsi:.1f} - 超買 ⚠️'
            elif rsi >= 60:
                rsi_score = 10
                details['RSI'] = f'{rsi:.1f} - 強勢'
            elif rsi >= 50:
                rsi_score = 5
                details['RSI'] = f'{rsi:.1f} - 偏多'
            elif rsi >= 40:
                rsi_score = -5
                details['RSI'] = f'{rsi:.1f} - 偏空'
            elif rsi >= 30:
                rsi_score = -10
                details['RSI'] = f'{rsi:.1f} - 弱勢'
            else:
                rsi_score = 15  # 超賣反而是買點
                details['RSI'] = f'{rsi:.1f} - 超賣(買點) ✅'
            
            score += rsi_score
        except:
            details['RSI'] = '資料不足'
        
        # 4. KD (25分)
        try:
            k = tech.get('K', 50)
            d = tech.get('D', 50)
            
            kd_score = 0
            if k > 80 and d > 80:
                kd_score = -15  # 超買
                details['KD'] = f'K={k:.1f}, D={d:.1f} - 超買 ⚠️'
            elif k > d and k > 50:
                kd_score = 25  # 黃金交叉且在高檔
                details['KD'] = f'K={k:.1f}, D={d:.1f} - 黃金交叉 ✅'
            elif k > d:
                kd_score = 15  # 黃金交叉
                details['KD'] = f'K={k:.1f}, D={d:.1f} - 多方'
            elif k < 20 and d < 20:
                kd_score = 15  # 超賣反而是買點
                details['KD'] = f'K={k:.1f}, D={d:.1f} - 超賣(買點) ✅'
            elif k < d and k < 50:
                kd_score = -25  # 死亡交叉且在低檔
                details['KD'] = f'K={k:.1f}, D={d:.1f} - 死亡交叉 ⚠️'
            elif k < d:
                kd_score = -15  # 死亡交叉
                details['KD'] = f'K={k:.1f}, D={d:.1f} - 空方'
            else:
                kd_score = 0
                details['KD'] = f'K={k:.1f}, D={d:.1f} - 中性'
            
            score += kd_score
        except:
            details['KD'] = '資料不足'
        
        return {
            'score': score,
            'max_score': 100,
            'weight': 0.4,
            'details': details
        }
    
    def _calculate_institutional_score(self, stock_id: str, date: str) -> Dict:
        """
        計算籌碼面分數 (30%權重)
        評估項目: 外資、投信、自營商買賣超趨勢
        """
        # 取得最近20天的法人資料
        end_date = datetime.strptime(date, '%Y-%m-%d')
        start_date = end_date - timedelta(days=30)
        
        inst_data = list(self.db['institutional_investors'].find({
            'symbol': stock_id,
            'date': {'$gte': start_date.strftime('%Y-%m-%d'), '$lte': date}
        }).sort('date', -1).limit(20))
        
        if not inst_data:
            return {'score': 0, 'details': '無法人資料'}
        
        score = 0
        details = {}
        
        # 1. 外資 (50分)
        try:
            foreign_5d = sum([d.get('foreignInvestorNetBuySell', 0) for d in inst_data[:5]])
            foreign_10d = sum([d.get('foreignInvestorNetBuySell', 0) for d in inst_data[:10]])
            foreign_20d = sum([d.get('foreignInvestorNetBuySell', 0) for d in inst_data[:20]])
            
            foreign_score = 0
            if foreign_5d > 0 and foreign_10d > 0 and foreign_20d > 0:
                foreign_score = 50  # 持續買超
                details['外資'] = f'持續買超 (5D:{foreign_5d/10000:.0f}萬) ✅'
            elif foreign_5d > 0 and foreign_10d > 0:
                foreign_score = 30
                details['外資'] = f'短期買超 (5D:{foreign_5d/10000:.0f}萬)'
            elif foreign_5d > 0:
                foreign_score = 15
                details['外資'] = f'近期買超 (5D:{foreign_5d/10000:.0f}萬)'
            elif foreign_5d < 0 and foreign_10d < 0 and foreign_20d < 0:
                foreign_score = -50  # 持續賣超
                details['外資'] = f'持續賣超 (5D:{foreign_5d/10000:.0f}萬) ⚠️'
            elif foreign_5d < 0 and foreign_10d < 0:
                foreign_score = -30
                details['外資'] = f'短期賣超 (5D:{foreign_5d/10000:.0f}萬)'
            elif foreign_5d < 0:
                foreign_score = -15
                details['外資'] = f'近期賣超 (5D:{foreign_5d/10000:.0f}萬)'
            else:
                foreign_score = 0
                details['外資'] = '中性'
            
            score += foreign_score
        except:
            details['外資'] = '資料不足'
        
        # 2. 投信 (30分)
        try:
            trust_5d = sum([d.get('investmentTrustNetBuySell', 0) for d in inst_data[:5]])
            trust_10d = sum([d.get('investmentTrustNetBuySell', 0) for d in inst_data[:10]])
            
            trust_score = 0
            if trust_5d > 0 and trust_10d > 0:
                trust_score = 30
                details['投信'] = f'持續買超 (5D:{trust_5d/10000:.0f}萬) ✅'
            elif trust_5d > 0:
                trust_score = 15
                details['投信'] = f'近期買超 (5D:{trust_5d/10000:.0f}萬)'
            elif trust_5d < 0 and trust_10d < 0:
                trust_score = -30
                details['投信'] = f'持續賣超 (5D:{trust_5d/10000:.0f}萬) ⚠️'
            elif trust_5d < 0:
                trust_score = -15
                details['投信'] = f'近期賣超 (5D:{trust_5d/10000:.0f}萬)'
            else:
                trust_score = 0
                details['投信'] = '中性'
            
            score += trust_score
        except:
            details['投信'] = '資料不足'
        
        # 3. 自營商 (20分)
        try:
            dealer_5d = sum([d.get('dealerProprietaryNetBuySell', 0) for d in inst_data[:5]])
            
            dealer_score = 0
            if dealer_5d > 0:
                dealer_score = 20
                details['自營商'] = f'買超 (5D:{dealer_5d/10000:.0f}萬)'
            elif dealer_5d < 0:
                dealer_score = -20
                details['自營商'] = f'賣超 (5D:{dealer_5d/10000:.0f}萬)'
            else:
                dealer_score = 0
                details['自營商'] = '中性'
            
            score += dealer_score
        except:
            details['自營商'] = '資料不足'
        
        return {
            'score': score,
            'max_score': 100,
            'weight': 0.3,
            'details': details
        }
    
    def _calculate_margin_score(self, stock_id: str, date: str) -> Dict:
        """
        計算資券面分數 (30%權重)
        評估項目: 融資餘額變化、融券餘額變化、券資比
        """
        # 取得最近20天的融資券資料
        end_date = datetime.strptime(date, '%Y-%m-%d')
        start_date = end_date - timedelta(days=30)
        
        margin_data = list(self.db['margin_trading'].find({
            'symbol': stock_id,
            'date': {'$gte': start_date.strftime('%Y-%m-%d'), '$lte': date}
        }).sort('date', -1).limit(20))
        
        if not margin_data:
            return {'score': 0, 'details': '無資券資料'}
        
        score = 0
        details = {}
        
        try:
            # 最新資料
            latest = margin_data[0]
            margin_balance = latest.get('marginBalance', 0)
            short_balance = latest.get('shortBalance', 0)
            
            # 5天前資料
            if len(margin_data) >= 5:
                prev_5d = margin_data[4]
                margin_change_5d = margin_balance - prev_5d.get('marginBalance', 0)
                short_change_5d = short_balance - prev_5d.get('shortBalance', 0)
            else:
                margin_change_5d = 0
                short_change_5d = 0
            
            # 1. 融資餘額變化 (50分)
            margin_score = 0
            if margin_change_5d < 0:  # 融資減少是好訊號
                margin_score = 50
                details['融資'] = f'減少 {abs(margin_change_5d):.0f}張 ✅'
            elif margin_change_5d > margin_balance * 0.05:  # 增加超過5%是警訊
                margin_score = -30
                details['融資'] = f'增加 {margin_change_5d:.0f}張 ⚠️'
            elif margin_change_5d > 0:
                margin_score = -15
                details['融資'] = f'增加 {margin_change_5d:.0f}張'
            else:
                margin_score = 0
                details['融資'] = '持平'
            
            score += margin_score
            
            # 2. 融券餘額變化 (30分)
            short_score = 0
            if short_change_5d > 0:  # 融券增加是空方力量
                short_score = -30
                details['融券'] = f'增加 {short_change_5d:.0f}張 (空方) ⚠️'
            elif short_change_5d < 0:  # 融券減少(回補)是好訊號
                short_score = 30
                details['融券'] = f'減少 {abs(short_change_5d):.0f}張 (回補) ✅'
            else:
                short_score = 0
                details['融券'] = '持平'
            
            score += short_score
            
            # 3. 券資比 (20分)
            if margin_balance > 0:
                short_margin_ratio = (short_balance / margin_balance) * 100
                
                ratio_score = 0
                if short_margin_ratio > 20:
                    ratio_score = -20  # 高券資比是空方力量
                    details['券資比'] = f'{short_margin_ratio:.1f}% (偏高) ⚠️'
                elif short_margin_ratio > 10:
                    ratio_score = -10
                    details['券資比'] = f'{short_margin_ratio:.1f}%'
                elif short_margin_ratio < 5:
                    ratio_score = 20
                    details['券資比'] = f'{short_margin_ratio:.1f}% (健康) ✅'
                else:
                    ratio_score = 10
                    details['券資比'] = f'{short_margin_ratio:.1f}%'
                
                score += ratio_score
            else:
                details['券資比'] = '無融資'
            
        except Exception as e:
            details['錯誤'] = str(e)
        
        return {
            'score': score,
            'max_score': 100,
            'weight': 0.3,
            'details': details
        }
    
    def _get_grade(self, score: float) -> str:
        """評級"""
        if score >= 80:
            return 'A+'
        elif score >= 60:
            return 'A'
        elif score >= 40:
            return 'B'
        elif score >= 20:
            return 'C'
        elif score >= -20:
            return 'D'
        elif score >= -40:
            return 'E'
        else:
            return 'F'
    
    def _get_signal(self, score: float) -> str:
        """訊號"""
        if score >= 60:
            return '極多 🚀'
        elif score >= 30:
            return '偏多 📈'
        elif score >= -10:
            return '中性 ➡️'
        elif score >= -40:
            return '偏空 📉'
        else:
            return '極空 ⚠️'
    
    def batch_calculate(self, stock_ids: List[str], save_to_db: bool = True) -> List[Dict]:
        """批量計算多空指標"""
        results = []
        
        for stock_id in stock_ids:
            try:
                result = self.calculate_bull_bear_score(stock_id)
                results.append(result)
                
                if save_to_db:
                    self.db['bull_bear_indicators'].update_one(
                        {'stock_id': stock_id, 'date': result['date']},
                        {'$set': result},
                        upsert=True
                    )
                    
                print(f"✅ {stock_id}: {result['signal']} (分數: {result['total_score']:.1f})")
            except Exception as e:
                print(f"❌ {stock_id}: {str(e)}")
        
        return results


def main():
    """測試範例"""
    calculator = BullBearCalculator()
    
    # 測試股票
    test_stocks = ['2330', '2317', '2454', '2412', '2308']
    
    print("=" * 80)
    print("🎯 多空指標計算系統")
    print("=" * 80)
    
    for stock_id in test_stocks:
        print(f"\n📊 {stock_id}:")
        result = calculator.calculate_bull_bear_score(stock_id)
        
        print(f"   總分: {result['total_score']:.1f}")
        print(f"   等級: {result['grade']}")
        print(f"   訊號: {result['signal']}")
        
        print(f"\n   技術面 ({result['technical_score']['score']:.1f}/100):")
        if isinstance(result['technical_score']['details'], dict):
            for key, value in result['technical_score']['details'].items():
                print(f"      {key}: {value}")
        else:
            print(f"      {result['technical_score']['details']}")
        
        print(f"\n   籌碼面 ({result['institutional_score']['score']:.1f}/100):")
        if isinstance(result['institutional_score']['details'], dict):
            for key, value in result['institutional_score']['details'].items():
                print(f"      {key}: {value}")
        else:
            print(f"      {result['institutional_score']['details']}")
        
        print(f"\n   資券面 ({result['margin_score']['score']:.1f}/100):")
        if isinstance(result['margin_score']['details'], dict):
            for key, value in result['margin_score']['details'].items():
                print(f"      {key}: {value}")
        else:
            print(f"      {result['margin_score']['details']}")
        
        # 儲存到資料庫
        calculator.db['bull_bear_indicators'].update_one(
            {'stock_id': stock_id, 'date': result['date']},
            {'$set': result},
            upsert=True
        )
    
    print("\n" + "=" * 80)
    print("✅ 計算完成並已儲存至 bull_bear_indicators 集合")
    print("=" * 80)


if __name__ == '__main__':
    main()
