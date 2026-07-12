#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
形態學12神招 - 技術型態辨識模組
根據專業技術分析報告建立的標準化型態識別系統

作者: 技術分析系統
日期: 2026-02-13
版本: 1.1.0
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


@dataclass
class PatternSignal:
    """型態信號數據類"""
    symbol: str  # 股票代碼 (新)
    pattern_name: str  # 型態名稱
    pattern_type: str  # 型態類型: bullish(多頭) / bearish(空頭)
    signal_type: str  # 信號類型: buy(買入) / sell(賣出)
    confidence: float  # 信號可信度 (0-1)
    
    # 關鍵價位
    current_price: float
    neckline: float  # 頸線
    entry_price: float  # 進場價
    stop_loss: float  # 停損價
    target_1: float  # 目標價1
    
    # 以下為有預設值的欄位
    target_2: Optional[float] = None  # 目標價2 (由強度評估決定)
    structure_score: int = 0  # 結構強度分數 (0-8)
    
    # 計算參數
    height: float = 0.0  # 型態高度
    potential_gain: float = 0.0  # 潛在獲利%
    risk_reward: float = 0.0  # 風險報酬比
    
    # 型態細節
    formation_days: int = 0  # 型態形成天數
    volume_confirmation: bool = False  # 量能確認
    detected_date: str = ""  # 檢測日期
    status: str = "forming"  # forming/confirmed/completed
    metadata: Dict = field(default_factory=dict) # 元數據 (新)


