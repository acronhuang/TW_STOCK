"""
SenVision 量化形態選股系統 - ZigZag 轉折點提取引擎

ZigZag 算法用於濾除價格雜訊，提取有意義的波峰波谷，
是形態識別的基礎。

Author: SenVision Team
Date: 2026-02-24
"""

import numpy as np
import pandas as pd
from typing import List, Tuple, Optional, Literal
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Peak:
    """轉折點數據結構"""
    index: int              # 在序列中的索引
    date: datetime          # 日期
    price: float            # 價格
    type: Literal['H', 'L'] # H=High(波峰), L=Low(波谷)
    
    def __repr__(self):
        return f"Peak({self.date.strftime('%Y-%m-%d')}, {self.type}, {self.price:.2f})"


class ZigZagIndicator:
    """
    ZigZag 指標計算器
    
    基本原理：
    1. 從序列起點開始，尋找第一個有效轉折點
    2. 轉折點定義：價格變動幅度 >= threshold
    3. 高點後只找低點，低點後只找高點
    4. 持續迭代直到序列結束
    
    使用範例：
    ```python
    zigzag = ZigZagIndicator(threshold=0.05)  # 5% 閾值
    peaks = zigzag.calculate(df)
    
    for peak in peaks:
        print(f"{peak.date}: {peak.type} at {peak.price}")
    ```
    """
    
    def __init__(self, threshold: float = 0.05):
        """
        Args:
            threshold: 最小變動幅度（預設 5%）
                      - 過小：產生過多雜訊轉折點
                      - 過大：錯過重要轉折
                      - 建議範圍：3%-8%
        """
        if threshold <= 0 or threshold >= 1:
            raise ValueError("threshold 必須在 (0, 1) 範圍內")
        
        self.threshold = threshold
    
    def calculate(self, df: pd.DataFrame, 
                  high_col: str = 'high',
                  low_col: str = 'low',
                  date_col: str = 'date') -> List[Peak]:
        """
        計算 ZigZag 轉折點
        
        Args:
            df: DataFrame，必須包含 high、low、date 欄位
            high_col: 最高價欄位名稱
            low_col: 最低價欄位名稱
            date_col: 日期欄位名稱
            
        Returns:
            peaks: 轉折點列表，按時間順序排列
            
        演算法說明：
        1. 尋找第一個有效轉折點（高點或低點）
        2. 高點後尋找低點：price_drop >= threshold
        3. 低點後尋找高點：price_rise >= threshold
        4. 動態更新當前轉折點（回撤時）
        """
        if df.empty:
            return []
        
        if not all(col in df.columns for col in [high_col, low_col, date_col]):
            raise ValueError(f"DataFrame 必須包含 {high_col}, {low_col}, {date_col} 欄位")
        
        highs = df[high_col].values
        lows = df[low_col].values
        dates = pd.to_datetime(df[date_col])
        
        peaks = []
        
        # 初始化：從第一個點開始
        last_peak_idx = 0
        last_peak_price = highs[0]
        last_peak_type = None
        
        # 尋找第一個轉折點
        max_high_idx = 0
        max_high = highs[0]
        min_low_idx = 0
        min_low = lows[0]
        
        for i in range(len(df)):
            # 追蹤區間內的最高點和最低點
            if highs[i] > max_high:
                max_high = highs[i]
                max_high_idx = i
            if lows[i] < min_low:
                min_low = lows[i]
                min_low_idx = i
            
            # 判斷是否形成第一個有效轉折
            high_to_low = (max_high - lows[i]) / max_high if max_high > 0 else 0.0
            low_to_high = (highs[i] - min_low) / min_low if min_low > 0 else 0.0
            
            if high_to_low >= self.threshold:
                # 形成有效下跌，最高點是第一個波峰
                peaks.append(Peak(
                    index=max_high_idx,
                    date=dates.iloc[max_high_idx],
                    price=max_high,
                    type='H'
                ))
                last_peak_idx = i
                last_peak_price = lows[i]
                last_peak_type = 'L'
                break
            elif low_to_high >= self.threshold:
                # 形成有效上漲，最低點是第一個波谷
                peaks.append(Peak(
                    index=min_low_idx,
                    date=dates.iloc[min_low_idx],
                    price=min_low,
                    type='L'
                ))
                last_peak_idx = i
                last_peak_price = highs[i]
                last_peak_type = 'H'
                break
        
        # 如果沒有找到第一個轉折點，返回空列表
        if last_peak_type is None:
            return []
        
        # 繼續尋找後續轉折點
        candidate_peak_idx = last_peak_idx
        candidate_peak_price = last_peak_price
        
        for i in range(last_peak_idx + 1, len(df)):
            if last_peak_type == 'H':
                # 當前在高點，尋找低點
                if lows[i] < candidate_peak_price:
                    # 找到更低的低點，更新候選
                    candidate_peak_idx = i
                    candidate_peak_price = lows[i]
                
                # 檢查是否形成有效轉折
                price_drop = (last_peak_price - candidate_peak_price) / last_peak_price if last_peak_price > 0 else 0.0

                if price_drop >= self.threshold:
                    # 確認低點回升超過閾值，形成有效波谷
                    if candidate_peak_price > 0 and highs[i] - candidate_peak_price >= candidate_peak_price * self.threshold:
                        peaks.append(Peak(
                            index=candidate_peak_idx,
                            date=dates.iloc[candidate_peak_idx],
                            price=candidate_peak_price,
                            type='L'
                        ))
                        last_peak_idx = candidate_peak_idx
                        last_peak_price = candidate_peak_price
                        last_peak_type = 'L'
                        candidate_peak_idx = i
                        candidate_peak_price = highs[i]
            
            else:  # last_peak_type == 'L'
                # 當前在低點，尋找高點
                if highs[i] > candidate_peak_price:
                    # 找到更高的高點，更新候選
                    candidate_peak_idx = i
                    candidate_peak_price = highs[i]
                
                # 檢查是否形成有效轉折
                price_rise = (candidate_peak_price - last_peak_price) / last_peak_price if last_peak_price > 0 else 0.0

                if price_rise >= self.threshold:
                    # 確認高點回落超過閾值，形成有效波峰
                    if candidate_peak_price > 0 and candidate_peak_price - lows[i] >= candidate_peak_price * self.threshold:
                        peaks.append(Peak(
                            index=candidate_peak_idx,
                            date=dates.iloc[candidate_peak_idx],
                            price=candidate_peak_price,
                            type='H'
                        ))
                        last_peak_idx = candidate_peak_idx
                        last_peak_price = candidate_peak_price
                        last_peak_type = 'H'
                        candidate_peak_idx = i
                        candidate_peak_price = lows[i]
        
        return peaks
    
    def calculate_simple(self, prices: np.ndarray) -> List[Tuple[int, float, str]]:
        """
        簡化版 ZigZag 計算（僅使用收盤價）
        
        Args:
            prices: 價格序列（收盤價）
            
        Returns:
            peaks: [(index, price, type), ...]
        """
        if len(prices) == 0:
            return []
        
        peaks = []
        last_peak_price = prices[0]
        last_peak_idx = 0
        last_peak_type = None
        
        # 尋找第一個轉折點
        max_price = prices[0]
        max_idx = 0
        min_price = prices[0]
        min_idx = 0
        
        for i in range(len(prices)):
            if prices[i] > max_price:
                max_price = prices[i]
                max_idx = i
            if prices[i] < min_price:
                min_price = prices[i]
                min_idx = i
            
            # 判斷是否形成有效轉折
            if max_price > 0 and (max_price - prices[i]) / max_price >= self.threshold:
                peaks.append((max_idx, max_price, 'H'))
                last_peak_price = prices[i]
                last_peak_idx = i
                last_peak_type = 'L'
                break
            elif min_price > 0 and (prices[i] - min_price) / min_price >= self.threshold:
                peaks.append((min_idx, min_price, 'L'))
                last_peak_price = prices[i]
                last_peak_idx = i
                last_peak_type = 'H'
                break
        
        if last_peak_type is None:
            return []
        
        # 繼續尋找後續轉折點
        for i in range(last_peak_idx + 1, len(prices)):
            if last_peak_type == 'H':
                if prices[i] < last_peak_price:
                    last_peak_price = prices[i]
                    last_peak_idx = i
                elif last_peak_price > 0 and (prices[i] - last_peak_price) / last_peak_price >= self.threshold:
                    peaks.append((last_peak_idx, last_peak_price, 'L'))
                    last_peak_price = prices[i]
                    last_peak_idx = i
                    last_peak_type = 'L'
            else:  # last_peak_type == 'L'
                if prices[i] > last_peak_price:
                    last_peak_price = prices[i]
                    last_peak_idx = i
                elif last_peak_price > 0 and (last_peak_price - prices[i]) / last_peak_price >= self.threshold:
                    peaks.append((last_peak_idx, last_peak_price, 'H'))
                    last_peak_price = prices[i]
                    last_peak_idx = i
                    last_peak_type = 'H'
        
        return peaks


