#!/usr/bin/env python3
"""
股價預測模型
===========
用 XGBoost + 技術特徵預測短期漲跌方向（分類）與報酬幅度（回歸）。

特徵工程：MA、RSI、MACD、成交量比、動量、波動度、籌碼面。
目標：未來 5 日報酬率 > 0（漲/跌分類）

Usage:
    from src.ml.predictor import StockPredictor
    sp = StockPredictor()
    sp.train('2330')
    prediction = sp.predict('2330')
"""

import sys
import logging
import pickle
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
from pymongo import MongoClient
from bson.decimal128 import Decimal128

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

logger = logging.getLogger(__name__)
MODEL_DIR = project_root / 'models'
MODEL_DIR.mkdir(exist_ok=True)


def _to_float(v) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, Decimal128):
        return float(v.to_decimal())
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class StockPredictor:
    """XGBoost 股價方向預測"""

    FEATURE_COLS = [
        'ma5_ratio', 'ma20_ratio', 'ma60_ratio',
        'rsi_14', 'macd_hist',
        'volume_ratio', 'volume_ma5_ratio',
        'return_1d', 'return_5d', 'return_20d',
        'volatility_10d', 'volatility_20d',
        'high_low_range', 'close_open_range',
        'bb_position',
    ]
    PREDICT_HORIZON = 5  # 預測未來 5 天

    def __init__(self,
                 mongo_uri: str = "mongodb://localhost:27017/",
                 db_name: str = "tw_stock_analysis"):
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.models = {}  # symbol → model

    # ──────────────────────────────────────────────
    #  特徵工程
    # ──────────────────────────────────────────────
    def _build_features(self, symbol: str, lookback_days: int = 500) -> Optional[pd.DataFrame]:
        """從股價建構特徵 DataFrame"""
        cutoff = datetime.now() - timedelta(days=int(lookback_days * 1.5))
        prices = list(self.db.stock_price.find(
            {'symbol': symbol, 'date': {'$gte': cutoff}},
            {'date': 1, 'open': 1, 'high': 1, 'low': 1, 'close': 1, 'volume': 1}
        ).sort('date', 1))

        if len(prices) < 120:
            return None

        df = pd.DataFrame([{
            'date': p['date'],
            'open': _to_float(p.get('open')),
            'high': _to_float(p.get('high')),
            'low': _to_float(p.get('low')),
            'close': _to_float(p.get('close')),
            'volume': _to_float(p.get('volume')),
        } for p in prices])

        df = df.dropna(subset=['close'])
        if len(df) < 120:
            return None

        c = df['close']
        v = df['volume'].fillna(0)
        h = df['high'].fillna(c)
        l = df['low'].fillna(c)
        o = df['open'].fillna(c)

        # 均線比率
        df['ma5_ratio'] = c / c.rolling(5).mean() - 1
        df['ma20_ratio'] = c / c.rolling(20).mean() - 1
        df['ma60_ratio'] = c / c.rolling(60).mean() - 1

        # RSI
        delta = c.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, 1e-10)
        df['rsi_14'] = 100 - 100 / (1 + rs)

        # MACD histogram
        ema12 = c.ewm(span=12).mean()
        ema26 = c.ewm(span=26).mean()
        macd_line = ema12 - ema26
        signal = macd_line.ewm(span=9).mean()
        df['macd_hist'] = (macd_line - signal) / c * 100

        # 成交量
        df['volume_ratio'] = v / v.rolling(20).mean().replace(0, 1)
        df['volume_ma5_ratio'] = v / v.rolling(5).mean().replace(0, 1)

        # 報酬率
        df['return_1d'] = c.pct_change(1) * 100
        df['return_5d'] = c.pct_change(5) * 100
        df['return_20d'] = c.pct_change(20) * 100

        # 波動度
        df['volatility_10d'] = c.pct_change().rolling(10).std() * 100
        df['volatility_20d'] = c.pct_change().rolling(20).std() * 100

        # 價格型態
        df['high_low_range'] = (h - l) / c * 100
        df['close_open_range'] = (c - o) / c * 100

        # Bollinger Band 位置
        bb_mid = c.rolling(20).mean()
        bb_std = c.rolling(20).std()
        df['bb_position'] = (c - bb_mid) / bb_std.replace(0, 1)

        # 目標：未來 N 天報酬率
        df['target_return'] = c.shift(-self.PREDICT_HORIZON) / c - 1
        df['target_class'] = (df['target_return'] > 0).astype(int)

        df = df.dropna()
        return df

    # ──────────────────────────────────────────────
    #  訓練
    # ──────────────────────────────────────────────
    def train(self, symbol: str, lookback_days: int = 500) -> Dict:
        """訓練個股預測模型"""
        from xgboost import XGBClassifier
        from sklearn.model_selection import TimeSeriesSplit
        from sklearn.metrics import accuracy_score, classification_report

        df = self._build_features(symbol, lookback_days)
        if df is None or len(df) < 100:
            return {'symbol': symbol, 'error': '資料不足'}

        X = df[self.FEATURE_COLS].values
        y = df['target_class'].values

        # 時間序列交叉驗證（避免前視偏差）
        tscv = TimeSeriesSplit(n_splits=5)
        scores = []

        for train_idx, test_idx in tscv.split(X):
            X_train, X_test = X[train_idx], X[test_idx]
            y_train, y_test = y[train_idx], y[test_idx]

            model = XGBClassifier(
                n_estimators=100,
                max_depth=4,
                learning_rate=0.1,
                subsample=0.8,
                colsample_bytree=0.8,
                eval_metric='logloss',
                verbosity=0,
            )
            model.fit(X_train, y_train)
            y_pred = model.predict(X_test)
            scores.append(accuracy_score(y_test, y_pred))

        # 用全部資料訓練最終模型
        final_model = XGBClassifier(
            n_estimators=100, max_depth=4, learning_rate=0.1,
            subsample=0.8, colsample_bytree=0.8,
            eval_metric='logloss', verbosity=0,
        )
        final_model.fit(X, y)

        self.models[symbol] = final_model

        # 儲存模型
        model_path = MODEL_DIR / f'{symbol}_xgb.pkl'
        with open(model_path, 'wb') as f:
            pickle.dump(final_model, f)

        # 特徵重要性
        importance = dict(zip(self.FEATURE_COLS,
                              final_model.feature_importances_))
        top_features = sorted(importance.items(), key=lambda x: -x[1])[:5]

        avg_acc = np.mean(scores)
        return {
            'symbol': symbol,
            'accuracy': round(avg_acc * 100, 2),
            'cv_scores': [round(s * 100, 2) for s in scores],
            'train_samples': len(X),
            'positive_ratio': round(y.mean() * 100, 1),
            'top_features': [{'feature': f, 'importance': round(float(v), 4)}
                             for f, v in top_features],
            'model_path': str(model_path),
        }

    # ──────────────────────────────────────────────
    #  預測
    # ──────────────────────────────────────────────
    def predict(self, symbol: str) -> Dict:
        """預測未來 N 天方向"""
        # 載入模型
        if symbol not in self.models:
            model_path = MODEL_DIR / f'{symbol}_xgb.pkl'
            if model_path.exists():
                with open(model_path, 'rb') as f:
                    self.models[symbol] = pickle.load(f)
            else:
                return {'symbol': symbol, 'error': '模型不存在，請先執行 train()'}

        model = self.models[symbol]

        # 取最新特徵
        df = self._build_features(symbol, lookback_days=120)
        if df is None or len(df) < 1:
            return {'symbol': symbol, 'error': '特徵資料不足'}

        # 用最後一筆（最新日期）做預測
        latest = df.iloc[-1]
        X_latest = latest[self.FEATURE_COLS].values.reshape(1, -1)

        prob = model.predict_proba(X_latest)[0]
        pred_class = int(model.predict(X_latest)[0])

        price = _to_float(latest.get('close'))
        direction = '上漲' if pred_class == 1 else '下跌'
        confidence = float(max(prob)) * 100

        return {
            'symbol': symbol,
            'date': str(latest['date'])[:10],
            'current_price': price,
            'prediction': {
                'horizon': f'{self.PREDICT_HORIZON}日',
                'direction': direction,
                'probability_up': round(float(prob[1]) * 100, 1),
                'probability_down': round(float(prob[0]) * 100, 1),
                'confidence': round(confidence, 1),
            },
            'features': {f: round(float(latest[f]), 4) for f in self.FEATURE_COLS[:5]},
        }

    # ──────────────────────────────────────────────
    #  批次預測
    # ──────────────────────────────────────────────
    def batch_predict(self, symbols: List[str]) -> List[Dict]:
        """批次預測多支股票"""
        results = []
        for sym in symbols:
            # 自動訓練
            if sym not in self.models and not (MODEL_DIR / f'{sym}_xgb.pkl').exists():
                self.train(sym)
            pred = self.predict(sym)
            if 'error' not in pred:
                results.append(pred)

        results.sort(key=lambda x: x['prediction']['probability_up'], reverse=True)
        return results


