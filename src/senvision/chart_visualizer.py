"""
SenVision 圖表視覺化引擎

整合所有技術分析元素，產出符合蔡森老師看盤習慣的圖表：

顏色規範：
    - 紅色水平線：壓力線 / 突破目標
    - 藍色水平線：支撐線 / 停損位置
    - 黃色斜線：下降切線（待突破）
    - 半透明帶狀區：支撐與壓力區域（而非單一點）

圖層順序（由底至頂）：
    1. K 線蠟燭圖
    2. 支撐壓力帶狀區（半透明）
    3. ZigZag 虛線
    4. 頸線 / 目標 / 停損水平線
    5. 趨勢切線
    6. 突破標記點

Author: SenVision Team
Date: 2026-02-24
"""

from __future__ import annotations

from typing import List, Optional

import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D

from .multi_timeframe import get_timeframe_label
from .pattern_detector import Pattern, PatternStatus
from .support_resistance import SRLevel
from .trendline import Trendline
from .zigzag import Peak

# ── 顏色配置 ────────────────────────────────────────────────────────────────────
_COLORS = {
    'up_candle':         '#e74c3c',   # 上漲蠟燭（紅）
    'down_candle':       '#26a65b',   # 下跌蠟燭（綠）
    'wick':              '#7f8c8d',   # 影線（灰）
    'resistance_line':   '#e74c3c',   # 壓力線（紅）
    'support_line':      '#3498db',   # 支撐線（藍）
    'trendline':         '#f39c12',   # 切線（黃）
    'neckline':          '#e74c3c',   # 頸線（紅）
    'stop_loss':         '#3498db',   # 停損（藍）
    'target':            '#9b59b6',   # 目標（紫）
    'zigzag':            '#95a5a6',   # ZigZag（灰）
    'breakout_star':     '#f1c40f',   # 突破標記（金）
    'volume_up':         '#e74c3c',
    'volume_down':       '#26a65b',
    'volume_ma':         '#f39c12',
    'bg_dark':           '#0d1117',
    'grid_dark':         '#21262d',
    # 均線配色（蔡森慣例：5白 10黃 20橙 60紫）
    'ma5':               '#e6edf3',   # MA5  白/淺灰
    'ma10':              '#f1c40f',   # MA10 黃
    'ma20':              '#e67e22',   # MA20 橙
    'ma60':              '#9b59b6',   # MA60 紫
}


def _to_dates_series(df: pd.DataFrame) -> pd.Series:
    """統一提取 DataFrame 的日期序列（Series of Timestamp）"""
    if 'date' in df.columns:
        return pd.to_datetime(df['date']).reset_index(drop=True)
    return pd.to_datetime(df.index).to_series().reset_index(drop=True)


def _dates_to_num(dates: pd.Series) -> np.ndarray:
    """轉換 datetime Series 為 matplotlib 日期數值"""
    return mdates.date2num(dates.values)


