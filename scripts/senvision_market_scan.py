"""
SenVision 全市場批量技術分析掃描

對資料庫中全部股票（或指定清單）執行多時間框架分析：
    W底 / M頭 / 三重底 / 三重頂 + 支撐壓力 + 趨勢切線（破切）偵測

評分系統（0 ~ 3.2）：
    基礎信心度 (confidence)     最大 1.0
    量能確認                   +0.15
    風報比 ≥ 3                 +0.15（≥ 2 +0.08）
    趨勢切線已突破（破切）      +0.12
    頸線附近有強支撐壓力        +0.08
    均線多頭/空頭排列           +0.10
    估值合理（PER）             +0.08
    月營收動能（YoY）           +0.10
    多時間框架共振（≥2個TF）    +0.06/+0.12
    × 時間框架乘數 (D=1.0 ~ Y=1.5)

Usage:
    # 掃描所有股票（日+週線，預設）
    python3 scripts/senvision_market_scan.py

    # 只掃描日線，回溯 180 天
    python3 scripts/senvision_market_scan.py --timeframes D --days 180

    # 掃描全部時間框架，取前 50 名，並產生圖表
    python3 scripts/senvision_market_scan.py --all-timeframes --top 50 --charts

    # 指定股票列表
    python3 scripts/senvision_market_scan.py --stocks 2330 2454 0050

    # 只顯示已突破（BREAKOUT）的信號
    python3 scripts/senvision_market_scan.py --status BREAKOUT

Author: SenVision Team
Date: 2026-02-24
"""

from __future__ import annotations

import argparse
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
from pymongo import MongoClient
from tqdm import tqdm

logger = logging.getLogger(__name__)

# ── 路徑設定 ───────────────────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / 'src'))

from senvision import TIMEFRAME_CONFIG
from senvision.scanner import MarketScanner


# ── 批量掃描引擎 ───────────────────────────────────────────────────────────────

