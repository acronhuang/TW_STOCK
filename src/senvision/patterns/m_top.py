"""形態識別 — M 頭（MTopDetector）。

自 pattern_detector.py 拆分而來（Phase 3 上帝模組拆分）。
"""

import pandas as pd

from .base import PatternDetector
from .types import Pattern, PatternStatus, PatternType


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
    
    def detect(self, df: pd.DataFrame, stock_id: str) -> list[Pattern]:
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


