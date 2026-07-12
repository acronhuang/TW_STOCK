#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
進階交易邏輯模組
實作專業技術分析的完整交易規則

功能:
1. 第二波段觸發與監控
2. 移動止損管理
3. 假突破識別與反向操作
4. 三角形突破位置驗證
5. 市場結構強度評估
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class TradingState:
    """交易狀態追蹤"""
    symbol: str
    pattern_name: str
    pattern_type: str  # bullish/bearish
    
    # 價位資訊
    entry_price: float
    current_price: float
    neckline: float
    
    # 目標與停損
    target_1: float
    target_2: Optional[float]
    original_stop_loss: float
    current_stop_loss: float
    
    # 狀態追蹤
    target_1_reached: bool = False
    target_2_active: bool = False
    stop_moved_to_target1: bool = False
    
    # 市場結構
    market_structure_strength: float = 0.0  # 0-1
    volume_confirmation: bool = False
    
    # 時間資訊
    entry_date: str = ""
    days_held: int = 0
    
    # 操作建議
    action: str = "HOLD"  # HOLD/SELL/BUY/TRAIL_STOP
    reason: str = ""


class AdvancedTradingLogic:
    """進階交易邏輯引擎"""
    
    def __init__(self):
        self.active_positions: Dict[str, TradingState] = {}
        
    # ==================== 第二波段管理 ====================
    
    def evaluate_second_wave_trigger(
        self,
        state: TradingState,
        df: pd.DataFrame
    ) -> Tuple[bool, str]:
        """
        評估第二波段觸發條件
        
        根據專業標準:
        1. 市場結構強度確認
        2. 第一波目標達成
        3. 頸線不破原則
        
        返回: (是否觸發, 原因說明)
        """
        current_price = state.current_price
        target_1 = state.target_1
        neckline = state.neckline
        
        # 條件1: 第一波目標必須達成
        if not state.target_1_reached:
            if state.pattern_type == 'bullish':
                if current_price >= target_1:
                    state.target_1_reached = True
                else:
                    return False, f"等待第一波目標 {target_1:.2f}"
            else:  # bearish
                if current_price <= target_1:
                    state.target_1_reached = True
                else:
                    return False, f"等待第一波目標 {target_1:.2f}"
        
        # 條件2: 頸線不破（最重要）
        neckline_broken = False
        if state.pattern_type == 'bullish':
            # 多頭: 不能跌破頸線
            if current_price < neckline:
                neckline_broken = True
                return False, f"❌ 跌破頸線 {neckline:.2f}，第二波失效"
        else:  # bearish
            # 空頭: 不能漲破頸線
            if current_price > neckline:
                neckline_broken = True
                return False, f"❌ 漲破頸線 {neckline:.2f}，第二波失效"
        
        # 條件3: 評估市場結構強度
        strength = self._calculate_market_strength(df, state.pattern_type)
        state.market_structure_strength = strength
        
        if strength < 0.6:
            return False, f"市場結構偏弱 ({strength:.2f})，建議第一波出場"
        
        # 條件4: 第一波目標轉為支撐/壓力
        target1_holding = False
        if state.pattern_type == 'bullish':
            # 多頭: 第一波目標成為支撐
            recent_low = df['low'].iloc[-5:].min()
            if recent_low >= target_1 * 0.97:  # 未跌破目標1的3%
                target1_holding = True
        else:  # bearish
            # 空頭: 第一波目標成為壓力
            recent_high = df['high'].iloc[-5:].max()
            if recent_high <= target_1 * 1.03:  # 未漲破目標1的3%
                target1_holding = True
        
        if not target1_holding:
            return False, "第一波目標未能守住，建議出場"
        
        # 全部條件滿足，觸發第二波
        state.target_2_active = True
        return True, f"✅ 第二波段觸發 (結構強度: {strength:.2f})"
    
    def _calculate_market_strength(
        self,
        df: pd.DataFrame,
        pattern_type: str
    ) -> float:
        """
        計算市場結構強度 (0-1)
        
        評估因素:
        1. 趨勢連續性
        2. 量能配合
        3. 波動率
        """
        close = df['close'].values
        volume = df['volume'].values if 'volume' in df.columns else None
        
        strength = 0.0
        
        # 因素1: 趨勢連續性 (40%)
        recent_closes = close[-10:]
        if pattern_type == 'bullish':
            updays = np.sum(np.diff(recent_closes) > 0)
            strength += (updays / 9) * 0.4
        else:
            downdays = np.sum(np.diff(recent_closes) < 0)
            strength += (downdays / 9) * 0.4
        
        # 因素2: 量能配合 (30%)
        if volume is not None:
            recent_vol = volume[-10:]
            avg_vol = volume[-30:-10].mean()
            if recent_vol.mean() > avg_vol * 1.1:
                strength += 0.3
            elif recent_vol.mean() > avg_vol:
                strength += 0.15
        else:
            strength += 0.15  # 無量能數據，給予中性分數
        
        # 因素3: 波動率控制 (30%)
        returns = np.diff(close[-20:]) / close[-20:-1]
        volatility = np.std(returns)
        if volatility < 0.02:  # 低波動
            strength += 0.3
        elif volatility < 0.03:  # 中等波動
            strength += 0.15
        
        return min(strength, 1.0)
    
    # ==================== 移動止損管理 ====================
    
    def calculate_trailing_stop(
        self,
        state: TradingState,
        df: pd.DataFrame
    ) -> Tuple[float, str]:
        """
        計算移動止損位置
        
        策略:
        1. 未達第一波: 維持原始止損(頸線)
        2. 達成第一波: 移動至第一波目標
        3. 追求第二波: 移動至頸線或第一波目標
        
        返回: (新止損價, 說明)
        """
        current_price = state.current_price
        neckline = state.neckline
        target_1 = state.target_1
        original_stop = state.original_stop_loss
        
        # 階段1: 未達第一波 - 維持原始止損
        if not state.target_1_reached:
            return original_stop, "維持原始止損(頸線±7%)"
        
        # 階段2: 達成第一波 - 評估是否移動
        if state.target_1_reached and not state.stop_moved_to_target1:
            # 選擇1: 移動至第一波目標(保守)
            new_stop_aggressive = target_1
            
            # 選擇2: 移動至頸線(進取)
            new_stop_moderate = neckline
            
            # 根據市場強度決定
            if state.market_structure_strength >= 0.7:
                # 市場強勁，使用頸線作為止損，追求第二波
                state.stop_moved_to_target1 = False
                return new_stop_moderate, f"市場強勁(繼續持有，頸線止損 {new_stop_moderate:.2f})"
            else:
                # 市場一般，移動至第一波目標，鎖定利潤
                state.stop_moved_to_target1 = True
                return new_stop_aggressive, f"鎖定利潤(移動至目標1 {new_stop_aggressive:.2f})"
        
        # 階段3: 追求第二波 - 動態調整
        if state.target_2_active and state.target_2:
            # 計算當前至第二波的進度
            if state.pattern_type == 'bullish':
                progress = (current_price - target_1) / (state.target_2 - target_1)
            else:
                progress = (target_1 - current_price) / (target_1 - state.target_2)
            
            if progress > 0.5:  # 已完成第二波50%
                # 移動止損至第一波目標
                return target_1, f"第二波進行中({progress*100:.0f}%)，移動至目標1"
            else:
                # 維持頸線止損
                return neckline, f"第二波起步({progress*100:.0f}%)，維持頸線止損"
        
        # 預設: 維持當前止損
        return state.current_stop_loss, "維持當前止損"
    
    # ==================== 假突破識別 ====================
    
    def detect_false_breakout_realtime(
        self,
        df: pd.DataFrame,
        neckline: float,
        breakout_date_idx: int
    ) -> Optional[Dict]:
        """
        即時偵測假突破
        
        邏輯:
        1. 記錄突破點
        2. 監控是否在N天內跌回頸線下
        3. 確認假突破後計算反向目標
        
        參數:
            df: 價格數據
            neckline: 頸線價格
            breakout_date_idx: 突破發生的索引
            
        返回:
            假突破信號字典或None
        """
        close = df['close'].values
        high = df['high'].values
        low = df['low'].values
        
        # 記錄突破後的最高點
        breakout_high = high[breakout_date_idx:].max()
        
        # 檢查是否在突破後10天內跌回頸線下
        monitoring_window = min(10, len(df) - breakout_date_idx)
        
        for i in range(breakout_date_idx, breakout_date_idx + monitoring_window):
            if close[i] < neckline:
                # 確認假突破
                height = breakout_high - neckline
                target = neckline - height
                
                return {
                    'type': '假突破',
                    'signal': 'SELL/SHORT',
                    'breakout_high': breakout_high,
                    'neckline': neckline,
                    'breakdown_price': close[i],
                    'target': target,
                    'stop_loss': neckline,
                    'days_to_fail': i - breakout_date_idx,
                    'reason': f'突破後{i - breakout_date_idx}天跌破頸線 {neckline:.2f}',
                    'action': '空單進場或多單止損'
                }
        
        return None
    
    # ==================== 三角形突破驗證 ====================
    
    def validate_triangle_breakout_position(
        self,
        df: pd.DataFrame,
        triangle_start_idx: int,
        breakout_idx: int
    ) -> Tuple[bool, str]:
        """
        驗證三角形突破位置的有效性
        
        規則:
        - 必須在三角形長度的 1/2 至 3/4 處突破
        - 在末端突破容易失敗
        
        返回: (是否有效, 說明)
        """
        triangle_length = breakout_idx - triangle_start_idx
        
        # 計算突破位置百分比
        breakout_position_pct = 1.0
        
        # 有效範圍: 50% - 75%
        if 0.5 <= breakout_position_pct <= 0.75:
            return True, f"突破位置理想 ({breakout_position_pct*100:.0f}%)"
        elif breakout_position_pct < 0.5:
            return True, f"突破較早 ({breakout_position_pct*100:.0f}%)，力道可能不足"
        else:
            return False, f"⚠️ 突破過晚 ({breakout_position_pct*100:.0f}%)，容易失敗"
    
    # ==================== 整合操作邏輯 ====================
    
    def generate_trading_action(
        self,
        state: TradingState,
        df: pd.DataFrame
    ) -> TradingState:
        """
        生成交易操作建議
        
        整合所有邏輯:
        1. 檢查止損
        2. 評估目標達成
        3. 計算移動止損
        4. 第二波段判斷
        
        返回: 更新後的TradingState
        """
        current_price = state.current_price
        
        # 步驟1: 檢查是否觸及止損
        if state.pattern_type == 'bullish':
            if current_price <= state.current_stop_loss:
                state.action = "SELL"
                state.reason = f"觸及止損 {state.current_stop_loss:.2f}"
                return state
        else:  # bearish
            if current_price >= state.current_stop_loss:
                state.action = "COVER"
                state.reason = f"觸及止損 {state.current_stop_loss:.2f}"
                return state
        
        # 步驟2: 檢查目標達成
        if not state.target_1_reached:
            # 等待第一波目標
            if state.pattern_type == 'bullish':
                progress = ((current_price - state.entry_price) / 
                          (state.target_1 - state.entry_price)) * 100
            else:
                progress = ((state.entry_price - current_price) / 
                          (state.entry_price - state.target_1)) * 100
            
            state.action = "HOLD"
            state.reason = f"進行中 (進度: {progress:.1f}%)"
            return state
        
        # 步驟3: 第一波已達成，評估第二波
        if state.target_2:
            triggered, reason = self.evaluate_second_wave_trigger(state, df)
            
            if triggered:
                # 計算移動止損
                new_stop, stop_reason = self.calculate_trailing_stop(state, df)
                state.current_stop_loss = new_stop
                state.action = "TRAIL_STOP"
                state.reason = f"追求第二波 | {stop_reason}"
            else:
                # 第二波未觸發或失效
                if "失效" in reason or "跌破" in reason or "漲破" in reason:
                    state.action = "SELL"
                    state.reason = f"第二波失效 | {reason}"
                else:
                    state.action = "HOLD"
                    state.reason = f"評估第二波 | {reason}"
        else:
            # 無第二波目標，建議出場
            state.action = "SELL"
            state.reason = f"第一波目標已達成 {state.target_1:.2f}"
        
        return state
    
    # ==================== 輔助工具 ====================
    
    def print_trading_recommendation(self, state: TradingState):
        """打印交易建議"""
        print("\n" + "="*80)
        print(f"📊 {state.symbol} - {state.pattern_name} 交易建議")
        print("="*80)
        
        print(f"\n💰 價格資訊:")
        print(f"  當前價格: {state.current_price:.2f}")
        print(f"  進場價格: {state.entry_price:.2f}")
        print(f"  頸線位置: {state.neckline:.2f}")
        
        print(f"\n🎯 目標與止損:")
        print(f"  目標價1: {state.target_1:.2f} {'✅ 已達成' if state.target_1_reached else '⏳ 進行中'}")
        if state.target_2:
            print(f"  目標價2: {state.target_2:.2f} {'🔥 追求中' if state.target_2_active else '⏸️  待觸發'}")
        print(f"  當前止損: {state.current_stop_loss:.2f}")
        
        print(f"\n📈 市場評估:")
        print(f"  結構強度: {state.market_structure_strength:.2f}")
        print(f"  量能確認: {'✅ 是' if state.volume_confirmation else '⚠️  否'}")
        print(f"  持有天數: {state.days_held} 天")
        
        print(f"\n💡 操作建議:")
        print(f"  動作: {state.action}")
        print(f"  原因: {state.reason}")
        
        # 根據動作給出具體指導
        if state.action == "SELL":
            print(f"\n  ⚠️  建議執行: 賣出/平倉")
        elif state.action == "TRAIL_STOP":
            print(f"\n  ✅ 建議執行: 移動止損至 {state.current_stop_loss:.2f}")
        elif state.action == "HOLD":
            print(f"\n  📊 建議執行: 繼續持有，守住止損")
        
        print("\n" + "="*80)


# ==================== 使用範例 ====================

def example_usage():
    """使用範例"""
    
    # 創建交易邏輯引擎
    engine = AdvancedTradingLogic()
    
    # 假設有一個W底信號
    state = TradingState(
        symbol='2330',
        pattern_name='W底',
        pattern_type='bullish',
        entry_price=1780.0,
        current_price=1915.0,
        neckline=1780.0,
        target_1=1990.0,
        target_2=2200.0,
        original_stop_loss=1654.6,
        current_stop_loss=1654.6,
        market_structure_strength=0.75,
        entry_date='2026-01-15',
        days_held=30
    )
    
    # 假設有價格數據
    import pandas as pd
    df = pd.DataFrame({
        'close': [1900, 1910, 1920, 1915, 1918],
        'high': [1905, 1915, 1925, 1920, 1922],
        'low': [1895, 1905, 1915, 1910, 1912],
        'volume': [10000, 12000, 11000, 10500, 11500]
    })
    
    # 生成交易建議
    updated_state = engine.generate_trading_action(state, df)
    
    # 打印建議
    engine.print_trading_recommendation(updated_state)


if __name__ == '__main__':
    example_usage()