class SenVisionChart:
    """
    SenVision 技術分析圖表引擎

    用法::

        chart = SenVisionChart(dark_theme=True)
        chart.plot(
            df=df_weekly,
            stock_id='2330',
            timeframe='W',
            peaks=peaks,
            patterns=patterns,
            sr_levels=sr_levels,
            trendlines=trendlines,
            save_path='charts/2330_W.png',
        )
    """

    def __init__(self, dark_theme: bool = True):
        self.dark_theme = dark_theme
        self._bg = _COLORS['bg_dark'] if dark_theme else '#ffffff'
        self._fg = '#e6edf3' if dark_theme else '#24292f'
        self._grid = _COLORS['grid_dark'] if dark_theme else '#e1e4e8'

        # 設定中文字體（macOS 優先，fallback to sans-serif）
        plt.rcParams['font.family'] = [
            'Arial Unicode MS', 'PingFang HK', 'Heiti TC',
            'STHeiti', 'DejaVu Sans'
        ]
        plt.rcParams['axes.unicode_minus'] = False

        # 抑制字型找不到的警告（不影響功能）
        import logging
        logging.getLogger('matplotlib.font_manager').setLevel(logging.ERROR)

    # ── 私有繪製方法 ──────────────────────────────────────────────────────────────

    def _draw_candlesticks(
        self,
        ax: plt.Axes,
        df: pd.DataFrame,
        dates_num: np.ndarray,
        candle_width_days: float = 0.6,
    ) -> None:
        """繪製蠟燭圖（身體 + 上下影線）"""
        # 計算柱寬（使用實際日期間距）
        if len(dates_num) > 1:
            avg_gap = np.median(np.diff(dates_num))
            width = avg_gap * 0.7
        else:
            width = candle_width_days * 0.7

        for i in range(len(df)):
            o = float(df['open'].iloc[i])
            h = float(df['high'].iloc[i])
            l = float(df['low'].iloc[i])
            c = float(df['close'].iloc[i])
            x = dates_num[i]

            is_up = c >= o
            color = _COLORS['up_candle'] if is_up else _COLORS['down_candle']
            body_low = min(o, c)
            body_high = max(o, c)
            body_height = max(body_high - body_low, (h - l) * 0.01)  # 最小高度

            # 燭體
            rect = mpatches.FancyBboxPatch(
                (x - width / 2, body_low),
                width, body_height,
                boxstyle='square,pad=0',
                facecolor=color,
                edgecolor=color,
                alpha=0.85,
                zorder=2,
            )
            ax.add_patch(rect)

            # 上下影線
            ax.vlines(x, l, body_low, color=color, linewidth=0.7, zorder=2)
            ax.vlines(x, body_high, h, color=color, linewidth=0.7, zorder=2)

    def _draw_zigzag(
        self,
        ax: plt.Axes,
        dates: pd.Series,
        peaks: List[Peak],
        df_len: int,
    ) -> None:
        """繪製 ZigZag 折線與高低點標記"""
        valid = [p for p in peaks if p.index < df_len]
        if len(valid) < 2:
            return

        xs = [dates.iloc[p.index] for p in valid]
        ys = [p.price for p in valid]

        ax.plot(xs, ys,
                color=_COLORS['zigzag'],
                linewidth=1.2,
                linestyle='--',
                alpha=0.65,
                zorder=3,
                label='ZigZag')

        for p in valid:
            d = dates.iloc[p.index]
            if p.type == 'H':
                ax.scatter(d, p.price, color=_COLORS['resistance_line'],
                           s=40, marker='v', zorder=5, alpha=0.8)
            else:
                ax.scatter(d, p.price, color=_COLORS['support_line'],
                           s=40, marker='^', zorder=5, alpha=0.8)

    def _draw_sr_levels(
        self,
        ax: plt.Axes,
        dates: pd.Series,
        sr_levels: List[SRLevel],
        tolerance: float = 0.01,
    ) -> None:
        """繪製支撐壓力帶狀區與水平線標籤"""
        if not sr_levels:
            return

        x_end = dates.iloc[-1]

        for sr in sr_levels:
            band_lo = sr.price * (1.0 - tolerance)
            band_hi = sr.price * (1.0 + tolerance)

            if sr.type == 'resistance':
                color = _COLORS['resistance_line']
                ls = '--'
            else:
                color = _COLORS['support_line']
                ls = '--'

            alpha_band = 0.18 if sr.strength == 'strong' else 0.10
            alpha_line = 0.90 if sr.strength == 'strong' else 0.55
            lw = 1.5 if sr.strength == 'strong' else 0.9

            # 半透明帶狀區
            ax.axhspan(band_lo, band_hi, alpha=alpha_band, color=color, zorder=1)

            # 水平線
            ax.axhline(y=sr.price, color=color, linewidth=lw,
                       linestyle=ls, alpha=alpha_line, zorder=2)

            # 右側標籤
            strength_ch = '強' if sr.strength == 'strong' else ('中' if sr.strength == 'moderate' else '弱')
            label = f" {sr.price:.1f}[{strength_ch}{sr.touches}]"
            ax.text(x_end, sr.price, label,
                    color=color, fontsize=7, va='center', ha='left',
                    alpha=0.85, zorder=6)

    def _draw_patterns(
        self,
        ax: plt.Axes,
        dates: pd.Series,
        patterns: List[Pattern],
    ) -> None:
        """繪製形態頸線、目標價、停損位與突破標記"""
        if not patterns:
            return

        x_end = dates.iloc[-1]

        for p in patterns:
            # 頸線（紅色實線）
            ax.axhline(y=p.neckline, color=_COLORS['neckline'],
                       linewidth=2.0, linestyle='-', alpha=0.9, zorder=4)
            ax.axhspan(p.neckline * 0.996, p.neckline * 1.004,
                       alpha=0.12, color=_COLORS['neckline'], zorder=1)
            ax.text(x_end, p.neckline,
                    f" 頸{p.neckline:.1f}",
                    color=_COLORS['neckline'], fontsize=8,
                    va='bottom', ha='left', fontweight='bold', zorder=7)

            # 目標價（紫色虛線）
            if p.target and p.target > 0:
                ax.axhline(y=p.target, color=_COLORS['target'],
                           linewidth=1.2, linestyle=':', alpha=0.80, zorder=3)
                ax.text(x_end, p.target,
                        f" 目標{p.target:.1f}",
                        color=_COLORS['target'], fontsize=7,
                        va='bottom', ha='left', zorder=7)

            # 停損（藍色虛線）
            if p.stop_loss and p.stop_loss > 0:
                ax.axhline(y=p.stop_loss, color=_COLORS['stop_loss'],
                           linewidth=1.2, linestyle=':', alpha=0.80, zorder=3)
                ax.text(x_end, p.stop_loss,
                        f" 停損{p.stop_loss:.1f}",
                        color=_COLORS['stop_loss'], fontsize=7,
                        va='top', ha='left', zorder=7)

            # 突破垂直標線
            if p.status == PatternStatus.BREAKOUT and p.breakout_date:
                ax.axvline(x=p.breakout_date,
                           color=_COLORS['breakout_star'],
                           linewidth=1.5, linestyle='--', alpha=0.70, zorder=4)

    def _draw_trendlines(
        self,
        ax: plt.Axes,
        dates: pd.Series,
        trendlines: List[Trendline],
        df_len: int,
    ) -> None:
        """繪製趨勢切線（斜線）及突破標記"""
        if not trendlines:
            return

        for tl in trendlines:
            if tl.p1.index >= df_len or tl.p2.index >= df_len:
                continue

            # 延伸至最後一根 K 線再多 10%
            end_idx = min(df_len - 1, tl.p2.index + int((df_len - tl.p2.index) * 0.25) + 3)
            bar_idxs = range(tl.p1.index, end_idx + 1)

            tl_dates = [dates.iloc[i] for i in bar_idxs]
            tl_prices = [tl.price_at(i) for i in bar_idxs]

            color = _COLORS['trendline']
            lw = 1.8 if not tl.is_broken else 1.2
            alpha = 0.85 if not tl.is_broken else 0.50

            ax.plot(tl_dates, tl_prices,
                    color=color, linewidth=lw,
                    linestyle='-', alpha=alpha, zorder=4)

            # 兩個錨點
            ax.scatter(dates.iloc[tl.p1.index], tl.p1.price,
                       color=color, s=35, marker='o', zorder=5, alpha=0.8)
            ax.scatter(dates.iloc[tl.p2.index], tl.p2.price,
                       color=color, s=35, marker='o', zorder=5, alpha=0.8)

            # 突破標記（金色星形）
            if tl.is_broken and tl.break_index is not None and tl.break_index < df_len:
                bx = dates.iloc[tl.break_index]
                by = tl.break_price
                ax.scatter(bx, by,
                           color=_COLORS['breakout_star'],
                           s=200, marker='*', zorder=6)
                ax.text(bx, by, ' 破切!',
                        color=_COLORS['breakout_star'],
                        fontsize=9, fontweight='bold', va='bottom', zorder=7)

    def _draw_ma_lines(
        self,
        ax: plt.Axes,
        df: pd.DataFrame,
        dates: pd.Series,
        periods: tuple = (5, 10, 20, 60),
    ) -> List[Line2D]:
        """繪製均線（MA5/10/20/60）並回傳圖例項目"""
        color_map = {5: _COLORS['ma5'], 10: _COLORS['ma10'],
                     20: _COLORS['ma20'], 60: _COLORS['ma60']}
        lw_map    = {5: 1.0, 10: 1.0, 20: 1.2, 60: 1.5}
        legend_items = []
        for p in periods:
            if len(df) < p:
                continue
            ma = df['close'].rolling(p, min_periods=p).mean()
            color = color_map.get(p, '#ffffff')
            lw    = lw_map.get(p, 1.0)
            ax.plot(dates.values, ma.values,
                    color=color, linewidth=lw, alpha=0.85, zorder=3,
                    label=f'MA{p}')
            legend_items.append(
                Line2D([0], [0], color=color, lw=lw, label=f'MA{p}')
            )
        return legend_items

    def _draw_volume(
        self,
        ax: plt.Axes,
        df: pd.DataFrame,
        dates_num: np.ndarray,
        vol_ma_period: int = 5,
    ) -> None:
        """繪製成交量柱狀圖與均量線"""
        if 'volume' not in df.columns:
            return

        if len(dates_num) > 1:
            avg_gap = np.median(np.diff(dates_num))
            width = avg_gap * 0.7
        else:
            width = 0.6

        for i in range(len(df)):
            color = (_COLORS['volume_up']
                     if df['close'].iloc[i] >= df['open'].iloc[i]
                     else _COLORS['volume_down'])
            ax.bar(dates_num[i], df['volume'].iloc[i],
                   width=width, color=color, alpha=0.65, zorder=2)

        vol_ma = df['volume'].rolling(vol_ma_period, min_periods=1).mean()
        dates = _to_dates_series(df)
        ax.plot(dates.values, vol_ma.values,
                color=_COLORS['volume_ma'], linewidth=1.2,
                label=f'MA{vol_ma_period}量', zorder=3)

    # ── 主繪圖方法 ────────────────────────────────────────────────────────────────

    def plot(
        self,
        df: pd.DataFrame,
        stock_id: str,
        timeframe: str = 'D',
        peaks: Optional[List[Peak]] = None,
        patterns: Optional[List[Pattern]] = None,
        sr_levels: Optional[List[SRLevel]] = None,
        trendlines: Optional[List[Trendline]] = None,
        ma_alignment: str = 'mixed',
        candle_width_days: float = 0.6,
        save_path: Optional[str] = None,
        show: bool = True,
    ) -> plt.Figure:
        """
        繪製完整技術分析圖表

        Args:
            df: OHLCV DataFrame（含 date, open, high, low, close, volume）
            stock_id: 股票代碼
            timeframe: 時間框架代號（'D'/'W'/'M'/'Q'/'6M'/'Y'）
            peaks: ZigZag 轉折點列表
            patterns: 形態列表
            sr_levels: 支撐壓力位列表
            trendlines: 趨勢切線列表
            ma_alignment: 均線排列狀態（'bullish'/'bearish'/'mixed'）
            candle_width_days: 蠟燭圖柱寬（天數）
            save_path: 圖表儲存路徑（None=不儲存）
            show: 是否呼叫 plt.show()

        Returns:
            matplotlib Figure 物件
        """
        tf_label = get_timeframe_label(timeframe)

        dates = _to_dates_series(df)
        dates_num = _dates_to_num(dates)

        # ── 建立圖表佈局 ──────────────────────────────────────────
        fig, (ax1, ax2) = plt.subplots(
            2, 1,
            figsize=(18, 11),
            gridspec_kw={'height_ratios': [7, 3]},
            sharex=False,   # volume 用不同 x 軸型態
        )

        fig.patch.set_facecolor(self._bg)
        ax1.set_facecolor(self._bg)
        ax2.set_facecolor(self._bg)

        # ── 主圖：價格 ────────────────────────────────────────────
        self._draw_candlesticks(ax1, df, dates_num, candle_width_days)

        # 均線（繪於 K 線之上、SR 帶之下）
        ma_legend_items = self._draw_ma_lines(ax1, df, dates)

        if sr_levels:
            self._draw_sr_levels(ax1, dates, sr_levels)

        if patterns:
            self._draw_patterns(ax1, dates, patterns)

        if peaks:
            self._draw_zigzag(ax1, dates, peaks, len(df))

        if trendlines:
            self._draw_trendlines(ax1, dates, trendlines, len(df))

        # X 軸設定（使用 date2num 格式，再用 DateFormatter 顯示）
        ax1.xaxis_date()
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        ax1.set_xlim(dates_num[0] - 1, dates_num[-1] + max(int(len(df) * 0.12), 6))

        # Y 軸設定（留 8% 上下空間讓標籤不被裁切）
        price_min = float(df['low'].min())
        price_max = float(df['high'].max())
        margin = (price_max - price_min) * 0.12
        ax1.set_ylim(price_min - margin, price_max + margin)

        ax1.set_ylabel('價格', color=self._fg, fontsize=10)
        ax1.yaxis.set_label_position('left')
        ax1.tick_params(colors=self._fg, labelsize=8)
        ax1.grid(True, alpha=0.15, color=self._grid, linewidth=0.5)

        # 圖例（均線 + 技術元素）
        legend_items = ma_legend_items + [
            Line2D([0], [0], color=_COLORS['resistance_line'], lw=1.5, ls='--', label='壓力線'),
            Line2D([0], [0], color=_COLORS['support_line'],    lw=1.5, ls='--', label='支撐線'),
            Line2D([0], [0], color=_COLORS['trendline'],       lw=1.5, ls='-',  label='切線(破切)'),
            Line2D([0], [0], color=_COLORS['neckline'],        lw=2.0, ls='-',  label='頸線'),
            Line2D([0], [0], color=_COLORS['zigzag'],          lw=1.2, ls='--', label='ZigZag'),
        ]
        ax1.legend(handles=legend_items, loc='upper left',
                   fontsize=8, framealpha=0.35,
                   labelcolor=self._fg,
                   facecolor=self._bg)

        # 標題（含均線排列狀態）
        current_price = float(df['close'].iloc[-1])
        n_patterns = len(patterns) if patterns else 0
        n_sr = len(sr_levels) if sr_levels else 0
        _align_label = {'bullish': '多頭排列↑', 'bearish': '空頭排列↓', 'mixed': '均線糾結'}.get(ma_alignment, '')
        title = (
            f"{stock_id}  {tf_label}   "
            f"現價 {current_price:.2f}   "
            f"{_align_label}   "
            f"形態:{n_patterns}  支撐壓力:{n_sr}"
        )
        ax1.set_title(title, color=self._fg, fontsize=13, fontweight='bold', pad=8)

        # ── 成交量圖 ─────────────────────────────────────────────
        self._draw_volume(ax2, df, dates_num)
        ax2.xaxis_date()
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
        ax2.set_xlim(dates_num[0] - 1, dates_num[-1] + max(int(len(df) * 0.12), 6))
        ax2.set_ylabel('成交量', color=self._fg, fontsize=9)
        ax2.tick_params(colors=self._fg, labelsize=7)
        ax2.grid(True, alpha=0.15, color=self._grid, linewidth=0.5)

        # ── 共用 X 軸刻度旋轉 ─────────────────────────────────────
        for tick in ax1.get_xticklabels():
            tick.set_rotation(30)
            tick.set_color(self._fg)
        for tick in ax2.get_xticklabels():
            tick.set_rotation(30)
            tick.set_color(self._fg)

        plt.tight_layout(h_pad=0.3)

        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight',
                        facecolor=self._bg)
            print(f"圖表已儲存：{save_path}")

        if show:
            plt.show()

        return fig
