"""
v2.1 整合策略

整合架構:
1. Stage 1: 17 因子初選（30 支）
2. Stage 2: 形態學過濾（15-20 支）
3. Stage 3: 籌碼面確認（10 支）
4. Stage 4: 綜合評分與倉位分配

出場邏輯:
- 固定停損 -8%
- 形態破壞訊號
- 量價背離
- 主力出貨訊號

作者: Ming
創建日期: 2026-02-23
"""

from typing import Dict, List, Tuple, Optional
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.strategy.multi_factor_strategy import MultiFactorStrategy
from morphology.pattern_detector import PatternDetector
from chip_analysis import ChipAnalyzer


@dataclass
class StockRanking:
    """股票評分排名"""
    stock_id: str
    date: str
    
    # Stage 1: 因子評分
    factor_score: float
    factor_rank: int
    
    # Stage 2: 形態評分
    pattern_score: float
    patterns_detected: List[str]
    
    # Stage 3: 籌碼評分
    chip_score: float
    chip_signal: str
    
    # Stage 4: 綜合評分
    integrated_score: float
    
    # Optional fields with defaults
    pattern_rank: Optional[int] = None
    chip_rank: Optional[int] = None
    final_rank: Optional[int] = None
    position_weight: float = 0.0
    
    def __repr__(self):
        return (f"StockRanking({self.stock_id}, "
                f"integrated={self.integrated_score:.3f}, "
                f"rank={self.final_rank}, weight={self.position_weight:.1%})")


@dataclass
class PositionExitSignal:
    """出場訊號"""
    stock_id: str
    date: str
    entry_price: float
    current_price: float
    return_pct: float
    
    # 出場原因
    stop_loss_triggered: bool = False       # 固定停損
    pattern_breakdown: bool = False         # 形態破壞
    volume_divergence: bool = False         # 量價背離
    chip_distribution: bool = False         # 主力出貨
    
    should_exit: bool = False
    exit_reason: str = ""
    
    def __repr__(self):
        return (f"ExitSignal({self.stock_id}, return={self.return_pct:+.2%}, "
                f"exit={self.should_exit}, reason={self.exit_reason})")


