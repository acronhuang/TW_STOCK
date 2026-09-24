"""形態識別 — W 底（WBottomDetector）。

自 pattern_detector.py 拆分而來（Phase 3 上帝模組拆分）。
"""

import pandas as pd

from .base import PatternDetector
from .types import Pattern, PatternStatus, PatternType


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
    
    def detect(self, df: pd.DataFrame, stock_id: str) -> list[Pattern]:
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


