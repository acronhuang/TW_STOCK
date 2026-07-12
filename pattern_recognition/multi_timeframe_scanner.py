#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多時間週期形態掃描器（整合支撐壓力與頸線驗證）
整合12神招形態識別，支援多時間週期共振分析，並使用支撐壓力與頸線模組進行雙重驗證

使用範例:
    python3 multi_timeframe_scanner.py --symbol 2330
    python3 multi_timeframe_scanner.py --symbol 2330 --timeframes D W M
    python3 multi_timeframe_scanner.py --symbol 2330 --timeframes W M --min-confidence 0.80

作者: Ming
日期: 2026-02-24
版本: 2.0.0 (整合支撐壓力驗證)
"""

import sys
import os
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import argparse
import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from pymongo import MongoClient
from dotenv import load_dotenv
import logging

from pattern_recognition.timeframe_converter import TimeframeConverter
from pattern_recognition.patterns_12_masters import Pattern12Masters, PatternSignal
from pattern_recognition.multi_timeframe_analysis import MultiTimeframeAnalyzer
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


class MultiTimeframePatternScanner:
    """多時間週期形態掃描器"""

    def __init__(self, mongo_uri: str = None):
        """
        初始化掃描器

        參數:
            mongo_uri: MongoDB 連接字串
        """
        if mongo_uri is None:
            mongo_uri = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/tw_stock_analysis')

        self.client = MongoClient(mongo_uri)
        self.db = self.client['tw_stock_analysis']
        self.converter = TimeframeConverter()
        self.pattern_detector = Pattern12Masters()
        self.analyzer = MultiTimeframeAnalyzer(mongo_uri)

        # 支撐壓力與頸線識別模組
        self.pivot_identifier = PivotIdentifier(order=5, threshold=0.02)
        self.neckline_detector = NecklineDetector(tolerance=0.03)
        self.trendline_detector = TrendlineDetector(min_points=2)
        self.sr_detector = SupportResistanceDetector(tolerance=0.02, min_touches=2)

    def scan_multi_timeframe(
        self,
        symbol: str,
        timeframes: List[str] = ['D', 'W', 'M'],
        min_confidence: float = 0.75
    ) -> Dict[str, List[PatternSignal]]:
        """
        掃描多個時間週期的形態

        參數:
            symbol: 股票代碼
            timeframes: 時間週期列表
            min_confidence: 最小信心度過濾

        返回:
            各時間週期的形態信號 {timeframe: [signals]}
        """
        results = {}

        # 取得日線數據
        daily_data = self.analyzer.get_daily_data(symbol, days=500)

        if daily_data is None or len(daily_data) == 0:
            logger.error(f"無法獲取 {symbol} 的數據")
            return results

        # 掃描各時間週期
        for tf in timeframes:
            try:
                # 轉換時間週期
                if tf == 'D':
                    df_tf = daily_data.copy()
                else:
                    df_tf = self.converter.convert_timeframe(daily_data, tf)

                if df_tf is None or len(df_tf) == 0:
                    logger.warning(f"時間週期 {tf} 轉換失敗")
                    continue

                # 檢查數據量是否足夠
                min_bars = {
                    'D': 60,
                    'W': 20,
                    'M': 12,
                    'Q': 8,
                    '6M': 6,
                    'Y': 5
                }

                if len(df_tf) < min_bars.get(tf, 20):
                    logger.warning(
                        f"時間週期 {tf} 數據量不足: "
                        f"{len(df_tf)} < {min_bars.get(tf, 20)}"
                    )
                    continue

                # 掃描形態
                signals = self.pattern_detector.scan_all_patterns(df_tf, symbol)

                # 過濾信心度
                filtered_signals = [
                    s for s in signals
                    if s.confidence >= min_confidence
                ]

                # 使用支撐壓力模組進行驗證和增強
                if filtered_signals:
                    enhanced_signals, sr_info = self.validate_and_enhance_signals(
                        df_tf,
                        filtered_signals,
                        timeframe=tf
                    )

                    # 再次過濾（增強後信心度可能更高）
                    final_signals = [
                        s for s in enhanced_signals
                        if s.confidence >= min_confidence
                    ]

                    if final_signals:
                        results[tf] = final_signals
                        logger.info(
                            f"時間週期 {tf}: 找到 {len(final_signals)} 個形態信號 "
                            f"(頸線驗證: {sr_info['necklines_detected']}, "
                            f"支撐: {len(sr_info['support_levels'])}, "
                            f"壓力: {len(sr_info['resistance_levels'])})"
                        )

            except Exception as e:
                logger.error(f"掃描時間週期 {tf} 失敗: {e}")

        return results

    def validate_and_enhance_signals(
        self,
        df: pd.DataFrame,
        signals: List[PatternSignal],
        timeframe: str = 'D'
    ) -> Tuple[List[PatternSignal], Dict]:
        """
        使用支撐壓力與頸線模組驗證並增強形態信號

        參數:
            df: 價格數據
            signals: 形態信號列表
            timeframe: 時間週期

        返回:
            (增強後的信號列表, 支撐壓力資訊)
        """
        enhanced_signals = []
        sr_info = {
            'support_levels': [],
            'resistance_levels': [],
            'necklines_detected': 0,
            'trendlines_detected': 0
        }

        try:
            # 1. 識別轉折點
            highs, lows = self.pivot_identifier.find_pivots(df)
            all_pivots = highs + lows
            all_pivots.sort(key=lambda x: x.index)

            if not all_pivots:
                logger.warning(f"時間週期 {timeframe}: 未找到轉折點，跳過驗證")
                return signals, sr_info

            # 2. 檢測頸線
            w_necklines = self.neckline_detector.detect_w_bottom_neckline(df, all_pivots)
            m_necklines = self.neckline_detector.detect_m_top_neckline(df, all_pivots)
            sr_info['necklines_detected'] = len(w_necklines) + len(m_necklines)

            # 3. 檢測支撐壓力位
            sr_levels = self.sr_detector.detect_levels(df, all_pivots, lookback=100)
            current_price = df.iloc[-1]['close']

            # 分類支撐壓力
            for level in sr_levels:
                level_dict = {
                    'price': level.price,
                    'strength': level.strength,
                    'is_broken': level.is_broken,
                    'distance_pct': ((level.price - current_price) / current_price) * 100
                }

                if level.type == 'support':
                    sr_info['support_levels'].append(level_dict)
                else:
                    sr_info['resistance_levels'].append(level_dict)

            # 4. 驗證形態信號
            for signal in signals:
                enhanced_signal = signal

                # W底驗證
                if signal.pattern_name in ['W底', '破底翻W底']:
                    for neck in w_necklines:
                        # 檢查頸線價格是否匹配（容許3%誤差）
                        if abs(neck.price - signal.neckline) / signal.neckline < 0.03:
                            enhanced_signal.confidence = min(signal.confidence + 0.05, 1.0)
                            logger.info(
                                f"✅ 雙重確認: {signal.pattern_name} + 頸線驗證 "
                                f"(信心度 {signal.confidence*100:.0f}% → {enhanced_signal.confidence*100:.0f}%)"
                            )

                            # 如果有突破且量能確認，再提高信心度
                            if neck.is_broken and neck.breakout_volume_confirmed:
                                enhanced_signal.confidence = min(enhanced_signal.confidence + 0.03, 1.0)
                                logger.info(f"✅ 突破量能確認 (信心度 → {enhanced_signal.confidence*100:.0f}%)")
                            break

                # M頭驗證
                elif signal.pattern_name in ['M頭', '頭肩頂']:
                    for neck in m_necklines:
                        if abs(neck.price - signal.neckline) / signal.neckline < 0.03:
                            enhanced_signal.confidence = min(signal.confidence + 0.05, 1.0)
                            logger.info(
                                f"✅ 雙重確認: {signal.pattern_name} + 頸線驗證 "
                                f"(信心度 {signal.confidence*100:.0f}% → {enhanced_signal.confidence*100:.0f}%)"
                            )

                            if neck.is_broken and neck.breakout_volume_confirmed:
                                enhanced_signal.confidence = min(enhanced_signal.confidence + 0.03, 1.0)
                                logger.info(f"✅ 跌破量能確認 (信心度 → {enhanced_signal.confidence*100:.0f}%)")
                            break

                enhanced_signals.append(enhanced_signal)

        except Exception as e:
            logger.warning(f"驗證信號時發生錯誤: {e}")
            return signals, sr_info

        return enhanced_signals, sr_info


    def analyze_resonance(
        self,
        signals: Dict[str, List[PatternSignal]]
    ) -> Dict:
        """
        分析多時間週期共振

        參數:
            signals: 各時間週期的形態信號

        返回:
            共振分析結果
        """
        if not signals:
            return {
                'resonance_type': 'none',
                'strength': 0.0,
                'description': '無信號'
            }

        # 統計各類型信號數量
        bullish_count = 0
        bearish_count = 0
        total_count = 0

        for tf, sigs in signals.items():
            for sig in sigs:
                total_count += 1
                if sig.pattern_type == 'bullish':
                    bullish_count += 1
                elif sig.pattern_type == 'bearish':
                    bearish_count += 1

        if total_count == 0:
            return {
                'resonance_type': 'none',
                'strength': 0.0,
                'description': '無信號'
            }

        # 計算共振強度
        bullish_strength = bullish_count / total_count
        bearish_strength = bearish_count / total_count

        # 判定共振類型
        if bullish_strength >= 0.8:
            resonance_type = 'strong_bullish'
            description = f'🔥 強勢多頭共振 ({bullish_strength*100:.0f}%)！多個時間週期確認多頭信號，可信度極高。'
        elif bullish_strength >= 0.6:
            resonance_type = 'bullish'
            description = f'📈 多頭共振 ({bullish_strength*100:.0f}%)。多數時間週期支持多頭，建議順勢操作。'
        elif bearish_strength >= 0.8:
            resonance_type = 'strong_bearish'
            description = f'❄️ 強勢空頭共振 ({bearish_strength*100:.0f}%)！多個時間週期確認空頭信號，謹慎為上。'
        elif bearish_strength >= 0.6:
            resonance_type = 'bearish'
            description = f'📉 空頭共振 ({bearish_strength*100:.0f}%)。多數時間週期支持空頭，注意風險。'
        else:
            resonance_type = 'divergent'
            description = f'⚠️ 信號分歧 (多:{bullish_strength*100:.0f}% 空:{bearish_strength*100:.0f}%)。建議觀望或小倉位測試。'

        return {
            'resonance_type': resonance_type,
            'strength': max(bullish_strength, bearish_strength),
            'bullish_count': bullish_count,
            'bearish_count': bearish_count,
            'total_count': total_count,
            'description': description
        }

    def print_multi_timeframe_report(
        self,
        symbol: str,
        signals: Dict[str, List[PatternSignal]],
        resonance: Dict
    ):
        """
        打印多時間週期報告

        參數:
            symbol: 股票代碼
            signals: 形態信號
            resonance: 共振分析結果
        """
        print(f"\n{'=' * 80}")
        print(f"📊 {symbol} 多時間週期形態分析報告")
        print(f"{'=' * 80}\n")

        if not signals:
            print("❌ 未檢測到任何形態信號")
            return

        # 按時間週期顯示
        for tf, sigs in sorted(signals.items()):
            tf_name = TimeframeConverter.TIMEFRAMES.get(tf, tf)

            print(f"【{tf_name}】")

            for i, sig in enumerate(sigs, 1):
                # 形態名稱和類型
                if sig.pattern_type == 'bullish':
                    emoji = '📈'
                    type_text = '多頭'
                else:
                    emoji = '📉'
                    type_text = '空頭'

                print(f"  {i}. {sig.pattern_name} {emoji} {type_text}")
                print(f"     當前價格: {sig.current_price:.2f}")
                print(f"     頸線: {sig.neckline:.2f}")

                # 目標價
                if sig.pattern_type == 'bullish':
                    gain1 = ((sig.target_1 - sig.current_price) / sig.current_price) * 100
                    print(f"     目標1: {sig.target_1:.2f} ({gain1:+.2f}%)")

                    if sig.target_2:
                        gain2 = ((sig.target_2 - sig.current_price) / sig.current_price) * 100
                        print(f"     目標2: {sig.target_2:.2f} ({gain2:+.2f}%)")
                else:
                    gain1 = ((sig.current_price - sig.target_1) / sig.current_price) * 100
                    print(f"     目標1: {sig.target_1:.2f} (規避跌幅 {gain1:.2f}%)")

                    if sig.target_2:
                        gain2 = ((sig.current_price - sig.target_2) / sig.current_price) * 100
                        print(f"     目標2: {sig.target_2:.2f} (規避跌幅 {gain2:.2f}%)")

                # 止損
                print(f"     止損: {sig.stop_loss:.2f}")

                # 風報比
                if sig.risk_reward > 0:
                    print(f"     風報比: {sig.risk_reward:.2f}")

                # 信心度
                print(f"     信心度: {sig.confidence*100:.0f}%")

                # 結構強度
                if sig.structure_score > 0:
                    print(f"     結構強度: {sig.structure_score}/8")

                print()

        # 共振分析
        print(f"{'=' * 80}")
        print(f"🔄 多時間週期共振分析")
        print(f"{'=' * 80}\n")
        print(resonance['description'])
        print()
        print(f"  多頭信號: {resonance['bullish_count']}")
        print(f"  空頭信號: {resonance['bearish_count']}")
        print(f"  共振強度: {resonance['strength']*100:.0f}%")
        print()

    def get_trading_suggestion(
        self,
        signals: Dict[str, List[PatternSignal]],
        resonance: Dict
    ) -> Dict:
        """
        基於多時間週期分析給出交易建議

        參數:
            signals: 形態信號
            resonance: 共振分析

        返回:
            交易建議
        """
        suggestion = {
            'action': 'wait',  # buy, sell, wait
            'position_size': 0.0,  # 0.0 - 1.0
            'entry_price': None,
            'stop_loss': None,
            'targets': [],
            'timeframe': None,
            'reason': ''
        }

        if not signals or resonance['strength'] < 0.6:
            suggestion['reason'] = '信號不足或分歧，建議觀望'
            return suggestion

        resonance_type = resonance['resonance_type']

        # 強勢多頭共振
        if resonance_type == 'strong_bullish':
            suggestion['action'] = 'buy'
            suggestion['position_size'] = 1.0

            # 找最大週期的信號作為主要依據
            tf_priority = ['Y', '6M', 'Q', 'M', 'W', 'D']
            for tf in tf_priority:
                if tf in signals and signals[tf]:
                    sig = signals[tf][0]  # 取第一個信號
                    suggestion['entry_price'] = sig.neckline
                    suggestion['stop_loss'] = sig.stop_loss
                    suggestion['targets'] = [sig.target_1, sig.target_2] if sig.target_2 else [sig.target_1]
                    suggestion['timeframe'] = tf
                    break

            suggestion['reason'] = f'多時間週期強勢多頭共振({resonance["strength"]*100:.0f}%)，建議全倉進場'

        # 一般多頭共振
        elif resonance_type == 'bullish':
            suggestion['action'] = 'buy'
            suggestion['position_size'] = 0.5

            # 找週線或月線信號
            for tf in ['M', 'W', 'D']:
                if tf in signals and signals[tf]:
                    sig = signals[tf][0]
                    suggestion['entry_price'] = sig.neckline
                    suggestion['stop_loss'] = sig.stop_loss
                    suggestion['targets'] = [sig.target_1]
                    suggestion['timeframe'] = tf
                    break

            suggestion['reason'] = f'多頭共振({resonance["strength"]*100:.0f}%)，建議半倉進場'

        # 強勢空頭共振
        elif resonance_type == 'strong_bearish':
            suggestion['action'] = 'sell'
            suggestion['position_size'] = 1.0
            suggestion['reason'] = f'多時間週期強勢空頭共振({resonance["strength"]*100:.0f}%)，建議出清持股'

        # 一般空頭共振
        elif resonance_type == 'bearish':
            suggestion['action'] = 'sell'
            suggestion['position_size'] = 0.5
            suggestion['reason'] = f'空頭共振({resonance["strength"]*100:.0f}%)，建議減倉或觀望'

        # 信號分歧
        else:
            suggestion['reason'] = '時間週期信號分歧，建議觀望'

        return suggestion


def main():
    """主程序"""
    parser = argparse.ArgumentParser(description='多時間週期形態掃描器')
    parser.add_argument(
        '-s', '--symbol',
        type=str,
        required=True,
        help='股票代碼'
    )
    parser.add_argument(
        '-t', '--timeframes',
        type=str,
        nargs='+',
        default=['D', 'W', 'M'],
        help='時間週期列表（預設: D W M）'
    )
    parser.add_argument(
        '--min-confidence',
        type=float,
        default=0.75,
        help='最小信心度（預設: 0.75）'
    )
    parser.add_argument(
        '--show-suggestion',
        action='store_true',
        help='顯示交易建議'
    )

    args = parser.parse_args()

    # 建立掃描器
    scanner = MultiTimeframePatternScanner()

    # 掃描
    print(f"\n🔍 掃描 {args.symbol} 的多時間週期形態...")
    print(f"   時間週期: {', '.join(args.timeframes)}")
    print(f"   最小信心度: {args.min_confidence*100:.0f}%\n")

    signals = scanner.scan_multi_timeframe(
        symbol=args.symbol,
        timeframes=args.timeframes,
        min_confidence=args.min_confidence
    )

    if not signals:
        print("❌ 未檢測到符合條件的形態信號")
        return

    # 共振分析
    resonance = scanner.analyze_resonance(signals)

    # 打印報告
    scanner.print_multi_timeframe_report(args.symbol, signals, resonance)

    # 交易建議
    if args.show_suggestion:
        suggestion = scanner.get_trading_suggestion(signals, resonance)

        print(f"{'=' * 80}")
        print(f"💡 交易建議")
        print(f"{'=' * 80}\n")

        action_emoji = {
            'buy': '🟢 買入',
            'sell': '🔴 賣出',
            'wait': '⚪ 觀望'
        }

        print(f"  操作: {action_emoji.get(suggestion['action'], suggestion['action'])}")
        print(f"  倉位: {suggestion['position_size']*100:.0f}%")

        if suggestion['entry_price']:
            print(f"  進場價: {suggestion['entry_price']:.2f}")
        if suggestion['stop_loss']:
            print(f"  止損價: {suggestion['stop_loss']:.2f}")
        if suggestion['targets']:
            for i, target in enumerate(suggestion['targets'], 1):
                print(f"  目標{i}: {target:.2f}")
        if suggestion['timeframe']:
            tf_name = TimeframeConverter.TIMEFRAMES.get(suggestion['timeframe'])
            print(f"  依據週期: {tf_name}")

        print(f"\n  理由: {suggestion['reason']}")
        print()

    print(f"{'=' * 80}")
    print(f"✅ 掃描完成！")
    print(f"{'=' * 80}\n")


if __name__ == '__main__':
    main()
