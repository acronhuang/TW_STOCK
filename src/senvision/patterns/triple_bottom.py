"""形態識別 — 三重底（TripleBottomDetector）。

自 pattern_detector.py 拆分而來（Phase 3 上帝模組拆分）。
"""

import pandas as pd

from .base import PatternDetector
from .types import Pattern, PatternStatus, PatternType


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

    def detect(self, df: pd.DataFrame, stock_id: str) -> list[Pattern]:
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


