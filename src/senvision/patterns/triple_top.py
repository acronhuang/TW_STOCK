"""形態識別 — 三重頂（TripleTopDetector）。

自 pattern_detector.py 拆分而來（Phase 3 上帝模組拆分）。
"""

import pandas as pd

from .base import PatternDetector
from .types import Pattern, PatternStatus, PatternType


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

    def detect(self, df: pd.DataFrame, stock_id: str) -> list[Pattern]:
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
