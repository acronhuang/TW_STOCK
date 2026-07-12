"""
SenVision 多時間框架技術分析圖表

整合 ZigZag、W底/M頭/三重底/三重頂識別、支撐壓力強度評估、
趨勢切線（破切）偵測，輸出符合蔡森老師看盤習慣的完整圖表。

Usage:
    # 日線分析
    python3 scripts/senvision_chart.py --stock 2330

    # 週線分析，回溯 2 年
    python3 scripts/senvision_chart.py --stock 2330 --timeframe W --days 730

    # 一次輸出所有時間框架（日/週/月/季/半年/年）
    python3 scripts/senvision_chart.py --stock 2330 --all-timeframes

    # 不顯示圖形，直接儲存至 charts/
    python3 scripts/senvision_chart.py --stock 2330 --timeframe M --no-show

    # 指定輸出路徑
    python3 scripts/senvision_chart.py --stock 2330 -o /tmp/2330_W.png

Author: SenVision Team
Date: 2026-02-24
"""

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

# ── 添加 src 到路徑 ────────────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / 'src'))

from senvision import (
    TIMEFRAME_CONFIG,
    SenVisionChart,
)
from senvision.analysis import analyze_timeframe


# ── 資料獲取 ───────────────────────────────────────────────────────────────────

def _fetch_daily_data(db, stock_id: str, days: int) -> pd.DataFrame:
    """從 MongoDB 拉取日線 OHLCV 數據"""
    from datetime import datetime, timedelta
    start = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

    cursor = db.stock_price.find(
        {'stock_id': stock_id, 'date': {'$gte': start}},
        {'_id': 0, 'date': 1, 'open': 1, 'high': 1, 'low': 1, 'close': 1, 'volume': 1},
    ).sort('date', 1)

    df = pd.DataFrame(list(cursor))
    if df.empty:
        return df

    df['date'] = pd.to_datetime(df['date'])
    for col in ['open', 'high', 'low', 'close']:
        df[col] = df[col].apply(lambda x: float(str(x)) if x is not None else None)
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df['volume'] = df['volume'].apply(lambda x: float(str(x)) if x is not None else 0)
    df['volume'] = pd.to_numeric(df['volume'], errors='coerce').fillna(0)

    return df.dropna(subset=['close']).reset_index(drop=True)


# ── 文字摘要報告 ────────────────────────────────────────────────────────────────

def print_summary(result: dict, stock_id: str, tf_label: str) -> None:
    df = result['df']
    print(f"\n{'='*62}")
    print(f"  {stock_id}  {tf_label}")
    print(f"  {df['date'].iloc[0].strftime('%Y-%m-%d')} ~ "
          f"{df['date'].iloc[-1].strftime('%Y-%m-%d')}"
          f"  ({len(df)} 根 K 線)")
    kd_str = f"KD_K={result['kd_k']:.1f}  " if result.get('kd_k') is not None else ""
    bb_str = f"BB_%B={result['bb_pct']:.2f}" if result.get('bb_pct') is not None else ""
    print(f"  現價: {df['close'].iloc[-1]:.2f}   "
          f"ZigZag 轉折點: {len(result['peaks'])} 個   "
          f"{kd_str}{bb_str}")
    print(f"{'='*62}")

    if result['patterns']:
        print(f"\n  形態 ({len(result['patterns'])} 個):")
        for p in result['patterns']:
            vol = '✓量' if p.volume_confirmed else '  '
            print(f"    {p.pattern_type.value:<16} "
                  f"頸線={p.neckline:>8.2f}  "
                  f"目標={p.target:>8.2f}  "
                  f"停損={p.stop_loss:>8.2f}  "
                  f"風報={p.risk_reward_ratio:>4.1f}  "
                  f"{p.status.value} {vol}")

    if result['sr_levels']:
        print(f"\n  支撐壓力（前 8 個）:")
        shown = sorted(result['sr_levels'], key=lambda x: x.price, reverse=True)[:8]
        for sr in shown:
            mark = '【強】' if sr.strength == 'strong' else ('【中】' if sr.strength == 'moderate' else '    ')
            kind = '壓力' if sr.type == 'resistance' else '支撐'
            print(f"    {mark} {kind} {sr.price:>8.2f}  觸碰 {sr.touches} 次")

    if result['trendlines']:
        print(f"\n  趨勢切線:")
        for tl in result['trendlines']:
            kind = '下降切線(待向上突破)' if tl.type == 'descending_resistance' else '上升切線(待向下突破)'
            brk = ' ★ 已突破!' if tl.is_broken else ''
            print(f"    {kind}: {tl.p1.price:.2f} → {tl.p2.price:.2f}{brk}")


