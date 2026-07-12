#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全市場多時間週期形態掃描器
掃描所有台股，找出最佳交易機會

使用範例:
    python3 market_multi_timeframe_scanner.py
    python3 market_multi_timeframe_scanner.py --timeframes W M
    python3 market_multi_timeframe_scanner.py --timeframes D W --min-resonance 0.80 --top 50
    python3 market_multi_timeframe_scanner.py --industry 半導體 --timeframes W M

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
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from pymongo import MongoClient
from dotenv import load_dotenv
import logging
import json
from tqdm import tqdm

from pattern_recognition.timeframe_converter import TimeframeConverter
from pattern_recognition.multi_timeframe_scanner import MultiTimeframePatternScanner

# 載入環境變數
load_dotenv()

# 日誌設定
logging.basicConfig(
    level=logging.WARNING,  # 減少日誌輸出
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MarketMultiTimeframeScanner:
    """全市場多時間週期掃描器"""

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
        self.scanner = MultiTimeframePatternScanner(mongo_uri)

    def get_stock_list(
        self,
        industry: Optional[str] = None,
        exclude_suspended: bool = True
    ) -> List[Dict]:
        """
        獲取股票清單

        參數:
            industry: 產業類別過濾
            exclude_suspended: 排除處置股和全額交割股

        返回:
            股票清單
        """
        query = {}

        # 產業過濾
        if industry:
            query['industry_category'] = {'$regex': industry}

        # 排除處置股和全額交割股
        if exclude_suspended:
            query['$or'] = [
                {'stock_name': {'$not': {'$regex': '處置|全額|KY-'}}},
                {'stock_name': {'$exists': True}}
            ]

        try:
            stocks = list(self.db.taiwan_stock_info.find(query, {
                'stock_id': 1,
                'stock_name': 1,
                'industry_category': 1,
                '_id': 0
            }))

            logger.info(f"找到 {len(stocks)} 支股票")
            return stocks

        except Exception as e:
            logger.error(f"獲取股票清單失敗: {e}")
            return []

    def scan_market(
        self,
        timeframes: List[str] = ['D', 'W', 'M'],
        min_confidence: float = 0.75,
        min_resonance: float = 0.60,
        industry: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Dict]:
        """
        掃描全市場

        參數:
            timeframes: 時間週期列表
            min_confidence: 最小信心度
            min_resonance: 最小共振強度
            industry: 產業類別過濾
            limit: 限制掃描股票數量

        返回:
            交易機會列表
        """
        # 獲取股票清單
        stock_list = self.get_stock_list(industry=industry)

        if limit:
            stock_list = stock_list[:limit]

        if not stock_list:
            print("❌ 沒有找到符合條件的股票")
            return []

        print(f"\n🔍 開始掃描 {len(stock_list)} 支股票...")
        print(f"   時間週期: {', '.join(timeframes)}")
        print(f"   最小信心度: {min_confidence*100:.0f}%")
        print(f"   最小共振強度: {min_resonance*100:.0f}%\n")

        opportunities = []

        # 使用進度條
        for stock in tqdm(stock_list, desc="掃描中", ncols=100):
            symbol = stock['stock_id']
            name = stock['stock_name']

            try:
                # 掃描形態
                signals = self.scanner.scan_multi_timeframe(
                    symbol=symbol,
                    timeframes=timeframes,
                    min_confidence=min_confidence
                )

                if not signals:
                    continue

                # 共振分析
                resonance = self.scanner.analyze_resonance(signals)

                # 過濾共振強度
                if resonance['strength'] < min_resonance:
                    continue

                # 交易建議
                suggestion = self.scanner.get_trading_suggestion(signals, resonance)

                # 計算統計
                total_signals = sum(len(sigs) for sigs in signals.values())
                bullish_signals = sum(
                    len([s for s in sigs if s.pattern_type == 'bullish'])
                    for sigs in signals.values()
                )
                bearish_signals = sum(
                    len([s for s in sigs if s.pattern_type == 'bearish'])
                    for sigs in signals.values()
                )

                # 找出主要信號（選擇最大週期的第一個信號）
                main_signal = None
                for tf in ['Y', '6M', 'Q', 'M', 'W', 'D']:
                    if tf in signals and signals[tf]:
                        main_signal = signals[tf][0]
                        break

                if main_signal:
                    opportunity = {
                        'symbol': symbol,
                        'name': name,
                        'industry': stock.get('industry_category', 'N/A'),
                        'resonance_type': resonance['resonance_type'],
                        'resonance_strength': resonance['strength'],
                        'total_signals': total_signals,
                        'bullish_signals': bullish_signals,
                        'bearish_signals': bearish_signals,
                        'action': suggestion['action'],
                        'position_size': suggestion['position_size'],
                        'current_price': main_signal.current_price,
                        'entry_price': main_signal.neckline,
                        'stop_loss': main_signal.stop_loss,
                        'target_1': main_signal.target_1,
                        'target_2': main_signal.target_2,
                        'risk_reward': main_signal.risk_reward,
                        'pattern_name': main_signal.pattern_name,
                        'pattern_type': main_signal.pattern_type,
                        'confidence': main_signal.confidence,
                        'timeframe': suggestion.get('timeframe', 'D'),
                        'detected_timeframes': list(signals.keys()),
                        'reason': suggestion['reason']
                    }

                    opportunities.append(opportunity)

            except Exception as e:
                logger.debug(f"掃描 {symbol} 失敗: {e}")
                continue

        return opportunities

    def print_opportunities_report(
        self,
        opportunities: List[Dict],
        top: int = 20
    ):
        """
        打印交易機會報告

        參數:
            opportunities: 交易機會列表
            top: 顯示前幾名
        """
        if not opportunities:
            print("\n❌ 未找到符合條件的交易機會")
            return

        # 排序（按共振強度降序）
        sorted_opps = sorted(
            opportunities,
            key=lambda x: x['resonance_strength'],
            reverse=True
        )[:top]

        print(f"\n{'=' * 100}")
        print(f"📊 全市場多時間週期形態分析報告 - Top {min(top, len(opportunities))}")
        print(f"{'=' * 100}\n")

        print(f"總共找到 {len(opportunities)} 個交易機會\n")

        # 統計
        bullish_count = len([o for o in opportunities if o['pattern_type'] == 'bullish'])
        bearish_count = len([o for o in opportunities if o['pattern_type'] == 'bearish'])
        strong_resonance = len([o for o in opportunities if o['resonance_strength'] >= 0.8])

        print(f"📈 多頭機會: {bullish_count}")
        print(f"📉 空頭機會: {bearish_count}")
        print(f"🔥 強勢共振(≥80%): {strong_resonance}\n")

        print(f"{'=' * 100}")
        print(f"排名 | 代碼 | 股票名稱      | 產業      | 型態      | 共振 | 動作 | 當前價 | 目標價 | 風報比 | 理由")
        print(f"{'=' * 100}")

        for i, opp in enumerate(sorted_opps, 1):
            # 動作emoji
            action_emoji = {
                'buy': '🟢',
                'sell': '🔴',
                'wait': '⚪'
            }.get(opp['action'], '⚪')

            # 共振emoji
            if opp['resonance_strength'] >= 0.8:
                resonance_emoji = '🔥'
            elif opp['resonance_strength'] >= 0.6:
                resonance_emoji = '✅'
            else:
                resonance_emoji = '⚠️'

            print(
                f"{i:3d}  | {opp['symbol']:4s} | "
                f"{opp['name'][:8]:8s} | "
                f"{opp['industry'][:8]:8s} | "
                f"{opp['pattern_name'][:8]:8s} | "
                f"{resonance_emoji} {opp['resonance_strength']*100:3.0f}% | "
                f"{action_emoji} {opp['action']:4s} | "
                f"{opp['current_price']:6.1f} | "
                f"{opp['target_1']:6.1f} | "
                f"{opp['risk_reward']:4.1f} | "
                f"{opp['reason'][:30]}"
            )

        print(f"{'=' * 100}\n")

    def save_to_csv(
        self,
        opportunities: List[Dict],
        filename: str = None
    ):
        """
        儲存為CSV檔案

        參數:
            opportunities: 交易機會列表
            filename: 檔案名稱
        """
        if not opportunities:
            print("❌ 沒有數據可以儲存")
            return

        if filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"market_scan_{timestamp}.csv"

        df = pd.DataFrame(opportunities)

        # 選擇要輸出的欄位
        output_columns = [
            'symbol', 'name', 'industry',
            'pattern_name', 'pattern_type',
            'resonance_type', 'resonance_strength',
            'action', 'position_size',
            'current_price', 'entry_price', 'stop_loss',
            'target_1', 'target_2', 'risk_reward',
            'confidence', 'timeframe',
            'detected_timeframes', 'reason'
        ]

        df = df[output_columns]

        # 儲存
        output_path = Path('reports') / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, index=False, encoding='utf-8-sig')

        print(f"✅ 已儲存報告: {output_path}")

        return str(output_path)

    def save_to_json(
        self,
        opportunities: List[Dict],
        filename: str = None
    ):
        """
        儲存為JSON檔案

        參數:
            opportunities: 交易機會列表
            filename: 檔案名稱
        """
        if not opportunities:
            print("❌ 沒有數據可以儲存")
            return

        if filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"market_scan_{timestamp}.json"

        output_path = Path('reports') / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(opportunities, f, ensure_ascii=False, indent=2)

        print(f"✅ 已儲存JSON報告: {output_path}")

        return str(output_path)


