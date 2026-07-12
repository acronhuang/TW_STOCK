#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
形態學12神招 - 全市場掃描器
掃描所有股票並篩選符合12種技術型態的標的

作者: 技術分析系統
日期: 2026-02-13
版本: 1.0.0
"""

import sys
import os
from pathlib import Path

# 添加專案路徑
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pymongo import MongoClient
import json
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.font_manager as fm

from pattern_recognition.patterns_12_masters import Pattern12Masters, PatternSignal
from mplfinance.original_flavor import candlestick_ohlc

# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MarketScanner:
    """全市場型態掃描器"""
    
    def __init__(self, mongo_uri='mongodb://localhost:27017/', db_name='tw_stock_analysis'):
        """
        初始化掃描器
        
        參數:
            mongo_uri: MongoDB連接字串
            db_name: 資料庫名稱
        """
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.detector = Pattern12Masters()
        
        # 掃描結果
        self.scan_results = []
        
    def get_all_stock_symbols(self) -> List[str]:
        """
        取得所有股票代碼
        
        返回:
            List[str]: 股票代碼列表
        """
        try:
            # 從 'stocks' 集合讀取股票列表（已整合 company_basic_info）
            stocks = list(self.db.stocks.find({}, {'symbol': 1, '_id': 0}))
            if not stocks:
                # 備用：嘗試使用舊的 _id 格式
                stocks = list(self.db.stocks.find({}, {'_id': 1}))
                symbols = [stock['_id'] for stock in stocks if '_id' in stock]
            else:
                # 提取 symbol
                symbols = [stock['symbol'] for stock in stocks if 'symbol' in stock]

            logger.info(f"載入 {len(symbols)} 支股票")
            return symbols
        except Exception as e:
            logger.error(f"取得股票代碼失敗: {e}")
            return []
    
    def get_stock_data(self, symbol: str, days: int = 250) -> Optional[pd.DataFrame]:
        """
        取得股票歷史資料
        
        參數:
            symbol: 股票代碼
            days: 取得天數
            
        返回:
            pd.DataFrame: 股票資料
        """
        try:
            # 從 stock_price 集合取得最近的資料
            # 使用 sort 降序並 limit，然後再反轉順序
            cursor = self.db.stock_price.find(
                {'symbol': symbol},
                {'_id': 0}
            ).sort('date', -1).limit(days * 2)  # 多取一些確保有足夠交易日
            
            data = list(cursor)
            
            if not data or len(data) < 60:
                logger.warning(f"股票 {symbol} 的數據不足 (少於60天)，無法進行分析。")
                return None
            
            # 反轉順序，使日期由舊到新
            data.reverse()
            
            df = pd.DataFrame(data)
            
            # 確保必要欄位存在
            required_cols = ['date', 'open', 'high', 'low', 'close', 'volume']
            if not all(col in df.columns for col in required_cols):
                logger.warning(f"{symbol} 缺少必要欄位")
                return None
                
            # 轉換資料型態
            df['date'] = pd.to_datetime(df['date'])
            for col in ['open', 'high', 'low', 'close']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            df['volume'] = pd.to_numeric(df['volume'], errors='coerce')
            
            # 移除NaN
            df = df.dropna(subset=['close'])
            
            if len(df) < 60:
                logger.warning(f"股票 {symbol} 清理後的數據不足 (少於60天)，無法進行分析。")
                return None
                
            return df.tail(days) # 回傳指定天數的數據
            
        except Exception as e:
            logger.error(f"取得 {symbol} 資料失敗: {e}")
            return None
    
    def scan_single_stock(self, symbol: str) -> List[PatternSignal]:
        """
        掃描單一股票
        
        參數:
            symbol: 股票代碼
            
        返回:
            List[PatternSignal]: 檢測到的型態信號
        """
        try:
            # 取得股票資料
            df = self.get_stock_data(symbol)
            if df is None:
                return []
            
            # 掃描所有型態
            signals = self.detector.scan_all_patterns(df, symbol)
            
            if signals:
                logger.info(f"{symbol} 檢測到 {len(signals)} 個型態")
                
            return signals
            
        except Exception as e:
            logger.error(f"掃描 {symbol} 失敗: {e}")
            return []
    
    def scan_market(
        self,
        symbols: Optional[List[str]] = None,
        pattern_filter: Optional[List[str]] = None,
        pattern_type: Optional[str] = None, # 'bullish' or 'bearish'
        confidence_threshold: float = 0.7,
        min_score: int = 0,
        max_workers: int = 10
    ) -> List[PatternSignal]:
        """
        掃描市場
        
        參數:
            symbols: 要掃描的股票代碼列表（None=全部）
            pattern_filter: 要篩選的型態名稱列表
            signal_type: 信號類型篩選 ('buy'/'sell'/None)
            min_confidence: 最低信心度
            min_strength: 最低結構強度
            max_workers: 並行執行緒數
            
        返回:
            List[PatternSignal]: 掃描結果的 PatternSignal 物件列表
        """
        if symbols is None:
            symbols = self.get_all_stock_symbols()
            
        if not symbols:
            logger.error("沒有可掃描的股票")
            return []
        
        logger.info(f"開始掃描 {len(symbols)} 支股票...")
        self.scan_results = []
        
        # 使用多執行緒掃描
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_symbol = {
                executor.submit(self.scan_single_stock, symbol): symbol 
                for symbol in symbols
            }
            
            for future in as_completed(future_to_symbol):
                symbol = future_to_symbol[future]
                try:
                    signals = future.result()
                    
                    for signal in signals:
                        # 套用篩選條件
                        if pattern_filter and signal.pattern_name not in pattern_filter:
                            continue
                            
                        if pattern_type and signal.pattern_type != pattern_type:
                            continue
                            
                        if signal.confidence < confidence_threshold:
                            continue

                        if signal.structure_score < min_score:
                            continue
                        
                        # 加入結果
                        self.scan_results.append(signal)
                        
                except Exception as e:
                    logger.error(f"處理 {symbol} 結果時發生錯誤: {e}")
        
        logger.info(f"掃描完成，共找到 {len(self.scan_results)} 個型態信號")
        
        # 排序結果
        self.scan_results.sort(key=lambda s: (s.structure_score, s.confidence, s.risk_reward), reverse=True)
        
        return self.scan_results
    
    def filter_by_pattern(self, pattern_name: str) -> List[Dict]:
        """依型態名稱篩選結果"""
        return [r for r in self.scan_results if r['pattern_name'] == pattern_name]
    
    def filter_by_signal_type(self, signal_type: str) -> List[Dict]:
        """依信號類型篩選結果"""
        return [r for r in self.scan_results if r['signal_type'] == signal_type]
    
    def get_top_opportunities(self, n: int = 20, signal_type: str = 'buy') -> List[Dict]:
        """
        取得前N個最佳機會
        
        參數:
            n: 取得數量
            signal_type: 信號類型
            
        返回:
            List[Dict]: 最佳機會列表
        """
        filtered = self.filter_by_signal_type(signal_type)
        return filtered[:n]
    
    def generate_report(self, output_format: str = 'text') -> str:
        """
        生成掃描報告
        
        參數:
            output_format: 輸出格式 ('text'/'json')
            
        返回:
            str: 報告內容
        """
        if not self.scan_results:
            return "沒有掃描結果"
        
        if output_format == 'json':
            # 將 PatternSignal 物件轉換為字典
            results_as_dict = [s.__dict__ for s in self.scan_results]
            return json.dumps(results_as_dict, ensure_ascii=False, indent=2)
        
        # 文字報告
        report_lines = [
            f"{'代碼':<8} {'型態':<15} {'強度':<4} {'當前價':<8} {'目標1':<8} {'目標2':<8} {'獲利%':<8} {'報酬比':<8} {'信心度':<8}"
        ]
        report_lines.append("-" * 90)
        
        for signal in self.scan_results:
            target_2_str = f"{signal.target_2:.2f}" if signal.target_2 else "N/A"
            report_lines.append(
                f"{signal.symbol:<8} {signal.pattern_name:<15} {signal.structure_score:<4} "
                f"{signal.current_price:<8.2f} {signal.target_1:<8.2f} {target_2_str:<8} "
                f"{signal.potential_gain:<7.2f}% {signal.risk_reward:<7.2f}:1 "
                f"{signal.confidence*100:<7.1f}%"
            )
            
        return "\n".join(report_lines)
    
    def export_to_csv(self, filename: str = 'pattern_scan_results.csv'):
        """匯出為CSV"""
        if not self.scan_results:
            logger.warning("沒有結果可匯出")
            return
        
        df = pd.DataFrame(self.scan_results)
        df.to_csv(filename, index=False, encoding='utf-8-sig')
        logger.info(f"結果已匯出至 {filename}")
    
    def save_to_database(self):
        """儲存結果到資料庫"""
        if not self.scan_results:
            logger.warning("沒有結果可儲存")
            return
        
        try:
            collection = self.db.pattern_signals
            
            # 清除舊資料（可選）
            # collection.delete_many({'detected_date': datetime.now().strftime('%Y-%m-%d')})
            
            # 插入新資料
            for result in self.scan_results:
                result['_id'] = f"{result['symbol']}_{result['pattern_name']}_{result['detected_date']}"
                collection.update_one(
                    {'_id': result['_id']},
                    {'$set': result},
                    upsert=True
                )
            
            logger.info(f"已儲存 {len(self.scan_results)} 筆信號到資料庫")
            
        except Exception as e:
            logger.error(f"儲存到資料庫失敗: {e}")


class PatternScreener:
    """型態篩選器 - 提供更細緻的篩選功能"""
    
    def __init__(self, scanner: MarketScanner):
        self.scanner = scanner
        self.db = scanner.db
        
        # Set Chinese font
        try:
            # For macOS
            plt.rcParams['font.sans-serif'] = ['PingFang HK']
            plt.rcParams['axes.unicode_minus'] = False
        except:
            try:
                # For Windows
                plt.rcParams['font.sans-serif'] = ['Microsoft JhengHei']
                plt.rcParams['axes.unicode_minus'] = False
            except:
                # For Linux
                # You might need to install a font like Noto Sans CJK TC
                # and then update the font cache
                font_path = '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
                if fm.findfont(fm.FontProperties(fname=font_path)):
                     plt.rcParams['font.sans-serif'] = [fm.FontProperties(fname=font_path).get_name()]
                else:
                    print("未找到中文字體，圖表中的中文可能無法正常顯示。")
                    print("請安裝支援中文的字體，例如 'Noto Sans CJK TC'。")

    def get_pattern_metadata(self, pattern_name):
        """取得型態的元資料"""
        metadata = {
            'W底': {'neckline': '頸線', 'target_1': '目標價1', 'target_2': '目標價2'},
            '破底翻': {'neckline': '頸線', 'target_1': '目標價1', 'target_2': '目標價2'},
            '破底翻W底': {'neckline': '頸線', 'target_1': '目標價1', 'target_2': '目標價2'},
            '下飄旗形': {'neckline': '頸線', 'target_1': '目標價1', 'target_2': '目標價2'},
            '上飄旗形': {'neckline': '頸線', 'target_1': '目標價1', 'target_2': '目標價2'},
            'M頭': {'neckline': '頸線', 'target_1': '目標價1', 'target_2': '目標價2'},
            '假突破': {'neckline': '頸線', 'target_1': '目標價1', 'target_2': '目標價2'},
            '頭肩頂': {'neckline': '頸線', 'target_1': '目標價1', 'target_2': '目標價2'},
            '假突破頭肩頂': {'neckline': '頸線', 'target_1': '目標價1', 'target_2': '目標價2'},
            '頭肩底': {'neckline': '頸線', 'target_1': '目標價1', 'target_2': '目標價2'},
            '收斂三角形頂': {'neckline': '頸線', 'target_1': '目標價1', 'target_2': '目標價2'},
            '收斂三角形底': {'neckline': '頸線', 'target_1': '目標價1', 'target_2': '目標價2'},
        }
        
        return metadata.get(pattern_name, {})
    
    def screen_by_criteria(
        self,
        min_potential_gain: float = 10.0,
        min_risk_reward: float = 2.0,
        max_formation_days: int = 60,
        patterns: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        依據條件篩選
        
        參數:
            min_potential_gain: 最小潛在獲利%
            min_risk_reward: 最小風險報酬比
            max_formation_days: 最大形成天數
            patterns: 指定型態列表
            
        返回:
            List[Dict]: 符合條件的信號
        """
        results = []
        
        for signal in self.scanner.scan_results:
            # 檢查條件
            if signal['potential_gain'] < min_potential_gain:
                continue
                
            if signal['risk_reward'] < min_risk_reward:
                continue
                
            if signal['formation_days'] > max_formation_days:
                continue
                
            if patterns and signal['pattern_name'] not in patterns:
                continue
            
            results.append(signal)
        
        return results
    
    def get_confirmed_patterns_only(self) -> List[Dict]:
        """只取得已確認的型態"""
        return [r for r in self.scanner.scan_results if r['status'] == 'confirmed']
    
    def get_high_confidence_signals(self, min_confidence: float = 0.85) -> List[Dict]:
        """取得高信心度信號"""
        return [r for r in self.scanner.scan_results if r['confidence'] >= min_confidence]
    
    def get_best_risk_reward(self, n: int = 10) -> List[Dict]:
        """取得最佳風險報酬比的信號"""
        sorted_results = sorted(
            self.scanner.scan_results, 
            key=lambda x: x['risk_reward'], 
            reverse=True
        )
        return sorted_results[:n]


