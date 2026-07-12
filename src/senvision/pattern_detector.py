"""
SenVision 形態識別引擎

實現 12 神招的自動化識別：
- 底部反轉：W底、頭肩底、破底翻
- 頭部反轉：M頭、頭肩頂、破天翻
- 趨勢突破：破切、旗型、三角收斂、箱型突破

Author: SenVision Team
Date: 2026-02-24
"""

import numpy as np
import pandas as pd
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from .zigzag import Peak, ZigZagIndicator


class PatternType(Enum):
    """形態類型枚舉"""
    # 底部反轉
    W_BOTTOM = "W-Bottom"                    # W底（雙底）
    TRIPLE_BOTTOM = "Triple-Bottom"          # 三重底
    HEAD_SHOULDERS_BOTTOM = "HS-Bottom"      # 頭肩底
    FAILED_BREAKDOWN = "Failed-Breakdown"    # 破底翻

    # 頭部反轉
    M_TOP = "M-Top"                          # M頭（雙頂）
    TRIPLE_TOP = "Triple-Top"               # 三重頂
    HEAD_SHOULDERS_TOP = "HS-Top"            # 頭肩頂
    FAILED_BREAKOUT = "Failed-Breakout"      # 破天翻

    # 趨勢突破
    TRENDLINE_BREAK = "Trendline-Break"      # 破切
    FLAG = "Flag"                            # 旗型
    TRIANGLE = "Triangle"                    # 三角收斂
    BOX_BREAKOUT = "Box-Breakout"           # 箱型突破

    # 12 神招擴充（方向性細分）
    FAILED_BREAKDOWN_W = "Failed-Breakdown-W"      # 破底翻W底（多）
    FLAG_FALLING = "Flag-Falling"                  # 下飄旗形（多）
    FLAG_RISING = "Flag-Rising"                    # 上飄旗形（空）
    FAILED_BREAKOUT_HST = "Failed-Breakout-HST"    # 假突破頭肩頂（空）
    TRIANGLE_UP = "Triangle-Up"                    # 收斂三角形頂（多，向上突破）
    TRIANGLE_DOWN = "Triangle-Down"                # 收斂三角形底（空，向下跌破）


class PatternStatus(Enum):
    """形態狀態"""
    FORMING = "成型中"      # 形態即將完成
    BREAKOUT = "剛突破"     # 當日突破
    CONFIRMED = "已確認"    # 突破後確認有效
    IN_PROGRESS = "進行中"  # 測幅進行中
    TARGET_HIT = "達標"     # 達到目標價
    STOP_LOSS = "停損"      # 觸發停損
    EXPIRED = "失效"        # 形態失效


