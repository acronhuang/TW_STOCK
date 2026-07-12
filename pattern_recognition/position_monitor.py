#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
持倉監控與交易建議系統
整合進階交易邏輯，提供即時操作建議
"""

import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from pymongo import MongoClient
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict
from pattern_recognition.patterns_12_masters import Pattern12Masters
from pattern_recognition.advanced_trading_logic import (
    AdvancedTradingLogic,
    TradingState
)


class PositionMonitor:
    """持倉監控系統"""
    
    def __init__(self):
        self.client = MongoClient('mongodb://localhost:27017/')
        self.db = self.client['tw_stock_analysis']
        self.detector = Pattern12Masters()
        self.trading_engine = AdvancedTradingLogic()
        
    def monitor_position(
        self,
        symbol: str,
        entry_date: str,
        entry_price: float,
        pattern_name: str = None
    ) -> TradingState:
        """
        監控單一持倉
        
        參數:
            symbol: 股票代碼
            entry_date: 進場日期 (YYYY-MM-DD)
            entry_price: 進場價格
            pattern_name: 型態名稱（可選，會自動檢測）
        """
        # 取得最新數據
        cursor = self.db.stock_price.find(
            {'symbol': symbol},
            {'_id': 0}
        ).sort('date', -1).limit(120)
        
        data = list(cursor)
        if not data:
            raise ValueError(f"找不到 {symbol} 的數據")
        
        data.reverse()
        df = pd.DataFrame(data)
        
        # 獲取當前價格
        current_price = df['close'].iloc[-1]
        current_date = df['date'].iloc[-1]
        
        # 計算持有天數
        entry_datetime = datetime.strptime(entry_date, '%Y-%m-%d')
        current_datetime = current_date
        days_held = (current_datetime - entry_datetime).days
        
        # 檢測型態（如果未提供）
        if not pattern_name:
            signals = self.detector.scan_all_patterns(df, symbol)
            if not signals:
                raise ValueError(f"{symbol} 未檢測到型態")
            signal = signals[0]
        else:
            # 重新檢測指定型態
            signals = self.detector.scan_all_patterns(df, symbol)
            signal = next((s for s in signals if s.pattern_name == pattern_name), None)
            if not signal:
                raise ValueError(f"{symbol} 未檢測到 {pattern_name} 型態")
        
        # 創建交易狀態
        state = TradingState(
            symbol=symbol,
            pattern_name=signal.pattern_name,
            pattern_type=signal.pattern_type,
            entry_price=entry_price,
            current_price=current_price,
            neckline=signal.neckline,
            target_1=signal.target_1,
            target_2=signal.target_2,
            original_stop_loss=signal.stop_loss,
            current_stop_loss=signal.stop_loss,
            market_structure_strength=0.0,
            volume_confirmation=signal.volume_confirmation,
            entry_date=entry_date,
            days_held=days_held
        )
        
        # 檢查是否已達第一波目標
        if signal.pattern_type == 'bullish':
            if current_price >= signal.target_1:
                state.target_1_reached = True
        else:
            if current_price <= signal.target_1:
                state.target_1_reached = True
        
        # 生成交易建議
        state = self.trading_engine.generate_trading_action(state, df)
        
        return state
    
    def scan_and_monitor_all(self) -> List[TradingState]:
        """
        掃描全市場並監控已突破的型態
        自動識別需要關注的機會
        """
        print("\n" + "="*80)
        print("🔍 全市場型態掃描與監控")
        print("="*80)
        
        # 取得所有股票代碼（從 stocks 集合，已整合 company_basic_info）
        stocks = list(self.db.stocks.find(
            {},
            {'symbol': 1, 'name': 1, '_id': 0}
        ))
        
        monitoring_list = []
        
        print(f"\n📊 掃描 {len(stocks)} 檔股票...\n")
        
        for idx, stock_info in enumerate(stocks, 1):
            symbol = stock_info['symbol']
            name = stock_info.get('name', symbol)
            
            try:
                # 取得數據
                cursor = self.db.stock_price.find(
                    {'symbol': symbol},
                    {'_id': 0}
                ).sort('date', -1).limit(120)
                
                data = list(cursor)
                if len(data) < 60:
                    continue
                
                data.reverse()
                df = pd.DataFrame(data)
                
                # 檢測型態
                signals = self.detector.scan_all_patterns(df, symbol)
                
                for signal in signals:
                    # 只關注已突破的型態
                    if signal.status == 'confirmed':
                        # 創建監控狀態
                        state = TradingState(
                            symbol=symbol,
                            pattern_name=signal.pattern_name,
                            pattern_type=signal.pattern_type,
                            entry_price=signal.entry_price,
                            current_price=signal.current_price,
                            neckline=signal.neckline,
                            target_1=signal.target_1,
                            target_2=signal.target_2,
                            original_stop_loss=signal.stop_loss,
                            current_stop_loss=signal.stop_loss,
                            volume_confirmation=signal.volume_confirmation,
                            entry_date=signal.detected_date,
                            days_held=0
                        )
                        
                        # 評估交易狀態
                        state = self.trading_engine.generate_trading_action(state, df)
                        monitoring_list.append(state)
                
                if idx % 100 == 0:
                    print(f"  已掃描 {idx}/{len(stocks)} 檔...")
                    
            except Exception as e:
                continue
        
        print(f"\n✅ 掃描完成！找到 {len(monitoring_list)} 個監控機會")
        return monitoring_list
    
    def print_monitoring_report(self, states: List[TradingState]):
        """打印監控報告"""
        
        if not states:
            print("\n⚠️  目前無持倉需要監控")
            return
        
        print("\n" + "="*80)
        print("📋 持倉監控報告")
        print("="*80)
        print(f"生成時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"監控數量: {len(states)} 個部位")
        print("="*80)
        
        # 分類統計
        actions = {}
        for state in states:
            actions[state.action] = actions.get(state.action, 0) + 1
        
        print(f"\n📊 操作分布:")
        for action, count in sorted(actions.items(), key=lambda x: x[1], reverse=True):
            print(f"  {action}: {count} 個")
        
        # 按行動分類顯示
        print("\n" + "-"*80)
        print("🚨 需要立即處理的部位:")
        print("-"*80)
        
        urgent_count = 0
        for state in states:
            if state.action in ['SELL', 'COVER']:
                urgent_count += 1
                self._print_compact_state(state)
        
        if urgent_count == 0:
            print("  ✅ 無需立即處理的部位")
        
        print("\n" + "-"*80)
        print("📈 建議移動止損的部位:")
        print("-"*80)
        
        trail_count = 0
        for state in states:
            if state.action == 'TRAIL_STOP':
                trail_count += 1
                self._print_compact_state(state)
        
        if trail_count == 0:
            print("  - 無建議移動止損的部位")
        
        print("\n" + "-"*80)
        print("💼 繼續持有的部位:")
        print("-"*80)
        
        hold_count = 0
        for state in states:
            if state.action == 'HOLD':
                hold_count += 1
                if hold_count <= 10:  # 只顯示前10個
                    self._print_compact_state(state)
        
        if hold_count > 10:
            print(f"  ... 還有 {hold_count - 10} 個持有部位（略）")
        
        print("\n" + "="*80)
    
    def _print_compact_state(self, state: TradingState):
        """精簡格式打印狀態"""
        pnl = ((state.current_price - state.entry_price) / state.entry_price) * 100
        if state.pattern_type == 'bearish':
            pnl = -pnl
        
        print(f"\n  {state.symbol} | {state.pattern_name} ({state.pattern_type})")
        print(f"    價格: {state.entry_price:.2f} → {state.current_price:.2f} ({pnl:+.2f}%)")
        print(f"    目標: T1={state.target_1:.2f}{'✅' if state.target_1_reached else '⏳'} | "
              f"T2={state.target_2:.2f if state.target_2 else 'N/A'}")
        print(f"    止損: {state.current_stop_loss:.2f} | 強度: {state.market_structure_strength:.2f}")
        print(f"    建議: {state.action} - {state.reason}")
    
    def export_to_csv(self, states: List[TradingState], filename: str = None):
        """匯出為CSV"""
        if not filename:
            filename = f"position_monitor_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        data = []
        for state in states:
            pnl = ((state.current_price - state.entry_price) / state.entry_price) * 100
            if state.pattern_type == 'bearish':
                pnl = -pnl
            
            data.append({
                '股票代碼': state.symbol,
                '型態名稱': state.pattern_name,
                '型態類型': state.pattern_type,
                '進場價格': state.entry_price,
                '當前價格': state.current_price,
                '損益%': f"{pnl:.2f}",
                '頸線': state.neckline,
                '目標價1': state.target_1,
                '目標價2': state.target_2 if state.target_2 else '',
                '當前止損': state.current_stop_loss,
                '市場強度': f"{state.market_structure_strength:.2f}",
                '持有天數': state.days_held,
                '操作建議': state.action,
                '建議原因': state.reason
            })
        
        df = pd.DataFrame(data)
        df.to_csv(filename, index=False, encoding='utf-8-sig')
        print(f"\n✅ 已匯出至 {filename}")
    
    def close(self):
        """關閉資料庫連接"""
        self.client.close()


def main():
    """主程式"""
    import argparse
    
    parser = argparse.ArgumentParser(description='持倉監控與交易建議系統')
    parser.add_argument('--symbol', '-s', help='監控單一股票')
    parser.add_argument('--entry-date', '-d', help='進場日期 (YYYY-MM-DD)')
    parser.add_argument('--entry-price', '-p', type=float, help='進場價格')
    parser.add_argument('--pattern', help='型態名稱')
    parser.add_argument('--scan-all', action='store_true', help='掃描全市場')
    parser.add_argument('--export', '-e', help='匯出CSV檔案名稱')
    
    args = parser.parse_args()
    
    monitor = PositionMonitor()
    
    try:
        if args.symbol:
            # 監控單一股票
            if not args.entry_date or not args.entry_price:
                print("❌ 監控單一股票需要提供 --entry-date 和 --entry-price")
                return
            
            print(f"\n🔍 監控 {args.symbol}...")
            state = monitor.monitor_position(
                args.symbol,
                args.entry_date,
                args.entry_price,
                args.pattern
            )
            
            monitor.trading_engine.print_trading_recommendation(state)
            
        elif args.scan_all:
            # 掃描全市場
            states = monitor.scan_and_monitor_all()
            monitor.print_monitoring_report(states)
            
            if args.export:
                monitor.export_to_csv(states, args.export)
        
        else:
            print("請指定操作模式:")
            print("  --symbol XXXX --entry-date YYYY-MM-DD --entry-price PRICE  # 監控單一持倉")
            print("  --scan-all  # 掃描全市場")
            
    except KeyboardInterrupt:
        print("\n\n⚠️  使用者中斷")
    except Exception as e:
        print(f"\n❌ 執行失敗: {e}")
        import traceback
        traceback.print_exc()
    finally:
        monitor.close()


if __name__ == '__main__':
    main()
