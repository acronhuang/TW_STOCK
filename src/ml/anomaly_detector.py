#!/usr/bin/env python3
"""
異常偵測模組
===========
偵測股價/成交量異常行為，用於風險預警和機會發現。

方法：
1. 統計方法：Z-Score、IQR
2. Isolation Forest（無監督 ML）
3. 成交量異常偵測
4. 價格跳空偵測

Usage:
    from src.ml.anomaly_detector import AnomalyDetector
    ad = AnomalyDetector()
    anomalies = ad.detect('2330')
    market_anomalies = ad.scan_market()
"""

import sys
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
from pymongo import MongoClient
from bson.decimal128 import Decimal128

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

logger = logging.getLogger(__name__)


def _to_float(v) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, Decimal128):
        return float(v.to_decimal())
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class AnomalyDetector:
    """股票異常偵測器"""

    def __init__(self,
                 mongo_uri: str = "mongodb://localhost:27017/",
                 db_name: str = "tw_stock_analysis"):
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]

    def detect(self, symbol: str, lookback: int = 60) -> Dict:
        """個股異常偵測（綜合）"""
        df = self._get_price_df(symbol, lookback)
        if df is None or len(df) < 20:
            return {'symbol': symbol, 'error': '資料不足'}

        anomalies = []

        # 1. 價格 Z-Score 異常
        price_anoms = self._detect_price_zscore(df)
        anomalies.extend(price_anoms)

        # 2. 成交量異常
        vol_anoms = self._detect_volume_anomaly(df)
        anomalies.extend(vol_anoms)

        # 3. 跳空缺口
        gap_anoms = self._detect_gap(df)
        anomalies.extend(gap_anoms)

        # 4. Isolation Forest
        if_anoms = self._detect_isolation_forest(df)
        anomalies.extend(if_anoms)

        # 依日期排序（最新在前）
        anomalies.sort(key=lambda x: x.get('date', ''), reverse=True)

        # 異常嚴重度
        severity = 'low'
        if len(anomalies) >= 5:
            severity = 'high'
        elif len(anomalies) >= 2:
            severity = 'medium'

        return {
            'symbol': symbol,
            'lookback_days': lookback,
            'anomaly_count': len(anomalies),
            'severity': severity,
            'anomalies': anomalies[:10],
            'latest_price': float(df['close'].iloc[-1]),
            'latest_date': str(df['date'].iloc[-1])[:10],
        }

    def scan_market(self, limit: int = 20) -> List[Dict]:
        """全市場異常掃描"""
        # 取活躍股票（有近期價格的）
        cutoff = datetime.now() - timedelta(days=5)
        symbols = self.db.stock_price.distinct(
            'symbol', {'date': {'$gte': cutoff}})

        # 只取一般股票
        symbols = [s for s in symbols if s.isdigit() and len(s) == 4]
        logger.info(f'掃描 {len(symbols)} 支股票...')

        results = []
        for sym in symbols:
            try:
                result = self.detect(sym, lookback=30)
                if result.get('anomaly_count', 0) >= 2:
                    results.append(result)
            except Exception:
                pass

        results.sort(key=lambda x: x['anomaly_count'], reverse=True)
        return results[:limit]

    # ──────────────────────────────────────────────
    #  偵測方法
    # ──────────────────────────────────────────────
    def _detect_price_zscore(self, df: pd.DataFrame, threshold: float = 2.5) -> List[Dict]:
        """價格報酬 Z-Score 異常"""
        returns = df['close'].pct_change()
        mean = returns.mean()
        std = returns.std()
        if std == 0:
            return []

        z_scores = (returns - mean) / std
        anomalies = []

        for i in range(len(df)):
            z = z_scores.iloc[i]
            if abs(z) > threshold:
                ret = returns.iloc[i]
                anomalies.append({
                    'type': 'price_zscore',
                    'date': str(df['date'].iloc[i])[:10],
                    'description': f'報酬 Z-Score={z:.2f} (報酬{ret*100:+.2f}%)',
                    'severity': 'high' if abs(z) > 3 else 'medium',
                    'direction': 'up' if ret > 0 else 'down',
                    'z_score': round(float(z), 2),
                })

        return anomalies

    def _detect_volume_anomaly(self, df: pd.DataFrame, multiplier: float = 3.0) -> List[Dict]:
        """爆量偵測（成交量 > N 倍均量）"""
        vol = df['volume']
        vol_ma20 = vol.rolling(20).mean()
        anomalies = []

        for i in range(20, len(df)):
            if vol_ma20.iloc[i] and vol_ma20.iloc[i] > 0:
                ratio = vol.iloc[i] / vol_ma20.iloc[i]
                if ratio > multiplier:
                    ret = df['close'].pct_change().iloc[i]
                    anomalies.append({
                        'type': 'volume_spike',
                        'date': str(df['date'].iloc[i])[:10],
                        'description': f'成交量 {ratio:.1f} 倍均量',
                        'severity': 'high' if ratio > 5 else 'medium',
                        'direction': 'up' if ret > 0 else 'down',
                        'volume_ratio': round(float(ratio), 1),
                    })

        return anomalies

    def _detect_gap(self, df: pd.DataFrame, threshold: float = 0.03) -> List[Dict]:
        """跳空缺口偵測"""
        anomalies = []

        for i in range(1, len(df)):
            prev_close = df['close'].iloc[i - 1]
            curr_open = df['open'].iloc[i]
            if prev_close and prev_close > 0:
                gap = (curr_open - prev_close) / prev_close
                if abs(gap) > threshold:
                    anomalies.append({
                        'type': 'gap',
                        'date': str(df['date'].iloc[i])[:10],
                        'description': f'跳{"漲" if gap > 0 else "跌"}缺口 {gap*100:+.2f}%',
                        'severity': 'high' if abs(gap) > 0.05 else 'medium',
                        'direction': 'up' if gap > 0 else 'down',
                        'gap_pct': round(float(gap) * 100, 2),
                    })

        return anomalies

    def _detect_isolation_forest(self, df: pd.DataFrame) -> List[Dict]:
        """Isolation Forest 無監督異常偵測"""
        try:
            from sklearn.ensemble import IsolationForest
        except ImportError:
            return []

        # 特徵：日報酬、成交量比、振幅
        returns = df['close'].pct_change().fillna(0)
        vol_ratio = (df['volume'] / df['volume'].rolling(20).mean()).fillna(1)
        amplitude = ((df['high'] - df['low']) / df['close']).fillna(0)

        features = np.column_stack([
            returns.values,
            vol_ratio.values,
            amplitude.values,
        ])

        # 訓練
        iso = IsolationForest(
            n_estimators=100,
            contamination=0.05,
            random_state=42,
        )
        labels = iso.fit_predict(features)
        scores = iso.decision_function(features)

        anomalies = []
        for i in range(len(df)):
            if labels[i] == -1:  # 異常
                anomalies.append({
                    'type': 'isolation_forest',
                    'date': str(df['date'].iloc[i])[:10],
                    'description': f'ML 異常偵測 (score={scores[i]:.3f})',
                    'severity': 'medium',
                    'direction': 'up' if returns.iloc[i] > 0 else 'down',
                    'anomaly_score': round(float(scores[i]), 4),
                })

        return anomalies

    # ──────────────────────────────────────────────
    #  資料
    # ──────────────────────────────────────────────
    def _get_price_df(self, symbol: str, lookback: int) -> Optional[pd.DataFrame]:
        cutoff = datetime.now() - timedelta(days=int(lookback * 1.5))
        prices = list(self.db.stock_price.find(
            {'symbol': symbol, 'date': {'$gte': cutoff}},
            {'date': 1, 'open': 1, 'high': 1, 'low': 1, 'close': 1, 'volume': 1}
        ).sort('date', 1))

        if len(prices) < 20:
            return None

        df = pd.DataFrame([{
            'date': p['date'],
            'open': _to_float(p.get('open')) or 0,
            'high': _to_float(p.get('high')) or 0,
            'low': _to_float(p.get('low')) or 0,
            'close': _to_float(p.get('close')) or 0,
            'volume': _to_float(p.get('volume')) or 0,
        } for p in prices])

        df = df[df['close'] > 0]
        return df if len(df) >= 20 else None


# ──────────────────────────────────────────────
#  CLI
# ──────────────────────────────────────────────
if __name__ == '__main__':
    from dotenv import load_dotenv
    load_dotenv(str(project_root / '.env'))

    ad = AnomalyDetector()

    for sym in ['2330', '2317', '2603']:
        print(f"\n{'='*55}")
        result = ad.detect(sym, lookback=60)
        if result.get('error'):
            print(f"  {sym}: {result['error']}")
            continue

        print(f"  {sym} 異常偵測 (近 {result['lookback_days']} 日)")
        print(f"  異常數: {result['anomaly_count']}  嚴重度: {result['severity']}")

        for a in result['anomalies'][:5]:
            icon = '🔴' if a['severity'] == 'high' else '🟡'
            print(f"    {icon} {a['date']} [{a['type']}] {a['description']}")
