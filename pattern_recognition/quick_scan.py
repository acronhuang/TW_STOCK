#!/usr/bin/env python3
"""
形態學12神招 - 快速掃描腳本
直接使用Python API，避免CLI問題
"""

import sys
from pathlib import Path

# 添加專案路徑
project_root = Path('/home/mdsadmin/Stock/tw-stock-analysis')
sys.path.insert(0, str(project_root))

from pattern_recognition.market_scanner import MarketScanner, PatternScreener
from datetime import datetime

def main():
    print("=" * 80)
    print("📊 形態學12神招 - 全市場掃描")
    print("=" * 80)
    print(f"執行時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"最低信心度: 0.85")
    print(f"信號類型: 買入 (多頭型態)")
    print()
    
    try:
        # 建立掃描器
        print("🔧 初始化掃描器...")
        scanner = MarketScanner(
            mongo_uri='mongodb://localhost:27017/',
            db_name='tw_stock_analysis'
        )
        
        # 執行掃描
        print("🔍 開始掃描市場...")
        print()
        
        results = scanner.scan_market(
            signal_type='buy',
            min_confidence=0.85
        )
        
        if not results:
            print("⚠️  未找到符合條件的型態")
            return
        
        # 顯示結果
        print("\n" + "=" * 80)
        print(f"📈 找到 {len(results)} 個買入信號")
        print("=" * 80 + "\n")
        
        # 取得前20個最佳機會
        top_results = sorted(
            results, 
            key=lambda x: x.get('risk_reward', 0) * x.get('confidence', 0),
            reverse=True
        )[:20]
        
        print(f"{'排名':<4} {'代碼':<8} {'型態':<15} {'當前價':<8} {'目標價':<8} {'獲利%':<8} {'信心度':<8} {'報酬比'}")
        print("-" * 80)
        
        for i, signal in enumerate(top_results, 1):
            symbol = signal.get('symbol', 'N/A')
            pattern = signal.get('pattern_name', 'N/A')
            current = signal.get('current_price', 0)
            target = signal.get('target_1', 0)
            gain = signal.get('potential_gain', 0)
            confidence = signal.get('confidence', 0)
            rr = signal.get('risk_reward', 0)
            
            print(f"{i:<4} {symbol:<8} {pattern:<15} {current:<8.2f} {target:<8.2f} "
                  f"{gain:<8.1f} {confidence*100:<8.1f} {rr:.2f}:1")
        
        # 統計摘要
        print("\n" + "=" * 80)
        print("📊 統計摘要")
        print("=" * 80)
        
        # 按型態分類
        pattern_counts = {}
        for signal in results:
            pattern = signal.get('pattern_name', 'Unknown')
            pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1
        
        print("\n型態分布:")
        for pattern, count in sorted(pattern_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"  {pattern}: {count} 個")
        
        # 平均指標
        avg_gain = sum(s.get('potential_gain', 0) for s in results) / len(results)
        avg_confidence = sum(s.get('confidence', 0) for s in results) / len(results)
        avg_rr = sum(s.get('risk_reward', 0) for s in results) / len(results)
        
        print(f"\n平均指標:")
        print(f"  平均潛在獲利: {avg_gain:.2f}%")
        print(f"  平均信心度: {avg_confidence*100:.1f}%")
        print(f"  平均風險報酬比: {avg_rr:.2f}:1")
        
        # 匯出選項
        print("\n" + "=" * 80)
        response = input("\n是否匯出結果為CSV? (y/n): ").strip().lower()
        
        if response == 'y':
            filename = f"pattern_scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            scanner.export_to_csv(filename)
            print(f"✅ 結果已匯出至: {filename}")
        
        print("\n✅ 掃描完成")
        print("=" * 80 + "\n")
        
    except Exception as e:
        print(f"\n❌ 錯誤: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