def main():
    """主程序"""
    parser = argparse.ArgumentParser(description='全市場多時間週期形態掃描器')
    parser.add_argument(
        '-t', '--timeframes',
        type=str,
        nargs='+',
        default=['D', 'W'],
        help='時間週期列表（預設: D W）'
    )
    parser.add_argument(
        '--min-confidence',
        type=float,
        default=0.75,
        help='最小信心度（預設: 0.75）'
    )
    parser.add_argument(
        '--min-resonance',
        type=float,
        default=0.60,
        help='最小共振強度（預設: 0.60）'
    )
    parser.add_argument(
        '--industry',
        type=str,
        default=None,
        help='產業類別過濾（例如: 半導體）'
    )
    parser.add_argument(
        '--top',
        type=int,
        default=20,
        help='顯示前幾名（預設: 20）'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='限制掃描股票數量（用於測試）'
    )
    parser.add_argument(
        '--save-csv',
        action='store_true',
        help='儲存為CSV檔案'
    )
    parser.add_argument(
        '--save-json',
        action='store_true',
        help='儲存為JSON檔案'
    )
    parser.add_argument(
        '--bullish-only',
        action='store_true',
        help='僅顯示多頭機會'
    )
    parser.add_argument(
        '--bearish-only',
        action='store_true',
        help='僅顯示空頭機會'
    )

    args = parser.parse_args()

    # 建立掃描器
    scanner = MarketMultiTimeframeScanner()

    # 開始掃描
    print(f"\n{'=' * 100}")
    print(f"🚀 SenVision 全市場多時間週期形態掃描器")
    print(f"{'=' * 100}")

    opportunities = scanner.scan_market(
        timeframes=args.timeframes,
        min_confidence=args.min_confidence,
        min_resonance=args.min_resonance,
        industry=args.industry,
        limit=args.limit
    )

    if not opportunities:
        print("\n❌ 未找到符合條件的交易機會")
        return

    # 過濾多空
    if args.bullish_only:
        opportunities = [o for o in opportunities if o['pattern_type'] == 'bullish']
        print(f"\n📈 僅顯示多頭機會")
    elif args.bearish_only:
        opportunities = [o for o in opportunities if o['pattern_type'] == 'bearish']
        print(f"\n📉 僅顯示空頭機會")

    # 打印報告
    scanner.print_opportunities_report(opportunities, top=args.top)

    # 儲存報告
    if args.save_csv:
        scanner.save_to_csv(opportunities)

    if args.save_json:
        scanner.save_to_json(opportunities)

    print(f"\n{'=' * 100}")
    print(f"✅ 掃描完成！")
    print(f"{'=' * 100}\n")


if __name__ == '__main__':
    main()