class IntegratedStrategyV21:
    """v2.1 整合策略"""
    
    def __init__(
        self,
        db_connection,
        factor_config: Optional[Dict] = None,
        pattern_config: Optional[Dict] = None,
        chip_config: Optional[Dict] = None,
        enable_pattern_filter: bool = False,
        enable_chip_filter: bool = False
    ):
        """
        初始化
        
        Args:
            db_connection: MongoDB 連接
            factor_config: 因子策略配置
            pattern_config: 形態學配置
            chip_config: 籌碼分析配置
            enable_pattern_filter: 是否啟用形態過濾（默認 False，因為需要價格數據）
            enable_chip_filter: 是否啟用籌碼過濾（默認 False，因為需要籌碼數據）
        """
        self.db = db_connection
        self.enable_pattern_filter = enable_pattern_filter
        self.enable_chip_filter = enable_chip_filter
        
        # Stage 1: 因子策略（v2.0）
        self.factor_strategy = MultiFactorStrategy(db_connection)
        if factor_config:
            self.factor_strategy.update_config(factor_config)
        
        # Stage 2: 形態偵測器
        self.pattern_detector = PatternDetector()
        self.pattern_config = pattern_config or {
            'min_patterns': 0,  # 默認 0，不強制要求形態
            'min_pattern_score': 0.5
        }
        
        # Stage 3: 籌碼分析器
        self.chip_analyzer = ChipAnalyzer(db_connection)
        self.chip_config = chip_config or {
            'min_chip_score': 0.3  # 降低閾值
        }
        
        # Stage 4: 整合配置
        self.integration_config = {
            'stage1_top_n': 30,           # 因子初選數量
            'stage2_min_pass': 15,        # 形態過濾最少通過數
            'stage3_final_n': 10,         # 最終選股數量
            'weights': {
                'factor': 0.4,            # 因子權重
                'pattern': 0.35,          # 形態權重
                'chip': 0.25              # 籌碼權重
            }
        }
        
        # 出場配置
        self.exit_config = {
            'fixed_stop_loss': -0.08,     # 固定停損 -8%
            'atr_multiplier': 2.5,        # ATR 停損倍數
            'pattern_breakdown_exit': True,
            'volume_divergence_exit': True,
            'chip_distribution_exit': True
        }
    
    def stage_1_factor_selection(
        self,
        rebalance_date: str,
        top_n: int = 30,
        require_price_data: bool = True
    ) -> List[StockRanking]:
        """
        Stage 1: 17 因子初選
        
        Args:
            rebalance_date: 再平衡日期
            top_n: 選擇數量
            require_price_data: 是否要求股票有價格數據（回測時必須為 True）
        
        Returns:
            StockRanking 列表
        """
        print(f"\n========== Stage 1: 因子初選 ==========")
        
        # 獲取有價格數據的股票列表（用於過濾）
        valid_stocks = set()
        if require_price_data:
            # 獲取所有有價格數據的股票（不限日期）
            valid_stocks = set(self.db['stock_price'].distinct('stock_id'))
            print(f"可用股票池: {len(valid_stocks)} 支 (有價格數據)")
        
        # 使用 v2.0 因子策略選股（多選一些，以便過濾後仍有足夠數量）
        factor_selections = self.factor_strategy.select_stocks(
            rebalance_date, 
            top_n=top_n * 5 if require_price_data else top_n
        )
        
        rankings = []
        skipped = 0
        for i, selection in enumerate(factor_selections):
            stock_id = selection['stock_id']
            
            # 檢查是否在有效股票池中
            if require_price_data and stock_id not in valid_stocks:
                skipped += 1
                continue  # 跳過沒有價格數據的股票
            
            ranking = StockRanking(
                stock_id=stock_id,
                date=rebalance_date,
                factor_score=selection['composite_score'],
                factor_rank=len(rankings) + 1,  # 重新排名
                pattern_score=0.0,
                patterns_detected=[],
                chip_score=0.0,
                chip_signal='unknown',
                integrated_score=0.0
            )
            rankings.append(ranking)
            
            # 達到目標數量後停止
            if len(rankings) >= top_n:
                break
        
        if require_price_data:
            print(f"✓ 因子初選完成: {len(rankings)} 支 (已過濾 {skipped} 支無價格數據)")
        else:
            print(f"✓ 因子初選完成: {len(rankings)} 支")
        return rankings
    
    def stage_2_pattern_filtering(
        self,
        stage1_rankings: List[StockRanking]
    ) -> List[StockRanking]:
        """
        Stage 2: 形態學過濾
        
        Args:
            stage1_rankings: Stage 1 排名結果
        
        Returns:
            通過形態過濾的 StockRanking 列表
        """
        print(f"\n========== Stage 2: 形態過濾 ==========")
        
        # 檢查是否有候選股票
        if not stage1_rankings:
            print(f"⚠️  無候選股票，跳過形態過濾")
            return []
        
        stock_ids = [r.stock_id for r in stage1_rankings]
        date = stage1_rankings[0].date
        
        # 批量形態偵測
        pattern_results = self.pattern_detector.batch_detect(stock_ids, date)
        
        # 更新排名資訊
        for ranking in stage1_rankings:
            pattern_result = next((p for p in pattern_results if p.stock_id == ranking.stock_id), None)
            
            if pattern_result:
                ranking.pattern_score = pattern_result.composite_score
                ranking.patterns_detected = pattern_result.patterns
        
        # 過濾：至少 1 個形態且評分 >= 0.5
        filtered = [
            r for r in stage1_rankings 
            if (len(r.patterns_detected) >= self.pattern_config['min_patterns'] and
                r.pattern_score >= self.pattern_config['min_pattern_score'])
        ]
        
        # 按形態評分排序
        filtered.sort(key=lambda x: x.pattern_score, reverse=True)
        for i, r in enumerate(filtered):
            r.pattern_rank = i + 1
        
        print(f"✓ 形態過濾完成: {len(filtered)}/{len(stage1_rankings)} 支通過")
        return filtered
    
    def stage_3_chip_confirmation(
        self,
        stage2_rankings: List[StockRanking]
    ) -> List[StockRanking]:
        """
        Stage 3: 籌碼面確認
        
        Args:
            stage2_rankings: Stage 2 排名結果
        
        Returns:
            通過籌碼確認的 StockRanking 列表
        """
        print(f"\n========== Stage 3: 籌碼確認 ==========")
        
        # 檢查是否有候選股票
        if not stage2_rankings:
            print(f"⚠️  無候選股票，跳過籌碼確認")
            return []
        
        stock_ids = [r.stock_id for r in stage2_rankings]
        date = stage2_rankings[0].date
        
        # 批量籌碼分析
        chip_signals = self.chip_analyzer.batch_analyze(stock_ids, date)
        
        # 更新排名資訊
        for ranking in stage2_rankings:
            chip_signal = next((c for c in chip_signals if c.stock_id == ranking.stock_id), None)
            
            if chip_signal:
                ranking.chip_score = chip_signal.chip_score
                ranking.chip_signal = chip_signal.main_force_signal
        
        # 過濾：籌碼評分 >= 0.5
        filtered = [
            r for r in stage2_rankings 
            if r.chip_score >= self.chip_config['min_chip_score']
        ]
        
        # 按籌碼評分排序
        filtered.sort(key=lambda x: x.chip_score, reverse=True)
        for i, r in enumerate(filtered):
            r.chip_rank = i + 1
        
        print(f"✓ 籌碼確認完成: {len(filtered)}/{len(stage2_rankings)} 支通過")
        return filtered
    
    def stage_4_integrated_ranking(
        self,
        stage3_rankings: List[StockRanking],
        top_n: int = 10
    ) -> List[StockRanking]:
        """
        Stage 4: 綜合評分與排名
        
        Args:
            stage3_rankings: Stage 3 排名結果
            top_n: 最終選擇數量
        
        Returns:
            最終排名的 StockRanking 列表（前 N 名）
        """
        print(f"\n========== Stage 4: 綜合排名 ==========")        
        # 檢查是否有候選股票
        if not stage3_rankings:
            print(f"⚠️  無候選股票，跳過綜合評分")
            return []        
        weights = self.integration_config['weights']
        
        # 根據啟用的過濾器調整權重
        active_weights = {}
        total_weight = 0.0
        
        # 因子評分始終啟用
        active_weights['factor'] = weights['factor']
        total_weight += weights['factor']
        
        # 形態評分（如果啟用）
        if self.enable_pattern_filter:
            active_weights['pattern'] = weights['pattern']
            total_weight += weights['pattern']
        
        # 籌碼評分（如果啟用）
        if self.enable_chip_filter:
            active_weights['chip'] = weights['chip']
            total_weight += weights['chip']
        
        # 標準化權重
        for key in active_weights:
            active_weights[key] /= total_weight
        
        # 計算綜合評分
        for ranking in stage3_rankings:
            score = ranking.factor_score * active_weights['factor']
            
            if self.enable_pattern_filter:
                score += ranking.pattern_score * active_weights.get('pattern', 0)
            
            if self.enable_chip_filter:
                score += ranking.chip_score * active_weights.get('chip', 0)
            
            ranking.integrated_score = score
        
        print(f"使用權重: 因子={active_weights['factor']:.2f}", end="")
        if self.enable_pattern_filter:
            print(f", 形態={active_weights.get('pattern', 0):.2f}", end="")
        if self.enable_chip_filter:
            print(f", 籌碼={active_weights.get('chip', 0):.2f}", end="")
        print()
        
        # 按綜合評分排序
        stage3_rankings.sort(key=lambda x: x.integrated_score, reverse=True)
        
        # 更新最終排名
        for i, r in enumerate(stage3_rankings):
            r.final_rank = i + 1
        
        # 取前 N 名
        final_selections = stage3_rankings[:top_n]
        
        print(f"✓ 綜合排名完成: 最終選出 {len(final_selections)} 支")
        
        return final_selections
    
    def allocate_positions(
        self,
        final_rankings: List[StockRanking]
    ) -> List[StockRanking]:
        """
        倉位分配
        
        使用綜合評分加權分配，評分越高倉位越大
        
        Args:
            final_rankings: 最終排名結果
        
        Returns:
            分配倉位後的 StockRanking 列表
        """
        if not final_rankings:
            return []
        
        # 計算權重（根據評分）
        total_score = sum(r.integrated_score for r in final_rankings)
        
        if total_score == 0:
            # 如果所有評分都是 0，使用等權重
            for ranking in final_rankings:
                ranking.position_weight = 1.0 / len(final_rankings)
            return final_rankings
        
        for ranking in final_rankings:
            # 基礎權重
            base_weight = ranking.integrated_score / total_score
            
            # 強化邏輯（只在相關過濾器啟用時使用）
            boost = 1.0
            
            if self.enable_chip_filter and self.enable_pattern_filter:
                # 主力累積 + 形態強 → 加權 1.2
                if ranking.chip_signal == 'accumulating' and ranking.pattern_score >= 0.7:
                    boost = 1.2
            
            if self.enable_pattern_filter:
                # 多個形態確認 → 加權 1.1
                if len(ranking.patterns_detected) >= 2:
                    boost *= 1.1
            
            # 計算最終權重
            ranking.position_weight = base_weight * boost
        
        # 標準化權重（總和 = 1.0）
        total_weight = sum(r.position_weight for r in final_rankings)
        for r in final_rankings:
            r.position_weight = r.position_weight / total_weight
        
        # 限制單股最大權重 12%
        for r in final_rankings:
            if r.position_weight > 0.12:
                r.position_weight = 0.12
        
        # 再次標準化
        total_weight = sum(r.position_weight for r in final_rankings)
        for r in final_rankings:
            r.position_weight = r.position_weight / total_weight
        
        return final_rankings
    
    def select_stocks(self, rebalance_date: str) -> List[StockRanking]:
        """
        完整選股流程（4 個階段）
        
        Args:
            rebalance_date: 再平衡日期
        
        Returns:
            最終選股結果（含倉位配置）
        """
        print(f"\n{'='*60}")
        print(f"v2.1 整合策略選股")
        print(f"日期: {rebalance_date}")
        print(f"{'='*60}")
        
        # Stage 1: 因子初選（30 支）
        stage1 = self.stage_1_factor_selection(
            rebalance_date, 
            top_n=self.integration_config['stage1_top_n']
        )
        
        # Stage 2: 形態過濾（15-20 支）
        if self.enable_pattern_filter:
            stage2 = self.stage_2_pattern_filtering(stage1)
        else:
            print(f"\n========== Stage 2: 形態過濾 ==========")
            print(f"⚠️  形態過濾已停用（enable_pattern_filter=False），跳過此階段")
            stage2 = stage1  # 跳過過濾，直接使用 Stage 1 結果
        
        # Stage 3: 籌碼確認（10-15 支）
        if self.enable_chip_filter:
            stage3 = self.stage_3_chip_confirmation(stage2)
        else:
            print(f"\n========== Stage 3: 籌碼確認 ==========")
            print(f"⚠️  籌碼確認已停用（enable_chip_filter=False），跳過此階段")
            stage3 = stage2  # 跳過過濾，直接使用 Stage 2 結果
        
        # Stage 4: 綜合排名（10 支）
        stage4 = self.stage_4_integrated_ranking(
            stage3,
            top_n=self.integration_config['stage3_final_n']
        )
        
        # 倉位分配
        final_selections = self.allocate_positions(stage4)
        
        # 顯示結果
        print(f"\n{'='*60}")
        print(f"最終選股結果（{len(final_selections)} 支）:")
        print(f"{'='*60}")
        for r in final_selections:
            print(f"  {r.stock_id}: 綜合={r.integrated_score:.3f} "
                  f"(因子={r.factor_score:.2f}, 形態={r.pattern_score:.2f}, 籌碼={r.chip_score:.2f}), "
                  f"倉位={r.position_weight:.1%}, 形態={r.patterns_detected}")
        
        return final_selections
    
    def check_exit_signals(
        self,
        holdings: List[Dict],
        current_date: str
    ) -> List[PositionExitSignal]:
        """
        檢查出場訊號
        
        Args:
            holdings: 當前持倉列表
                [{'stock_id': '2330', 'entry_price': 580, 'entry_date': '2024-01-01'}, ...]
            current_date: 當前日期
        
        Returns:
            PositionExitSignal 列表
        """
        exit_signals = []
        
        for holding in holdings:
            stock_id = holding['stock_id']
            entry_price = holding['entry_price']
            
            # 獲取當前價格
            price_data = self.db['stock_price'].find_one({
                'stock_id': stock_id,
                'date': current_date
            })
            
            if not price_data:
                continue
            
            current_price = price_data['close']
            return_pct = (current_price - entry_price) / entry_price
            
            signal = PositionExitSignal(
                stock_id=stock_id,
                date=current_date,
                entry_price=entry_price,
                current_price=current_price,
                return_pct=return_pct
            )
            
            # 1. 固定停損 -8%
            if return_pct <= self.exit_config['fixed_stop_loss']:
                signal.stop_loss_triggered = True
                signal.should_exit = True
                signal.exit_reason = "固定停損"
            
            # 2. 形態破壞（只在啟用形態檢測時執行）
            if self.enable_pattern_filter and self.exit_config['pattern_breakdown_exit']:
                # TODO: 實作形態破壞檢測
                # pattern_result = self.pattern_detector.detect(stock_id, current_date)
                # if pattern_result and pattern_result.breakdown_detected:
                #     signal.pattern_breakdown = True
                #     signal.should_exit = True
                #     signal.exit_reason = "形態破壞"
                pass
            
            # 3. 量價背離
            if self.exit_config['volume_divergence_exit']:
                try:
                    # 簡化判斷：價漲量縮
                    recent_data = list(self.db['stock_price'].find({
                        'stock_id': stock_id,
                        'date': {'$lte': current_date}
                    }).sort('date', -1).limit(5))
                    
                    if len(recent_data) >= 5:
                        df = pd.DataFrame(recent_data)
                        
                        # 檢查必要欄位是否存在
                        if 'close' in df.columns and 'volume' in df.columns:
                            price_trend = df['close'].iloc[0] > df['close'].iloc[4]
                            volume_trend = df['volume'].iloc[0] < df['volume'].iloc[4]
                            
                            if price_trend and volume_trend:
                                signal.volume_divergence = True
                                signal.should_exit = True
                                signal.exit_reason = "量價背離"
                except Exception as e:
                    # 量價分析失敗，跳過
                    pass
            
            # 4. 主力出貨（只在啟用籌碼檢測時執行）
            if self.enable_chip_filter and self.exit_config['chip_distribution_exit']:
                try:
                    # TODO: 實作主力出貨檢測
                    # chip_signal = self.chip_analyzer.analyze(stock_id, current_date)
                    # if chip_signal.main_force_signal == 'distributing':
                    #     signal.chip_distribution = True
                    #     signal.should_exit = True
                    #     signal.exit_reason = "主力出貨"
                    pass
                except Exception as e:
                    pass
            
            exit_signals.append(signal)
        
        return exit_signals


if __name__ == "__main__":
    """測試範例"""
    from pymongo import MongoClient
    
    # 連接資料庫
    client = MongoClient('mongodb://localhost:27017/')
    db = client['tw_stock_analysis']
    
    # 初始化策略
    strategy = IntegratedStrategyV21(db)
    
    # 選股測試
    rebalance_date = '2024-12-31'
    selections = strategy.select_stocks(rebalance_date)
    
    print(f"\n最終選股結果:")
    for s in selections:
        print(f"  {s}")