class Pattern12Masters:
    """形態學12神招辨識器"""
    
    def __init__(self):
        self.patterns = {
            'W底': self._detect_w_bottom,
            '破底翻': self._detect_false_breakdown,
            '破底翻W底': self._detect_false_breakdown_w,
            '下飄旗形': self._detect_falling_flag,
            '上飄旗形': self._detect_rising_flag,
            'M頭': self._detect_m_top,
            '假突破': self._detect_false_breakout,
            '頭肩頂': self._detect_head_shoulders_top,
            '假突破頭肩頂': self._detect_false_breakout_hst,
            '頭肩底': self._detect_head_shoulders_bottom,
            '收斂三角形頂': self._detect_triangle_top,
            '收斂三角形底': self._detect_triangle_bottom,
        }
        
    def scan_all_patterns(self, df: pd.DataFrame, symbol: str) -> List[PatternSignal]:
        """
        掃描所有12種型態
        
        參數:
            df: 包含OHLCV數據的DataFrame
            symbol: 股票代碼
            
        返回:
            List[PatternSignal]: 檢測到的型態信號列表
        """
        signals = []
        
        for pattern_name, detect_func in self.patterns.items():
            try:
                # detect_func 現在返回 List[PatternSignal]
                detected_signals, metadata = detect_func(df)
                if detected_signals:
                    # 使用 extend 將列表合併
                    for signal in detected_signals:
                        signal.symbol = symbol # 賦值 symbol
                        signal.metadata.update(metadata) # 將 metadata 附加到每個信號
                        logger.info(f"{symbol} 檢測到 {signal.pattern_name} 型態")
                        # 評估強度
                        if signal.pattern_type == 'bullish':
                            signal = self._assess_structure_strength(signal, df)
                    signals.extend(detected_signals)
            except Exception as e:
                logger.error(f"檢測 {pattern_name} 時發生錯誤: {e}")
                
        return signals
    
    # ==================== 多頭型態 ====================
    
    def _detect_w_bottom(self, df: pd.DataFrame) -> Tuple[List[PatternSignal], Dict]:
        """
        1. W底（雙底）檢測
        
        特徵:
        - 兩個低點價格接近（誤差<3%）
        - 中間有一個反彈形成頸線
        - 突破頸線確認型態
        
        計算公式:
        - 距離 = 頸線 - 底部
        - 目標1 = 突破點 + 距離
        - 目標2 = 目標1 + 距離
        """
        signals = []
        metadata = {}
        
        if len(df) < 60:
            return [], {}
            
        close = df['close'].values
        low = df['low'].values
        high = df['high'].values
        
        # 尋找最近60天內的雙底結構
        for i in range(len(df) - 60, 20, -1):
            # 檢查是否有兩個低點
            window = 20
            if i < window:
                continue
                
            # 找第一個低點
            bottom1_idx = i - window + np.argmin(low[i-window:i])
            bottom1 = low[bottom1_idx]
            
            # 找中間反彈高點（頸線）
            neckline_idx = bottom1_idx + np.argmax(high[bottom1_idx:i])
            neckline = high[neckline_idx]
            
            # 找第二個低點
            bottom2_idx = neckline_idx + np.argmin(low[neckline_idx:i+10])
            bottom2 = low[bottom2_idx]
            
            # 檢查雙底條件
            if bottom1 == 0 or abs(bottom1 - bottom2) / bottom1 > 0.03:  # 兩底誤差>3%
                continue
                
            if neckline < (bottom1 + bottom2) / 2 * 1.02:  # 頸線不夠高
                continue
                
            # 檢查是否突破頸線
            current_price = close[-1]
            breakout_idx = -1
            if current_price > neckline:
                # 尋找突破點
                breakout_candidates = np.where(close[neckline_idx:] > neckline)[0]
                if len(breakout_candidates) > 0:
                    breakout_idx = neckline_idx + breakout_candidates[0]

            if current_price < neckline * 0.98:
                continue
                
            # 計算目標價
            avg_bottom = (bottom1 + bottom2) / 2
            height = neckline - avg_bottom
            entry = neckline
            target1 = entry + height
            target2 = target1 + height
            stop_loss = entry * 0.93  # 7%停損
            
            potential_gain = ((target1 - current_price) / current_price) * 100
            risk = ((current_price - stop_loss) / current_price) * 100
            risk_reward = potential_gain / risk if risk > 0 else 0
            
            metadata = {
                'pivots': [bottom1_idx, neckline_idx, bottom2_idx],
                'breakout_date': df.iloc[breakout_idx]['date'].strftime('%Y-%m-%d') if breakout_idx != -1 else None,
                'breakout_price': close[breakout_idx] if breakout_idx != -1 else None,
                'neckline': neckline,
                'stop_loss': stop_loss
            }

            # 建立信號
            signal = PatternSignal(
                symbol="", # 將由 scan_all_patterns 填寫
                pattern_name='W底',
                pattern_type='bullish',
                signal_type='buy',
                confidence=0.85,
                current_price=current_price,
                neckline=neckline,
                entry_price=entry,
                stop_loss=stop_loss,
                target_1=target1,
                target_2=target2,
                height=height,
                potential_gain=potential_gain,
                risk_reward=risk_reward,
                formation_days=i - bottom1_idx,
                detected_date=datetime.now().strftime('%Y-%m-%d'),
                status='confirmed' if current_price > neckline else 'forming'
            )
            
            signals.append(signal)
            
            # 只取最新的有效信號
            if signals:
                return [signals[-1]], metadata
                
        return [], {}
    
    def _detect_false_breakdown(self, df: pd.DataFrame) -> Tuple[List[PatternSignal], Dict]:
        """
        2. 破底翻檢測（Broken Bottom Reversal）- 專業版
        
        演算法邏輯（四階段）:
        
        階段1: 盤整區間建立 (Consolidation Phase)
        - 下緣支撐線: 識別反覆測試的底部
        - 上緣頸線: 識別盤整區高點連線
        
        階段2: 破底訊號偵測 (False Breakdown)
        - 條件: 收盤價 < 下緣支撐
        - 意義: 主力「甩轎」動作，清洗浮額
        
        階段3: 翻升站回確認 (Reclaiming Support) ★核心★
        - 關鍵: 跌破後迅速收復失土
        - 條件: 當前收盤價 > 下緣支撐 且 前幾根 < 下緣支撐
        - 意義: 難得的多頭止穩買進訊號
        
        階段4: 突破上緣與進場 (Breakout & Entry)
        - 買進點: 突破上緣頸線
        - 條件: 後續不應拉回跌破頸線
        
        計算公式:
        - 等幅距離 D = 領線價格 - 底部最低點
        - 目標價1 = 突破點 + D（第一波滿足）
        - 目標價2 = 突破點 + 2D（第二波滿足）
        - 止損 = 領線位置或前一低點
        - 續抱條件 = 領線不破
        """
        if len(df) < 60:
            return [], {}
            
        close = df['close'].values
        low = df['low'].values
        high = df['high'].values
        volume = df['volume'].values if 'volume' in df.columns else None
        
        # ==================== 階段1: 盤整區間建立 ====================
        # 回溯視窗: 尋找40-60天的盤整期
        for lookback_start in range(len(df) - 60, len(df) - 30):
            if lookback_start < 0:
                continue
            
            consolidation_window = 30  # 盤整區間觀察期
            consolidation_end = min(lookback_start + consolidation_window, len(df) - 10)
            
            if consolidation_end >= len(df):
                continue
            
            # 計算盤整區間
            consolidation_lows = low[lookback_start:consolidation_end]
            consolidation_highs = high[lookback_start:consolidation_end]
            consolidation_closes = close[lookback_start:consolidation_end]
            
            # 下緣支撐線: 取10-20百分位的低點（反覆測試的底部）
            support_line = np.percentile(consolidation_lows, 15)
            
            # 上緣頸線: 取80-90百分位的高點（盤整區高點連線）
            resistance_line = np.percentile(consolidation_highs, 85)
            
            # 檢查是否為有效盤整區
            consolidation_range = resistance_line - support_line
            mid_price = (resistance_line + support_line) / 2
            
            # 盤整區寬度應在5-20%之間
            range_pct = (consolidation_range / (mid_price + 1e-9)) * 100
            if range_pct < 5 or range_pct > 20:
                continue
            
            # 確認多數時間在盤整區內
            in_range_count = np.sum(
                (consolidation_closes >= support_line * 0.98) & 
                (consolidation_closes <= resistance_line * 1.02)
            )
            if in_range_count / len(consolidation_closes) < 0.7:
                continue
            
            # ==================== 階段2: 破底訊號偵測 ====================
            # 檢查盤整結束後是否出現破底
            breakdown_window_start = consolidation_end
            breakdown_window_end = min(breakdown_window_start + 15, len(df))
            
            breakdown_idx = None
            breakdown_low = None
            
            for i in range(breakdown_window_start, breakdown_window_end):
                # 條件: 收盤價跌破下緣支撐
                if close[i] < support_line * 0.97:  # 跌破3%確認破底
                    breakdown_idx = i
                    breakdown_low = low[i]
                    break
            
            if breakdown_idx is None:
                continue
            
            # 記錄底部最低點（可能在破底當天或前後）
            bottom_low = low[max(0, breakdown_idx-3):min(len(df), breakdown_idx+4)].min()
            
            # ==================== 階段3: 翻升站回確認（核心） ====================
            # 關鍵: 跌破後迅速收復失土，重新站回支撐線之上
            
            reclaim_idx = None
            reclaim_confirmed = False
            
            # 在破底後5-10根K線內尋找站回訊號
            reclaim_search_start = breakdown_idx + 1
            reclaim_search_end = min(breakdown_idx + 10, len(df) - 1)
            
            for i in range(reclaim_search_start, reclaim_search_end):
                # 核心條件: 當前收盤價 > 支撐線 且 前一根 < 支撐線
                if close[i] > support_line and close[i-1] < support_line:
                    reclaim_idx = i
                    reclaim_confirmed = True
                    break
            
            if not reclaim_confirmed:
                continue
            
            # 確認站回後持穩: 後續幾根K線應維持在支撐線之上
            stability_check_end = min(reclaim_idx + 5, len(df))
            stability_count = 0
            
            for i in range(reclaim_idx, stability_check_end):
                if close[i] > support_line:
                    stability_count += 1
            
            # 至少要有70%的時間維持在支撐線之上
            if (stability_check_end - reclaim_idx > 0) and (stability_count / (stability_check_end - reclaim_idx)) < 0.7:
                continue
            
            # ==================== 階段4: 突破上緣與進場邏輯 ====================
            # 檢查是否已突破上緣頸線（或接近突破）
            
            current_price = close[-1]
            
            # 三種進場時機:
            # 1. 已突破頸線
            # 2. 站回支撐且接近頸線（預期突破）
            # 3. 站回後整理中，等待突破
            
            breakout_confirmed = current_price > resistance_line
            approaching_breakout = (current_price > resistance_line * 0.95) and (current_price > support_line)
            
            breakout_idx = -1
            if breakout_confirmed:
                # 尋找突破點
                breakout_candidates = np.where(close[reclaim_idx:] > resistance_line)[0]
                if len(breakout_candidates) > 0:
                    breakout_idx = reclaim_idx + breakout_candidates[0]

            if not (breakout_confirmed or approaching_breakout):
                continue
            
            # ==================== 計算目標價與止損 ====================
            
            # 等幅距離 D = 領線 - 底部最低點
            equal_distance = resistance_line - bottom_low
            
            # 進場價格
            if breakout_confirmed:
                entry_price = resistance_line  # 突破頸線價
            else:
                entry_price = current_price  # 當前價格（預期突破）
            
            # 目標價計算
            # 目標1 = 突破點 + D（第一波滿足）
            target_1 = resistance_line + equal_distance
            
            # 目標2 = 突破點 + 2D（第二波滿足）
            target_2 = resistance_line + (equal_distance * 2)
            
            # 止損設定: 領線（支撐線）或前一低點
            # 原則: 止損設在支撐線下方2-3%
            stop_loss_option_1 = support_line * 0.97  # 領線下方3%
            stop_loss_option_2 = bottom_low * 0.98    # 前低下方2%
            stop_loss = max(stop_loss_option_1, stop_loss_option_2)  # 取較高者（較緊）
            
            # ==================== 量能確認 ====================
            volume_confirmed = False
            if volume is not None and reclaim_idx is not None:
                # 檢查站回時的量能
                reclaim_volume = volume[reclaim_idx]
                avg_volume = np.mean(volume[max(0, reclaim_idx-20):reclaim_idx])
                
                # 站回時量能應放大（至少1.2倍）
                if reclaim_volume > avg_volume * 1.2:
                    volume_confirmed = True
            
            # ==================== 信心度評估 ====================
            confidence = 0.75  # 基礎信心度
            
            # 加分項目:
            if breakout_confirmed:
                confidence += 0.05  # 已突破頸線
            
            if volume_confirmed:
                confidence += 0.05  # 量能確認
            
            if (current_price - support_line) / support_line > 0.05:
                confidence += 0.03  # 站穩程度高
            
            if range_pct >= 8 and range_pct <= 15:
                confidence += 0.02  # 盤整區間適中
            
            confidence = min(confidence, 0.90)  # 上限90%
            
            # ==================== 計算績效指標 ====================
            potential_gain = ((target_1 - current_price) / current_price) * 100
            risk = ((current_price - stop_loss) / current_price) * 100
            risk_reward = potential_gain / risk if risk > 0 else 0
            
            formation_days = breakdown_idx - lookback_start
            
            # ==================== 回傳信號 ====================
            metadata = {
                'pivots': {
                    'consolidation_start': lookback_start,
                    'consolidation_end': consolidation_end,
                    'breakdown': breakdown_idx,
                    'reclaim': reclaim_idx,
                    'breakout': breakout_idx if breakout_idx != -1 else None,
                },
                'breakout_date': df.iloc[breakout_idx]['date'].strftime('%Y-%m-%d') if breakout_idx != -1 else None,
                'breakout_price': close[breakout_idx] if breakout_idx != -1 else None,
                'support_line': support_line,
                'resistance_line': resistance_line,
                'stop_loss': stop_loss,
                'bottom_low': bottom_low,
            }

            return [PatternSignal(
                symbol="", # 將由 scan_all_patterns 填寫
                pattern_name='破底翻',
                pattern_type='bullish',
                signal_type='buy',
                confidence=0.85,
                current_price=current_price,
                neckline=support_line,  # 領線 = 支撐線（續抱條件: 領線不破）
                entry_price=entry_price,
                stop_loss=stop_loss,
                target_1=target_1,
                target_2=target_2,
                height=equal_distance,
                potential_gain=potential_gain,
                risk_reward=risk_reward,
                formation_days=formation_days,
                volume_confirmation=volume_confirmed,
                detected_date=datetime.now().strftime('%Y-%m-%d'),
                status='confirmed' if breakout_confirmed else 'forming'
            )], metadata
        
        return [], {}
    
    def _detect_false_breakdown_w(self, df: pd.DataFrame) -> Tuple[List[PatternSignal], Dict]:
        """
        3. 破底翻（W底）檢測 - 專業版
        
        特徵:
        - W底形態 + 破底翻結構的組合
        - 第二隻腳出現破底後拉回
        - 突破頸線時作為加碼訊號
        
        邏輯:
        1. 先檢測標準W底結構
        2. 確認第二底有破第一底的動作（破底）
        3. 快速拉回站穩（翻）
        4. 突破頸線時進場
        
        優勢:
        - 比單純W底更安全（經過破底洗盤）
        - 比單純破底翻更有結構（雙底支撐）
        - 適合作為底部佈局的確認信號
        """
        signals = []
        metadata = {}
        if len(df) < 60:
            return [], {}
            
        close = df['close'].values
        low = df['low'].values
        high = df['high'].values
        volume = df['volume'].values if 'volume' in df.columns else None
        
        # ==================== 第一步: 尋找W底結構 ====================
        for lookback_start in range(len(df) - 60, len(df) - 20):
            if lookback_start < 20:
                continue
            
            window = 40
            segment = low[lookback_start:lookback_start + window]
            
            if len(segment) < 30:
                continue
            
            # 尋找兩個低點
            # 第一底: 在前半段
            first_half = segment[:len(segment)//2]
            first_bottom_idx = np.argmin(first_half)
            first_bottom = first_half[first_bottom_idx]
            
            # 第二底: 在後半段
            second_half = segment[len(segment)//2:]
            second_bottom_idx = len(segment)//2 + np.argmin(second_half)
            second_bottom = second_half[np.argmin(second_half)]
            
            # 兩底應在相近位置（誤差5%內）
            if first_bottom == 0 or abs(first_bottom - second_bottom) / first_bottom > 0.05:
                continue
            
            # 中間峰（頸線）
            middle_segment = segment[first_bottom_idx:second_bottom_idx]
            if len(middle_segment) == 0:
                continue
            
            # 對應的高點數據
            high_segment = high[lookback_start:lookback_start + window]
            middle_high = high_segment[first_bottom_idx:second_bottom_idx].max()
            
            neckline = middle_high
            
            # ==================== 第二步: 確認第二底有破底動作 ====================
            # 關鍵: 第二底應該「稍微」跌破第一底
            
            # 破底條件: 第二底比第一底低2-5%
            breakdown_pct = ((first_bottom - second_bottom) / (first_bottom + 1e-9)) * 100
            
            if breakdown_pct < 1 or breakdown_pct > 5:
                # 沒有破底（或破太多）
                continue
            
            # ==================== 第三步: 確認快速拉回站穩 ====================
            # 檢查第二底之後是否快速拉回到第一底水平之上
            
            second_bottom_abs_idx = lookback_start + second_bottom_idx
            
            reclaim_confirmed = False
            reclaim_idx = None
            
            # 在第二底後5-10根K線內尋找站回
            for i in range(second_bottom_abs_idx + 1, min(second_bottom_abs_idx + 10, len(df))):
                if close[i] > first_bottom * 1.02:  # 站回第一底水平之上
                    reclaim_confirmed = True
                    reclaim_idx = i
                    break
            
            if not reclaim_confirmed:
                continue
            
            # ==================== 第四步: 檢查是否突破頸線 ====================
            current_price = close[-1]
            
            # 突破確認或接近突破
            breakout_confirmed = current_price > neckline
            approaching_breakout = current_price > neckline * 0.95
            
            breakout_idx = -1
            if breakout_confirmed:
                # 尋找突破點
                breakout_candidates = np.where(close[reclaim_idx:] > neckline)[0]
                if len(breakout_candidates) > 0:
                    breakout_idx = reclaim_idx + breakout_candidates[0]

            if not (breakout_confirmed or approaching_breakout):
                continue
            
            # ==================== 計算目標價與止損 ====================
            
            # W底的等幅距離 = 領線 - 底部（取較低的底）
            bottom_low = min(first_bottom, second_bottom)
            equal_distance = neckline - bottom_low
            
            # 目標價計算
            target_1 = neckline + equal_distance
            target_2 = neckline + (equal_distance * 2)
            
            # 進場價
            entry_price = neckline if breakout_confirmed else current_price
            
            # 止損: 第二底下方2-3%
            stop_loss = second_bottom * 0.97
            
            # ==================== 量能確認 ====================
            volume_confirmed = False
            if volume is not None:
                # 檢查突破時的量能
                if breakout_confirmed:
                    recent_volume = volume[-5:].mean()
                    avg_volume = volume[max(0, len(volume)-30):-5].mean()
                    if recent_volume > avg_volume * 1.3:
                        volume_confirmed = True
            
            # ==================== 信心度評估 ====================
            confidence = 0.82  # 基礎信心度（比單純W底或破底翻高）
            
            # 加分項目:
            if breakout_confirmed:
                confidence += 0.05
            
            if volume_confirmed:
                confidence += 0.05
            
            if breakdown_pct >= 2 and breakdown_pct <= 4:
                confidence += 0.03  # 破底幅度適中
            
            confidence = min(confidence, 0.92)
            
            # ==================== 計算績效指標 ====================
            potential_gain = ((target_1 - current_price) / current_price) * 100
            risk = ((current_price - stop_loss) / current_price) * 100
            risk_reward = potential_gain / risk if risk > 0 else 0
            
            formation_days = second_bottom_abs_idx - (lookback_start + first_bottom_idx)
            
            metadata = {
                'pivots': {
                    'first_bottom': lookback_start + first_bottom_idx,
                    'neckline': lookback_start + first_bottom_idx + np.argmax(high_segment[first_bottom_idx:second_bottom_idx]),
                    'second_bottom': second_bottom_abs_idx,
                    'reclaim': reclaim_idx,
                    'breakout': breakout_idx if breakout_idx != -1 else None,
                },
                'breakout_date': df.iloc[breakout_idx]['date'].strftime('%Y-%m-%d') if breakout_idx != -1 else None,
                'breakout_price': close[breakout_idx] if breakout_idx != -1 else None,
                'neckline_price': neckline,
                'stop_loss': stop_loss,
                'first_bottom_price': first_bottom,
                'second_bottom_price': second_bottom,
            }

            return [PatternSignal(
                symbol="", # 將由 scan_all_patterns 填寫
                pattern_name='破底翻W底',
                pattern_type='bullish',
                signal_type='buy',
                confidence=0.85,
                current_price=current_price,
                neckline=neckline,
                entry_price=entry_price,
                stop_loss=stop_loss,
                target_1=target_1,
                target_2=target_2,
                height=equal_distance,
                potential_gain=potential_gain,
                risk_reward=risk_reward,
                formation_days=formation_days,
                volume_confirmation=volume_confirmed,
                detected_date=datetime.now().strftime('%Y-%m-%d'),
                status='confirmed' if breakout_confirmed else 'forming'
            )], metadata
        
        return [], {}
    
    def _detect_falling_flag(self, df: pd.DataFrame) -> Tuple[List[PatternSignal], Dict]:
        """
        4. 下飄旗形（多頭中繼）檢測
        
        特徵:
        - 上漲後向下整理
        - 形成旗形通道
        - 突破上緣頸線為買進信號
        
        計算:
        - 第一波漲幅 = 前高 - 前低
        - 目標 = 突破點 + 第一波漲幅
        """
        if len(df) < 50:
            return [], {}
            
        close = df['close'].values
        high = df['high'].values
        low = df['low'].values
        
        # 檢查是否有明顯上漲波段
        lookback = 40
        prev_low = low[-lookback:-20].min()
        prev_high = high[-lookback:-20].max()
        first_wave = prev_high - prev_low
        
        if prev_low == 0 or first_wave / prev_low < 0.15:  # 第一波漲幅需>15%
            return [], {}
            
        # 檢查是否形成下飄旗形（整理區）
        consolidation_high = high[-20:].max()
        consolidation_low = low[-20:].min()
        consolidation_range = consolidation_high - consolidation_low
        
        # 旗形特徵：整理區幅度較小
        if consolidation_high == 0 or consolidation_range / consolidation_high > 0.10:  # 整理幅度不超過10%
            return [], {}
            
        # 檢查整理區是否向下傾斜
        recent_highs = []
        for i in range(len(df) - 20, len(df), 5):
            recent_highs.append(high[i:i+5].max())
            
        if len(recent_highs) >= 3:
            if recent_highs[-1] > recent_highs[0]:  # 不是向下
                return [], {}
                
        # 檢查是否突破上緣
        current_price = close[-1]
        upper_line = consolidation_high
        
        breakout_idx = -1
        if current_price > upper_line:
            # 尋找突破點
            breakout_candidates = np.where(close[-20:] > upper_line)[0]
            if len(breakout_candidates) > 0:
                breakout_idx = len(df) - 20 + breakout_candidates[0]

        if current_price < upper_line * 0.98:
            return [], {}
            
        # 計算目標價
        entry = upper_line
        target1 = entry + first_wave
        stop_loss = entry * 0.93
        
        potential_gain = ((target1 - current_price) / current_price) * 100
        risk = ((current_price - stop_loss) / current_price) * 100
        
        # 取得旗形通道的點位
        flag_highs_idx = len(df) - 20 + np.where(high[-20:] == consolidation_high)[0]
        flag_lows_idx = len(df) - 20 + np.where(low[-20:] == consolidation_low)[0]

        metadata = {
            'pivots': {
                'pole_start': len(df) - lookback + np.argmin(low[-lookback:-20]),
                'pole_end': len(df) - lookback + np.argmax(high[-lookback:-20]),
                'flag_high': flag_highs_idx[0] if len(flag_highs_idx) > 0 else None,
                'flag_low': flag_lows_idx[0] if len(flag_lows_idx) > 0 else None,
                'breakout': breakout_idx if breakout_idx != -1 else None,
            },
            'breakout_date': df.iloc[breakout_idx]['date'].strftime('%Y-%m-%d') if breakout_idx != -1 else None,
            'breakout_price': close[breakout_idx] if breakout_idx != -1 else None,
            'upper_line': upper_line,
            'stop_loss': stop_loss,
        }

        return [PatternSignal(
            symbol="", # 將由 scan_all_patterns 填寫
            pattern_name='下飄旗形',
            pattern_type='bullish',
            signal_type='buy',
            confidence=0.82,
            current_price=current_price,
            neckline=upper_line,
            entry_price=entry,
            stop_loss=stop_loss,
            target_1=target1,
            height=first_wave,
            potential_gain=potential_gain,
            risk_reward=potential_gain / risk if risk > 0 else 0,
            formation_days=20,
            detected_date=datetime.now().strftime('%Y-%m-%d'),
            status='confirmed'
        )], metadata
    
    def _detect_rising_flag(self, df: pd.DataFrame) -> Tuple[List[PatternSignal], Dict]:
        """
        5. 上飄旗形（空頭中繼）檢測
        
        特徵:
        - 下跌後向上整理
        - 形成旗形通道
        - 跌破下緣頸線為賣出信號
        
        計算:
        - 第一波跌幅 = 前高 - 前低
        - 目標 = 跌破點 - 第一波跌幅
        """
        if len(df) < 50:
            return [], {}
            
        close = df['close'].values
        high = df['high'].values
        low = df['low'].values
        
        # 檢查是否有明顯下跌波段
        lookback = 40
        prev_high = high[-lookback:-20].max()
        prev_low = low[-lookback:-20].min()
        first_wave = prev_high - prev_low
        
        if prev_high == 0 or first_wave / prev_high < 0.15:  # 第一波跌幅需>15%
            return [], {}
            
        # 檢查是否形成上飄旗形（整理區）
        consolidation_high = high[-20:].max()
        consolidation_low = low[-20:].min()
        consolidation_range = consolidation_high - consolidation_low
        
        # 旗形特徵：整理區幅度較小
        if consolidation_low == 0 or consolidation_range / consolidation_low > 0.10:  # 整理幅度不超過10%
            return [], {}
            
        # 檢查整理區是否向上傾斜
        recent_lows = []
        for i in range(len(df) - 20, len(df), 5):
            recent_lows.append(low[i:i+5].min())
            
        if len(recent_lows) >= 3:
            if recent_lows[-1] < recent_lows[0]:  # 不是向上
                return [], {}
                
        # 檢查是否跌破下緣
        current_price = close[-1]
        lower_line = consolidation_low
        
        breakout_idx = -1
        if current_price < lower_line:
            # 尋找跌破點
            breakout_candidates = np.where(close[-20:] < lower_line)[0]
            if len(breakout_candidates) > 0:
                breakout_idx = len(df) - 20 + breakout_candidates[0]

        if current_price > lower_line * 1.02:
            return [], {}
            
        # 計算目標價
        entry = lower_line
        target1 = entry - first_wave
        stop_loss = entry * 1.07
        
        potential_loss_avoid = ((current_price - target1) / (current_price + 1e-9)) * 100
        risk = ((stop_loss - current_price) / (current_price + 1e-9)) * 100
        
        # 取得旗形通道的點位
        flag_highs_idx = len(df) - 20 + np.where(high[-20:] == consolidation_high)[0]
        flag_lows_idx = len(df) - 20 + np.where(low[-20:] == consolidation_low)[0]

        metadata = {
            'pivots': {
                'pole_start': len(df) - lookback + np.argmax(high[-lookback:-20]),
                'pole_end': len(df) - lookback + np.argmin(low[-lookback:-20]),
                'flag_high': flag_highs_idx[0] if len(flag_highs_idx) > 0 else None,
                'flag_low': flag_lows_idx[0] if len(flag_lows_idx) > 0 else None,
                'breakout': breakout_idx if breakout_idx != -1 else None,
            },
            'breakout_date': df.iloc[breakout_idx]['date'].strftime('%Y-%m-%d') if breakout_idx != -1 else None,
            'breakout_price': close[breakout_idx] if breakout_idx != -1 else None,
            'lower_line': lower_line,
            'stop_loss': stop_loss,
        }

        return [PatternSignal(
            symbol="", # 將由 scan_all_patterns 填寫
            pattern_name='上飄旗形',
            pattern_type='bearish',
            signal_type='sell',
            confidence=0.82,
            current_price=current_price,
            neckline=lower_line,
            entry_price=entry,
            stop_loss=stop_loss,
            target_1=target1,
            height=first_wave,
            potential_gain=potential_loss_avoid,
            risk_reward=potential_loss_avoid / risk if risk > 0 else 0,
            formation_days=20,
            detected_date=datetime.now().strftime('%Y-%m-%d'),
            status='confirmed'
        )], metadata

    # ==================== 空頭型態 ====================

    def _detect_m_top(self, df: pd.DataFrame) -> Tuple[List[PatternSignal], Dict]:
        """
        6. M頭（雙頂）檢測
        
        特徵:
        - 兩個高點價格接近（誤差<3%）
        - 中間有一個回檔形成頸線
        - 跌破頸線確認型態
        
        計算公式:
        - 距離 = 頂部 - 頸線
        - 目標1 = 跌破點 - 距離
        - 目標2 = 目標1 - 距離
        """
        signals = []
        metadata = {}
        if len(df) < 60:
            return [], {}
            
        close = df['close'].values
        low = df['low'].values
        high = df['high'].values
        
        # 尋找最近60天內的雙頂結構
        for i in range(len(df) - 40, len(df) - 10):
            # 檢查是否有兩個高點
            window = 20
            if i < window:
                continue
                
            # 找第一個高點
            top1_idx = i - window + np.argmax(high[i-window:i])
            top1 = high[top1_idx]
            
            # 找中間回檔低點（頸線）
            neckline_idx = top1_idx + np.argmin(low[top1_idx:i])
            neckline = low[neckline_idx]
            
            # 找第二個高點
            top2_idx = neckline_idx + np.argmax(high[neckline_idx:i+10])
            top2 = high[top2_idx]
            
            # 檢查雙頂條件
            if top1 == 0 or abs(top1 - top2) / top1 > 0.03:  # 兩頂誤差>3%
                continue
                
            if neckline > (top1 + top2) / 2 * 0.98:  # 頸線不夠低
                continue
                
            # 檢查是否跌破頸線
            current_price = close[-1]
            breakout_idx = -1
            if current_price < neckline:
                # 尋找跌破點
                breakout_candidates = np.where(close[neckline_idx:] < neckline)[0]
                if len(breakout_candidates) > 0:
                    breakout_idx = neckline_idx + breakout_candidates[0]

            if current_price > neckline * 1.02:
                continue
                
            # 計算目標價
            avg_top = (top1 + top2) / 2
            height = avg_top - neckline
            if height <= 0: continue
            entry = neckline
            target1 = entry - height
            target2 = target1 - height
            stop_loss = entry * 1.07  # 7%停損
            
            potential_loss_avoid = ((current_price - target1) / (current_price + 1e-9)) * 100
            risk = ((stop_loss - current_price) / (current_price + 1e-9)) * 100
            
            metadata = {
                'pivots': {
                    'top1': top1_idx,
                    'neckline': neckline_idx,
                    'top2': top2_idx,
                    'breakout': breakout_idx if breakout_idx != -1 else None,
                },
                'breakout_date': df.iloc[breakout_idx]['date'].strftime('%Y-%m-%d') if breakout_idx != -1 else None,
                'breakout_price': close[breakout_idx] if breakout_idx != -1 else None,
                'neckline_price': neckline,
                'stop_loss': stop_loss,
            }

            # 建立信號
            signal = PatternSignal(
                symbol="", # 將由 scan_all_patterns 填寫
                pattern_name='M頭',
                pattern_type='bearish',
                signal_type='sell',
                confidence=0.85,
                current_price=current_price,
                neckline=neckline,
                entry_price=entry,
                stop_loss=stop_loss,
                target_1=target1,
                target_2=target2,
                height=height,
                potential_gain=potential_loss_avoid,
                risk_reward=potential_loss_avoid / risk if risk > 0 else 0,
                formation_days=i - top1_idx,
                detected_date=datetime.now().strftime('%Y-%m-%d'),
                status='confirmed' if current_price < neckline else 'forming'
            )
            signals.append(signal)

        return signals, metadata
    
    def _detect_false_breakout(self, df: pd.DataFrame) -> Tuple[List[PatternSignal], Dict]:
        """
        7. 假突破（Bull Trap）檢測
        
        特徵:
        - 突破前高後快速拉回
        - 跌破頸線（前高）確認
        
        計算:
        - 目標 = 領線 - (突破高點 - 領線)
        """
        signals = []
        metadata = {}
        if len(df) < 40:
            return [], {}
            
        close = df['close'].values
        high = df['high'].values
        low = df['low'].values
        
        # 找前高
        prev_high_idx = len(df) - 40 + np.argmax(high[-40:-10])
        prev_high = high[prev_high_idx]
        
        # 檢查是否有突破
        breakout_high_idx = len(df) - 10 + np.argmax(high[-10:])
        breakout_high = high[breakout_high_idx]

        if breakout_high < prev_high:
            return [], {}
            
        # 檢查是否拉回
        current_price = close[-1]
        if current_price > prev_high:
            return [], {}
            
        # 尋找跌破點
        breakdown_idx = -1
        breakdown_candidates = np.where(close[breakout_high_idx:] < prev_high)[0]
        if len(breakdown_candidates) > 0:
            breakdown_idx = breakout_high_idx + breakdown_candidates[0]

        # 計算目標價
        neckline = prev_high
        height = breakout_high - neckline
        target1 = neckline - height
        stop_loss = breakout_high
        
        potential_loss_avoid = ((current_price - target1) / (current_price + 1e-9)) * 100
        risk = ((stop_loss - current_price) / (current_price + 1e-9)) * 100
        
        metadata = {
            'pivots': {
                'prev_high': prev_high_idx,
                'breakout_high': breakout_high_idx,
                'breakdown': breakdown_idx if breakdown_idx != -1 else None,
            },
            'breakout_date': df.iloc[breakdown_idx]['date'].strftime('%Y-%m-%d') if breakdown_idx != -1 else None,
            'breakout_price': close[breakdown_idx] if breakdown_idx != -1 else None,
            'neckline_price': neckline,
            'stop_loss': stop_loss,
        }

        return [PatternSignal(
            symbol="", # 將由 scan_all_patterns 填寫
            pattern_name='假突破',
            pattern_type='bearish',
            signal_type='sell',
            confidence=0.80,
            current_price=current_price,
            neckline=neckline,
            entry_price=neckline,
            stop_loss=stop_loss,
            target_1=target1,
            height=height,
            potential_gain=potential_loss_avoid,
            risk_reward=potential_loss_avoid / risk if risk > 0 else 0,
            formation_days=10,
            detected_date=datetime.now().strftime('%Y-%m-%d'),
            status='confirmed'
        )], metadata

    def _detect_head_shoulders_top(self, df: pd.DataFrame) -> Tuple[List[PatternSignal], Dict]:
        """
        8. 頭肩頂檢測
        
        特徵:
        - 左肩、頭部、右肩形成
        - 頭部最高、兩肩較低
        - 跌破頸線確認
        
        計算:
        - 距離 = 頭部 - 頸線
        - 目標1 = 跌破點 - 距離
        - 目標2 = 目標1 - 距離
        """
        signals = []
        metadata = {}
        if len(df) < 60:
            return [], {}
            
        low = df['low'].values
        high = df['high'].values
        close = df['close'].values
        
        # 尋找頭肩頂結構
        for i in range(len(df) - 50, len(df) - 10):
            window = 40
            if i < window:
                continue
                
            segment = high[i-window:i+10]
            
            # 找三個高點
            highs_idx = []
            for j in range(5, len(segment) - 5):
                if segment[j] == segment[max(0, j-5):min(len(segment), j+6)].max():
                    highs_idx.append(j)
                    
            if len(highs_idx) < 3:
                continue
                
            # 取最近的三個高點
            highs_idx_rel = highs_idx[-3:]
            left_shoulder_idx = i - window + highs_idx_rel[0]
            head_idx = i - window + highs_idx_rel[1]
            right_shoulder_idx = i - window + highs_idx_rel[2]

            left_shoulder = high[left_shoulder_idx]
            head = high[head_idx]
            right_shoulder = high[right_shoulder_idx]
            
            # 檢查頭肩頂特徵
            if head < left_shoulder or head < right_shoulder:  # 頭部應最高
                continue
                
            if left_shoulder == 0 or abs(left_shoulder - right_shoulder) / left_shoulder > 0.05:  # 兩肩應接近
                continue
                
            # 計算頸線（兩肩之間的低點連線）
            neckline_low1_idx = left_shoulder_idx + np.argmin(low[left_shoulder_idx:head_idx])
            neckline_low2_idx = head_idx + np.argmin(low[head_idx:right_shoulder_idx])
            neckline = min(low[neckline_low1_idx], low[neckline_low2_idx])
            
            # 檢查是否跌破頸線
            current_price = close[-1]
            breakout_idx = -1
            if current_price < neckline:
                # 尋找跌破點
                breakout_candidates = np.where(close[right_shoulder_idx:] < neckline)[0]
                if len(breakout_candidates) > 0:
                    breakout_idx = right_shoulder_idx + breakout_candidates[0]

            if current_price > neckline * 1.02:
                continue
            
            # 計算目標價
            height = head - neckline
            entry = neckline
            target1 = entry - height
            target2 = target1 - height
            stop_loss = entry * 1.07
            
            potential_loss_avoid = ((current_price - target1) / (current_price + 1e-9)) * 100
            risk = ((stop_loss - current_price) / current_price) * 100
            
            metadata = {
                'pivots': {
                    'left_shoulder': left_shoulder_idx,
                    'head': head_idx,
                    'right_shoulder': right_shoulder_idx,
                    'neckline1': neckline_low1_idx,
                    'neckline2': neckline_low2_idx,
                    'breakout': breakout_idx if breakout_idx != -1 else None,
                },
                'breakout_date': df.iloc[breakout_idx]['date'].strftime('%Y-%m-%d') if breakout_idx != -1 else None,
                'breakout_price': close[breakout_idx] if breakout_idx != -1 else None,
                'neckline_price': neckline,
                'stop_loss': stop_loss,
            }

            # 建立信號
            signal = PatternSignal(
                symbol="", # 將由 scan_all_patterns 填寫
                pattern_name='頭肩頂',
                pattern_type='bearish',
                signal_type='sell',
                confidence=0.86,
                current_price=current_price,
                neckline=neckline,
                entry_price=entry,
                stop_loss=stop_loss,
                target_1=target1,
                target_2=target2,
                height=height,
                potential_gain=potential_loss_avoid,
                risk_reward=potential_loss_avoid / risk if risk > 0 else 0,
                formation_days=right_shoulder_idx - left_shoulder_idx,
                detected_date=datetime.now().strftime('%Y-%m-%d'),
                status='confirmed'
            )
            signals.append(signal)

        return signals, metadata
            
        return [], {}

    def _detect_false_breakout_hst(self, df: pd.DataFrame) -> Tuple[List[PatternSignal], Dict]:
        """
        9. 假突破（頭肩頂）檢測
        
        特徵:
        - 頭肩頂 + 假突破組合
        - 右肩出現假突破後拉回
        - 跌破頸線確認
        
        邏輯:
        1. 先檢測頭肩頂結構
        2. 確認右肩有突破左肩的動作
        3. 快速拉回
        """
        signals = []
        metadata = {}
        if len(df) < 60:
            return [], {}
            
        low = df['low'].values
        high = df['high'].values
        close = df['close'].values
        
        # 尋找頭肩頂結構
        for i in range(len(df) - 50, len(df) - 10):
            window = 40
            if i < window:
                continue
                
            segment = high[i-window:i+10]
            
            # 找三個高點
            highs_idx = []
            for j in range(5, len(segment) - 5):
                if segment[j] == segment[max(0, j-5):min(len(segment), j+6)].max():
                    highs_idx.append(j)
                    
            if len(highs_idx) < 3:
                continue
                
            highs_idx_rel = highs_idx[-3:]
            left_shoulder_idx = i - window + highs_idx_rel[0]
            head_idx = i - window + highs_idx_rel[1]
            right_shoulder_idx = i - window + highs_idx_rel[2]

            left_shoulder = high[left_shoulder_idx]
            head = high[head_idx]
            right_shoulder = high[right_shoulder_idx]
            
            # 檢查頭肩頂特徵
            if head < left_shoulder or head < right_shoulder:
                continue
                
            # 檢查右肩是否假突破
            if right_shoulder < left_shoulder:
                continue
                
            # 檢查是否快速拉回
            if right_shoulder_idx >= len(close) - 1 or close[right_shoulder_idx+1] > right_shoulder:
                continue
                
            # 計算頸線
            neckline_low1_idx = left_shoulder_idx + np.argmin(low[left_shoulder_idx:head_idx])
            neckline_low2_idx = head_idx + np.argmin(low[head_idx:right_shoulder_idx])
            neckline = min(low[neckline_low1_idx], low[neckline_low2_idx])
            
            # 檢查是否跌破頸線
            current_price = close[-1]
            breakout_idx = -1
            if current_price < neckline:
                # 尋找跌破點
                breakout_candidates = np.where(close[right_shoulder_idx:] < neckline)[0]
                if len(breakout_candidates) > 0:
                    breakout_idx = right_shoulder_idx + breakout_candidates[0]

            if current_price > neckline * 1.02:
                continue
            
            # 計算目標價
            height = head - neckline
            entry = neckline
            target1 = entry - height
            target2 = target1 - height
            stop_loss = entry * 1.07
            
            potential_loss_avoid = ((current_price - target1) / (current_price + 1e-9)) * 100
            risk = ((stop_loss - current_price) / current_price) * 100
            
            metadata = {
                'pivots': {
                    'left_shoulder': left_shoulder_idx,
                    'head': head_idx,
                    'right_shoulder': right_shoulder_idx,
                    'neckline1': neckline_low1_idx,
                    'neckline2': neckline_low2_idx,
                    'breakout': breakout_idx if breakout_idx != -1 else None,
                },
                'breakout_date': df.iloc[breakout_idx]['date'].strftime('%Y-%m-%d') if breakout_idx != -1 else None,
                'breakout_price': close[breakout_idx] if breakout_idx != -1 else None,
                'neckline_price': neckline,
                'stop_loss': stop_loss,
            }

            return [PatternSignal(
                symbol="", # 將由 scan_all_patterns 填寫
                pattern_name='假突破頭肩頂',
                pattern_type='bearish',
                signal_type='sell',
                confidence=0.88,
                current_price=current_price,
                neckline=neckline,
                entry_price=entry,
                stop_loss=stop_loss,
                target_1=target1,
                target_2=target2,
                height=height,
                potential_gain=potential_loss_avoid,
                risk_reward=potential_loss_avoid / risk if risk > 0 else 0,
                formation_days=right_shoulder_idx - left_shoulder_idx,
                detected_date=datetime.now().strftime('%Y-%m-%d'),
                status='confirmed'
            )], metadata
            
        return [], {}

    def _detect_head_shoulders_bottom(self, df: pd.DataFrame) -> Tuple[List[PatternSignal], Dict]:
        """
        11. 頭肩底檢測
        
        特徵:
        - 左肩、頭部、右肩形成
        - 頭部最低、兩肩較高
        - 突破頸線確認
        
        計算:
        - 距離 = 領線 - 頭部
        - 目標1 = 突破點 + 距離
        - 目標2 = 目標1 + 距離
        """
        signals = []
        metadata = {}
        if len(df) < 60:
            return [], {}
            
        low = df['low'].values
        high = df['high'].values
        close = df['close'].values
        
        # 尋找頭肩底結構
        for i in range(len(df) - 50, len(df) - 10):
            window = 40
            if i < window:
                continue
                
            segment = low[i-window:i+10]
            
            # 找三個低點
            lows_idx = []
            for j in range(5, len(segment) - 5):
                if segment[j] == segment[max(0, j-5):min(len(segment), j+6)].min():
                    lows_idx.append(j)
                    
            if len(lows_idx) < 3:
                continue
                
            # 取最近的三個低點
            lows_idx_rel = lows_idx[-3:]
            left_shoulder_idx = i - window + lows_idx_rel[0]
            head_idx = i - window + lows_idx_rel[1]
            right_shoulder_idx = i - window + lows_idx_rel[2]

            left_shoulder = low[left_shoulder_idx]
            head = low[head_idx]
            right_shoulder = low[right_shoulder_idx]
            
            # 檢查頭肩底特徵
            if head > left_shoulder or head > right_shoulder:  # 頭部應最低
                continue
                
            if left_shoulder == 0 or abs(left_shoulder - right_shoulder) / left_shoulder > 0.05:  # 兩肩應接近
                continue
                
            # 計算頸線（兩肩之間的高點連線）
            neckline_high1_idx = left_shoulder_idx + np.argmax(high[left_shoulder_idx:head_idx])
            neckline_high2_idx = head_idx + np.argmax(high[head_idx:right_shoulder_idx])
            neckline = max(high[neckline_high1_idx], high[neckline_high2_idx])
            
            # 檢查是否突破頸線
            current_price = close[-1]
            breakout_idx = -1
            if current_price > neckline:
                # 尋找突破點
                breakout_candidates = np.where(close[right_shoulder_idx:] > neckline)[0]
                if len(breakout_candidates) > 0:
                    breakout_idx = right_shoulder_idx + breakout_candidates[0]

            if current_price < neckline * 0.98:
                continue
            
            # 計算目標價
            height = neckline - head
            entry = neckline
            target1 = entry + height
            target2 = target1 + height
            stop_loss = entry * 0.93
            
            potential_gain = ((target1 - current_price) / current_price) * 100
            risk = ((current_price - stop_loss) / current_price) * 100
            
            metadata = {
                'pivots': {
                    'left_shoulder': left_shoulder_idx,
                    'head': head_idx,
                    'right_shoulder': right_shoulder_idx,
                    'neckline1': neckline_high1_idx,
                    'neckline2': neckline_high2_idx,
                    'breakout': breakout_idx if breakout_idx != -1 else None,
                },
                'breakout_date': df.iloc[breakout_idx]['date'].strftime('%Y-%m-%d') if breakout_idx != -1 else None,
                'breakout_price': close[breakout_idx] if breakout_idx != -1 else None,
                'neckline_price': neckline,
                'stop_loss': stop_loss,
            }

            # 建立信號
            signal = PatternSignal(
                symbol="", # 將由 scan_all_patterns 填寫
                pattern_name='頭肩底',
                pattern_type='bullish',
                signal_type='buy',
                confidence=0.86,
                current_price=current_price,
                neckline=neckline,
                entry_price=entry,
                stop_loss=stop_loss,
                target_1=target1,
                target_2=target2,
                height=height,
                potential_gain=potential_gain,
                risk_reward=potential_gain / risk if risk > 0 else 0,
                formation_days=right_shoulder_idx - left_shoulder_idx,
                detected_date=datetime.now().strftime('%Y-%m-%d'),
                status='confirmed'
            )
            signals.append(signal)

        return signals, metadata
            
        return [], {}

    def _detect_triangle_top(self, df: pd.DataFrame) -> Tuple[List[PatternSignal], Dict]:
        """
        10. 收斂三角形頂部檢測
        
        特徵:
        - 高點逐漸降低，低點逐漸升高
        - 需在1/2到3/4處突破
        - 突破確認後計算等長目標
        
        計算:
        - 邊長 = 三角形起點高度
        - 目標1 = 突破點 + 邊長
        - 目標2 = 目標1 + 邊長
        """
        signals = []
        metadata = {}
        if len(df) < 50:
            return [], {}
            
        high = df['high'].values
        low = df['low'].values
        close = df['close'].values
        
        lookback = 40
        
        # 尋找收斂趨勢
        highs = high[-lookback:]
        lows = low[-lookback:]
        
        if len(highs) < 2 or len(lows) < 2:
            return [], {}

        # 擬合趨勢線
        x = np.arange(lookback)
        m_high, c_high = np.polyfit(x, highs, 1)
        m_low, c_low = np.polyfit(x, lows, 1)

        # 檢查高點是否下降
        if m_high >= 0:
            return [], {}
            
        # 檢查低點是否上升
        if m_low <= 0:
            return [], {}
            
        # 檢查是否突破上緣
        current_price = close[-1]
        upper_line_val = m_high * (lookback - 1) + c_high
        
        breakout_idx = -1
        if current_price > upper_line_val:
            # 尋找突破點
            breakout_candidates = np.where(close[-lookback:] > (m_high * x + c_high))[0]
            if len(breakout_candidates) > 0:
                breakout_idx = len(df) - lookback + breakout_candidates[0]

        if current_price < upper_line_val:
            return [], {}
            
        # 計算目標價
        edge_length = (m_high * 0 + c_high) - (m_low * 0 + c_low)
        entry = upper_line_val
        target1 = entry + edge_length
        target2 = target1 + edge_length
        
        # 止損設在最近低點
        stop_loss = lows[-1]
        
        potential_gain = ((target1 - current_price) / current_price) * 100
        risk = ((current_price - stop_loss) / current_price) * 100
        
        metadata = {
            'pivots': {
                'start_high': len(df) - lookback,
                'start_low': len(df) - lookback,
                'end_high': len(df) - 1,
                'end_low': len(df) - 1,
                'breakout': breakout_idx if breakout_idx != -1 else None,
            },
            'trendlines': {
                'upper': (m_high, c_high),
                'lower': (m_low, c_low),
            },
            'breakout_date': df.iloc[breakout_idx]['date'].strftime('%Y-%m-%d') if breakout_idx != -1 else None,
            'breakout_price': close[breakout_idx] if breakout_idx != -1 else None,
            'stop_loss': stop_loss,
        }

        return [PatternSignal(
            symbol="", # 將由 scan_all_patterns 填寫
            pattern_name='收斂三角形頂',
            pattern_type='bullish',
            signal_type='buy',
            confidence=0.75,
            current_price=current_price,
            neckline=upper_line_val,
            entry_price=entry,
            stop_loss=stop_loss,
            target_1=target1,
            target_2=target2,
            height=edge_length,
            potential_gain=potential_gain,
            risk_reward=potential_gain / risk if risk > 0 else 0,
            formation_days=lookback,
            detected_date=datetime.now().strftime('%Y-%m-%d'),
            status='confirmed'
        )], metadata

    def _detect_triangle_bottom(self, df: pd.DataFrame) -> Tuple[List[PatternSignal], Dict]:
        """
        12. 收斂三角形底部檢測 (空頭)
        
        特徵:
        - 高點逐漸降低，低點逐漸升高
        - 向下突破
        
        計算:
        - 邊長 = 三角形起點高度
        - 目標1 = 跌破點 - 邊長
        - 目標2 = 目標1 - 邊長
        """
        signals = []
        metadata = {}
        if len(df) < 50:
            return [], {}
            
        high = df['high'].values
        low = df['low'].values
        close = df['close'].values
        
        lookback = 40
        
        # 尋找收斂趨勢
        highs = high[-lookback:]
        lows = low[-lookback:]
        
        if len(highs) < 2 or len(lows) < 2:
            return [], {}

        # 擬合趨勢線
        x = np.arange(lookback)
        m_high, c_high = np.polyfit(x, highs, 1)
        m_low, c_low = np.polyfit(x, lows, 1)

        # 檢查高點是否下降
        if m_high >= 0:
            return [], {}
            
        # 檢查低點是否上升
        if m_low <= 0:
            return [], {}
            
        # 檢查是否跌破下緣
        current_price = close[-1]
        lower_line_val = m_low * (lookback - 1) + c_low

        breakout_idx = -1
        if current_price < lower_line_val:
            # 尋找跌破點
            breakout_candidates = np.where(close[-lookback:] < (m_low * x + c_low) )[0]
            if len(breakout_candidates) > 0:
                breakout_idx = len(df) - lookback + breakout_candidates[0]
        
        if current_price > lower_line_val:
            return [], {}
            
        # 計算目標價
        edge_length = (m_high * 0 + c_high) - (m_low * 0 + c_low)
        entry = lower_line_val
        target1 = entry - edge_length
        target2 = entry - edge_length * 1.5
        
        # 止損設在最近高點
        stop_loss = highs[-5:].mean()
        
        potential_loss_avoid = ((current_price - target1) / (current_price + 1e-9)) * 100
        risk = ((stop_loss - current_price) / (current_price + 1e-9)) * 100
        
        metadata = {
            'pivots': {
                'start_high': len(df) - lookback,
                'start_low': len(df) - lookback,
                'end_high': len(df) - 1,
                'end_low': len(df) - 1,
                'breakout': breakout_idx if breakout_idx != -1 else None,
            },
            'trendlines': {
                'upper': (m_high, c_high),
                'lower': (m_low, c_low),
            },
            'breakout_date': df.iloc[breakout_idx]['date'].strftime('%Y-%m-%d') if breakout_idx != -1 else None,
            'breakout_price': close[breakout_idx] if breakout_idx != -1 else None,
            'stop_loss': stop_loss,
        }

        return [PatternSignal(
            symbol="", # 將由 scan_all_patterns 填寫
            pattern_name='收斂三角形底',
            pattern_type='bearish',
            signal_type='sell',
            confidence=0.78,
            current_price=current_price,
            neckline=lower_line_val,
            entry_price=entry,
            stop_loss=stop_loss,
            target_1=target1,
            target_2=target2,
            height=edge_length,
            potential_gain=potential_loss_avoid,
            risk_reward=potential_loss_avoid / risk if risk > 0 else 0,
            formation_days=lookback,
            detected_date=datetime.now().strftime('%Y-%m-%d'),
            status='confirmed'
        )], metadata

    # ==================== 結構強度評估 ====================
    
    def _assess_structure_strength(self, signal: PatternSignal, df: pd.DataFrame) -> PatternSignal:
        """
        評估型態結構的強度
        
        參數:
            signal: PatternSignal 類型的型態信號
            df: 原始數據的 DataFrame
            
        返回:
            PatternSignal: 更新後的型態信號，包含強度分數
        """
        # 以 W 底 為例，評估其結構強度
        if signal.pattern_name == 'W底':
            # 強度評估邏輯 (範例)
            score = 0
            
            # 1. 兩底距離適中 (避免過深或過淺)
            if signal.height > 0.05 and signal.height < 0.15:
                score += 1
            
            # 2. 頸線突破後的回撤幅度小於 3%
            if df['close'].iloc[-1] < signal.neckline * 1.03:
                score += 1
            
            # 3. 量能確認: 當前量能 > 之前20天的平均量能
            if df['volume'].iloc[-1] > df['volume'].rolling(window=20).mean().iloc[-1]:
                score += 1
            
            # 4. 形成天數適中 (避免過長或過短)
            if signal.formation_days > 5 and signal.formation_days < 20:
                score += 1
            
            # 5. 潛在獲利率 > 10%
            if signal.potential_gain > 10:
                score += 1
            
            # 6. 風險報酬比 > 2
            if signal.risk_reward > 2:
                score += 1
            
            # 7. 型態完成度: 已確認 (confirmed) 且 停損未被觸發
            if signal.status == 'confirmed' and df['close'].iloc[-1] > signal.stop_loss:
                score += 1
            
            # 8. 領先指標: RSI < 70 (避免超買區)
            if 'rsi' in df.columns and df['rsi'].iloc[-1] < 70:
                score += 1
            
            signal.structure_score = score
        
        return signal
