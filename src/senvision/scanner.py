"""
SenVision 市場掃描器

自動掃描全市場，識別符合條件的技術形態

Usage:
    python3 src/senvision/scanner.py --pattern W-Bottom --days 60
    python3 src/senvision/scanner.py --pattern M-Top --min-rrr 2.5
    python3 src/senvision/scanner.py --all --output results/patterns.csv

Author: SenVision Team
Date: 2026-02-24
"""

import sys
import logging
from pathlib import Path
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
import argparse
import pandas as pd
from pymongo import MongoClient
from tqdm import tqdm

logger = logging.getLogger(__name__)

# 添加項目路徑
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / 'src'))

from senvision.pattern_detector import (
    Pattern, PatternType, PatternStatus,
    WBottomDetector, MTopDetector,
    TripleBottomDetector, TripleTopDetector,
)
from senvision.analysis import analyze_timeframe, score_signal

try:
    from utils.stock_classifier import StockClassifier
    _HAS_CLASSIFIER = True
except ImportError:
    _HAS_CLASSIFIER = False


_VOL_STATE_NAME = {1: '絕望量', 2: '鎖籌', 3: '窒息量'}   # 框架量價情境(僅供判讀,非評分訊號)


def _volume_state_label(volume_ratio, vol_pct_60d, vp_divergence, vol_state=None):
    """將量價因子彙整為人類可讀標籤，如『爆量/空背』『量縮/窒息量』『正常/多背』。None 表資料不足。
    vol_state：框架量價情境碼(1絕望量/2鎖籌/3窒息量)，回測無單獨 edge，僅作情境註記。"""
    parts = []
    if volume_ratio is not None:
        if volume_ratio >= 2.0 or (vol_pct_60d is not None and vol_pct_60d >= 90):
            parts.append('爆量')
        elif volume_ratio <= 0.7 or (vol_pct_60d is not None and vol_pct_60d <= 20):
            parts.append('量縮')
        else:
            parts.append('正常')
    if vp_divergence == -1:
        parts.append('空背')
    elif vp_divergence == 1:
        parts.append('多背')
    if vol_state is not None:
        name = _VOL_STATE_NAME.get(int(vol_state))   # 快取會 float() 轉型 → 轉回 int 查表
        if name:
            parts.append(name)
    return '/'.join(parts) if parts else None