# ── CLI 入口 ───────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description='SenVision 多時間框架技術分析圖表',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  python3 scripts/senvision_chart.py --stock 2330
  python3 scripts/senvision_chart.py --stock 2330 --timeframe W --days 730
  python3 scripts/senvision_chart.py --stock 2330 --all-timeframes --no-show
  python3 scripts/senvision_chart.py --stock 0050 --timeframe M -o charts/0050_M.png
        """,
    )
    p.add_argument('--stock', '-s', required=True,
                   help='股票代碼（例如 2330）')
    p.add_argument('--timeframe', '-t', default='D',
                   choices=list(TIMEFRAME_CONFIG.keys()),
                   help='時間框架（預設：D 日線）')
    p.add_argument('--all-timeframes', action='store_true',
                   help='分析全部時間框架並各自輸出圖表')
    p.add_argument('--days', type=int, default=365,
                   help='回溯日線天數（預設 365；建議週線 730、月線以上 1460）')
    p.add_argument('--output', '-o', default=None,
                   help='圖表輸出路徑（--all-timeframes 時自動命名）')
    p.add_argument('--no-show', action='store_true',
                   help='不顯示圖表視窗（只儲存檔案）')
    p.add_argument('--light', action='store_true',
                   help='使用淺色主題（預設深色）')
    p.add_argument('--db-uri', default='mongodb://localhost:27017/',
                   help='MongoDB 連線 URI')
    return p


def main() -> None:
    args = _build_parser().parse_args()

    # ── 連接資料庫 ──────────────────────────────────────────────
    try:
        from pymongo import MongoClient
        client = MongoClient(args.db_uri, serverSelectionTimeoutMS=5000)
        client.server_info()  # 快速連線測試
        db = client['tw_stock_analysis']
    except Exception as e:
        print(f"MongoDB 連線失敗: {e}")
        sys.exit(1)

    try:
        # ── 取得日線數據 ─────────────────────────────────────────
        fetch_days = max(args.days, 365 * 3)   # 至少 3 年確保月/季線有足夠 K 線
        print(f"\n[SenVision]  股票: {args.stock}   回溯: {fetch_days} 天日線")
        df_daily = _fetch_daily_data(db, args.stock, fetch_days)

        if df_daily.empty:
            print(f"錯誤: 找不到 {args.stock} 的價格數據（請先執行 main_download.py）")
            sys.exit(1)

        print(f"日線數據: {len(df_daily)} 根 "
              f"({df_daily['date'].iloc[0].strftime('%Y-%m-%d')} ~ "
              f"{df_daily['date'].iloc[-1].strftime('%Y-%m-%d')})")

        # ── 決定要分析的時間框架 ─────────────────────────────────
        timeframes = list(TIMEFRAME_CONFIG.keys()) if args.all_timeframes else [args.timeframe]

        # ── 圖表引擎 ─────────────────────────────────────────────
        chart = SenVisionChart(dark_theme=not args.light)

        # ── 逐一時間框架分析 ─────────────────────────────────────
        charts_dir = _PROJECT_ROOT / 'charts'
        charts_dir.mkdir(exist_ok=True)

        for tf in timeframes:
            tf_label = TIMEFRAME_CONFIG[tf]['label']
            print(f"\n分析 {tf_label}...")

            result = analyze_timeframe(df_daily, args.stock, tf)
            if result is None:
                continue

            print_summary(result, args.stock, tf_label)

            # 決定存檔路徑
            if args.output and len(timeframes) == 1:
                save_path = args.output
            else:
                ts = datetime.now().strftime('%m%d_%H%M')
                save_path = str(charts_dir / f"{args.stock}_{tf}_{ts}.png")

            chart.plot(
                df=result['df'],
                stock_id=args.stock,
                timeframe=tf,
                peaks=result['peaks'],
                patterns=result['patterns'],
                sr_levels=result['sr_levels'],
                trendlines=result['trendlines'],
                ma_alignment=result.get('ma_alignment', 'mixed'),
                candle_width_days=TIMEFRAME_CONFIG[tf]['candle_width_days'],
                save_path=save_path,
                show=not args.no_show,
            )

        print("\n分析完成。")

    except KeyboardInterrupt:
        print("\n已中斷。")
    finally:
        client.close()


if __name__ == '__main__':
    main()
