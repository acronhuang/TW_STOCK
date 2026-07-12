"""
SenVision 核心分析引擎

提供可被多個腳本重複使用的純函式：
    - analyze_timeframe(): 對單支股票的單一時間框架執行全套分析
    - score_signal(): 計算技術訊號的綜合評分

以上函式不依賴 MongoDB，只接受 DataFrame，確保可單元測試。

Author: SenVision Team
Date: 2026-02-24
"""

from __future__ import annotations

import logging
import math
from typing import Dict, List, Optional, Any

import pandas as pd

logger = logging.getLogger(__name__)

from .multi_timeframe import (
    resample_ohlcv,
    get_zigzag_threshold,
    get_pattern_width_params,
    TIMEFRAME_CONFIG,
)
from .pattern_detector import (
    Pattern,
    PatternType,
    PatternStatus,
    WBottomDetector,
    MTopDetector,
    TripleBottomDetector,
    TripleTopDetector,
)
from .support_resistance import SRLevel, find_support_resistance
from .trendline import (
    Trendline,
    detect_trendline_break,
    find_ascending_support,
    find_descending_resistance,
)
from .zigzag import Peak, ZigZagIndicator


# 時間框架加分（加法，避免乘法過度放大弱信號）
_TF_BONUS: Dict[str, float] = {
    'D': 0.00,
    'W': 0.05,
    'M': 0.10,
    'Q': 0.15,
    '6M': 0.20,
    'Y': 0.25,
}

# MA 週期設定（日線基準；週線 / 月線 K 線數少，保留短週期）
_MA_PERIODS = [5, 10, 20, 60]

# ── 多/空型態分類（供 lifecycle / score_signal 共用）──────────────────────────
_BULLISH_TYPES = {
    PatternType.W_BOTTOM, PatternType.TRIPLE_BOTTOM,
    PatternType.HEAD_SHOULDERS_BOTTOM, PatternType.FAILED_BREAKDOWN,
    PatternType.FAILED_BREAKDOWN_W, PatternType.FLAG_FALLING,
    PatternType.TRIANGLE_UP,
}
_BEARISH_TYPES = {
    PatternType.M_TOP, PatternType.TRIPLE_TOP,
    PatternType.HEAD_SHOULDERS_TOP, PatternType.FAILED_BREAKOUT,
    PatternType.FAILED_BREAKOUT_HST, PatternType.FLAG_RISING,
    PatternType.TRIANGLE_DOWN,
}


# ── 型態生命週期管理 ─────────────────────────────────────────────────────────

def _apply_lifecycle(patterns: List[Pattern], df: pd.DataFrame,
                     timeframe: str = 'D') -> List[Pattern]:
    """過濾已達標、已停損、或已過期的型態（過期天數隨時間框架調整）。"""
    if not patterns or len(df) == 0:
        return patterns

    current_price = float(df['close'].iloc[-1])
    current_date = pd.to_datetime(df['date'].iloc[-1])

    # 根據時間框架計算過期天數
    cfg = TIMEFRAME_CONFIG.get(timeframe, TIMEFRAME_CONFIG['D'])
    candle_days = cfg.get('candle_width_days', 0.6)
    max_w = cfg.get('max_width_bars', 60)
    forming_expiry = max(180, int(max_w * candle_days * 3))
    breakout_expiry = max(60, int(max_w * candle_days))

    alive: List[Pattern] = []

    for p in patterns:
        # 三路方向判斷：明確多頭 / 明確空頭 / 中性型態用幾何推斷
        if p.pattern_type in _BULLISH_TYPES:
            is_bull = True
        elif p.pattern_type in _BEARISH_TYPES:
            is_bull = False
        else:
            is_bull = p.target > p.neckline  # 中性型態：目標 > 頸線 → 多頭方向

        # 達標檢查
        if is_bull and current_price >= p.target:
            continue
        if not is_bull and current_price <= p.target:
            continue

        # 停損檢查
        if is_bull and current_price <= p.stop_loss:
            continue
        if not is_bull and current_price >= p.stop_loss:
            continue

        # 過期檢查（天數隨時間框架調整）
        age_days = (current_date - p.formation_date).days
        if p.status == PatternStatus.FORMING and age_days > forming_expiry:
            continue
        if p.status == PatternStatus.BREAKOUT and age_days > breakout_expiry:
            continue

        alive.append(p)
    return alive


