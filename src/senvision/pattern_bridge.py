"""
SenVision ↔ Pattern12Masters 橋接模組

將 pattern_recognition/patterns_12_masters.py 的 PatternSignal 物件
轉換為 senvision Pattern 物件，使 12 神招額外型態能流入
analyze_timeframe() → score_signal() → comprehensive_scan_stock() 管線。

W底 / M頭 已由 senvision 原生偵測器處理，此模組預設排除以避免重複。

Author: SenVision Team
Date: 2026-02-26
"""

from __future__ import annotations

import math
import sys
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set

import numpy as np
import pandas as pd

from .pattern_detector import Pattern, PatternType, PatternStatus
from .zigzag import Peak

logger = logging.getLogger(__name__)

# ── 匯入 Pattern12Masters ───────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_PR_DIR = str(_PROJECT_ROOT / 'pattern_recognition')
if _PR_DIR not in sys.path:
    sys.path.insert(0, _PR_DIR)

from patterns_12_masters import Pattern12Masters, PatternSignal  # noqa: E402

# ── 映射表 ──────────────────────────────────────────────────────────────────

_P12M_TO_PATTERN_TYPE: Dict[str, PatternType] = {
    '破底翻':       PatternType.FAILED_BREAKDOWN,
    '破底翻W底':    PatternType.FAILED_BREAKDOWN_W,
    '下飄旗形':     PatternType.FLAG_FALLING,
    '頭肩底':       PatternType.HEAD_SHOULDERS_BOTTOM,
    '收斂三角形頂': PatternType.TRIANGLE_UP,
    '上飄旗形':     PatternType.FLAG_RISING,
    '假突破':       PatternType.FAILED_BREAKOUT,
    '頭肩頂':       PatternType.HEAD_SHOULDERS_TOP,
    '假突破頭肩頂': PatternType.FAILED_BREAKOUT_HST,
    '收斂三角形底': PatternType.TRIANGLE_DOWN,
}
# W底 / M頭 故意不在此表 → 由 senvision WBottomDetector / MTopDetector 負責

_STATUS_MAP: Dict[str, PatternStatus] = {
    'confirmed': PatternStatus.BREAKOUT,
    'forming':   PatternStatus.FORMING,
    'completed': PatternStatus.CONFIRMED,
}

# ── 單例偵測器 ──────────────────────────────────────────────────────────────
_p12m = Pattern12Masters()


# ── 轉換函式 ────────────────────────────────────────────────────────────────

def _build_key_points(
    signal: PatternSignal,
    df: pd.DataFrame,
) -> Dict[str, Peak]:
    """從 PatternSignal.metadata['pivots'] 建構 Peak 字典。"""
    pivots = signal.metadata.get('pivots', {})
    if not pivots or not isinstance(pivots, dict):
        return {}

    key_points: Dict[str, Peak] = {}
    dates = pd.to_datetime(df['date'])

    for label, idx in pivots.items():
        if idx is None or not isinstance(idx, (int, np.integer)):
            continue
        if idx < 0 or idx >= len(df):
            continue

        # 依標籤名稱推測高/低點
        low_keywords = ('bottom', 'low', 'support', 'breakdown', 'reclaim')
        is_low = any(kw in str(label).lower() for kw in low_keywords)
        peak_type = 'L' if is_low else 'H'
        price = (float(df['low'].iloc[idx])
                 if peak_type == 'L'
                 else float(df['high'].iloc[idx]))

        key_points[label] = Peak(
            index=int(idx),
            date=dates.iloc[idx],
            price=price,
            type=peak_type,
        )

    return key_points


