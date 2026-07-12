#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多時間週期分析工具
提供基礎的多時間週期數據分析和視覺化

使用範例:
    python3 multi_timeframe_analysis.py --symbol 2330
    python3 multi_timeframe_analysis.py --symbol 2330 --timeframes D W M

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
from typing import Dict, List, Optional
from pymongo import MongoClient
from dotenv import load_dotenv
import logging

from pattern_recognition.timeframe_converter import TimeframeConverter

# 載入環境變數
load_dotenv()

# 日誌設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MultiTimeframeAnalyzer:
    """多時間週期分析器"""

    def __init__(self, mongo_uri: str = None):
        """
        初始化分析器

        參數:
            mongo_uri: MongoDB 連接字串
        """
        if mongo_uri is None:
            mongo_uri = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/tw_stock_analysis')

        self.client = MongoClient(mongo_uri)
        self.db = self.client['tw_stock_analysis']
        self.converter = TimeframeConverter()

    def get_daily_data(
        self,
        symbol: str,
        days: int = 500
    ) -> Optional[pd.DataFrame]:
        """
        從數據庫取得日線數據

        參數:
            symbol: 股票代碼
            days: 取得天數

        返回:
            日線數據 DataFrame
        """
        try:
            # 計算起始日期
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)

            # 查詢數據
            cursor = self.db.stock_price.find({
                'stock_id': symbol,
                'date': {'$gte': start_date, '$lte': end_date}
            }).sort('date', 1)

            data = list(cursor)

            if not data:
                logger.warning(f"找不到 {symbol} 的數據")
                return None

            # 轉換為 DataFrame
            df = pd.DataFrame(data)

            # 確保必要欄位存在
            required_columns = ['date', 'open', 'high', 'low', 'close']
            if not all(col in df.columns for col in required_columns):
                logger.error(f"數據缺少必要欄位")
                return None

            # 轉換 Decimal128 為 float
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = df[col].apply(
                        lambda x: float(x.to_decimal()) if hasattr(x, 'to_decimal') else (float(x) if x is not None else 0.0)
                    )

            # 確保 date 為 datetime
            df['date'] = pd.to_datetime(df['date'])

            # 排序
            df.sort_values('date', inplace=True)
            df.reset_index(drop=True, inplace=True)

            logger.info(f"成功載入 {symbol} 的 {len(df)} 筆日線數據")

            return df

        except Exception as e:
            logger.error(f"取得日線數據失敗: {e}")
            return None

    def analyze_multiple_timeframes(
        self,
        symbol: str,
        timeframes: List[str] = ['D', 'W', 'M'],
        ma_periods: List[int] = [5, 20, 60]
    ) -> Dict[str, pd.DataFrame]:
        """
        分析多個時間週期

        參數:
            symbol: 股票代碼
            timeframes: 時間週期列表
            ma_periods: MA 週期列表

        返回:
            各時間週期的分析結果
        """
        results = {}

        # 取得日線數據
        daily_data = self.get_daily_data(symbol)

        if daily_data is None or len(daily_data) == 0:
            logger.error(f"無法獲取 {symbol} 的數據")
            return results

        # 轉換並分析各時間週期
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

                # 添加移動平均線
                df_tf = self.converter.add_moving_averages(df_tf, ma_periods)

                # 計算趨勢斜率
                df_tf['trend_slope'] = self.converter.calculate_trend_slope(df_tf)

                # 檢測交叉
                crosses = self.converter.detect_golden_cross(df_tf, 5, 20)

                # 均線排列分析
                alignment = self.converter.analyze_ma_alignment(df_tf, ma_periods)

                # 支撐壓力
                support_resistance = self.converter.get_support_resistance(df_tf)

                # 儲存結果
                results[tf] = {
                    'data': df_tf,
                    'crosses': crosses,
                    'alignment': alignment,
                    'support_resistance': support_resistance,
                    'latest_price': float(df_tf['close'].iloc[-1]) if len(df_tf) > 0 else None
                }

                logger.info(f"成功分析時間週期 {tf}: {len(df_tf)} 筆數據")

            except Exception as e:
                logger.error(f"分析時間週期 {tf} 失敗: {e}")

        return results

    def print_analysis_report(
        self,
        symbol: str,
        results: Dict
    ):
        """
        打印分析報告

        參數:
            symbol: 股票代碼
            results: 分析結果
        """
        print(f"\n{'=' * 80}")
        print(f"📊 {symbol} 多時間週期分析報告")
        print(f"{'=' * 80}\n")

        for tf, result in results.items():
            tf_name = TimeframeConverter.TIMEFRAMES.get(tf, tf)
            data = result['data']
            alignment = result['alignment']
            crossing = result['crosses']
            sr = result['support_resistance']

            print(f"【{tf_name}】")
            print(f"  數據量: {len(data)} 筆")

            # 當前價格
            if result['latest_price']:
                print(f"  當前價格: {result['latest_price']:.2f}")

            # 均線排列
            if alignment == 'bullish_strong':
                print(f"  均線排列: 🔥 強勢多頭")
            elif alignment == 'bullish':
                print(f"  均線排列: 📈 多頭")
            elif alignment == 'bearish_strong':
                print(f"  均線排列: ❄️ 強勢空頭")
            elif alignment == 'bearish':
                print(f"  均線排列: 📉 空頭")
            else:
                print(f"  均線排列: 🔄 盤整")

            # 趨勢方向
            if 'trend_slope' in data.columns:
                latest_slope = data['trend_slope'].iloc[-1]
                if not pd.isna(latest_slope):
                    direction = "上升" if latest_slope > 0 else "下降"
                    print(f"  趨勢方向: {direction} ({latest_slope:.2f}/期)")

            # 支撐壓力
            if sr['support'] and sr['resistance']:
                print(f"  支撐位: {sr['support']:.2f}")
                print(f"  壓力位: {sr['resistance']:.2f}")

            # 最近交叉
            if crossing and len(crossing) > 0:
                latest_cross = crossing[-1]
                cross_type = latest_cross['type']
                cross_date = latest_cross['date']

                if cross_type == 'golden_cross':
                    print(f"  最近交叉: ✅ 黃金交叉 ({cross_date.strftime('%Y-%m-%d')})")
                else:
                    print(f"  最近交叉: ⚠️ 死亡交叉 ({cross_date.strftime('%Y-%m-%d')})")

            print()


def main():
    """主程序"""
    parser = argparse.ArgumentParser(description='多時間週期分析工具')
    parser.add_argument(
        '-s', '--symbol',
        type=str,
        default='2330',
        help='股票代碼（預設: 2330）'
    )
    parser.add_argument(
        '-t', '--timeframes',
        type=str,
        nargs='+',
        default=['D', 'W', 'M'],
        help='時間週期列表（預設: D W M）'
    )
    parser.add_argument(
        '--ma-periods',
        type=int,
        nargs='+',
        default=[5, 20, 60],
        help='MA 週期列表（預設: 5 20 60）'
    )

    args = parser.parse_args()

    # 建立分析器
    analyzer = MultiTimeframeAnalyzer()

    # 分析
    print(f"\n🔍 開始分析 {args.symbol} 的多時間週期...")
    results = analyzer.analyze_multiple_timeframes(
        symbol=args.symbol,
        timeframes=args.timeframes,
        ma_periods=args.ma_periods
    )

    if not results:
        print("❌ 分析失敗或無數據")
        return

    # 打印報告
    analyzer.print_analysis_report(args.symbol, results)

    print(f"\n{'=' * 80}")
    print(f"✅ 分析完成！")
    print(f"{'=' * 80}\n")


if __name__ == '__main__':
    main()