class BatchScanner:
    """
    全市場批量掃描引擎

    使用 MarketScanner 的 comprehensive_scan_stock() 對每支股票
    執行多時間框架分析，彙整結果並排名輸出。
    """

    # 顯示時要特別標記的信號類別
    _HIGHLIGHT = {'BREAKOUT', '剛突破'}

    def __init__(self, db_uri: str = 'mongodb://localhost:27017/'):
        self.scanner = MarketScanner(db_uri=db_uri)
        self._db = self.scanner.db

    def _fetch_daily(self, stock_id: str, days: int) -> Optional[pd.DataFrame]:
        """從 MongoDB 取得日線數據"""
        start = datetime.now() - timedelta(days=days)
        cursor = self._db.stock_price.find(
            {'stock_id': stock_id, 'date': {'$gte': start}},
            {'_id': 0, 'date': 1, 'open': 1, 'high': 1,
             'low': 1, 'close': 1, 'volume': 1},
        ).sort('date', 1)

        df = pd.DataFrame(list(cursor))
        if df.empty:
            return None

        df['date'] = pd.to_datetime(df['date'])
        for col in ['open', 'high', 'low', 'close']:
            df[col] = df[col].apply(lambda x: float(str(x)) if x is not None else None)
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df['volume'] = df['volume'].apply(lambda x: float(str(x)) if x is not None else 0)
        df['volume'] = pd.to_numeric(df['volume'], errors='coerce').fillna(0)

        # 資料驗證：過濾無效價格（OHLC ≤ 0 或 High < Low）
        for col in ['open', 'high', 'low', 'close']:
            df = df[df[col] > 0]
        df = df[df['high'] >= df['low']]

        df = df.dropna(subset=['close']).reset_index(drop=True)
        return df if len(df) >= 30 else None

    def _process_one(
        self,
        stock_id: str,
        days: int,
        timeframes: List[str],
        min_rrr: float,
        min_score: float,
    ) -> List[Dict]:
        """處理單支股票（執行緒安全）"""
        try:
            df = self._fetch_daily(stock_id, days)
            if df is None:
                return []
            return self.scanner.comprehensive_scan_stock(
                stock_id=stock_id,
                df_daily=df,
                timeframes=timeframes,
                min_rrr=min_rrr,
                min_score=min_score,
            )
        except Exception as e:
            logger.debug(f'{stock_id} 掃描失敗: {e}')
            return []

    def run(
        self,
        stock_ids: Optional[List[str]] = None,
        timeframes: Optional[List[str]] = None,
        days: int = 500,
        min_rrr: float = 0.5,
        min_score: float = 0.60,
        status_filter: Optional[str] = None,
        workers: int = 4,
    ) -> pd.DataFrame:
        """
        執行批量掃描

        Args:
            stock_ids: 股票代碼列表（None=全市場）
            timeframes: 時間框架列表（預設 ['D', 'W']）
            days: 回溯日線天數
            min_rrr: 最小風報比
            min_score: 最小綜合評分
            status_filter: 狀態過濾（'BREAKOUT' / 'FORMING' / None）
            workers: 並行執行緒數

        Returns:
            signals_df: 所有信號的 DataFrame（已按評分降序排列）
        """
        if timeframes is None:
            timeframes = ['D', 'W']

        if stock_ids is None:
            print("取得股票清單...")
            stock_ids = self.scanner.get_stock_list()

        print(f"\n掃描參數：")
        print(f"  股票數：{len(stock_ids)}")
        print(f"  時間框架：{' / '.join(TIMEFRAME_CONFIG[t]['label'] for t in timeframes)}")
        print(f"  回溯天數：{days}")
        print(f"  最小風報比：{min_rrr}   最小評分：{min_score}")
        if status_filter:
            print(f"  狀態過濾：{status_filter}")

        # 預載基本面快取（PER + 月營收年增率），供 score_signal() 使用
        print("\n載入基本面快取...")
        self.scanner.load_fundamentals_cache()
        print()

        all_signals: List[Dict] = []

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(
                    self._process_one, sid, days, timeframes, min_rrr, min_score
                ): sid
                for sid in stock_ids
            }

            with tqdm(total=len(stock_ids), desc="掃描進度", unit="股") as pbar:
                for future in as_completed(futures):
                    signals = future.result()
                    all_signals.extend(signals)
                    pbar.update(1)
                    if signals:
                        pbar.set_postfix(
                            signals=len(all_signals),
                            last=futures[future],
                        )

        df = pd.DataFrame(all_signals)
        if df.empty:
            return df

        # 狀態過濾
        if status_filter:
            df = df[df['status'].str.contains(status_filter, case=False, na=False)]

        # 評分排序
        df = df.sort_values('score', ascending=False).reset_index(drop=True)
        return df

    def close(self):
        self.scanner.close()


# ── 報表輸出 ───────────────────────────────────────────────────────────────────

