"""
形態偵測引擎 (Pattern Detector)

整合所有形態偵測模組，提供統一的偵測介面。

作者: Ming
創建日期: 2026-02-23
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from .bottom_reversal import detect_bottom_reversal
from .w_bottom import detect_w_bottom
from .neckline_breakout import detect_neckline_breakout
from .volume_analysis import detect_volume_surge, detect_volume_price_divergence
from .pattern_scorer import PatternScorer, calculate_pattern_strength


class PatternDetector:
    """形態偵測引擎"""
    
    def __init__(
        self,
        enable_patterns: Optional[List[str]] = None,
        custom_weights: Optional[Dict[str, float]] = None
    ):
        """
        初始化形態偵測引擎
        
        Args:
            enable_patterns: 啟用的形態列表，None 表示全部啟用
            custom_weights: 自訂形態權重
        """
        self.available_patterns = [
            'bottom_reversal',
            'w_bottom',
            'neckline_breakout',
            'volume_surge',
            'volume_price_divergence'
        ]
        
        self.enable_patterns = enable_patterns if enable_patterns else self.available_patterns
        
        # 驗證啟用的形態
        invalid = set(self.enable_patterns) - set(self.available_patterns)
        if invalid:
            raise ValueError(f"無效的形態名稱: {invalid}")
        
        # 初始化評分器
        self.scorer = PatternScorer(weights=custom_weights)
    
    def detect_all(
        self,
        df: pd.DataFrame,
        stock_id: Optional[str] = None
    ) -> Dict[str, Dict]:
        """
        偵測所有啟用的形態
        
        Args:
            df: 股票數據 DataFrame
            stock_id: 股票代碼（可選，用於日誌）
        
        Returns:
            Dict: 形態偵測結果
                {
                    'bottom_reversal': {
                        'detected': True/False,
                        'signal': pd.Series,
                        'details': pd.DataFrame,
                        'score': float,
                        'latest': {...}  # 最近一次形態的資訊
                    },
                    ...
                }
        """
        results = {}
        
        # 破底翻
        if 'bottom_reversal' in self.enable_patterns:
            signal, details = detect_bottom_reversal(df)
            results['bottom_reversal'] = self._format_result(
                'bottom_reversal', signal, details
            )
        
        # 雙底
        if 'w_bottom' in self.enable_patterns:
            signal, details = detect_w_bottom(df)
            results['w_bottom'] = self._format_result(
                'w_bottom', signal, details
            )
        
        # 頸線突破
        if 'neckline_breakout' in self.enable_patterns:
            signal, details = detect_neckline_breakout(df)
            results['neckline_breakout'] = self._format_result(
                'neckline_breakout', signal, details
            )
        
        # 量價噴出
        if 'volume_surge' in self.enable_patterns:
            signal, details = detect_volume_surge(df)
            results['volume_surge'] = self._format_result(
                'volume_surge', signal, details
            )
        
        # 量價背離
        if 'volume_price_divergence' in self.enable_patterns:
            signal, details = detect_volume_price_divergence(df)
            results['volume_price_divergence'] = self._format_result(
                'volume_price_divergence', signal, details
            )
        
        return results
    
    def _format_result(
        self,
        pattern_name: str,
        signal: pd.Series,
        details: pd.DataFrame
    ) -> Dict:
        """格式化形態偵測結果"""
        detected = signal.sum() > 0
        
        result = {
            'detected': detected,
            'signal': signal,
            'details': details,
            'count': signal.sum()
        }
        
        if detected and not details.empty:
            # 最近一次形態
            latest = details.iloc[-1].to_dict()
            result['latest'] = latest
            result['score'] = latest.get('pattern_score', 0.5)
        else:
            result['latest'] = None
            result['score'] = 0.0
        
        return result
    
    def get_latest_patterns(
        self,
        df: pd.DataFrame,
        lookback_days: int = 5,
        min_score: float = 0.5
    ) -> Dict[str, Dict]:
        """
        獲取最近 N 天的形態
        
        Args:
            df: 股票數據
            lookback_days: 回溯天數
            min_score: 最低評分閾值
        
        Returns:
            Dict: 最近的形態
        """
        all_results = self.detect_all(df)
        recent_patterns = {}
        
        cutoff_date = df.index[-lookback_days] if len(df) >= lookback_days else df.index[0]
        
        for pattern_name, result in all_results.items():
            if not result['detected']:
                continue
            
            details = result['details']
            recent = details[details.index >= cutoff_date]
            
            if not recent.empty:
                # 過濾低分形態
                high_score = recent[recent['pattern_score'] >= min_score]
                
                if not high_score.empty:
                    recent_patterns[pattern_name] = {
                        'detected': True,
                        'score': high_score['pattern_score'].mean(),
                        'count': len(high_score),
                        'details': high_score.iloc[-1].to_dict()
                    }
        
        return recent_patterns
    
    def calculate_overall_score(
        self,
        df: pd.DataFrame,
        lookback_days: int = 5
    ) -> float:
        """
        計算綜合形態評分
        
        Args:
            df: 股票數據
            lookback_days: 回溯天數
        
        Returns:
            float: 綜合評分（0-1）
        """
        recent = self.get_latest_patterns(df, lookback_days=lookback_days)
        
        if not recent:
            return 0.0
        
        # 轉換為評分器格式
        patterns_for_scoring = {}
        for pattern_name, data in recent.items():
            patterns_for_scoring[pattern_name] = {
                'detected': data['detected'],
                'score': data['score']
            }
        
        return self.scorer.calculate_score(patterns_for_scoring)
    
    def filter_stocks(
        self,
        stocks_data: Dict[str, pd.DataFrame],
        min_patterns: int = 1,
        min_score: float = 0.5,
        lookback_days: int = 5
    ) -> List[Tuple[str, float, Dict]]:
        """
        用形態學過濾股票
        
        Args:
            stocks_data: {股票代碼: DataFrame}
            min_patterns: 最少需要的形態數量
            min_score: 最低綜合評分
            lookback_days: 回溯天數
        
        Returns:
            List[Tuple[str, float, Dict]]: [(股票代碼, 綜合評分, 形態詳情), ...]
                按評分降序排列
        """
        results = []
        
        for stock_id, df in stocks_data.items():
            try:
                recent = self.get_latest_patterns(df, lookback_days=lookback_days)
                
                if len(recent) < min_patterns:
                    continue
                
                overall_score = self.calculate_overall_score(df, lookback_days=lookback_days)
                
                if overall_score < min_score:
                    continue
                
                results.append((stock_id, overall_score, recent))
            
            except Exception as e:
                print(f"警告: 處理 {stock_id} 時發生錯誤: {e}")
                continue
        
        # 按評分降序排列
        results.sort(key=lambda x: x[1], reverse=True)
        
        return results
    
    def generate_summary(
        self,
        df: pd.DataFrame,
        stock_id: str = "未知"
    ) -> str:
        """
        生成形態偵測摘要報告
        
        Args:
            df: 股票數據
            stock_id: 股票代碼
        
        Returns:
            str: 格式化的報告
        """
        results = self.detect_all(df)
        overall_score = self.calculate_overall_score(df)
        
        report = []
        report.append("=" * 70)
        report.append(f"形態偵測報告 - {stock_id}")
        report.append("=" * 70)
        report.append(f"數據期間: {df.index[0]} ~ {df.index[-1]}")
        report.append(f"綜合評分: {overall_score:.3f}")
        report.append("")
        report.append("-" * 70)
        report.append("各形態偵測結果:")
        report.append("-" * 70)
        
        for pattern_name, result in results.items():
            status = "✓" if result['detected'] else "✗"
            count = result['count']
            score = result['score']
            
            report.append(f"{status} {pattern_name:25s} | "
                         f"出現次數: {count:3d} | "
                         f"評分: {score:.3f}")
            
            if result['latest']:
                latest = result['latest']
                report.append(f"    最近一次: {latest}")
        
        report.append("=" * 70)
        
        return "\n".join(report)
    
    def batch_detect(self, stock_ids: List[str], date: str):
        """
        批量檢測多支股票的形態
        
        Args:
            stock_ids: 股票代碼列表
            date: 檢測日期
        
        Returns:
            檢測結果列表，每個結果包含 stock_id, composite_score, patterns
        """
        from dataclasses import dataclass
        from typing import List
        
        @dataclass
        class PatternResult:
            stock_id: str
            composite_score: float
            patterns: List[str]
        
        results = []
        
        # TODO: 實作批量形態檢測
        # 目前返回空結果，避免阻塞回測流程
        for stock_id in stock_ids:
            results.append(PatternResult(
                stock_id=stock_id,
                composite_score=0.0,
                patterns=[]
            ))
        
        return results


if __name__ == "__main__":
    # 測試範例
    print("形態偵測引擎測試")
    print("=" * 60)
    
    # 創建測試數據
    dates = pd.date_range('2024-01-01', '2024-06-30', freq='D')
    np.random.seed(42)
    
    # 模擬複雜走勢（包含多種形態）
    prices = np.concatenate([
        np.linspace(100, 85, 20),   # 下跌
        np.array([83, 81, 86, 88]), # 破底翻
        np.linspace(88, 95, 15),    # 反彈
        np.linspace(95, 86, 15),    # 回落（W 底）
        np.array([86, 88, 92, 97, 103, 108]),  # 突破（頸線）
        np.linspace(108, 120, 20)   # 持續上漲
    ])
    
    volumes = np.concatenate([
        np.random.uniform(1000, 2000, 20),
        np.array([2000, 2500, 5000, 5500]),  # 破底翻放量
        np.random.uniform(1500, 2500, 15),
        np.random.uniform(1200, 2200, 15),
        np.array([3000, 4000, 6000, 7000, 6500, 6000]),  # 突破爆量
        np.random.uniform(2000, 3000, 20)
    ])
    
    df = pd.DataFrame({
        'open': prices * 0.998,
        'high': prices * 1.015,
        'low': prices * 0.985,
        'close': prices,
        'volume': volumes
    }, index=dates[:len(prices)])
    
    # 初始化偵測器
    detector = PatternDetector()
    
    # 執行全部偵測
    results = detector.detect_all(df, stock_id="2330")
    
    # 生成報告
    print(detector.generate_summary(df, stock_id="2330"))
    
    # 獲取最近 5 天的形態
    recent = detector.get_latest_patterns(df, lookback_days=5)
    print(f"\n最近 5 天的形態數: {len(recent)}")
    for pattern, data in recent.items():
        print(f"  {pattern}: 評分 {data['score']:.3f}")