def plot_zigzag(df: pd.DataFrame, peaks: List[Peak], 
                save_path: Optional[str] = None):
    """
    繪製 ZigZag 圖表
    
    Args:
        df: 原始價格數據
        peaks: ZigZag 轉折點
        save_path: 儲存路徑（可選）
    """
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    
    fig, ax = plt.subplots(figsize=(15, 7))
    
    # 繪製收盤價
    ax.plot(df['date'], df['close'], 
            color='gray', alpha=0.5, linewidth=1, label='收盤價')
    
    # 繪製 ZigZag 線
    peak_dates = [p.date for p in peaks]
    peak_prices = [p.price for p in peaks]
    ax.plot(peak_dates, peak_prices, 
            color='blue', linewidth=2, marker='o', markersize=6, label='ZigZag')
    
    # 標註波峰波谷
    for peak in peaks:
        color = 'red' if peak.type == 'H' else 'green'
        marker = 'v' if peak.type == 'H' else '^'
        ax.scatter(peak.date, peak.price, 
                  color=color, s=100, marker=marker, zorder=5)
        ax.text(peak.date, peak.price, f'{peak.price:.1f}',
               fontsize=9, ha='center', va='bottom' if peak.type == 'L' else 'top')
    
    ax.set_xlabel('日期', fontsize=12)
    ax.set_ylabel('價格', fontsize=12)
    ax.set_title('ZigZag 轉折點分析', fontsize=14, fontweight='bold')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # 格式化日期軸
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    plt.xticks(rotation=45)
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        print(f"✅ 圖表已儲存至 {save_path}")
    else:
        plt.show()


