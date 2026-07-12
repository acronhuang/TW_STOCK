"""
形態評分系統

整合所有形態的評分，計算綜合形態強度。

作者: Ming
創建日期: 2026-02-23
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class PatternScore:
    """形態評分結果"""
    pattern_name: str
    score: float  # 0-1
    weight: float
    detected: bool
    details: Dict


class PatternScorer:
    """形態評分器"""
    
    # 預設權重（可調整）
    DEFAULT_WEIGHTS = {
        'bottom_reversal': 0.30,
        'w_bottom': 0.30,
        'neckline_breakout': 0.25,
        'volume_surge': 0.10,
        'ma_alignment': 0.05
    }
    
    def __init__(self, weights: Optional[Dict[str, float]] = None):
        """
        初始化形態評分器
        
        Args:
            weights: 自訂權重字典，若未提供則使用預設權重
        """
        self.weights = weights if weights else self.DEFAULT_WEIGHTS.copy()
        self._validate_weights()
    
    def _validate_weights(self):
        """驗證權重總和為 1.0"""
        total = sum(self.weights.values())
        if not (0.99 <= total <= 1.01):  # 容許小誤差
            raise ValueError(f"權重總和必須為 1.0，當前為 {total:.3f}")
    
    def calculate_score(
        self,
        patterns: Dict[str, Dict]
    ) -> float:
        """
        計算綜合形態評分
        
        Args:
            patterns: 形態字典，格式:
                {
                    'bottom_reversal': {
                        'detected': True,
                        'score': 0.85,
                        'details': {...}
                    },
                    'w_bottom': {
                        'detected': False
                    },
                    ...
                }
        
        Returns:
            float: 綜合評分（0-1）
        """
        total_score = 0.0
        
        for pattern_name, weight in self.weights.items():
            if pattern_name not in patterns:
                continue
            
            pattern_data = patterns[pattern_name]
            
            if pattern_data.get('detected', False):
                pattern_score = pattern_data.get('score', 0.5)
                total_score += weight * pattern_score
        
        return min(total_score, 1.0)
    
    def get_pattern_scores(
        self,
        patterns: Dict[str, Dict]
    ) -> List[PatternScore]:
        """
        獲取所有形態的詳細評分
        
        Args:
            patterns: 形態字典
        
        Returns:
            List[PatternScore]: 形態評分列表
        """
        scores = []
        
        for pattern_name, weight in self.weights.items():
            if pattern_name not in patterns:
                continue
            
            pattern_data = patterns[pattern_name]
            detected = pattern_data.get('detected', False)
            score = pattern_data.get('score', 0.0) if detected else 0.0
            details = pattern_data.get('details', {})
            
            scores.append(PatternScore(
                pattern_name=pattern_name,
                score=score,
                weight=weight,
                detected=detected,
                details=details
            ))
        
        # 按權重排序
        scores.sort(key=lambda x: x.weight, reverse=True)
        
        return scores
    
    def get_top_patterns(
        self,
        patterns: Dict[str, Dict],
        top_n: int = 3
    ) -> List[PatternScore]:
        """
        獲取評分最高的 N 個形態
        
        Args:
            patterns: 形態字典
            top_n: 返回數量
        
        Returns:
            List[PatternScore]: 前 N 個形態
        """
        all_scores = self.get_pattern_scores(patterns)
        
        # 只選擇已偵測到的形態
        detected_scores = [s for s in all_scores if s.detected]
        
        # 按加權評分排序
        detected_scores.sort(key=lambda x: x.score * x.weight, reverse=True)
        
        return detected_scores[:top_n]


def calculate_pattern_strength(patterns: Dict[str, Dict]) -> float:
    """
    便捷函數：計算綜合形態強度
    
    這是一個快速計算形態強度的函數，使用預設權重。
    
    Args:
        patterns: 形態字典
    
    Returns:
        float: 綜合評分（0-1）
    
    Example:
        >>> patterns = {
        ...     'bottom_reversal': {'detected': True, 'score': 0.85},
        ...     'w_bottom': {'detected': False},
        ...     'neckline_breakout': {'detected': True, 'score': 0.72}
        ... }
        >>> score = calculate_pattern_strength(patterns)
        >>> print(f"綜合評分: {score:.3f}")
    """
    scorer = PatternScorer()
    return scorer.calculate_score(patterns)


def calculate_position_weight(
    base_weight: float,
    pattern_score: float,
    max_boost: float = 1.2,
    min_score_threshold: float = 0.5
) -> float:
    """
    根據形態評分計算倉位權重
    
    Args:
        base_weight: 基礎權重（如 0.10，即 10%）
        pattern_score: 形態評分（0-1）
        max_boost: 最大加成倍數（預設 1.2，即 20% 加成）
        min_score_threshold: 最低評分閾值（低於此分數不調整）
    
    Returns:
        float: 調整後的倉位權重
    
    Example:
        >>> # 基礎權重 10%，形態評分 0.85，最多加到 12%
        >>> weight = calculate_position_weight(0.10, 0.85, max_boost=1.2)
        >>> print(f"調整後權重: {weight:.2%}")
    """
    if pattern_score < min_score_threshold:
        return base_weight
    
    # 線性加成：評分越高，加成越多
    boost_factor = 1.0 + (max_boost - 1.0) * pattern_score
    
    adjusted_weight = base_weight * boost_factor
    
    return adjusted_weight


def generate_pattern_report(
    patterns: Dict[str, Dict],
    include_details: bool = True
) -> str:
    """
    生成形態分析報告
    
    Args:
        patterns: 形態字典
        include_details: 是否包含詳細資訊
    
    Returns:
        str: 格式化的報告文字
    """
    scorer = PatternScorer()
    overall_score = scorer.calculate_score(patterns)
    pattern_scores = scorer.get_pattern_scores(patterns)
    
    report = []
    report.append("=" * 60)
    report.append("形態分析報告")
    report.append("=" * 60)
    report.append(f"\n綜合評分: {overall_score:.3f}")
    report.append(f"評級: {_get_grade(overall_score)}")
    report.append("\n" + "-" * 60)
    report.append("各形態詳細評分:")
    report.append("-" * 60)
    
    for ps in pattern_scores:
        status = "✓" if ps.detected else "✗"
        weighted_score = ps.score * ps.weight if ps.detected else 0.0
        
        report.append(f"{status} {ps.pattern_name:20s} | "
                     f"評分: {ps.score:.3f} | "
                     f"權重: {ps.weight:.2f} | "
                     f"加權: {weighted_score:.3f}")
        
        if include_details and ps.detected and ps.details:
            for key, value in ps.details.items():
                report.append(f"    {key}: {value}")
    
    report.append("=" * 60)
    
    return "\n".join(report)


def _get_grade(score: float) -> str:
    """根據評分給予評級"""
    if score >= 0.8:
        return "A (優秀)"
    elif score >= 0.6:
        return "B (良好)"
    elif score >= 0.4:
        return "C (普通)"
    elif score >= 0.2:
        return "D (不佳)"
    else:
        return "F (極差)"


if __name__ == "__main__":
    # 測試範例
    print("形態評分系統測試")
    print("=" * 60)
    
    # 模擬形態偵測結果
    test_patterns = {
        'bottom_reversal': {
            'detected': True,
            'score': 0.85,
            'details': {
                'support_line': 580,
                'recovery_price': 595,
                'days_to_recover': 3,
                'volume_ratio': 2.1
            }
        },
        'w_bottom': {
            'detected': False
        },
        'neckline_breakout': {
            'detected': True,
            'score': 0.72,
            'details': {
                'neckline': 600,
                'breakout_price': 618,
                'volume_ratio': 2.5
            }
        },
        'volume_surge': {
            'detected': True,
            'score': 0.68,
            'details': {
                'volume_ratio': 3.2,
                'intraday_gain': 0.058
            }
        },
        'ma_alignment': {
            'detected': False
        }
    }
    
    # 計算評分
    scorer = PatternScorer()
    overall = scorer.calculate_score(test_patterns)
    
    print(f"\n綜合評分: {overall:.3f}")
    print(f"評級: {_get_grade(overall)}")
    
    # 獲取前 3 個形態
    top_patterns = scorer.get_top_patterns(test_patterns, top_n=3)
    print(f"\n前 3 個形態:")
    for ps in top_patterns:
        print(f"  {ps.pattern_name}: {ps.score:.3f} (權重 {ps.weight:.2f})")
    
    # 計算倉位權重
    base = 0.10
    adjusted = calculate_position_weight(base, overall, max_boost=1.2)
    print(f"\n倉位權重調整:")
    print(f"  基礎權重: {base:.2%}")
    print(f"  調整後: {adjusted:.2%} ({(adjusted/base - 1)*100:+.1f}%)")
    
    # 生成完整報告
    print("\n" + generate_pattern_report(test_patterns, include_details=True))