def generate_pattern_infographic(signal: PatternSignal, df: pd.DataFrame, save_path: str = './charts'):
    """
    根據型態信號和K線數據生成詳細的技術分析圖表。

    Args:
        signal (PatternSignal): 型態信號物件
        df (pd.DataFrame): 包含K線數據的DataFrame
        save_path (str): 圖表儲存路徑
    """
    # 設定 Matplotlib 支援中文的字體
    plt.rcParams['font.sans-serif'] = ['PingFang TC', 'Heiti TC', 'Arial Unicode MS']
    plt.rcParams['axes.unicode_minus'] = False  # 修正負號顯示問題

    if not os.path.exists(save_path):
        os.makedirs(save_path)

    fig, ax = plt.subplots(figsize=(16, 8))
    
    # 準備 K線資料
    df_chart = df.copy()
    df_chart['date'] = pd.to_datetime(df_chart['date'])
    df_chart['date_num'] = df_chart['date'].map(mdates.date2num)
    ohlc = df_chart[['date_num', 'open', 'high', 'low', 'close']]

    candlestick_ohlc(ax, ohlc.values, width=0.6, colorup='r', colordown='g', alpha=0.8)

    # 格式化X軸
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    plt.xticks(rotation=45)

    # 標題與標籤
    plt.title(f'{signal.symbol} - {signal.pattern_name} ({signal.signal_type.upper()})', fontsize=20)
    plt.xlabel('Date', fontsize=12)
    plt.ylabel('Price', fontsize=12)
    
    metadata = signal.metadata
    
    # 繪製頸線
    if 'neckline' in metadata:
        neckline_y = metadata['neckline']
        ax.axhline(y=neckline_y, color='b', linestyle='--', label=f'Neckline ({neckline_y:.2f})')

    # 標示關鍵點 (轉折點)
    if 'pivots' in metadata and metadata['pivots']:
        try:
            # 強制轉換為整數列表，以處理潛在的格式問題
            pivot_indices = [int(p) for p in metadata['pivots']]
            
            if isinstance(pivot_indices, list) and all(isinstance(i, int) for i in pivot_indices):
                valid_indices = [i for i in pivot_indices if i < len(df)]
                if valid_indices:
                    pivot_dates = df.iloc[valid_indices]['date'].map(mdates.date2num)
                    pivot_prices = df.iloc[valid_indices]['close']
                    ax.plot(pivot_dates, pivot_prices, 'o-', color='orange', markersize=8, label='Pivots')
            else:
                logger.warning(f"信號 {signal.symbol} 的 'pivots' 格式不正確，即使在轉換後也是如此。")
        except (ValueError, TypeError) as e:
            logger.warning(f"處理信號 {signal.symbol} 的 'pivots' 時出錯: {e}")

    # 標示突破/跌破點
    if 'breakout_date' in metadata and metadata['breakout_date']:
        breakout_date = mdates.date2num(pd.to_datetime(metadata['breakout_date']))
        breakout_price = metadata.get('breakout_price', signal.current_price)
        ax.plot(breakout_date, breakout_price, 'r*', markersize=15, label=f'Breakout ({breakout_price:.2f})')

    # 標示目標價
    if signal.target_1:
        ax.axhline(y=signal.target_1, color='purple', linestyle=':', label=f'Target 1 ({signal.target_1:.2f})')
    if signal.target_2:
        ax.axhline(y=signal.target_2, color='purple', linestyle='-.', label=f'Target 2 ({signal.target_2:.2f})')
        
    # 標示止損價
    if 'stop_loss' in metadata and metadata['stop_loss'] is not None:
        stop_loss_y = metadata['stop_loss']
        ax.axhline(y=stop_loss_y, color='red', linestyle='--', label=f'Stop Loss ({stop_loss_y:.2f})')

    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    
    # 儲存圖表
    chart_filename = os.path.join(save_path, f'{signal.symbol}_{signal.pattern_name}.png')
    plt.savefig(chart_filename)
    plt.close(fig) # 確保關閉正確的 figure 物件
    logger.info(f"已生成圖表: {chart_filename}")
    return chart_filename