# ──────────────────────────────────────────────
#  CLI
# ──────────────────────────────────────────────
if __name__ == '__main__':
    from dotenv import load_dotenv
    load_dotenv(str(project_root / '.env'))

    sp = StockPredictor()
    test_symbols = ['2330', '2317', '0056']

    for sym in test_symbols:
        print(f"\n{'='*55}")
        print(f"  {sym} 股價預測模型")
        print(f"{'='*55}")

        # 訓練
        result = sp.train(sym)
        if result.get('error'):
            print(f"  錯誤: {result['error']}")
            continue

        print(f"  準確率: {result['accuracy']:.1f}%  "
              f"CV: {result['cv_scores']}")
        print(f"  樣本數: {result['train_samples']}  "
              f"上漲比例: {result['positive_ratio']}%")
        print(f"  重要特徵:")
        for f in result['top_features'][:3]:
            print(f"    {f['feature']}: {f['importance']:.4f}")

        # 預測
        pred = sp.predict(sym)
        if 'error' not in pred:
            p = pred['prediction']
            print(f"\n  📊 預測 ({p['horizon']}): {p['direction']}")
            print(f"  上漲機率: {p['probability_up']}%  "
                  f"下跌機率: {p['probability_down']}%  "
                  f"信心: {p['confidence']}%")