def _deduplicate_patterns(patterns: List[Pattern]) -> List[Pattern]:
    """去重：同類型+頸線接近(±2%) → 保留 confidence 最高。"""
    if len(patterns) <= 1:
        return patterns
    best: Dict[str, Pattern] = {}
    for p in patterns:
        bucket = round(math.log(max(p.neckline, 0.01)) * 50)  # ~2% per step (log-space)
        key = f'{p.pattern_type.value}_{bucket}'
        if key not in best or p.confidence > best[key].confidence:
            best[key] = p
    return list(best.values())


def _limit_per_type(patterns: List[Pattern], max_per_type: int = 2) -> List[Pattern]:
    """每種型態最多保留 max_per_type 個（取 confidence 最高）。"""
    from collections import defaultdict
    groups: Dict[PatternType, List[Pattern]] = defaultdict(list)
    for p in patterns:
        groups[p.pattern_type].append(p)
    result: List[Pattern] = []
    for plist in groups.values():
        plist.sort(key=lambda x: x.confidence, reverse=True)
        result.extend(plist[:max_per_type])
    return result


def compute_kd_k(df: pd.DataFrame, rsv_period: int = 9) -> Optional[float]:
    """
    計算隨機指標（KD）的 K 值（最新一根）。

    使用台股標準公式：
        RSV = (收盤 - N日最低) / (N日最高 - N日最低) × 100
        K = K前 × (2/3) + RSV × (1/3)     （等效 EMA alpha=1/3）

    Args:
        df: 含 high/low/close 欄的 DataFrame
        rsv_period: RSV 計算週期（預設 9）

    Returns:
        K 值 (0~100)，資料不足時返回 None
    """
    if len(df) < rsv_period:
        return None

    high_max = df['high'].rolling(rsv_period).max()
    low_min  = df['low'].rolling(rsv_period).min()
    denom = (high_max - low_min).replace(0, float('nan'))
    rsv = (df['close'] - low_min) / denom * 100.0
    rsv = rsv.fillna(50.0)  # 無法計算時以 50 中性填充

    k = rsv.ewm(alpha=1 / 3, adjust=False).mean()
    val = float(k.iloc[-1])
    return round(val, 2)


def compute_bb_pct(df: pd.DataFrame,
                   period: int = 20,
                   std_dev: float = 2.0) -> Optional[float]:
    """
    計算布林通道 %B（Bollinger Bands %B）。

    %B = (收盤 - 下軌) / (上軌 - 下軌)
        0 = 下軌（超賣區）  1 = 上軌（超買區）  0.5 = 中軌

    Args:
        df: 含 close 欄的 DataFrame
        period: 移動平均週期（預設 20）
        std_dev: 標準差倍數（預設 2.0）

    Returns:
        %B 值 (通常介於 -0.1 ~ 1.1)，資料不足時返回 None
    """
    if len(df) < period:
        return None

    close = df['close']
    ma    = close.rolling(period).mean()
    std   = close.rolling(period).std(ddof=0)
    upper = ma + std_dev * std
    lower = ma - std_dev * std

    last_close = float(close.iloc[-1])
    last_upper = float(upper.iloc[-1])
    last_lower = float(lower.iloc[-1])

    band_width = last_upper - last_lower
    if band_width <= 0:
        return 0.5  # 帶寬收窄到 0，無意義

    return round((last_close - last_lower) / band_width, 4)


def get_ma_alignment(df: pd.DataFrame) -> str:
    """
    計算收盤價均線排列狀態（蔡森多頭/空頭排列）。

    多頭排列：MA5 > MA10 > MA20 > MA60
    空頭排列：MA5 < MA10 < MA20 < MA60
    其餘：mixed

    Args:
        df: 含 close 欄的 DataFrame（至少 60 根；不足則用最長可用週期）

    Returns:
        'bullish' | 'bearish' | 'mixed'
    """
    close = df['close']
    mas = {}
    for p in _MA_PERIODS:
        if len(close) >= p:
            mas[p] = float(close.rolling(p).mean().iloc[-1])

    if len(mas) < 2:
        return 'mixed'

    periods = sorted(mas)
    values = [mas[p] for p in periods]

    if all(values[i] > values[i + 1] for i in range(len(values) - 1)):
        return 'bullish'
    if all(values[i] < values[i + 1] for i in range(len(values) - 1)):
        return 'bearish'
    return 'mixed'