def _print_console_report(df: pd.DataFrame, top_n: int) -> None:
    """在終端機輸出格式化的掃描報告"""
    if df.empty:
        print("\n未找到符合條件的信號。")
        return

    show = df.head(top_n)

    header = (
        f"\n{'排名':>4}  {'股票':^6}  {'時框':^4}  {'形態':^14}  "
        f"{'狀態':^8}  {'評分':^5}  {'頸線':>8}  {'目標':>8}  "
        f"{'停損':>8}  {'風報':>4}  {'量確':^4}  {'破切':^4}  {'強SR':^4}  "
        f"{'PER':>6}  {'營收YoY':>7}  {'共振TF':>5}"
    )
    sep = "-" * len(header)

    print(f"\n{'='*len(header)}")
    print(f"  SenVision 全市場掃描結果  "
          f"({datetime.now().strftime('%Y-%m-%d %H:%M')})  "
          f"共 {len(df)} 個信號，顯示前 {len(show)} 名")
    print(f"{'='*len(header)}")
    print(header)
    print(sep)

    for rank, row in enumerate(show.itertuples(), 1):
        status_mark = "★" if row.status in ('BREAKOUT', '剛突破') else " "
        vol_mark = "Y" if row.volume_confirmed else "N"
        tl_mark  = "Y" if row.tl_break else "N"
        sr_mark  = "Y" if row.strong_sr else "N"
        per_str  = f"{row.per:>6.1f}" if getattr(row, 'per', None) is not None else f"{'--':>6}"
        yoy_str  = f"{row.revenue_yoy:>+7.1f}%" if getattr(row, 'revenue_yoy', None) is not None else f"{'--':>7} "
        cf_str   = str(getattr(row, 'confluence_tfs', 1))

        print(
            f"{rank:>4}  "
            f"{row.stock_id:^6}  "
            f"{row.timeframe:^4}  "
            f"{row.pattern:^14}  "
            f"{status_mark}{row.status:^7}  "
            f"{row.score:>5.3f}  "
            f"{row.neckline:>8.2f}  "
            f"{row.target:>8.2f}  "
            f"{row.stop_loss:>8.2f}  "
            f"{row.rrr:>4.1f}  "
            f"{vol_mark:^4}  "
            f"{tl_mark:^4}  "
            f"{sr_mark:^4}  "
            f"{per_str}  "
            f"{yoy_str}  "
            f"{cf_str:^5}"
        )

    print(f"{'='*len(header)}")

    # ── 統計摘要 ────────────────────────────────────────────────
    print("\n【統計摘要】")
    print(f"  總信號數  : {len(df)}")
    print(f"  唯一股票  : {df['stock_id'].nunique()}")
    print()

    # 按形態分組
    by_pattern = df.groupby('pattern').size().sort_values(ascending=False)
    print("  按形態分布：")
    for pat, cnt in by_pattern.items():
        print(f"    {pat:<16} {cnt:>4} 個")

    # 按時間框架分組
    tf_labels = {k: v['label'] for k, v in TIMEFRAME_CONFIG.items()}
    by_tf = df.groupby('timeframe').size().reindex(list(TIMEFRAME_CONFIG.keys())).dropna().astype(int)
    print("\n  按時間框架分布：")
    for tf, cnt in by_tf.items():
        print(f"    {tf_labels.get(tf, tf):<6} {cnt:>4} 個")

    # 按狀態分組
    by_status = df.groupby('status').size().sort_values(ascending=False)
    print("\n  按狀態分布：")
    for st, cnt in by_status.items():
        print(f"    {st:<10} {cnt:>4} 個")

    # 突破訊號
    breakout_df = df[df['status'].str.contains('BREAKOUT|剛突破', na=False)]
    if not breakout_df.empty:
        print(f"\n  ★ 突破信號 ({len(breakout_df)} 個)：")
        for _, row in breakout_df.head(10).iterrows():
            print(f"    {row['stock_id']:^6}  "
                  f"{TIMEFRAME_CONFIG.get(row['timeframe'], {}).get('label', row['timeframe']):^4}  "
                  f"{row['pattern']:<14}  "
                  f"頸線={row['neckline']:.2f}  "
                  f"目標={row['target']:.2f}  "
                  f"評分={row['score']:.3f}")


def _save_results(df: pd.DataFrame, output_path: str) -> None:
    """儲存結果 CSV"""
    col_rename = {
        'stock_id':         '股票代碼',
        'timeframe':        '時間框架',
        'pattern':          '形態',
        'status':           '狀態',
        'confidence':       '信心度',
        'neckline':         '頸線',
        'target':           '目標價',
        'stop_loss':        '停損價',
        'rrr':              '風報比',
        'volume_confirmed': '量能確認',
        'tl_break':         '趨勢線突破',
        'strong_sr':        '強支撐壓力',
        'ma_alignment':     '均線排列',
        'per':              'PER本益比',
        'revenue_yoy':      '月營收年增率%',
        'confluence_tfs':   '共振時框數',
        'kd_k':             'KD_K值',
        'bb_pct':           'BB_%B',
        'roe':              'ROE%',
        'rsi_14':           'RSI_14',
        'inst_net':         '三大法人買賣超(股)',
        'volume_ratio':     '量比',
        'vol_pct_60d':      '量能百分位',
        'obv_slope':        'OBV斜率',
        'vp_divergence':    '量價背離',
        'vp_state':         '量價狀態',
        'score':            '評分',
        'formation_date':   '形成日期',
    }
    out = df.rename(columns=col_rename)
    # 加入中文時框標籤欄
    out.insert(2, '時框', out['時間框架'].map(
        {k: v['label'] for k, v in TIMEFRAME_CONFIG.items()}
    ).fillna(out['時間框架']))

    out.to_csv(output_path, index=False, encoding='utf-8-sig')
    print(f"\n結果已儲存：{output_path}")


