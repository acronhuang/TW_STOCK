"""形態識別 — 型別定義（PatternType / PatternStatus / Pattern）。

自 pattern_detector.py 拆分而來（Phase 3 上帝模組拆分）。
"""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from ..zigzag import Peak


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
    key_points: dict[str, Peak]
    formation_date: datetime
    breakout_date: datetime | None = None
    current_price: float | None = None
    status: PatternStatus = PatternStatus.FORMING
    volume_confirmed: bool = False
    confidence: float = 0.0
    
    def __repr__(self):
        return (f"Pattern({self.stock_id}, {self.pattern_type.value}, "
                f"頸線={self.neckline:.2f}, 目標={self.target:.2f}, "
                f"風報比={self.risk_reward_ratio:.2f}, 狀態={self.status.value})")
    
    def to_dict(self) -> dict[str, Any]:
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