@dataclass
class Pattern:
    """
    形態數據結構
    
    Attributes:
        stock_id: 股票代碼
        pattern_type: 形態類型
        neckline: 頸線價格
        target: 目標價
        stop_loss: 停損價
        risk_reward_ratio: 風報比
        key_points: 關鍵點位 {'L1': Peak, 'H': Peak, 'L2': Peak, ...}
        formation_date: 形態形成日期
        breakout_date: 突破日期（可選）
        current_price: 當前價格
        status: 形態狀態
        volume_confirmed: 是否有量能確認
        confidence: 信心度 (0-1)
    """
    stock_id: str
    pattern_type: PatternType
    neckline: float
    target: float
    stop_loss: float
    risk_reward_ratio: float
    key_points: Dict[str, Peak]
    formation_date: datetime
    breakout_date: Optional[datetime] = None
    current_price: Optional[float] = None
    status: PatternStatus = PatternStatus.FORMING
    volume_confirmed: bool = False
    confidence: float = 0.0
    
    def __repr__(self):
        return (f"Pattern({self.stock_id}, {self.pattern_type.value}, "
                f"頸線={self.neckline:.2f}, 目標={self.target:.2f}, "
                f"風報比={self.risk_reward_ratio:.2f}, 狀態={self.status.value})")
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典格式"""
        return {
            'stock_id': self.stock_id,
            'pattern_type': self.pattern_type.value,
            'neckline': self.neckline,
            'target': self.target,
            'stop_loss': self.stop_loss,
            'risk_reward_ratio': self.risk_reward_ratio,
            'formation_date': self.formation_date.isoformat(),
            'breakout_date': self.breakout_date.isoformat() if self.breakout_date else None,
            'current_price': self.current_price,
            'status': self.status.value,
            'volume_confirmed': self.volume_confirmed,
            'confidence': self.confidence,
            'key_points': {
                k: {'date': v.date.isoformat(), 'price': v.price, 'type': v.type}
                for k, v in self.key_points.items()
            }
        }


class PatternDetector:
    """
    形態識別基礎類
    
    所有具體形態識別器的父類
    """
    
    def __init__(self, 
                 zigzag_threshold: float = 0.05,
                 min_pattern_width_days: int = 20,
                 max_pattern_width_days: int = 120):
        """
        Args:
            zigzag_threshold: ZigZag 閾值
            min_pattern_width_days: 形態最小寬度（交易日）
            max_pattern_width_days: 形態最大寬度（交易日）
        """
        self.zigzag = ZigZagIndicator(threshold=zigzag_threshold)
        self.min_pattern_width_days = min_pattern_width_days
        self.max_pattern_width_days = max_pattern_width_days
    
    # 價格容忍度（子類可覆寫）
    price_tolerance: float = 0.03

    def detect(self, df: pd.DataFrame, stock_id: str) -> List[Pattern]:
        """
        檢測形態（由子類實現）

        Args:
            df: 價格數據 DataFrame
            stock_id: 股票代碼

        Returns:
            patterns: 識別到的形態列表
        """
        raise NotImplementedError("子類必須實現 detect 方法")

    def _compute_confidence(
        self,
        status: PatternStatus,
        volume_confirmed: bool,
        price_diff: float,
        neckline: float,
        current_price: float,
        formation_index: int,
        total_bars: int,
        rrr: float = 0.0,
    ) -> float:
        """
        動態計算信心度 (0.20 ~ 0.95)

        Args:
            status: 型態狀態 (FORMING / BREAKOUT)
            volume_confirmed: 是否有量能確認
            price_diff: 兩底/兩頂的價差比 (0 ~ price_tolerance)
            neckline: 頸線價格
            current_price: 當前收盤價
            formation_index: 型態最後轉折點的 bar index
            total_bars: DataFrame 總 bar 數 (len(df))
            rrr: 風報比，用於品質加分

        Returns:
            confidence: 0.20 ~ 0.95
        """
        conf = 0.35  # 降低基礎分，拓寬分佈

        # 狀態加分
        if status == PatternStatus.BREAKOUT:
            conf += 0.15
            # 突破距離加分
            if neckline > 0:
                dist = abs(current_price - neckline) / neckline
                conf += min(0.08, dist * 2)
        elif neckline > 0 and abs(current_price - neckline) / neckline <= 0.02:
            conf += 0.05

        # 量能加分
        if volume_confirmed:
            conf += 0.10

        # RRR 品質加分（RRR 已改頸線算，門檻隨真實尺度下修）
        if rrr >= 1.5:
            conf += 0.10
        elif rrr >= 1.0:
            conf += 0.05

        # 型態對稱性（兩底/兩頂價差越小越可靠）
        tol = self.price_tolerance if self.price_tolerance > 0 else 0.03
        symmetry = max(0.0, 1.0 - price_diff / tol)
        conf += 0.10 * symmetry

        # 年齡衰減（越老越不可靠）
        age_bars = total_bars - formation_index
        if age_bars > 120:
            conf -= min(0.15, 0.15 * (age_bars - 120) / 240)

        return max(0.20, min(0.95, round(conf, 2)))

    def calculate_risk_reward_ratio(self,
                                     entry_price: float,
                                     target: float,
                                     stop_loss: float) -> float:
        """
        計算多方（做多）風報比。
        entry_price 應為「進場點＝頸線(突破價)」，不可用現價——成型中時現價貼停損會算出
        假性超高 RRR（風險趨近 0）。

        Args:
            entry_price: 進場參考價（頸線/突破價）
            target: 目標價（高於 entry_price）
            stop_loss: 停損價（低於 entry_price）

        Returns:
            risk_reward_ratio: 風報比，若無效則返回 0
        """
        risk = entry_price - stop_loss
        if risk <= 0:
            return 0.0
        reward = target - entry_price
        if reward <= 0:
            return 0.0
        return reward / risk

    def calculate_short_risk_reward_ratio(self,
                                           entry_price: float,
                                           target: float,
                                           stop_loss: float) -> float:
        """
        計算空方（做空）風報比。entry_price 為頸線(跌破價)，非現價（理由同多方）。

        Args:
            entry_price: 進場參考價（頸線/跌破價）
            target: 目標價（低於 entry_price）
            stop_loss: 停損價（高於 entry_price）

        Returns:
            risk_reward_ratio: 風報比，若無效則返回 0
        """
        risk = stop_loss - entry_price
        if risk <= 0:
            return 0.0
        reward = entry_price - target
        if reward <= 0:
            return 0.0
        return reward / risk
    
    def _find_breakout_bar(self, df: pd.DataFrame, neckline: float,
                           start_idx: int, is_bullish: bool) -> Optional[int]:
        """找到突破頸線的第一根 bar 索引。"""
        for i in range(start_idx, len(df)):
            if is_bullish and df['close'].iloc[i] >= neckline:
                return i
            if not is_bullish and df['close'].iloc[i] <= neckline:
                return i
        return None

    @staticmethod
    def _atr_tolerance(df: pd.DataFrame, period: int = 14) -> float:
        """根據 ATR 計算自適應價格容忍度 (2%~5%)。"""
        if len(df) < 2:
            return 0.03
        tr = pd.concat([
            df['high'] - df['low'],
            (df['high'] - df['close'].shift(1)).abs(),
            (df['low'] - df['close'].shift(1)).abs(),
        ], axis=1).max(axis=1)
        atr = tr.rolling(period, min_periods=1).mean().iloc[-1]
        price = df['close'].iloc[-1]
        if price <= 0:
            return 0.03
        return max(0.02, min(0.05, 1.5 * atr / price))

    def check_volume_confirmation(self,
                                   df: pd.DataFrame,
                                   breakout_index: int,
                                   ma_period: int = 5,
                                   volume_ratio: float = 1.5) -> bool:
        """
        檢查量能確認
        
        Args:
            df: 價格數據
            breakout_index: 突破日索引
            ma_period: 均量週期
            volume_ratio: 突破量倍數
            
        Returns:
            confirmed: 是否確認
        """
        if breakout_index < ma_period:
            return False
        
        # 計算 5 日均量
        ma_volume = df['volume'].iloc[breakout_index - ma_period:breakout_index].mean()
        
        # 突破日量能
        breakout_volume = df['volume'].iloc[breakout_index]
        
        return breakout_volume >= ma_volume * volume_ratio


class WBottomDetector(PatternDetector):
    """
    W 底形態識別器
    
    定義：
    - 兩個低點 L1, L2 價格差距 < 3%
    - 中間高點 H 定義為頸線
    - 突破條件：收盤價 > 頸線 且 成交量 > 5日均量 × 1.5
    
    測幅：目標價 = 頸線 + (頸線 - min(L1, L2))
    停損：min(L1, L2) × 0.97
    """
    
    def __init__(self, 
                 zigzag_threshold: float = 0.05,
                 price_tolerance: float = 0.03,
                 **kwargs):
        """
        Args:
            zigzag_threshold: ZigZag 閾值
            price_tolerance: L1 與 L2 價格容忍度（預設 3%）
        """
        super().__init__(zigzag_threshold, **kwargs)
        self.price_tolerance = price_tolerance
    
    def detect(self, df: pd.DataFrame, stock_id: str) -> List[Pattern]:
        """
        檢測 W 底形態
        
        Args:
            df: 價格數據，必須包含 date, high, low, close, volume
            stock_id: 股票代碼
            
        Returns:
            patterns: W 底形態列表
        """
        patterns = []
        
        # 計算 ZigZag 轉折點
        peaks = self.zigzag.calculate(df)
        
        if len(peaks) < 3:
            return patterns
        
        # 遍歷尋找 L-H-L 序列
        for i in range(len(peaks) - 2):
            if peaks[i].type == 'L' and peaks[i+1].type == 'H' and peaks[i+2].type == 'L':
                L1 = peaks[i]
                H = peaks[i+1]
                L2 = peaks[i+2]
                
                # 檢查形態寬度
                pattern_width = L2.index - L1.index
                if pattern_width < self.min_pattern_width_days or \
                   pattern_width > self.max_pattern_width_days:
                    continue
                
                # 判斷條件：L1 與 L2 價格差距 < 容忍度
                price_diff = abs(L1.price - L2.price) / min(L1.price, L2.price)
                if price_diff > self.price_tolerance:
                    continue
                
                # 計算關鍵價格
                neckline = H.price
                min_low = min(L1.price, L2.price)
                target = neckline + (neckline - min_low)
                stop_loss = min_low * 0.97
                
                # 檢查當前狀態
                current_price = df['close'].iloc[-1]

                # ATR 自適應容忍度
                tol = self._atr_tolerance(df)

                # 找突破 bar（從 L2 之後開始搜尋）
                bo_bar = self._find_breakout_bar(df, neckline, L2.index, is_bullish=True)

                if bo_bar is not None and current_price >= neckline:
                    status = PatternStatus.BREAKOUT
                    breakout_date_val = pd.to_datetime(df['date'].iloc[bo_bar])
                    volume_confirmed = self.check_volume_confirmation(df, bo_bar)
                else:
                    status = PatternStatus.FORMING
                    breakout_date_val = None
                    volume_confirmed = False

                # 計算風報比
                rrr = self.calculate_risk_reward_ratio(neckline, target, stop_loss)

                # 動態信心度
                confidence = self._compute_confidence(
                    status=status,
                    volume_confirmed=volume_confirmed,
                    price_diff=price_diff,
                    neckline=neckline,
                    current_price=current_price,
                    formation_index=L2.index,
                    total_bars=len(df),
                    rrr=rrr,
                )

                # 創建形態對象
                pattern = Pattern(
                    stock_id=stock_id,
                    pattern_type=PatternType.W_BOTTOM,
                    neckline=neckline,
                    target=target,
                    stop_loss=stop_loss,
                    risk_reward_ratio=rrr,
                    key_points={'L1': L1, 'H': H, 'L2': L2},
                    formation_date=L2.date,
                    breakout_date=breakout_date_val,
                    current_price=current_price,
                    status=status,
                    volume_confirmed=volume_confirmed,
                    confidence=confidence,
                )
                
                patterns.append(pattern)
        
        return patterns


class MTopDetector(PatternDetector):
    """
    M 頭形態識別器
    
    定義：
    - 兩個高點 H1, H2 價格差距 < 3%
    - 中間低點 L 定義為頸線
    - 突破條件：收盤價 < 頸線
    
    測幅：目標價 = 頸線 - (max(H1, H2) - 頸線)
    停損：max(H1, H2) × 1.03
    """
    
    def __init__(self, 
                 zigzag_threshold: float = 0.05,
                 price_tolerance: float = 0.03,
                 **kwargs):
        super().__init__(zigzag_threshold, **kwargs)
        self.price_tolerance = price_tolerance
    
    def detect(self, df: pd.DataFrame, stock_id: str) -> List[Pattern]:
        """檢測 M 頭形態"""
        patterns = []
        
        peaks = self.zigzag.calculate(df)
        
        if len(peaks) < 3:
            return patterns
        
        # 遍歷尋找 H-L-H 序列
        for i in range(len(peaks) - 2):
            if peaks[i].type == 'H' and peaks[i+1].type == 'L' and peaks[i+2].type == 'H':
                H1 = peaks[i]
                L = peaks[i+1]
                H2 = peaks[i+2]
                
                # 檢查形態寬度
                pattern_width = H2.index - H1.index
                if pattern_width < self.min_pattern_width_days or \
                   pattern_width > self.max_pattern_width_days:
                    continue
                
                # 判斷條件：H1 與 H2 價格差距 < 容忍度
                price_diff = abs(H1.price - H2.price) / max(H1.price, H2.price)
                if price_diff > self.price_tolerance:
                    continue
                
                # 計算關鍵價格
                neckline = L.price
                max_high = max(H1.price, H2.price)
                target = neckline - (max_high - neckline)
                stop_loss = max_high * 1.03
                
                # 檢查當前狀態
                current_price = df['close'].iloc[-1]

                # ATR 自適應容忍度
                tol = self._atr_tolerance(df)

                # 找突破 bar（空方：收盤 <= 頸線）
                bo_bar = self._find_breakout_bar(df, neckline, H2.index, is_bullish=False)

                if bo_bar is not None and current_price <= neckline:
                    status = PatternStatus.BREAKOUT
                    breakout_date_val = pd.to_datetime(df['date'].iloc[bo_bar])
                    volume_confirmed = self.check_volume_confirmation(df, bo_bar)
                else:
                    status = PatternStatus.FORMING
                    breakout_date_val = None
                    volume_confirmed = False

                # 計算風報比（空方）
                rrr = self.calculate_short_risk_reward_ratio(neckline, target, stop_loss)

                # 動態信心度
                confidence = self._compute_confidence(
                    status=status,
                    volume_confirmed=volume_confirmed,
                    price_diff=price_diff,
                    neckline=neckline,
                    current_price=current_price,
                    formation_index=H2.index,
                    total_bars=len(df),
                    rrr=rrr,
                )

                pattern = Pattern(
                    stock_id=stock_id,
                    pattern_type=PatternType.M_TOP,
                    neckline=neckline,
                    target=target,
                    stop_loss=stop_loss,
                    risk_reward_ratio=rrr,
                    key_points={'H1': H1, 'L': L, 'H2': H2},
                    formation_date=H2.date,
                    breakout_date=breakout_date_val,
                    current_price=current_price,
                    status=status,
                    volume_confirmed=volume_confirmed,
                    confidence=confidence,
                )
                
                patterns.append(pattern)
        
        return patterns


class TripleBottomDetector(PatternDetector):
    """
    三重底形態識別器

    定義：
    - 五個轉折點序列：L1-H1-L2-H2-L3
    - 三個低點（L1, L2, L3）價格差距 < 容忍度
    - 頸線 = (H1.price + H2.price) / 2
    - 突破條件：收盤價 > 頸線 且 成交量 > 5日均量 × 1.5

    測幅：目標價 = 頸線 + (頸線 - min(L1, L2, L3))
    停損：min(L1, L2, L3) × 0.97
    """

    def __init__(self,
                 zigzag_threshold: float = 0.05,
                 price_tolerance: float = 0.03,
                 **kwargs):
        super().__init__(zigzag_threshold, **kwargs)
        self.price_tolerance = price_tolerance

    def detect(self, df: pd.DataFrame, stock_id: str) -> List[Pattern]:
        patterns = []
        peaks = self.zigzag.calculate(df)

        if len(peaks) < 5:
            return patterns

        for i in range(len(peaks) - 4):
            # 找 L-H-L-H-L 序列
            if not (peaks[i].type == 'L' and peaks[i+1].type == 'H' and
                    peaks[i+2].type == 'L' and peaks[i+3].type == 'H' and
                    peaks[i+4].type == 'L'):
                continue

            L1, H1, L2, H2, L3 = peaks[i], peaks[i+1], peaks[i+2], peaks[i+3], peaks[i+4]

            # 形態寬度
            pattern_width = L3.index - L1.index
            if pattern_width < self.min_pattern_width_days or \
               pattern_width > self.max_pattern_width_days:
                continue

            # 三個低點需接近
            low_prices = [L1.price, L2.price, L3.price]
            min_low = min(low_prices)
            max_low = max(low_prices)
            if (max_low - min_low) / min_low > self.price_tolerance:
                continue

            neckline = (H1.price + H2.price) / 2.0
            min_low_val = min(low_prices)
            target = neckline + (neckline - min_low_val)
            stop_loss = min_low_val * 0.97

            current_price = df['close'].iloc[-1]

            # ATR 自適應容忍度
            tol = self._atr_tolerance(df)

            # 找突破 bar（多方）
            bo_bar = self._find_breakout_bar(df, neckline, L3.index, is_bullish=True)

            if bo_bar is not None and current_price >= neckline:
                status = PatternStatus.BREAKOUT
                breakout_date_val = pd.to_datetime(df['date'].iloc[bo_bar])
                volume_confirmed = self.check_volume_confirmation(df, bo_bar)
            else:
                status = PatternStatus.FORMING
                breakout_date_val = None
                volume_confirmed = False

            rrr = self.calculate_risk_reward_ratio(neckline, target, stop_loss)

            # 動態信心度（三底取最大價差比）
            triple_diff = (max_low - min_low) / min_low if min_low > 0 else 0
            confidence = self._compute_confidence(
                status=status,
                volume_confirmed=volume_confirmed,
                price_diff=triple_diff,
                neckline=neckline,
                current_price=current_price,
                formation_index=L3.index,
                total_bars=len(df),
                rrr=rrr,
            )

            patterns.append(Pattern(
                stock_id=stock_id,
                pattern_type=PatternType.TRIPLE_BOTTOM,
                neckline=round(neckline, 2),
                target=round(target, 2),
                stop_loss=round(stop_loss, 2),
                risk_reward_ratio=round(rrr, 2),
                key_points={'L1': L1, 'H1': H1, 'L2': L2, 'H2': H2, 'L3': L3},
                formation_date=L3.date,
                breakout_date=breakout_date_val,
                current_price=current_price,
                status=status,
                volume_confirmed=volume_confirmed,
                confidence=confidence,
            ))

        return patterns


class TripleTopDetector(PatternDetector):
    """
    三重頂形態識別器

    定義：
    - 五個轉折點序列：H1-L1-H2-L2-H3
    - 三個高點（H1, H2, H3）價格差距 < 容忍度
    - 頸線 = (L1.price + L2.price) / 2
    - 突破條件：收盤價 < 頸線

    測幅：目標價 = 頸線 - (max(H1, H2, H3) - 頸線)
    停損：max(H1, H2, H3) × 1.03
    """

    def __init__(self,
                 zigzag_threshold: float = 0.05,
                 price_tolerance: float = 0.03,
                 **kwargs):
        super().__init__(zigzag_threshold, **kwargs)
        self.price_tolerance = price_tolerance

    def detect(self, df: pd.DataFrame, stock_id: str) -> List[Pattern]:
        patterns = []
        peaks = self.zigzag.calculate(df)

        if len(peaks) < 5:
            return patterns

        for i in range(len(peaks) - 4):
            # 找 H-L-H-L-H 序列
            if not (peaks[i].type == 'H' and peaks[i+1].type == 'L' and
                    peaks[i+2].type == 'H' and peaks[i+3].type == 'L' and
                    peaks[i+4].type == 'H'):
                continue

            H1, L1, H2, L2, H3 = peaks[i], peaks[i+1], peaks[i+2], peaks[i+3], peaks[i+4]

            # 形態寬度
            pattern_width = H3.index - H1.index
            if pattern_width < self.min_pattern_width_days or \
               pattern_width > self.max_pattern_width_days:
                continue

            # 三個高點需接近
            high_prices = [H1.price, H2.price, H3.price]
            min_high = min(high_prices)
            max_high = max(high_prices)
            if (max_high - min_high) / min_high > self.price_tolerance:
                continue

            neckline = (L1.price + L2.price) / 2.0
            max_high_val = max(high_prices)
            target = neckline - (max_high_val - neckline)
            stop_loss = max_high_val * 1.03

            current_price = df['close'].iloc[-1]

            # ATR 自適應容忍度
            tol = self._atr_tolerance(df)

            # 找突破 bar（空方：收盤 <= 頸線）
            bo_bar = self._find_breakout_bar(df, neckline, H3.index, is_bullish=False)

            if bo_bar is not None and current_price <= neckline:
                status = PatternStatus.BREAKOUT
                breakout_date_val = pd.to_datetime(df['date'].iloc[bo_bar])
                volume_confirmed = self.check_volume_confirmation(df, bo_bar)
            else:
                status = PatternStatus.FORMING
                breakout_date_val = None
                volume_confirmed = False

            rrr = self.calculate_short_risk_reward_ratio(neckline, target, stop_loss)

            # 動態信心度
            triple_diff = (max_high - min_high) / min_high if min_high > 0 else 0
            confidence = self._compute_confidence(
                status=status,
                volume_confirmed=volume_confirmed,
                price_diff=triple_diff,
                neckline=neckline,
                current_price=current_price,
                formation_index=H3.index,
                total_bars=len(df),
                rrr=rrr,
            )

            patterns.append(Pattern(
                stock_id=stock_id,
                pattern_type=PatternType.TRIPLE_TOP,
                neckline=round(neckline, 2),
                target=round(target, 2),
                stop_loss=round(stop_loss, 2),
                risk_reward_ratio=round(rrr, 2),
                key_points={'H1': H1, 'L1': L1, 'H2': H2, 'L2': L2, 'H3': H3},
                formation_date=H3.date,
                breakout_date=breakout_date_val,
                current_price=current_price,
                status=status,
                volume_confirmed=volume_confirmed,
                confidence=confidence,
            ))

        return patterns


# 測試代碼
if __name__ == '__main__':
    import sys
    from pathlib import Path
    
    # 添加項目路徑
    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root / 'src'))
    
    print("="*80)
    print("形態識別引擎測試")
    print("="*80)
    
    # 生成測試數據 - W底形態
    np.random.seed(42)
    dates = pd.date_range('2024-01-01', periods=100, freq='D')
    
    # 創建 W 底形態
    prices = np.concatenate([
        np.linspace(100, 85, 20),   # 下跌至 L1
        np.linspace(85, 95, 15),    # 反彈至 H（頸線）
        np.linspace(95, 87, 20),    # 下跌至 L2
        np.linspace(87, 105, 45)    # 突破上漲
    ])
    
    df_test = pd.DataFrame({
        'date': dates,
        'open': prices,
        'high': prices + np.random.rand(100) * 2,
        'low': prices - np.random.rand(100) * 2,
        'close': prices,
        'volume': np.random.randint(1000000, 10000000, 100)
    })
    
    # 測試 W 底識別
    print("\n【測試 W 底識別】")
    detector_w = WBottomDetector()
    patterns_w = detector_w.detect(df_test, '2330')
    
    print(f"\n找到 {len(patterns_w)} 個 W 底形態:\n")
    for pattern in patterns_w:
        print(pattern)
        print(f"  關鍵點: {list(pattern.key_points.keys())}")
        print(f"  信心度: {pattern.confidence:.2%}")
        print()
    
    # 測試 M 頭識別
    print("\n【測試 M 頭識別】")
    # 創建 M 頭形態數據
    prices_m = np.concatenate([
        np.linspace(100, 120, 20),  # 上漲至 H1
        np.linspace(120, 105, 15),  # 下跌至 L（頸線）
        np.linspace(105, 118, 20),  # 上漲至 H2
        np.linspace(118, 95, 45)    # 跌破頸線
    ])
    
    df_test_m = pd.DataFrame({
        'date': dates,
        'open': prices_m,
        'high': prices_m + np.random.rand(100) * 2,
        'low': prices_m - np.random.rand(100) * 2,
        'close': prices_m,
        'volume': np.random.randint(1000000, 10000000, 100)
    })
    
    detector_m = MTopDetector()
    patterns_m = detector_m.detect(df_test_m, '2454')
    
    print(f"找到 {len(patterns_m)} 個 M 頭形態:\n")
    for pattern in patterns_m:
        print(pattern)
        print(f"  關鍵點: {list(pattern.key_points.keys())}")
        print(f"  信心度: {pattern.confidence:.2%}")
        print()
    
    print("✅ 測試完成")