def analyze_timeframe(
    df_daily: pd.DataFrame,
    stock_id: str,
    timeframe: str,
) -> Optional[Dict[str, Any]]:
    """
    對單支股票的單一時間框架執行全套技術分析。

    Steps:
        1. 重採樣日線 → 目標時間框架
        2. ZigZag 轉折點提取
        3. W底 / M頭 / 三重底 / 三重頂 識別
        4. 支撐壓力強度評估
        5. 趨勢切線識別 + 突破偵測

    Args:
        df_daily: 日線 OHLCV DataFrame（含 date, open, high, low, close, volume）
        stock_id: 股票代碼（用於 Pattern 物件的 stock_id 欄位）
        timeframe: 時間框架代號（'D'/'W'/'M'/'Q'/'6M'/'Y'）

    Returns:
        dict 含 df / peaks / patterns / sr_levels / trendlines
        若 K 線不足（< 15 根）則返回 None
    """
    df = resample_ohlcv(df_daily, timeframe)

    # 過濾無效價格（close=0、high<low 等髒數據）
    for col in ['open', 'high', 'low', 'close']:
        if col in df.columns:
            df = df[df[col] > 0]
    df = df[df['high'] >= df['low']].reset_index(drop=True)

    if len(df) < 15:
        return None

    threshold = get_zigzag_threshold(timeframe)
    min_w, max_w = get_pattern_width_params(timeframe)

    # ZigZag
    zigzag = ZigZagIndicator(threshold=threshold)
    peaks: List[Peak] = zigzag.calculate(df)

    # 形態識別（4 種 senvision 原生偵測器）
    patterns: List[Pattern] = []
    for DetectorCls in (WBottomDetector, MTopDetector,
                         TripleBottomDetector, TripleTopDetector):
        try:
            found = DetectorCls(
                zigzag_threshold=threshold,
                min_pattern_width_days=min_w,
                max_pattern_width_days=max_w,
            ).detect(df, stock_id)
            patterns.extend(found)
        except Exception as e:
            logger.debug(f'{stock_id}/{timeframe} {DetectorCls.__name__} 失敗: {e}')

    # 12 神招額外型態（排除 W底/M頭 避免重複）
    try:
        from .pattern_bridge import detect_12masters_patterns
        p12m_patterns = detect_12masters_patterns(df, stock_id)
        patterns.extend(p12m_patterns)
    except Exception as e:
        logger.debug(f'{stock_id}/{timeframe} Pattern12Masters 失敗: {e}')

    # 支撐壓力（最近 100 根或全部）
    sr_levels: List[SRLevel] = find_support_resistance(
        df, window=min(100, len(df))
    )

    # 趨勢切線 + 突破偵測
    trendlines: List[Trendline] = []
    if len(peaks) >= 2:
        trendlines = (
            find_descending_resistance(peaks) +
            find_ascending_support(peaks)
        )
        trendlines = detect_trendline_break(df, trendlines)

    ma_alignment = get_ma_alignment(df)
    kd_k   = compute_kd_k(df)
    bb_pct = compute_bb_pct(df)

    # 將 formation_date 上限設為日線資料末日（避免週/月重採樣日期超越實際日期）
    daily_end = pd.to_datetime(df_daily['date'].iloc[-1])
    for p in patterns:
        if p.formation_date > daily_end:
            p.formation_date = daily_end

    # 型態生命週期：過濾達標/停損/過期 → 去重 → 限數
    patterns = _apply_lifecycle(patterns, df, timeframe)
    patterns = _deduplicate_patterns(patterns)
    patterns = _limit_per_type(patterns)

    return {
        'df':           df,
        'peaks':        peaks,
        'patterns':     patterns,
        'sr_levels':    sr_levels,
        'trendlines':   trendlines,
        'ma_alignment': ma_alignment,
        'kd_k':         kd_k,    # K 值 (0~100)；None=資料不足
        'bb_pct':       bb_pct,  # %B (0~1)；None=資料不足
    }


