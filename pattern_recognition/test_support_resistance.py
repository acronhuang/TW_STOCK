#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
支撐壓力與頸線測試工具
測試並展示新模組的功能

使用範例:
    python3 test_support_resistance.py --symbol 2330
    python3 test_support_resistance.py --symbol 2330 --zigzag
    python3 test_support_resistance.py --symbol 2330 --all

作者: Ming
日期: 2026-02-24
版本: 1.0.0
"""

import sys
import os
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import argparse
import pandas as pd
from datetime import datetime, timedelta
from pymongo import MongoClient
from dotenv import load_dotenv
import logging

from pattern_recognition.support_resistance import (
    PivotIdentifier,
    NecklineDetector,
    TrendlineDetector,
    SupportResistanceDetector
)

# 載入環境變數
load_dotenv()

# 日誌設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_stock_data(symbol: str, days: int = 250) -> pd.DataFrame:
    """從MongoDB取得股票數據"""
    mongo_uri = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/tw_stock_analysis')
    client = MongoClient(mongo_uri)
    db = client['tw_stock_analysis']

    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    cursor = db.stock_price.find({
        'stock_id': symbol,
        'date': {'$gte': start_date, '$lte': end_date}
    }).sort('date', 1)

    data = list(cursor)

    if not data:
        raise ValueError(f"找不到 {symbol} 的數據")

    df = pd.DataFrame(data)

    # 轉換 Decimal128
    for col in ['open', 'high', 'low', 'close', 'volume']:
        if col in df.columns:
            df[col] = df[col].apply(
                lambda x: float(x.to_decimal()) if hasattr(x, 'to_decimal') else (float(x) if x is not None else 0.0)
            )

    df['date'] = pd.to_datetime(df['date'])
    df.sort_values('date', inplace=True)
    df.reset_index(drop=True, inplace=True)

    logger.info(f"成功載入 {symbol} 的 {len(df)} 筆數據")

    return df


def test_pivot_detection(df: pd.DataFrame, symbol: str):
    """測試轉折點識別"""
    print(f"\n{'=' * 80}")
    print(f"1. 轉折點識別測試 - {symbol}")
    print(f"{'=' * 80}\n")

    identifier = PivotIdentifier(order=5, threshold=0.02)

    # 方法1: argrelextrema
    highs, lows = identifier.find_pivots(df)

    print(f"方法1: argrelextrema")
    print(f"  找到 {len(highs)} 個高點")
    print(f"  找到 {len(lows)} 個低點")

    if highs:
        recent_highs = sorted(highs, key=lambda x: x.index, reverse=True)[:5]
        print(f"\n  最近5個高點:")
        for h in recent_highs:
            print(f"    {h.date.strftime('%Y-%m-%d')} │ ${h.price:.2f}")

    if lows:
        recent_lows = sorted(lows, key=lambda x: x.index, reverse=True)[:5]
        print(f"\n  最近5個低點:")
        for l in recent_lows:
            print(f"    {l.date.strftime('%Y-%m-%d')} │ ${l.price:.2f}")

    # 方法2: ZigZag
    print(f"\n方法2: ZigZag (5%波動)")
    zigzag_pivots = identifier.find_zigzag_pivots(df, min_change_pct=0.05)

    print(f"  找到 {len(zigzag_pivots)} 個顯著轉折點")
    if zigzag_pivots:
        recent_pivots = zigzag_pivots[-10:]
        print(f"\n  最近10個轉折點:")
        for p in recent_pivots:
            emoji = "🔺" if p.type == "high" else "🔻"
            print(f"    {emoji} {p.date.strftime('%Y-%m-%d')} │ ${p.price:.2f}")


def test_neckline_detection(df: pd.DataFrame, symbol: str):
    """測試頸線識別"""
    print(f"\n{'=' * 80}")
    print(f"2. 頸線識別測試 - {symbol}")
    print(f"{'=' * 80}\n")

    # 先找轉折點
    identifier = PivotIdentifier(order=5)
    highs, lows = identifier.find_pivots(df)
    all_pivots = highs + lows
    all_pivots.sort(key=lambda x: x.index)

    detector = NecklineDetector(tolerance=0.03)

    # W底頸線
    w_necklines = detector.detect_w_bottom_neckline(df, all_pivots)

    print(f"W底頸線:")
    print(f"  找到 {len(w_necklines)} 個W底頸線\n")

    for i, neck in enumerate(w_necklines[:5], 1):
        status = "✅ 已突破" if neck.is_broken else "⏳ 未突破"
        volume = "📊 量能確認" if neck.breakout_volume_confirmed else ""

        print(f"  {i}. 頸線價格: ${neck.price:.2f} │ {status} {volume}")
        print(f"     左底索引: {neck.left_pivot} │ 中峰索引: {neck.middle_pivot} │ 右底索引: {neck.right_pivot}")
        if neck.breakout_date:
            print(f"     突破日期: {neck.breakout_date.strftime('%Y-%m-%d')}")
        print()

    # M頭頸線
    m_necklines = detector.detect_m_top_neckline(df, all_pivots)

    print(f"M頭頸線:")
    print(f"  找到 {len(m_necklines)} 個M頭頸線\n")

    for i, neck in enumerate(m_necklines[:5], 1):
        status = "✅ 已突破" if neck.is_broken else "⏳ 未突破"
        volume = "📊 量能確認" if neck.breakout_volume_confirmed else ""

        print(f"  {i}. 頸線價格: ${neck.price:.2f} │ {status} {volume}")
        print(f"     左峰索引: {neck.left_pivot} │ 中谷索引: {neck.middle_pivot} │ 右峰索引: {neck.right_pivot}")
        if neck.breakout_date:
            print(f"     突破日期: {neck.breakout_date.strftime('%Y-%m-%d')}")
        print()


def test_trendline_detection(df: pd.DataFrame, symbol: str):
    """測試趨勢線識別"""
    print(f"\n{'=' * 80}")
    print(f"3. 趨勢線識別測試（破切分析）- {symbol}")
    print(f"{'=' * 80}\n")

    # 先找轉折點
    identifier = PivotIdentifier(order=5)
    highs, lows = identifier.find_pivots(df)
    all_pivots = highs + lows

    detector = TrendlineDetector(min_points=2)

    # 下降趨勢線（多方破切）
    desc_lines = detector.detect_descending_trendline(df, all_pivots, lookback=60)

    print(f"下降趨勢線（多方破切機會）:")
    print(f"  找到 {len(desc_lines)} 條下降趨勢線\n")

    for i, line in enumerate(desc_lines[:5], 1):
        status = "✅ 已突破" if line.is_broken else "⏳ 未突破"
        print(f"  {i}. 斜率: {line.slope:.4f} │ 截距: {line.intercept:.2f} │ {status}")
        print(f"     起始: {line.start_date.strftime('%Y-%m-%d')} → {line.end_date.strftime('%Y-%m-%d')}")

        # 計算當前位置的趨勢線價格
        current_idx = len(df) - 1
        trendline_price = line.slope * current_idx + line.intercept
        current_price = df.iloc[-1]['close']
        distance_pct = ((current_price - trendline_price) / trendline_price) * 100

        print(f"     當前價格: ${current_price:.2f} │ 趨勢線價格: ${trendline_price:.2f} │ 距離: {distance_pct:+.2f}%")
        print()

    # 上升趨勢線（空方破切）
    asc_lines = detector.detect_ascending_trendline(df, all_pivots, lookback=60)

    print(f"上升趨勢線（空方破切風險）:")
    print(f"  找到 {len(asc_lines)} 條上升趨勢線\n")

    for i, line in enumerate(asc_lines[:5], 1):
        status = "✅ 已跌破" if line.is_broken else "⏳ 未跌破"
        print(f"  {i}. 斜率: {line.slope:.4f} │ 截距: {line.intercept:.2f} │ {status}")
        print(f"     起始: {line.start_date.strftime('%Y-%m-%d')} → {line.end_date.strftime('%Y-%m-%d')}")

        current_idx = len(df) - 1
        trendline_price = line.slope * current_idx + line.intercept
        current_price = df.iloc[-1]['close']
        distance_pct = ((current_price - trendline_price) / trendline_price) * 100

        print(f"     當前價格: ${current_price:.2f} │ 趨勢線價格: ${trendline_price:.2f} │ 距離: {distance_pct:+.2f}%")
        print()


def test_support_resistance(df: pd.DataFrame, symbol: str):
    """測試支撐壓力識別"""
    print(f"\n{'=' * 80}")
    print(f"4. 支撐壓力識別測試 - {symbol}")
    print(f"{'=' * 80}\n")

    # 先找轉折點
    identifier = PivotIdentifier(order=5)
    highs, lows = identifier.find_pivots(df)
    all_pivots = highs + lows

    detector = SupportResistanceDetector(tolerance=0.01, min_touches=2)

    levels = detector.detect_levels(df, all_pivots, lookback=100)

    print(f"找到 {len(levels)} 個支撐壓力水平\n")

    current_price = df.iloc[-1]['close']

    print(f"當前價格: ${current_price:.2f}\n")

    # 壓力位
    resistances = [l for l in levels if l.type == 'resistance']
    print(f"壓力位 (Resistance) - 共 {len(resistances)} 個:")
    for i, level in enumerate(resistances[:10], 1):
        strength_emoji = "🔥" if level.strength >= 3 else "✅"
        status = "✅ 已突破" if level.is_broken else "⏳ 未突破"
        distance = ((level.price - current_price) / current_price) * 100

        print(f"  {i}. ${level.price:.2f} │ {strength_emoji} 強度: {level.strength} │ {status} │ 距離: +{distance:.1f}%")

    # 支撐位
    supports = [l for l in levels if l.type == 'support']
    print(f"\n支撐位 (Support) - 共 {len(supports)} 個:")
    for i, level in enumerate(supports[:10], 1):
        strength_emoji = "🔥" if level.strength >= 3 else "✅"
        status = "✅ 已跌破" if level.is_broken else "⏳ 未跌破"
        distance = ((current_price - level.price) / level.price) * 100

        print(f"  {i}. ${level.price:.2f} │ {strength_emoji} 強度: {level.strength} │ {status} │ 距離: +{distance:.1f}%")


def main():
    """主程序"""
    parser = argparse.ArgumentParser(description='支撐壓力與頸線測試工具')
    parser.add_argument('-s', '--symbol', type=str, default='2330', help='股票代碼')
    parser.add_argument('--pivots', action='store_true', help='測試轉折點識別')
    parser.add_argument('--necklines', action='store_true', help='測試頸線識別')
    parser.add_argument('--trendlines', action='store_true', help='測試趨勢線識別')
    parser.add_argument('--sr', action='store_true', help='測試支撐壓力識別')
    parser.add_argument('--all', action='store_true', help='測試所有功能')

    args = parser.parse_args()

    # 取得數據
    try:
        df = get_stock_data(args.symbol, days=250)
    except Exception as e:
        print(f"❌ 錯誤: {e}")
        return

    # 顯示基本資訊
    print(f"\n{'=' * 80}")
    print(f"📊 {args.symbol} 支撐壓力與頸線分析")
    print(f"{'=' * 80}")
    print(f"數據期間: {df.iloc[0]['date'].strftime('%Y-%m-%d')} ~ {df.iloc[-1]['date'].strftime('%Y-%m-%d')}")
    print(f"數據筆數: {len(df)} 筆")
    print(f"當前價格: ${df.iloc[-1]['close']:.2f}")
    print(f"最高價格: ${df['high'].max():.2f}")
    print(f"最低價格: ${df['low'].min():.2f}")

    # 執行測試
    if args.all or args.pivots:
        test_pivot_detection(df, args.symbol)

    if args.all or args.necklines:
        test_neckline_detection(df, args.symbol)

    if args.all or args.trendlines:
        test_trendline_detection(df, args.symbol)

    if args.all or args.sr:
        test_support_resistance(df, args.symbol)

    # 如果沒有指定任何測試，執行所有測試
    if not any([args.pivots, args.necklines, args.trendlines, args.sr, args.all]):
        test_pivot_detection(df, args.symbol)
        test_neckline_detection(df, args.symbol)
        test_trendline_detection(df, args.symbol)
        test_support_resistance(df, args.symbol)

    print(f"\n{'=' * 80}")
    print(f"✅ 測試完成！")
    print(f"{'=' * 80}\n")


if __name__ == '__main__':
    main()
