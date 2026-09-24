"""形態識別 — 基礎類 PatternDetector（信心度/風報比/量能確認等共用邏輯）。

自 pattern_detector.py 拆分而來（Phase 3 上帝模組拆分）。
"""
import pandas as pd

from ..zigzag import ZigZagIndicator
from .types import Pattern, PatternStatus


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

    def detect(self, df: pd.DataFrame, stock_id: str) -> list[Pattern]:
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
                           start_idx: int, is_bullish: bool) -> int | None:
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