class MarketScanner:
    """
    市場掃描器

    功能：
    - 掃描全市場或指定股票
    - 識別 W底 / M頭 / 三重底 / 三重頂（+ 三重底/三重頂）
    - 多時間框架綜合分析（透過 comprehensive_scan_stock）
    - 支撐壓力強度評估
    - 趨勢切線突破偵測
    - 過濾條件篩選與評分排名
    """

    def __init__(self,
                 db_uri: str = 'mongodb://localhost:27017/',
                 db_name: str = 'tw_stock_analysis'):
        """
        Args:
            db_uri: MongoDB 連線 URI
            db_name: 資料庫名稱
        """
        self.client = MongoClient(db_uri)
        self.db = self.client[db_name]

        if _HAS_CLASSIFIER:
            self.classifier = StockClassifier(self.db)
        else:
            self.classifier = None

        # 初始化形態檢測器（單一時間框架掃描用）
        self.detectors = {
            PatternType.W_BOTTOM:      WBottomDetector(),
            PatternType.M_TOP:         MTopDetector(),
            PatternType.TRIPLE_BOTTOM: TripleBottomDetector(),
            PatternType.TRIPLE_TOP:    TripleTopDetector(),
        }

        # 基本面快取（由 load_fundamentals_cache() 填充）
        # 所有估值數據統一來自 stock_factors 集合
        self._per_cache:     Dict[str, float] = {}    # stock_id → PE ratio (衍生自 _factors_cache)
        self._rev_cache:     Dict[str, float] = {}    # stock_id → revenue YoY %
        self._factors_cache: Dict[str, Dict]  = {}    # stock_id → {pe_ratio, pb_ratio, dividend_yield, roe, rsi_14, ...}
        self._inst_cache:    Dict[str, Dict]  = {}    # stock_id → {total_net, ...}

    def get_stock_list(self,
                       exclude_types: Optional[List] = None) -> List[str]:
        """
        獲取股票列表

        Args:
            exclude_types: 排除的證券類型（需 StockClassifier）

        Returns:
            stock_ids: 股票代碼列表
        """
        stock_ids = self.db.stock_price.distinct('stock_id')

        if self.classifier and exclude_types is not None:
            classified = self.classifier.classify_stock_list(stock_ids)
            filtered = []
            for sec_type, stocks in classified.items():
                if sec_type not in exclude_types:
                    filtered.extend(stocks)
            return sorted(filtered)

        # 無 classifier 時：優先使用 taiwan_stock_info 確認上市/上櫃股票
        try:
            info_ids = set(
                doc['stock_id']
                for doc in self.db.taiwan_stock_info.find(
                    {'type': {'$in': ['twse', 'tpex']},
                     'security_type': 'Stock'},
                    {'stock_id': 1, '_id': 0},
                )
            )
            if info_ids:
                # 取 stock_price 中有資料 AND taiwan_stock_info 確認為普通股的代碼
                filtered = sorted(info_ids & set(stock_ids))
                return filtered
        except Exception:
            pass
        # 回退：純數字 4~6 碼過濾
        filtered = [s for s in stock_ids
                    if isinstance(s, str) and s.isdigit() and 4 <= len(s) <= 6]
        return sorted(filtered)

    def get_price_data(self,
                       stock_id: str,
                       days: int = 120) -> Optional[pd.DataFrame]:
        """
        獲取股票價格數據

        Args:
            stock_id: 股票代碼
            days: 回溯天數

        Returns:
            df: 價格數據 DataFrame（至少 30 筆才回傳）
        """
        start_date = datetime.now() - timedelta(days=days)

        cursor = self.db.stock_price.find(
            {'stock_id': stock_id, 'date': {'$gte': start_date}},
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

    def load_fundamentals_cache(self) -> None:
        """
        一次性載入全市場基本面與技術因子快取，供 score_signal() 使用。

        資料來源整合（三合一）：
            TWSE/TPEX  → monthly_revenue (月營收年增率)
            FinMind    → stock_factors   (PE/ROE/RSI/動能)
            TWSE T86   → institutional_flow (三大法人籌碼)

        全部使用 MongoDB aggregation $group+$first，約 3 次 DB 往返
        即可載入 2,000+ 支股票的完整基本面。
        """
        # ── [1] 月營收年增率（monthly_revenue 集合）──────────────────
        # 欄位說明：key=symbol, sort=year_month, value=yoy_growth (%)
        try:
            pipeline = [
                {'$sort': {'year_month': -1}},
                {'$group': {
                    '_id':       '$symbol',       # monthly_revenue 使用 symbol
                    'yoy_growth': {'$first': '$yoy_growth'},
                }},
            ]
            self._rev_cache = {}
            for doc in self.db.monthly_revenue.aggregate(pipeline):
                sid = doc['_id']
                yoy = doc.get('yoy_growth')
                if yoy is not None:
                    try:
                        v = float(str(yoy))
                        if v == v:   # NaN check
                            self._rev_cache[sid] = v
                    except (ValueError, TypeError):
                        pass
            print(f"  月營收年增率快取：{len(self._rev_cache)} 支股票")
        except Exception as e:
            print(f"  月營收年增率快取載入失敗: {e}")

        # ── [2] 綜合因子快取（stock_factors 集合）──────────────────────
        # stock_factors 由多個來源寫入同一集合（可能合併至同一筆記錄）：
        #   TWSE/TPEX → pe_ratio, pb_ratio, dividend_yield
        #   factor_calc → roe, rsi_14, operating_margin, return_1m
        # 使用「近 30 天 + 取首個非 null 值」策略，來源無關、null 安全
        _FACTOR_FIELDS = (
            'pe_ratio', 'pb_ratio', 'dividend_yield',
            'roe', 'rsi_14', 'operating_margin', 'return_1m',
            'volume_ratio', 'vol_pct_60d', 'obv_slope', 'vp_divergence', 'vol_state',
            'ma_bias_20', 'ma_bias_60', 'ma_bias_120', 'ma_bias_240',
            'ma_above_long', 'ma_long_trend', 'foreign_streak', 'trust_streak',
        )
        try:
            cutoff = datetime.now() - timedelta(days=30)
            pipeline = [
                {'$match': {'date': {'$gte': cutoff}}},
                {'$sort': {'date': -1}},
                {'$group': {
                    '_id': '$symbol',
                    **{f'{f}_arr': {'$push': f'${f}'} for f in _FACTOR_FIELDS},
                }},
                {'$project': {
                    **{f: {'$first': {'$filter': {
                        'input': f'${f}_arr',
                        'cond': {'$ne': ['$$this', None]},
                    }}} for f in _FACTOR_FIELDS},
                }},
            ]
            self._factors_cache: Dict[str, Dict] = {}
            for doc in self.db.stock_factors.aggregate(pipeline, allowDiskUse=True):
                sid = doc['_id']
                entry = {}
                for field in _FACTOR_FIELDS:
                    val = doc.get(field)
                    if val is not None:
                        try:
                            fv = float(str(val))
                            if fv == fv:  # NaN check
                                entry[field] = fv
                        except (ValueError, TypeError):
                            pass
                if entry:
                    self._factors_cache[sid] = entry

            # pe_ratio 快取（從 _factors_cache 衍生，不再回退舊集合）
            self._per_cache = {
                sid: d['pe_ratio']
                for sid, d in self._factors_cache.items()
                if 'pe_ratio' in d and d['pe_ratio'] > 0
            }
            n_pb  = sum(1 for d in self._factors_cache.values() if 'pb_ratio' in d)
            n_div = sum(1 for d in self._factors_cache.values() if 'dividend_yield' in d)
            n_rsi = sum(1 for d in self._factors_cache.values() if 'rsi_14' in d)
            n_ret = sum(1 for d in self._factors_cache.values() if 'return_1m' in d)
            print(f"  綜合因子快取 (stock_factors)：{len(self._factors_cache)} 支股票"
                  f"，PE>0：{len(self._per_cache)}，PB：{n_pb}，股息：{n_div}"
                  f"，RSI：{n_rsi}，動能：{n_ret}")
        except Exception as e:
            print(f"  綜合因子快取載入失敗: {e}")

        # ── [3] 三大法人籌碼快取（institutional_flow 集合）──────────────
        # 由 twse_daily_update.py --no-institutional=False 定期更新
        try:
            pipeline = [
                {'$sort': {'date': -1}},
                {'$group': {
                    '_id':         '$stock_id',
                    'total_net':   {'$first': '$total_net'},
                    'foreign_net': {'$first': '$foreign_net'},
                    'trust_net':   {'$first': '$trust_net'},
                }},
            ]
            self._inst_cache: Dict[str, Dict] = {}
            for doc in self.db.institutional_flow.aggregate(pipeline):
                sid = doc['_id']
                entry = {}
                for field in ('total_net', 'foreign_net', 'trust_net'):
                    val = doc.get(field)
                    if val is not None:
                        try:
                            entry[field] = float(str(val))
                        except (ValueError, TypeError):
                            pass
                if entry:
                    self._inst_cache[sid] = entry
            if self._inst_cache:
                print(f"  三大法人籌碼快取：{len(self._inst_cache)} 支股票")
            else:
                print(f"  三大法人籌碼快取：無資料（請先執行 twse_daily_update.py）")
        except Exception as e:
            print(f"  三大法人籌碼快取載入失敗: {e}")

    # ── 單一形態掃描（原有方法，維持向後相容）─────────────────────────────────────

    def scan_pattern(self,
                     pattern_type: PatternType,
                     stock_ids: Optional[List[str]] = None,
                     days: int = 120,
                     min_rrr: float = 0.5,
                     status_filter: Optional[List[PatternStatus]] = None) -> List[Pattern]:
        """
        掃描指定形態

        Args:
            pattern_type: 形態類型
            stock_ids: 股票列表（None=全市場）
            days: 回溯天數
            min_rrr: 最小風報比
            status_filter: 狀態過濾（None=全部）

        Returns:
            patterns: 符合條件的形態列表
        """
        if stock_ids is None:
            stock_ids = self.get_stock_list()

        if pattern_type not in self.detectors:
            raise ValueError(f"不支援的形態類型: {pattern_type}")

        detector = self.detectors[pattern_type]
        all_patterns = []

        print(f"\n掃描 {pattern_type.value} 形態...")
        print(f"   股票數: {len(stock_ids)}  回溯: {days} 天  最小風報比: {min_rrr}")

        for stock_id in tqdm(stock_ids, desc="掃描進度"):
            try:
                df = self.get_price_data(stock_id, days)
                if df is None:
                    continue

                patterns = detector.detect(df, stock_id)

                for pattern in patterns:
                    if pattern.risk_reward_ratio < min_rrr:
                        continue
                    if status_filter and pattern.status not in status_filter:
                        continue
                    all_patterns.append(pattern)

            except Exception as e:
                logger.debug(f'{stock_id} 掃描失敗: {e}')
                continue

        return all_patterns

    def scan_all_patterns(self, **kwargs) -> Dict[PatternType, List[Pattern]]:
        """
        掃描所有形態（W底、M頭、三重底、三重頂）

        Args:
            **kwargs: 傳遞給 scan_pattern 的參數

        Returns:
            results: {PatternType: [Pattern, ...]}
        """
        results = {}
        for pattern_type in self.detectors:
            patterns = self.scan_pattern(pattern_type, **kwargs)
            if patterns:
                results[pattern_type] = patterns
        return results

    # ── 多時間框架綜合掃描（新增）─────────────────────────────────────────────────

    def comprehensive_scan_stock(
        self,
        stock_id: str,
        df_daily: pd.DataFrame,
        timeframes: List[str],
        min_rrr: float = 0.5,
        min_score: float = 0.60,
    ) -> List[Dict[str, Any]]:
        """
        對單支股票在多個時間框架上執行全套分析，並對每個信號評分。

        評分包含基本面（PER/月營收）與多時間框架共振加分，
        需先呼叫 load_fundamentals_cache() 以啟用基本面加分。

        Args:
            stock_id: 股票代碼
            df_daily: 日線 OHLCV DataFrame
            timeframes: 要分析的時間框架列表
            min_rrr: 最小風報比過濾
            min_score: 最小評分過濾（在多時間框架共振加分後再過濾）

        Returns:
            符合條件的信號列表，每個元素為 dict（含評分與形態資訊）
        """
        # ── 基本面數據（從快取取得，無快取則 None）──────────────────
        per: Optional[float] = self._per_cache.get(stock_id)
        revenue_yoy: Optional[float] = self._rev_cache.get(stock_id)
        factors = self._factors_cache.get(stock_id, {})
        roe     = factors.get('roe')
        rsi_14  = factors.get('rsi_14')
        volume_ratio  = factors.get('volume_ratio')
        vol_pct_60d   = factors.get('vol_pct_60d')
        obv_slope     = factors.get('obv_slope')
        vp_divergence = factors.get('vp_divergence')
        vol_state     = factors.get('vol_state')
        ma_bias_20    = factors.get('ma_bias_20')
        ma_bias_60    = factors.get('ma_bias_60')
        foreign_streak = factors.get('foreign_streak')
        trust_streak   = factors.get('trust_streak')
        ma_above_long  = factors.get('ma_above_long')
        inst_data  = self._inst_cache.get(stock_id, {})
        inst_net   = inst_data.get('total_net')

        # ── 第一輪：收集所有通過 RRR 門檻的候選信號 ─────────────────
        candidates: List[Dict[str, Any]] = []

        for tf in timeframes:
            try:
                result = analyze_timeframe(df_daily, stock_id, tf)
                if result is None:
                    continue

                ma_alignment = result.get('ma_alignment', 'mixed')
                tl_broken = any(tl.is_broken for tl in result['trendlines'])

                kd_k   = result.get('kd_k')
                bb_pct = result.get('bb_pct')

                for pattern in result['patterns']:
                    candidates.append({
                        'pattern':      pattern,
                        'tf':           tf,
                        'sr_levels':    result['sr_levels'],
                        'trendlines':   result['trendlines'],
                        'ma_alignment': ma_alignment,
                        'tl_broken':    tl_broken,
                        'kd_k':         kd_k,
                        'bb_pct':       bb_pct,
                    })

            except Exception as e:
                logger.debug(f'{stock_id}/{tf} 分析失敗: {e}')
                continue

        if not candidates:
            return []

        # ── 多時間框架共振計數（信號所涵蓋的 TF 數量）──────────────
        confluence_tfs = len({c['tf'] for c in candidates})

        # ── 第二輪：加入共振加分後重新評分，並過濾最小評分門檻 ──────
        signals: List[Dict[str, Any]] = []

        for c in candidates:
            pattern = c['pattern']
            sig_score = score_signal(
                pattern=pattern,
                timeframe=c['tf'],
                sr_levels=c['sr_levels'],
                trendlines=c['trendlines'],
                ma_alignment=c['ma_alignment'],
                per=per,
                revenue_yoy=revenue_yoy,
                confluence_timeframes=confluence_tfs,
                kd_k=c.get('kd_k'),
                bb_pct=c.get('bb_pct'),
                roe=roe,
                rsi_14=rsi_14,
                inst_net=inst_net,
                volume_ratio=volume_ratio,
                obv_slope=obv_slope,
                vp_divergence=int(vp_divergence) if vp_divergence is not None else None,
                foreign_streak=int(foreign_streak) if foreign_streak is not None else None,
                ma_above_long=int(ma_above_long) if ma_above_long is not None else None,
            )
            if sig_score < min_score:
                continue
            if pattern.risk_reward_ratio < min_rrr:
                continue

            signals.append({
                'stock_id':         stock_id,
                'timeframe':        c['tf'],
                'pattern':          pattern.pattern_type.value,
                'status':           pattern.status.value,
                'confidence':       round(pattern.confidence, 3),
                'neckline':         pattern.neckline,
                'target':           pattern.target,
                'stop_loss':        pattern.stop_loss,
                'rrr':              round(pattern.risk_reward_ratio, 2),
                'volume_confirmed': pattern.volume_confirmed,
                'tl_break':         c['tl_broken'],
                'strong_sr':        pattern.neckline > 0 and any(
                    sr.strength == 'strong' and
                    abs(sr.price - pattern.neckline) / pattern.neckline <= 0.02
                    for sr in c['sr_levels']
                ),
                'ma_alignment':     c['ma_alignment'],
                'per':              round(per, 2) if per is not None else None,
                'revenue_yoy':      round(revenue_yoy, 1) if revenue_yoy is not None else None,
                'confluence_tfs':   confluence_tfs,
                'kd_k':             round(c['kd_k'], 1) if c.get('kd_k') is not None else None,
                'bb_pct':           round(c['bb_pct'], 3) if c.get('bb_pct') is not None else None,
                'roe':              round(roe, 1) if roe is not None else None,
                'rsi_14':           round(rsi_14, 1) if rsi_14 is not None else None,
                'inst_net':         int(inst_net) if inst_net is not None else None,
                'volume_ratio':     round(volume_ratio, 2) if volume_ratio is not None else None,
                'vol_pct_60d':      round(vol_pct_60d, 1) if vol_pct_60d is not None else None,
                'obv_slope':        round(obv_slope, 4) if obv_slope is not None else None,
                'vp_divergence':    int(vp_divergence) if vp_divergence is not None else None,
                'vp_state':         _volume_state_label(volume_ratio, vol_pct_60d, vp_divergence, vol_state),
                'ma_bias_20':       round(ma_bias_20, 1) if ma_bias_20 is not None else None,
                'ma_bias_60':       round(ma_bias_60, 1) if ma_bias_60 is not None else None,
                'foreign_streak':   int(foreign_streak) if foreign_streak is not None else None,
                'trust_streak':     int(trust_streak) if trust_streak is not None else None,
                'score':            sig_score,
                'formation_date':   pattern.formation_date.strftime('%Y-%m-%d'),
            })

        return signals

    # ── 報表與輸出（維持原有方法）─────────────────────────────────────────────────

    def print_report(self, patterns: List[Pattern]):
        """打印單一形態掃描報告"""
        if not patterns:
            print("未找到符合條件的形態")
            return

        patterns.sort(key=lambda p: p.risk_reward_ratio, reverse=True)

        print("\n" + "="*100)
        print(f"找到 {len(patterns)} 個形態")
        print("="*100)
        print(f"\n{'股票':^8} {'形態':^15} {'頸線':^10} {'目標價':^10} "
              f"{'停損價':^10} {'風報比':^8} {'狀態':^10} {'量確認':^8}")
        print("-"*100)

        for pattern in patterns:
            vol = "Y" if pattern.volume_confirmed else "N"
            print(f"{pattern.stock_id:^8} "
                  f"{pattern.pattern_type.value:^15} "
                  f"{pattern.neckline:^10.2f} "
                  f"{pattern.target:^10.2f} "
                  f"{pattern.stop_loss:^10.2f} "
                  f"{pattern.risk_reward_ratio:^8.2f} "
                  f"{pattern.status.value:^10} "
                  f"{vol:^8}")

        print("="*100)

    def export_to_csv(self, patterns: List[Pattern], output_path: str):
        """導出形態列表為 CSV"""
        if not patterns:
            print("無數據可導出")
            return
        pd.DataFrame([p.to_dict() for p in patterns]).to_csv(
            output_path, index=False, encoding='utf-8-sig'
        )
        print(f"已導出至 {output_path}")

    def close(self):
        """關閉數據庫連接"""
        self.client.close()


def main():
    """主函數（單一形態掃描）"""
    parser = argparse.ArgumentParser(
        description='SenVision 市場掃描器 - 自動識別技術形態',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  python3 src/senvision/scanner.py --pattern W-Bottom
  python3 src/senvision/scanner.py --pattern M-Top --min-rrr 2.5
  python3 src/senvision/scanner.py --all --output results/patterns.csv
  python3 src/senvision/scanner.py --all --status BREAKOUT
        """,
    )

    parser.add_argument('--pattern', type=str,
                        choices=['W-Bottom', 'M-Top', 'Triple-Bottom', 'Triple-Top', 'all'],
                        default='all', help='形態類型（預設：all）')
    parser.add_argument('--days', type=int, default=120, help='回溯天數（預設：120）')
    parser.add_argument('--min-rrr', type=float, default=0.5, help='最小風報比（預設：0.5）')
    parser.add_argument('--status', type=str,
                        choices=['FORMING', 'BREAKOUT', 'CONFIRMED'], help='過濾狀態')
    parser.add_argument('--output', '-o', type=str, help='導出 CSV 路徑')
    parser.add_argument('--stocks', type=str, nargs='+', help='指定股票代碼（空格分隔）')

    args = parser.parse_args()

    scanner = MarketScanner()

    try:
        scan_kwargs = {
            'days': args.days,
            'min_rrr': args.min_rrr,
            'stock_ids': args.stocks,
        }
        if args.status:
            scan_kwargs['status_filter'] = [PatternStatus[args.status]]

        print("\n" + "="*80)
        print("SenVision 市場掃描器")
        print("="*80)
        print(f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        _name_map = {
            'W-Bottom':    PatternType.W_BOTTOM,
            'M-Top':       PatternType.M_TOP,
            'Triple-Bottom': PatternType.TRIPLE_BOTTOM,
            'Triple-Top':  PatternType.TRIPLE_TOP,
        }

        if args.pattern == 'all':
            results = scanner.scan_all_patterns(**scan_kwargs)
            all_patterns = [p for plist in results.values() for p in plist]
        else:
            pt = _name_map[args.pattern]
            all_patterns = scanner.scan_pattern(pt, **scan_kwargs)

        scanner.print_report(all_patterns)

        if args.output:
            scanner.export_to_csv(all_patterns, args.output)

        print("\n掃描完成")

    finally:
        scanner.close()


if __name__ == '__main__':
    main()
