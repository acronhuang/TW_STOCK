#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
形態學12神招 - 命令行工具
提供便捷的命令行介面進行型態掃描

使用範例:
    python pattern_cli.py scan                    # 掃描全市場
    python pattern_cli.py scan --buy              # 只掃描買入信號
    python pattern_cli.py scan --pattern W底      # 只掃描W底型態
    python pattern_cli.py list                    # 列出所有型態
    python pattern_cli.py stock 2330              # 查看特定股票
    python pattern_cli.py top --n 20              # 顯示前20個機會

作者: 技術分析系統
日期: 2026-02-13
"""

import sys
import os
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import argparse
from datetime import datetime
from pattern_recognition.patterns_12_masters import Pattern12Masters, PatternSignal
from pattern_recognition.market_scanner import MarketScanner, PatternScreener, generate_pattern_infographic
import json

# 顏色代碼
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def print_header(text):
    """印出標題"""
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.CYAN}{text:^80}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.ENDC}\n")


def print_success(text):
    """印出成功訊息"""
    print(f"{Colors.GREEN}✓ {text}{Colors.ENDC}")


def print_error(text):
    """印出錯誤訊息"""
    print(f"{Colors.RED}✗ {text}{Colors.ENDC}")


def print_warning(text):
    """印出警告訊息"""
    print(f"{Colors.YELLOW}⚠ {text}{Colors.ENDC}")


def print_info(text):
    """印出資訊訊息"""
    print(f"{Colors.BLUE}ℹ {text}{Colors.ENDC}")


def cmd_list_patterns(args):
    """列出所有支援的型態"""
    print_header("形態學12神招 - 支援型態列表")
    
    detector = Pattern12Masters()
    patterns = list(detector.patterns.keys())
    
    # 分類
    bullish = ['W底', '破底翻', '破底翻W底', '下飄旗形', '頭肩底', '收斂三角形底']
    bearish = ['上飄旗形', 'M頭', '假突破', '頭肩頂', '假突破頭肩頂', '收斂三角形頂']
    
    print(f"{Colors.BOLD}{Colors.GREEN}多頭型態（買入信號）:{Colors.ENDC}")
    for i, pattern in enumerate(bullish, 1):
        print(f"  {i:2d}. {pattern}")
    
    print(f"\n{Colors.BOLD}{Colors.RED}空頭型態（賣出信號）:{Colors.ENDC}")
    for i, pattern in enumerate(bearish, 1):
        print(f"  {i:2d}. {pattern}")
    
    print(f"\n{Colors.BOLD}總計: {len(patterns)} 種型態{Colors.ENDC}")


def cmd_scan_market(args):
    """掃描市場尋找交易機會"""
    scanner = MarketScanner()
    
    pattern_type = None
    if args.buy:
        pattern_type = 'bullish'
    elif args.sell:
        pattern_type = 'bearish'
    
    # 設定參數
    min_confidence = args.confidence
    min_score = args.min_score
    
    # 顯示設定
    print_info(f"型態篩選: {args.pattern if args.pattern else '全部'}")
    print_info(f"掃描方向: {pattern_type.capitalize() if pattern_type else '全部 (Bullish & Bearish)'}")
    print_info(f"最低信心度: {min_confidence*100:.0f}%")
    print_info(f"最低強度: {min_score}")
    
    if args.symbols:
        print_info(f"指定股票: {', '.join(args.symbols)}")
    
    # 建立掃描器
    print_info("正在初始化掃描器...")
    scanner = MarketScanner()
    
    # 執行掃描
    print_info("開始掃描市場...")
    results = scanner.scan_market(
        pattern_type=pattern_type,
        confidence_threshold=args.confidence,
        min_score=args.min_score
    )
    print_success(f"掃描完成，共找到 {len(results)} 個型態信號")

    if not results:
        print_warning("未找到符合條件的型態信號")
        return

    try:
        # 取得前 N 個結果
        top_signals = results[:args.n]

        print_header(f"前 {len(top_signals)} 名機會")

        for i, signal in enumerate(top_signals, 1):
            color = Colors.GREEN if signal.pattern_type == 'bullish' else Colors.RED
            strength_stars = '★' * signal.structure_score + '☆' * (8 - signal.structure_score)
            
            print(f"{color}{i:2d}. {Colors.BOLD}{signal.symbol:<8}{signal.pattern_name:<12}{Colors.ENDC}"
                  f"  強度: {strength_stars} ({signal.structure_score}/8)"
                  f"  信心度: {signal.confidence*100:.0f}%"
                  f"  現價: {signal.current_price:<8.2f}"
                  f"  目標: {Colors.GREEN}{signal.target_1:.2f}{Colors.ENDC}")

        # 產生圖表
        if args.generate_chart:
            print_info(f"\n為前 {len(top_signals)} 個機會生成圖表...")
            for signal in top_signals:
                df = scanner.get_stock_data(signal.symbol, days=250)
                if df is not None:
                    try:
                        chart_path = generate_pattern_infographic(signal, df)
                        print_success(f"已為 {signal.symbol} ({signal.pattern_name}) 生成圖表: {chart_path}")
                    except Exception as e:
                        print_error(f"為 {signal.symbol} 生成圖表時出錯: {e}")
                else:
                    print_warning(f"無法取得 {signal.symbol} 的資料來生成圖表")

    except Exception as e:
        print_error(f"掃描或報告生成時發生錯誤: {e}")


def cmd_find_pattern(args):
    """根據條件查找型態"""
    print_header("形態學12神招 - 根據條件查找型態")
    
    # 解析條件
    conditions = []
    if args.pattern:
        conditions.append(f"型態: {args.pattern}")
    if args.buy:
        conditions.append("信號類型: 買入")
    if args.sell:
        conditions.append("信號類型: 賣出")
    conditions.append(f"最低信心度: {args.confidence*100:.0f}%")
    conditions.append(f"最低強度: {args.min_strength}")
    
    print_info("查找條件:")
    for condition in conditions:
        print(f"  - {condition}")
    
    scanner = MarketScanner()
    
    # 執行查找
    print_info("正在查找符合條件的型態...")
    results = scanner.find_patterns(
        pattern_type=args.pattern,
        signal_type='buy' if args.buy else 'sell' if args.sell else None,
        confidence_threshold=args.confidence,
        min_score=args.min_strength
    )
    
    print_success(f"查找完成，共找到 {len(results)} 個符合條件的型態")

    if not results:
        print_warning("未找到符合條件的型態")
        return
    
    # 顯示結果
    for i, signal in enumerate(results, 1):
        color = Colors.GREEN if signal.pattern_type == 'bullish' else Colors.RED
        print(f"{color}{i:2d}. {Colors.BOLD}{signal.symbol:<8}{signal.pattern_name:<12}{Colors.ENDC}"
              f"  信心度: {signal.confidence*100:.0f}%"
              f"  強度: {signal.structure_score}/8"
              f"  現價: {signal.current_price:<8.2f}"
              f"  目標: {Colors.GREEN}{signal.target_1:.2f}{Colors.ENDC}")
    

def cmd_top_opportunities(args):
    """顯示最佳機會"""
    print_header("形態學12神招 - 最佳投資機會")
    
    # 設定信號類型
    signal_type = 'sell' if args.sell else 'buy'
    
    print_info(f"信號類型: {'賣出' if signal_type == 'sell' else '買入'}")
    print_info(f"顯示數量: 前 {args.n} 個")
    
    # 建立掃描器
    scanner = MarketScanner()
    
    # 執行掃描
    print_info("正在掃描市場...")
    results = scanner.scan_market(
        signal_type=signal_type,
        min_confidence=args.confidence
    )
    
    if not results:
        print_warning("未找到符合條件的型態信號")
        return
    
    # 取得前N個機會
    top = scanner.get_top_opportunities(args.n, signal_type)
    
    print_success(f"找到 {len(results)} 個信號，顯示前 {len(top)} 個最佳機會")
    
    # 顯示結果
    print(f"\n{Colors.BOLD}{'排名':<4} {'代碼':<8} {'型態':<15} {'當前價':<8} {'目標價':<8} {'獲利%':<8} {'報酬比':<8} {'信心度':<8}{Colors.ENDC}")
    print("-" * 80)
    
    for i, signal in enumerate(top, 1):
        color = Colors.GREEN if signal['signal_type'] == 'buy' else Colors.RED
        print(f"{color}{i:<4} {signal['symbol']:<8} {signal['pattern_name']:<15} "
              f"{signal['current_price']:<8.2f} {signal['target_1']:<8.2f} "
              f"{signal['potential_gain']:<7.2f}% {signal['risk_reward']:<7.2f}:1 "
              f"{signal['confidence']*100:<7.1f}%{Colors.ENDC}")


def cmd_stock_detail(args):
    """查看特定股票"""
    print_header(f"形態學12神招 - 股票分析 ({args.symbol})")
    
    scanner = MarketScanner()
    
    print_info(f"正在分析 {args.symbol}...")
    
    # 掃描單一股票
    signals = scanner.scan_single_stock(args.symbol)
    
    if not signals:
        print_warning(f"{args.symbol} 未檢測到任何型態")
        return
    
    print_success(f"找到 {len(signals)} 個型態信號")
    
    # 顯示詳細資訊
    for i, signal in enumerate(signals, 1):
        print(f"\n{Colors.BOLD}[{i}] {signal.pattern_name}{Colors.ENDC}")
        print(f"{'─'*60}")
        print(f"型態類型: {Colors.GREEN if signal.pattern_type == 'bullish' else Colors.RED}"
              f"{'多頭' if signal.pattern_type == 'bullish' else '空頭'}{Colors.ENDC}")
        print(f"信號類型: {Colors.GREEN if signal.signal_type == 'buy' else Colors.RED}"
              f"{'買入' if signal.signal_type == 'buy' else '賣出'}{Colors.ENDC}")
        print(f"信號可信度: {signal.confidence*100:.1f}%")
        print(f"型態狀態: {signal.status}")
        print(f"\n{Colors.BOLD}價格資訊:{Colors.ENDC}")
        print(f"  當前價格: {signal.current_price:.2f}")
        print(f"  頸線價格: {signal.neckline:.2f}")
        print(f"  進場價格: {signal.entry_price:.2f}")
        print(f"  停損價格: {signal.stop_loss:.2f}")
        print(f"  目標價1: {signal.target_1:.2f}")
        if signal.target_2:
            print(f"  目標價2: {Colors.YELLOW}{signal.target_2:.2f}{Colors.ENDC}")
        
        print(f"\n{Colors.BOLD}結構強度: {signal.structure_score}/8{Colors.ENDC}")
        if signal.metadata.get('strength_reasons'):
            print(f"  評分理由: {', '.join(signal.metadata['strength_reasons'])}")

        print(f"\n{Colors.BOLD}風險報酬:{Colors.ENDC}")
        print(f"  潛在獲利: {signal.potential_gain:.2f}%")
        print(f"  風險報酬比: {signal.risk_reward:.2f}:1")
        print(f"  形成天數: {signal.formation_days}天")

        # 如果有圖表，顯示圖表路徑
        if signal.metadata.get('chart_path'):
            print(f"\n{Colors.BOLD}圖表:{Colors.ENDC}")
            print(f"  圖表已儲存至: {signal.metadata['chart_path']}")


def cmd_test_charts(args):
    """測試所有型態的圖表生成"""
    print_header("圖表生成功能完整性測試")
    
    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)
    print_info(f"圖表將儲存至: {output_dir.resolve()}")

    scanner = MarketScanner()
    screener = PatternScreener(scanner) # 建立 PatternScreener
    detector = Pattern12Masters()
    all_patterns = list(detector.patterns.keys())
    
    report = []
    total_success = 0
    total_fail = 0

    for pattern_name in all_patterns:
        print(f"\n{Colors.BOLD}正在測試型態: {pattern_name}{Colors.ENDC}")
        
        try:
            # 掃描特定型態
            signals = scanner.scan_market(pattern_filter=[pattern_name], min_confidence=0.5)
            
            if not signals:
                print_warning(f"找不到 {pattern_name} 的範例，跳過測試。")
                report.append({'pattern': pattern_name, 'status': 'SKIPPED', 'reason': 'No examples found'})
                continue

            # 排序以取得最可信的範例
            signals.sort(key=lambda s: s.confidence, reverse=True)
            
            tested_count = 0
            for i, signal in enumerate(signals):
                if tested_count >= args.n:
                    break
                
                print_info(f"  正在為 {signal.symbol} 生成圖表...")
                
                try:
                    # 取得股票資料
                    df = scanner.get_stock_data(signal.symbol, days=250)
                    if df is None:
                        raise ValueError("無法獲取K線數據")

                    chart_path = generate_pattern_infographic(
                        signal, 
                        df, 
                        save_path=str(output_dir)
                    )
                    
                    if chart_path and Path(chart_path).exists():
                        print_success(f"  ✓ 圖表生成成功: {chart_path}")
                        report.append({'pattern': pattern_name, 'symbol': signal.symbol, 'status': 'SUCCESS', 'path': chart_path})
                        total_success += 1
                        tested_count += 1
                    else:
                        raise IOError("圖表檔案未被建立或路徑未返回")

                except Exception as e:
                    print_error(f"  ✗ 為 {signal.symbol} 生成圖表失敗: {e}")
                    report.append({'pattern': pattern_name, 'symbol': signal.symbol, 'status': 'FAIL', 'reason': str(e)})
                    total_fail += 1
                    tested_count += 1 # 即使失敗也算一次嘗試
        
        except Exception as e:
            print_error(f"測試 {pattern_name} 時發生嚴重錯誤: {e}")
            report.append({'pattern': pattern_name, 'status': 'ERROR', 'reason': str(e)})
            total_fail += 1

    # 生成報告
    print_header("測試報告")
    
    print(f"總覽: {Colors.GREEN}成功 {total_success}{Colors.ENDC} | {Colors.RED}失敗 {total_fail}{Colors.ENDC}")
    
    print(f"\n{Colors.BOLD}{'型態':<15} {'代碼':<10} {'狀態':<10} {'詳細資訊'}{Colors.ENDC}")
    print("-" * 80)
    
    for r in report:
        status_color = {
            'SUCCESS': Colors.GREEN,
            'FAIL': Colors.RED,
            'ERROR': Colors.RED,
            'SKIPPED': Colors.YELLOW
        }.get(r['status'], Colors.ENDC)
        
        symbol = r.get('symbol', 'N/A')
        details = r.get('path') or r.get('reason', 'N/A')
        
        print(f"{r['pattern']:<15} {symbol:<10} {status_color}{r['status']:<10}{Colors.ENDC} {details}")

    # 將報告寫入檔案
    report_path = output_dir / "test_report.json"
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print_success(f"\n詳細報告已儲存至: {report_path.resolve()}")


def cmd_filter(args):
    """進階篩選"""
    print_header("形態學12神招 - 進階篩選")
    
    print_info(f"最小獲利: {args.min_gain}%")
    print_info(f"最小報酬比: {args.min_rr}:1")
    print_info(f"最大形成天數: {args.max_days}天")
    
    scanner = MarketScanner()
    
    # 掃描市場
    print_info("正在掃描市場...")
    scanner.scan_market(min_confidence=args.confidence)
    
    # 建立篩選器
    screener = PatternScreener(scanner)
    
    # 套用篩選條件
    patterns = args.patterns.split(',') if args.patterns else None
    filtered = screener.screen_by_criteria(
        min_potential_gain=args.min_gain,
        min_risk_reward=args.min_rr,
        max_formation_days=args.max_days,
        patterns=patterns
    )
    
    if not filtered:
        print_warning("沒有符合條件的信號")
        return
    
    print_success(f"找到 {len(filtered)} 個符合條件的信號")
    
    # 顯示結果
    print(f"\n{Colors.BOLD}{'排名':<4} {'代碼':<8} {'型態':<15} {'獲利%':<8} {'報酬比':<8} {'天數':<6} {'信心度':<8}{Colors.ENDC}")
    print("-" * 80)
    
    for i, signal in enumerate(filtered[:args.n], 1):
        print(f"{i:<4} {signal['symbol']:<8} {signal['pattern_name']:<15} "
              f"{signal['potential_gain']:<7.2f}% {signal['risk_reward']:<7.2f}:1 "
              f"{signal['formation_days']:<6}天 {signal['confidence']*100:<7.1f}%")


def cmd_multi_timeframe(args):
    """多時間週期分析 (功能已整合，此命令保留但提示使用者)"""
    print_warning("多時間週期分析功能已整合至各掃描指令中。")
    print_info("此命令未來可能被移除。")
    pass


def main():
    """主程式"""
    parser = argparse.ArgumentParser(
        description='形態學12神招 - 命令行工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  %(prog)s list                          列出所有型態
  %(prog)s scan                          掃描全市場
  %(prog)s scan --buy                    只掃描買入信號
  %(prog)s scan --pattern W底            只掃描W底型態
  %(prog)s scan --symbols 2330 2317      掃描特定股票
  %(prog)s top --n 20                    顯示前20個機會
  %(prog)s stock 2330                    查看2330的型態
  %(prog)s filter --min-gain 15          篩選獲利15%%以上
  %(prog)s test-charts                   執行圖表生成完整性測試
  %(prog)s multi 2330                    2330多時間週期分析
  %(prog)s multi 2330 -t D W M Q Y 5Y    分析所有時間週期
"""
    )
    
    subparsers = parser.add_subparsers(dest='command', help='子命令')
    
    # list 命令
    parser_list = subparsers.add_parser('list', help='列出所有支援的型態')
    
    # scan 命令
    parser_scan = subparsers.add_parser('scan', help='掃描市場')
    parser_scan.add_argument('--symbols', nargs='+', help='指定股票代碼')
    parser_scan.add_argument('--pattern', help='指定型態')
    parser_scan.add_argument('--buy', action='store_true', help='只掃描買入信號')
    parser_scan.add_argument('--sell', action='store_true', help='只掃描賣出信號')
    parser_scan.add_argument('--confidence', type=float, default=0.7, help='最低信心度')
    parser_scan.add_argument('--min-score', type=int, default=0, help='最低結構強度分數 (0-8)')
    parser_scan.add_argument('-n', type=int, default=15, help='顯示前n個結果')
    parser_scan.add_argument('--output', choices=['text', 'json', 'csv'], default='text', help='輸出格式')
    parser_scan.add_argument('--file', help='輸出檔案名稱')
    parser_scan.add_argument('--save-db', action='store_true', help='儲存到資料庫')
    parser_scan.add_argument('--workers', type=int, default=10, help='並行執行緒數')
    parser_scan.add_argument('--generate-chart', action='store_true', help='為找到的頂級信號生成圖表')

    # test-charts 命令
    parser_test_charts = subparsers.add_parser('test-charts', help='測試所有型態的圖表生成')
    parser_test_charts.add_argument('--n', type=int, default=1, help='為每種型態測試n個範例')
    parser_test_charts.add_argument('--output-dir', default='chart_tests', help='圖表輸出目錄')
    
    # top 命令
    parser_top = subparsers.add_parser('top', help='顯示最佳機會')
    parser_top.add_argument('--n', type=int, default=20, help='顯示數量')
    parser_top.add_argument('--buy', action='store_true', help='買入信號（預設）')
    parser_top.add_argument('--sell', action='store_true', help='賣出信號')
    parser_top.add_argument('--confidence', type=float, default=0.75, help='最低信心度')
    
    # stock 命令
    parser_stock = subparsers.add_parser('stock', help='查看特定股票')
    parser_stock.add_argument('symbol', help='股票代碼')
    
    # filter 命令
    parser_filter = subparsers.add_parser('filter', help='進階篩選')
    parser_filter.add_argument('--min-gain', type=float, default=10.0, help='最小潛在獲利%%')
    parser_filter.add_argument('--min-rr', type=float, default=2.0, help='最小風險報酬比')
    parser_filter.add_argument('--max-days', type=int, default=60, help='最大形成天數')
    parser_filter.add_argument('--patterns', help='指定型態（逗號分隔）')
    parser_filter.add_argument('--confidence', type=float, default=0.75, help='最低信心度')
    parser_filter.add_argument('--n', type=int, default=20, help='顯示數量')
    
    # multi 命令 - 多時間週期分析
    parser_multi = subparsers.add_parser('multi', help='多時間週期分析')
    parser_multi.add_argument('symbol', help='股票代碼')
    parser_multi.add_argument('-t', '--timeframes', nargs='+', 
                             default=['D', 'W', 'M'],
                             help='時間週期 (D W M Q 6M Y 5Y 10Y)')
    parser_multi.add_argument('--list-timeframes', action='store_true',
                             help='列出所有支援的時間週期')
    
    args = parser.parse_args()
    
    if args.command == 'list':
        cmd_list_patterns(args)
    elif args.command == 'scan':
        cmd_scan_market(args)
    elif args.command == 'top':
        cmd_top_opportunities(args)
    elif args.command == 'stock':
        cmd_stock_detail(args)
    elif args.command == 'filter':
        cmd_filter(args)
    elif args.command == 'test-charts':
        cmd_test_charts(args)
    elif args.command == 'multi':
        cmd_multi_timeframe(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}程式已中斷{Colors.ENDC}")
        sys.exit(0)
    except Exception as e:
        print_error(f"發生錯誤: {e}")
        sys.exit(1)