def _generate_charts(
    df: pd.DataFrame,
    stock_ids: List[str],
    timeframes: List[str],
    days: int,
    db_uri: str,
    charts_dir: Path,
) -> None:
    """為 top-N 股票生成技術分析圖表"""
    from senvision import SenVisionChart
    from senvision.analysis import analyze_timeframe
    from pymongo import MongoClient

    client = MongoClient(db_uri)
    db = client['tw_stock_analysis']
    chart = SenVisionChart(dark_theme=True)
    charts_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n生成圖表（{len(stock_ids)} 支股票 × {len(timeframes)} 個時框）...")

    for stock_id in tqdm(stock_ids, desc="圖表生成"):
        # 取日線數據
        start = datetime.now() - timedelta(days=days)
        cursor = db.stock_price.find(
            {'stock_id': stock_id, 'date': {'$gte': start}},
            {'_id': 0, 'date': 1, 'open': 1, 'high': 1,
             'low': 1, 'close': 1, 'volume': 1},
        ).sort('date', 1)
        df_daily = pd.DataFrame(list(cursor))
        if df_daily.empty:
            continue

        df_daily['date'] = pd.to_datetime(df_daily['date'])
        for col in ['open', 'high', 'low', 'close']:
            df_daily[col] = df_daily[col].apply(lambda x: float(str(x)) if x is not None else None)
            df_daily[col] = pd.to_numeric(df_daily[col], errors='coerce')
        df_daily['volume'] = df_daily['volume'].apply(lambda x: float(str(x)) if x is not None else 0)
        df_daily['volume'] = pd.to_numeric(df_daily['volume'], errors='coerce').fillna(0)
        df_daily = df_daily.dropna(subset=['close']).reset_index(drop=True)

        for tf in timeframes:
            try:
                result = analyze_timeframe(df_daily, stock_id, tf)
                if result is None:
                    continue
                ts = datetime.now().strftime('%m%d_%H%M')
                save_path = str(charts_dir / f"{stock_id}_{tf}_{ts}.png")
                chart.plot(
                    df=result['df'],
                    stock_id=stock_id,
                    timeframe=tf,
                    peaks=result['peaks'],
                    patterns=result['patterns'],
                    sr_levels=result['sr_levels'],
                    trendlines=result['trendlines'],
                    ma_alignment=result.get('ma_alignment', 'mixed'),
                    candle_width_days=TIMEFRAME_CONFIG[tf]['candle_width_days'],
                    save_path=save_path,
                    show=False,
                )
            except Exception as e:
                logger.debug(f'{stock_id}/{tf} 圖表生成失敗: {e}')
                continue

    client.close()