def convert_signal_to_pattern(
    signal: PatternSignal,
    stock_id: str,
    df: pd.DataFrame,
) -> Optional[Pattern]:
    """將 Pattern12Masters 的 PatternSignal 轉換為 senvision Pattern。"""
    pattern_type = _P12M_TO_PATTERN_TYPE.get(signal.pattern_name)
    if pattern_type is None:
        return None  # W底 / M頭 或未知型態 → 跳過

    is_bearish = signal.pattern_type == 'bearish'
    entry = signal.neckline      # 進場參考＝頸線(突破/跌破價)；用現價會在成型中算出假性超高RRR
    target = signal.target_1
    stop_loss = signal.stop_loss

    # 風報比（以頸線為進場點；先驗證方向合理性，不用 abs 掩蓋幾何錯誤）
    if is_bearish and target >= entry:
        rrr = 0.0  # 空頭信號但目標在上方 → 無效
    elif not is_bearish and target <= entry:
        rrr = 0.0  # 多頭信號但目標在下方 → 無效
    else:
        if is_bearish:
            risk = stop_loss - entry
            reward = entry - target
        else:
            risk = entry - stop_loss
            reward = target - entry
        rrr = round(reward / risk, 2) if risk > 0 else 0.0

    # 日期：從 pivots 取最後轉折點日期（避免 detected_date=now() 導致 age=0 或負數）
    last_data_date = pd.to_datetime(df['date'].iloc[-1])
    pivots_meta = signal.metadata.get('pivots', {})
    pivot_indices = [v for v in pivots_meta.values()
                     if isinstance(v, (int, np.integer)) and 0 <= v < len(df)]
    if pivot_indices:
        last_pivot_idx = max(pivot_indices)
        formation_date = pd.to_datetime(df['date'].iloc[last_pivot_idx])
    else:
        # 無 pivot 資訊時，使用資料最後日期（detected_date 通常是 datetime.now()，不可靠）
        formation_date = last_data_date

    breakout_date = None
    bd_str = signal.metadata.get('breakout_date')
    if bd_str:
        try:
            breakout_date = pd.to_datetime(bd_str)
        except Exception:
            pass

    status = _STATUS_MAP.get(signal.status, PatternStatus.FORMING)

    # FORMING 階段不應有量能確認（量能只在突破 bar 有意義）
    vol_confirmed = signal.volume_confirmation if status != PatternStatus.FORMING else False

    return Pattern(
        stock_id=stock_id,
        pattern_type=pattern_type,
        neckline=signal.neckline,
        target=signal.target_1,
        stop_loss=signal.stop_loss,
        risk_reward_ratio=rrr,
        key_points=_build_key_points(signal, df),
        formation_date=formation_date,
        breakout_date=breakout_date,
        current_price=current_price,
        status=status,
        volume_confirmed=vol_confirmed,
        confidence=signal.confidence,
    )


# ── 主入口 ──────────────────────────────────────────────────────────────────

def detect_12masters_patterns(
    df: pd.DataFrame,
    stock_id: str,
    exclude_names: Optional[Set[str]] = None,
) -> List[Pattern]:
    """
    執行 Pattern12Masters 偵測，回傳 senvision Pattern 列表。

    Args:
        df: OHLCV DataFrame（需含 date, open, high, low, close, volume）
        stock_id: 股票代碼
        exclude_names: 要排除的型態名稱（預設 {'W底', 'M頭'}）

    Returns:
        轉換後的 senvision Pattern 物件列表
    """
    if exclude_names is None:
        exclude_names = {'W底', 'M頭'}

    try:
        signals = _p12m.scan_all_patterns(df, stock_id)
    except Exception as e:
        logger.debug(f'{stock_id}: Pattern12Masters 偵測失敗: {e}')
        return []

    patterns: List[Pattern] = []
    for sig in signals:
        if sig.pattern_name in exclude_names:
            continue
        pattern = convert_signal_to_pattern(sig, stock_id, df)
        if pattern is not None:
            patterns.append(pattern)

    # 去重：同一 PatternType + 頸線接近（±2%）只保留信心度最高的
    return _deduplicate(patterns)


def _deduplicate(patterns: List[Pattern]) -> List[Pattern]:
    """去除同類型、同頸線的重複型態。"""
    if len(patterns) <= 1:
        return patterns

    best: Dict[str, Pattern] = {}
    for p in patterns:
        # 用 (pattern_type, 對數空間 ~2% per step) 作為 key
        bucket = round(math.log(max(p.neckline, 0.01)) * 50)
        key = f'{p.pattern_type.value}_{bucket}'
        if key not in best or p.confidence > best[key].confidence:
            best[key] = p

    return list(best.values())