def score_signal(
    pattern: Pattern,
    timeframe: str,
    sr_levels: List[SRLevel],
    trendlines: List[Trendline],
    ma_alignment: str = 'mixed',
    per: Optional[float] = None,
    revenue_yoy: Optional[float] = None,
    confluence_timeframes: int = 1,
    kd_k: Optional[float] = None,
    bb_pct: Optional[float] = None,
    roe: Optional[float] = None,
    rsi_14: Optional[float] = None,
    inst_net: Optional[float] = None,
    volume_ratio: Optional[float] = None,
    obv_slope: Optional[float] = None,
    vp_divergence: Optional[int] = None,
    foreign_streak: Optional[int] = None,
    ma_above_long: Optional[int] = None,
    sr_neckline_tolerance: float = 0.02,
) -> float:
    """
    計算單一技術訊號的綜合評分（0 ~ 3.6）

    評分組成（最大原始分 = 2.39，+ 時間框架加分後最高可達 ~2.64）：
        技術面
        - 基礎信心度 (confidence)：          最大 1.0
        - 量能確認加分：                     +0.15
        - 風報比 ≥ 3 加分：                 +0.15（≥2 +0.08）
        - 趨勢切線突破加分：                 +0.12
        - 頸線附近有強支撐壓力：             +0.08
        - 均線多頭/空頭排列加分：             +0.10
        - KD 超賣/超買確認：                +0.10
        - 布林通道 %B 位置確認：             +0.08
        - RSI_14 超賣/超買確認：             +0.08
        基本面（來自 stock_factors / monthly_revenue）
        - 估值合理加分（PER）：              +0.08
        - 月營收動能加分（YoY≥20%）：        +0.10
        - ROE 品質加分（底部 ROE≥15%）：     +0.08
        籌碼面（來自 institutional_flow / TWSE T86）
        - 三大法人合計買超/賣超確認：         +0.12
        量價面（來自 stock_factors / volume_factors）
        - 量比放大確認（爆量配合方向）：       +0.06
        - OBV 資金流向與形態同向：            +0.06
        - 量價背離確認/矛盾：                +0.08 / -0.06
        多框架
        - 多時間框架共振加分（≥3/≥2 TF）：   +0.12/+0.06
        + 時間框架加分（D=0.0 ~ Y=0.25）

    Args:
        pattern: Pattern 物件
        timeframe: 時間框架代號
        sr_levels: 當前 S/R 水平位列表
        trendlines: 切線列表
        ma_alignment: 'bullish' / 'bearish' / 'mixed'
        per: 本益比（stock_factors.pe_ratio）；底部<20 或頂部>40 加分
        revenue_yoy: 月營收年增率 % (monthly_revenue.yoy_growth)
        confluence_timeframes: 同一股票觸發信號的時間框架數
        kd_k: KD 隨機指標 K 值（0~100，由 OHLCV 計算）
        bb_pct: 布林通道 %B（0~1，由 OHLCV 計算）
        roe: 股東權益報酬率 % (stock_factors.roe)；底部 ROE≥15% 加分
        rsi_14: RSI 14 日指標（0~100，stock_factors.rsi_14）
        inst_net: 三大法人合計淨買超股數 (institutional_flow.total_net)
        volume_ratio: 量比 = 當日量/前20日均量 (stock_factors.volume_ratio)；≥1.5 視為放量
        obv_slope: OBV 正規化斜率 (stock_factors.obv_slope)；>0 資金流入、<0 流出
        vp_divergence: 量價背離旗標 (stock_factors.vp_divergence)；-1 空頭背離 / 0 / +1 多頭背離
        sr_neckline_tolerance: 頸線附近 ±% 範圍

    Returns:
        float 評分（越高越好）
    """
    # 三路方向判斷：明確多頭 / 明確空頭 / 中性型態用幾何推斷
    if pattern.pattern_type in _BULLISH_TYPES:
        is_bottom, is_top = True, False
    elif pattern.pattern_type in _BEARISH_TYPES:
        is_bottom, is_top = False, True
    else:
        is_bottom = pattern.target > pattern.neckline
        is_top = not is_bottom

    score = pattern.confidence

    if pattern.volume_confirmed:
        score += 0.15

    rrr = pattern.risk_reward_ratio    # 註：RRR 已改頸線算(真實尺度,反轉型態多 0.7~1.5)，門檻隨之下修
    if rrr >= 1.5:
        score += 0.15
    elif rrr >= 1.0:
        score += 0.08

    # 趨勢切線已突破（方向必須與型態一致）
    if is_bottom and any(tl.is_broken and tl.type == 'descending_resistance' for tl in trendlines):
        score += 0.12
    elif is_top and any(tl.is_broken and tl.type == 'ascending_support' for tl in trendlines):
        score += 0.12

    # 頸線附近有強支撐壓力（±2%）
    neckline = pattern.neckline
    has_strong_sr = neckline > 0 and any(
        sr.strength == 'strong' and
        abs(sr.price - neckline) / neckline <= sr_neckline_tolerance
        for sr in sr_levels
    )
    if has_strong_sr:
        score += 0.08

    # 均線排列與形態方向一致
    if (is_bottom and ma_alignment == 'bullish') or (is_top and ma_alignment == 'bearish'):
        score += 0.10

    # 估值加分：底部形態 PER<20 或頂部形態 PER>40（台股中位 ~15-20）
    if per is not None and per > 0:
        if is_bottom and per < 20:
            score += 0.08
        elif is_top and per > 40:
            score += 0.08

    # 月營收年增率動能：底部形態 YoY>20% 或頂部形態 YoY<-10%
    if revenue_yoy is not None:
        if is_bottom and revenue_yoy >= 20:
            score += 0.10
        elif is_top and revenue_yoy <= -10:
            score += 0.10

    # 多時間框架共振：同一股票在 >=2 個時間框架出現同向信號
    if confluence_timeframes >= 3:
        score += 0.12
    elif confluence_timeframes >= 2:
        score += 0.06

    # KD 隨機指標確認（台股慣用：K<20 超賣 / K>80 超買）
    if kd_k is not None:
        if is_bottom and kd_k < 20:
            score += 0.10   # 底部形態 + KD 超賣 → 強力買進確認
        elif is_top and kd_k > 80:
            score += 0.10   # 頂部形態 + KD 超買 → 強力賣出確認

    # 布林通道 %B 位置確認
    if bb_pct is not None:
        if is_bottom and bb_pct < 0.10:
            score += 0.08   # 底部形態 + 股價貼近下軌 → 超賣確認
        elif is_top and bb_pct > 0.90:
            score += 0.08   # 頂部形態 + 股價貼近上軌 → 超買確認

    # RSI_14 超賣/超買確認（來自 stock_factors.rsi_14）
    if rsi_14 is not None:
        if is_bottom and rsi_14 < 30:
            score += 0.08   # 底部形態 + RSI<30 → 超賣確認
        elif is_top and rsi_14 > 70:
            score += 0.08   # 頂部形態 + RSI>70 → 超買確認

    # ROE 品質加分（底部形態才有意義：好公司跌深更有回升潛力）
    if roe is not None and is_bottom and roe >= 15.0:
        score += 0.08   # ROE≥15% 表示基本面紮實

    # 三大法人籌碼確認（來自 TWSE T86 / institutional_flow）
    if inst_net is not None:
        if is_bottom and inst_net > 0:
            score += 0.12   # 底部形態 + 三大法人合計買超 → 強力多頭確認
        elif is_top and inst_net < 0:
            score += 0.12   # 頂部形態 + 三大法人合計賣超 → 強力空頭確認

    # 量比放量確認（量價配合）：底部放量承接 / 頂部放量出貨
    if volume_ratio is not None and volume_ratio >= 1.5:
        score += 0.06       # 突破/反轉伴隨放量 → 動能與參與度確認

    # OBV 資金流向與形態方向一致
    if obv_slope is not None:
        if is_bottom and obv_slope > 0:
            score += 0.06   # 底部 + 資金持續流入 → 承接力道確認
        elif is_top and obv_slope < 0:
            score += 0.06   # 頂部 + 資金持續流出 → 派發確認

    # 量價背離（既是確認也是警示）
    if vp_divergence is not None and vp_divergence != 0:
        if is_top and vp_divergence == -1:
            score += 0.08   # 頂部 + 空頭背離（價漲量未跟）→ 反轉確認
        elif is_bottom and vp_divergence == 1:
            score += 0.08   # 底部 + 多頭背離（價跌量轉強）→ 底部承接確認
        elif is_bottom and vp_divergence == -1:
            score -= 0.06   # 底部形態卻空頭背離 → 量能不支持，警示扣分
        elif is_top and vp_divergence == 1:
            score -= 0.06   # 頂部形態卻多頭背離 → 矛盾，警示扣分

    # 外資連續買超（回測：連買≥3 → 20日超額+2.5%、勝60%；連賣不顯著故不扣）
    if foreign_streak is not None and foreign_streak >= 3:
        score += 0.05

    # 底部型態的年線位置（回測：底型態+站上年線 20日 +6.1% vs 年線下 +2.9%，差 ~3.15%）
    # 年線下的底型態=空頭弱反彈接刀(爛桶)→扣分；站上年線=多頭回檔買點→小幅加分
    if is_bottom and ma_above_long is not None:
        if ma_above_long == 0:        # 跌破全部長均(季/半年/年線)
            score -= 0.06
        elif ma_above_long >= 2:      # 站上年線(含)以上
            score += 0.04

    # 時間框架加分（加法）
    return round(score + _TF_BONUS.get(timeframe, 0.0), 3)