# 測試代碼
if __name__ == '__main__':
    # 生成測試數據
    np.random.seed(42)
    dates = pd.date_range('2024-01-01', periods=100, freq='D')
    
    # 生成有明顯波動的價格序列
    trend = np.linspace(100, 150, 100)
    noise = np.sin(np.linspace(0, 4*np.pi, 100)) * 15
    prices = trend + noise + np.random.randn(100) * 2
    
    df_test = pd.DataFrame({
        'date': dates,
        'open': prices,
        'high': prices + np.random.rand(100) * 2,
        'low': prices - np.random.rand(100) * 2,
        'close': prices,
        'volume': np.random.randint(1000000, 10000000, 100)
    })
    
    # 測試 ZigZag
    print("="*80)
    print("ZigZag 轉折點提取測試")
    print("="*80)
    
    zigzag = ZigZagIndicator(threshold=0.05)
    peaks = zigzag.calculate(df_test)
    
    print(f"\n找到 {len(peaks)} 個轉折點:\n")
    for i, peak in enumerate(peaks, 1):
        print(f"{i}. {peak}")
    
    # 繪製圖表
    print("\n繪製 ZigZag 圖表...")
    plot_zigzag(df_test, peaks, save_path='logs/zigzag_test.png')
    
    print("\n✅ 測試完成")