# ── CLI 入口 ───────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description='SenVision 全市場批量技術分析掃描',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  # 全市場日+週線掃描（預設）
  python3 scripts/senvision_market_scan.py

  # 只掃描日線，回溯 180 天
  python3 scripts/senvision_market_scan.py --timeframes D --days 180

  # 全時間框架掃描，顯示前 50，產生圖表
  python3 scripts/senvision_market_scan.py --all-timeframes --top 50 --charts

  # 只看已突破信號
  python3 scripts/senvision_market_scan.py --status BREAKOUT

  # 指定股票清單
  python3 scripts/senvision_market_scan.py --stocks 2330 2454 2382

  # 從文件讀取股票清單（每行一個代碼）
  python3 scripts/senvision_market_scan.py --stock-file my_watchlist.txt
        """,
    )
    p.add_argument('--timeframes', '-t', nargs='+',
                   choices=list(TIMEFRAME_CONFIG.keys()),
                   default=['D', 'W'],
                   help='時間框架（預設：D W）')
    p.add_argument('--all-timeframes', action='store_true',
                   help='掃描全部 6 個時間框架（D/W/M/Q/6M/Y）')
    p.add_argument('--days', type=int, default=500,
                   help='回溯日線天數（預設 500；月線以上建議 1460）')
    p.add_argument('--min-rrr', type=float, default=0.5,
                   help='最小風報比（預設 1.5）')
    p.add_argument('--min-score', type=float, default=0.60,
                   help='最小評分（預設 0.60）')
    p.add_argument('--status', type=str, default=None,
                   choices=['BREAKOUT', 'FORMING', 'CONFIRMED'],
                   help='只顯示指定狀態的信號')
    p.add_argument('--top', type=int, default=30,
                   help='顯示前 N 名信號（預設 30）')
    p.add_argument('--stocks', nargs='+',
                   help='指定股票代碼（空格分隔）')
    p.add_argument('--stock-file', type=str,
                   help='從文字檔讀取股票清單（每行一個代碼）')
    p.add_argument('--output', '-o', type=str, default=None,
                   help='CSV 輸出路徑（預設自動命名至 results/）')
    p.add_argument('--charts', action='store_true',
                   help='為前 top 名股票生成技術分析圖表')
    p.add_argument('--workers', type=int, default=4,
                   help='並行執行緒數（預設 4）')
    p.add_argument('--db-uri', default='mongodb://localhost:27017/',
                   help='MongoDB 連線 URI')
    return p


def main() -> None:
    args = _build_parser().parse_args()

    # ── 決定時間框架 ─────────────────────────────────────────────
    if args.all_timeframes:
        timeframes = list(TIMEFRAME_CONFIG.keys())   # D/W/M/Q/6M/Y
    else:
        timeframes = args.timeframes

    # ── 決定股票清單 ─────────────────────────────────────────────
    stock_ids: Optional[List[str]] = None

    if args.stocks:
        stock_ids = args.stocks
    elif args.stock_file:
        fpath = Path(args.stock_file)
        if not fpath.exists():
            print(f"錯誤: 找不到股票清單文件 {fpath}")
            sys.exit(1)
        stock_ids = [
            line.strip() for line in fpath.read_text().splitlines()
            if line.strip() and not line.startswith('#')
        ]
        print(f"從 {fpath} 讀取 {len(stock_ids)} 支股票")

    # ── 輸出路徑 ────────────────────────────────────────────────
    results_dir = _PROJECT_ROOT / 'results'
    results_dir.mkdir(exist_ok=True)

    if args.output:
        csv_path = args.output
    else:
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        tf_str = '_'.join(timeframes)
        csv_path = str(results_dir / f"scan_{tf_str}_{ts}.csv")

    # ── 執行掃描 ─────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("  SenVision 全市場批量技術分析掃描")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    batch = BatchScanner(db_uri=args.db_uri)

    try:
        result_df = batch.run(
            stock_ids=stock_ids,
            timeframes=timeframes,
            days=args.days,
            min_rrr=args.min_rrr,
            min_score=args.min_score,
            status_filter=args.status,
            workers=args.workers,
        )

        # ── 控制台報告 ───────────────────────────────────────────
        _print_console_report(result_df, top_n=args.top)

        # ── CSV 儲存 ─────────────────────────────────────────────
        if not result_df.empty:
            _save_results(result_df, csv_path)

        # ── 圖表生成（可選）─────────────────────────────────────
        if args.charts and not result_df.empty:
            top_stocks = result_df['stock_id'].unique()[:args.top].tolist()
            charts_dir = _PROJECT_ROOT / 'charts' / f"scan_{datetime.now().strftime('%m%d_%H%M')}"
            _generate_charts(
                df=result_df,
                stock_ids=top_stocks,
                timeframes=timeframes,
                days=args.days,
                db_uri=args.db_uri,
                charts_dir=charts_dir,
            )
            print(f"圖表已儲存至：{charts_dir}/")

        print("\n掃描完成。")

    except KeyboardInterrupt:
        print("\n已中斷。")
    finally:
        batch.close()


if __name__ == '__main__':
    main()