def main():
    """主程式"""
    import argparse
    
    parser = argparse.ArgumentParser(description='形態學12神招 - 全市場掃描器')
    parser.add_argument('--symbols', nargs='+', help='指定股票代碼')
    parser.add_argument('--pattern', choices=[
        'W底', '破底翻', '破底翻W底', '下飄旗形', '上飄旗形',
        'M頭', '假突破', '頭肩頂', '假突破頭肩頂', '頭肩底',
        '收斂三角形頂', '收斂三角形底'
    ], help='指定型態')
    parser.add_argument('--signal-type', choices=['buy', 'sell'], help='信號類型')
    parser.add_argument('--min-confidence', type=float, default=0.75, help='最低信心度')
    parser.add_argument('--output', default='text', choices=['text', 'json', 'csv'], help='輸出格式')
    parser.add_argument('--top', type=int, default=10, help='顯示前N個機會')
    parser.add_argument('--save-db', action='store_true', help='儲存到資料庫')
    parser.add_argument('--generate-chart', action='store_true', help='為最佳機會生成圖表')
    
    args = parser.parse_args()
    
    # 建立掃描器
    scanner = MarketScanner()
    
    # 執行掃描
    pattern_filter = [args.pattern] if args.pattern else None
    
    results = scanner.scan_market(
        symbols=args.symbols,
        pattern_filter=pattern_filter,
        signal_type=args.signal_type,
        min_confidence=args.min_confidence,
        min_strength=getattr(args, 'min_strength', 0) # 保持相容性
    )
    
    if not results:
        print("未找到符合條件的型態信號")
        return

    # 取得前N個結果用於報告和圖表
    top_results = results[:args.top]

    # 產生圖表
    if args.generate_chart:
        print(f"為前 {len(top_results)} 個機會生成圖表...")
        for signal in top_results:
            df = scanner.get_stock_data(signal.symbol, days=200) # 取得足夠繪圖的資料
            if df is not None:
                generate_pattern_infographic(signal, df)
            else:
                logger.warning(f"無法取得 {signal.symbol} 的資料來生成圖表")
    
    # 輸出結果
    if args.output == 'json':
        # 僅輸出前N個結果
        results_as_dict = [s.__dict__ for s in top_results]
        print(json.dumps(results_as_dict, ensure_ascii=False, indent=2))
    elif args.output == 'csv':
        scanner.export_to_csv(f'pattern_scan_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv')
        print("結果已匯出為CSV")
    else:
        # 建立一個只包含前N個結果的臨時掃描器來產生報告
        temp_scanner = MarketScanner()
        temp_scanner.scan_results = top_results
        print(temp_scanner.generate_report('text'))
    
    # 儲存到資料庫
    if args.save_db:
        scanner.save_to_database()


if __name__ == "__main__":
    main()
