#!/usr/bin/env python3
"""
多因子策略參數優化

使用遺傳算法優化策略參數，目標是提升年化報酬至 20%+
"""

import sys
from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd
from pymongo import MongoClient
import json
from typing import Dict, List, Tuple
import multiprocessing as mp
from functools import partial

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from examples.multifactor_strategy import MultiFactorStrategy
from examples.backtest_multifactor import MultiFactorBacktest


class ParameterOptimizer:
    """參數優化器"""
    
    def __init__(self,
                 start_date: datetime,
                 end_date: datetime,
                 population_size: int = 50,
                 generations: int = 30,
                 mutation_rate: float = 0.15,
                 crossover_rate: float = 0.7,
                 workers: int = 4):
        """
        初始化優化器
        
        Args:
            start_date: 回測開始日期
            end_date: 回測結束日期
            population_size: 族群大小
            generations: 代數
            mutation_rate: 突變率
            crossover_rate: 交叉率
            workers: 並行進程數
        """
        self.start_date = start_date
        self.end_date = end_date
        self.population_size = population_size
        self.generations = generations
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate
        self.workers = workers
        
        # 參數範圍
        self.param_ranges = {
            # 因子大類權重 (總和必須為 1.0)
            'momentum_weight': (0.30, 0.70),
            'value_weight': (0.10, 0.40),
            'quality_weight': (0.10, 0.30),
            
            # 動能子因子權重 (相對權重，會正規化)
            'return_3m_weight': (0.1, 0.5),
            'return_6m_weight': (0.1, 0.4),
            'return_12m_weight': (0.1, 0.4),
            'volatility_weight': (0.05, 0.3),
            'rsi_weight': (0.0, 0.2),
            
            # 價值子因子權重
            'pe_weight': (0.2, 0.5),
            'pb_weight': (0.2, 0.5),
            'earnings_yield_weight': (0.1, 0.4),
            
            # 質量子因子權重
            'roe_weight': (0.2, 0.5),
            'roa_weight': (0.2, 0.5),
            'profit_margin_weight': (0.1, 0.3),
            'debt_ratio_weight': (0.1, 0.3),
            
            # 交易參數
            'top_n': (10, 50),  # 持股數量（整數）
            'min_factors': (2, 6),  # 最少因子數（整數）
        }
        
        # 調倉頻率候選
        self.rebalance_freq_options = ['ME', 'QE', '2ME']  # 月末、季末、雙月末
        
        # 最佳個體
        self.best_individual = None
        self.best_fitness = -np.inf
        self.best_metrics = None
        
        # 歷史記錄
        self.history = []
        
    def create_individual(self) -> np.ndarray:
        """創建隨機個體"""
        individual = []
        
        # 連續參數
        for param, (low, high) in self.param_ranges.items():
            if param in ['top_n', 'min_factors']:
                # 整數參數
                individual.append(float(np.random.randint(low, high + 1)))
            else:
                # 連續參數
                individual.append(np.random.uniform(low, high))
        
        # 調倉頻率（0, 1, 2 對應三個選項）
        individual.append(float(np.random.randint(0, len(self.rebalance_freq_options))))
        
        return np.array(individual)
    
    def decode_individual(self, individual: np.ndarray) -> Dict:
        """
        解碼個體為參數字典
        
        Args:
            individual: 個體基因
        
        Returns:
            參數字典
        """
        params = {}
        param_names = list(self.param_ranges.keys())
        
        for i, param_name in enumerate(param_names):
            if param_name in ['top_n', 'min_factors']:
                params[param_name] = int(individual[i])
            else:
                params[param_name] = individual[i]
        
        # 調倉頻率
        freq_idx = int(individual[-1])
        params['rebalance_freq'] = self.rebalance_freq_options[freq_idx]
        
        # 正規化因子大類權重
        momentum_w = params['momentum_weight']
        value_w = params['value_weight']
        quality_w = params['quality_weight']
        total_w = momentum_w + value_w + quality_w
        
        params['momentum_weight'] = momentum_w / total_w
        params['value_weight'] = value_w / total_w
        params['quality_weight'] = quality_w / total_w
        
        # 正規化動能子因子權重
        momentum_sub_weights = [
            params['return_3m_weight'],
            params['return_6m_weight'],
            params['return_12m_weight'],
            params['volatility_weight'],
            params['rsi_weight']
        ]
        momentum_sub_total = sum(momentum_sub_weights)
        params['return_3m_weight'] /= momentum_sub_total
        params['return_6m_weight'] /= momentum_sub_total
        params['return_12m_weight'] /= momentum_sub_total
        params['volatility_weight'] /= momentum_sub_total
        params['rsi_weight'] /= momentum_sub_total
        
        # 正規化價值子因子權重
        value_sub_weights = [
            params['pe_weight'],
            params['pb_weight'],
            params['earnings_yield_weight']
        ]
        value_sub_total = sum(value_sub_weights)
        params['pe_weight'] /= value_sub_total
        params['pb_weight'] /= value_sub_total
        params['earnings_yield_weight'] /= value_sub_total
        
        # 正規化質量子因子權重
        quality_sub_weights = [
            params['roe_weight'],
            params['roa_weight'],
            params['profit_margin_weight'],
            params['debt_ratio_weight']
        ]
        quality_sub_total = sum(quality_sub_weights)
        params['roe_weight'] /= quality_sub_total
        params['roa_weight'] /= quality_sub_total
        params['profit_margin_weight'] /= quality_sub_total
        params['debt_ratio_weight'] /= quality_sub_total
        
        return params
    
    def evaluate_individual(self, individual: np.ndarray) -> Tuple[float, Dict]:
        """
        評估個體適應度
        
        Args:
            individual: 個體基因
        
        Returns:
            (適應度, 指標字典)
        """
        try:
            # 解碼參數
            params = self.decode_individual(individual)
            
            # 創建策略實例（修改配置）
            strategy = MultiFactorStrategy()
            
            # 更新因子配置
            strategy.factor_config = {
                'momentum': {
                    'weight': params['momentum_weight'],
                    'factors': {
                        'return_3m': {'weight': params['return_3m_weight'], 'direction': 1},
                        'return_6m': {'weight': params['return_6m_weight'], 'direction': 1},
                        'return_12m': {'weight': params['return_12m_weight'], 'direction': 1},
                        'volatility_30d': {'weight': params['volatility_weight'], 'direction': -1},
                        'rsi_14': {'weight': params['rsi_weight'], 'direction': 0}
                    }
                },
                'value': {
                    'weight': params['value_weight'],
                    'factors': {
                        'pe_ratio': {'weight': params['pe_weight'], 'direction': -1},
                        'pb_ratio': {'weight': params['pb_weight'], 'direction': -1},
                        'earnings_yield': {'weight': params['earnings_yield_weight'], 'direction': 1}
                    }
                },
                'quality': {
                    'weight': params['quality_weight'],
                    'factors': {
                        'roe': {'weight': params['roe_weight'], 'direction': 1},
                        'roa': {'weight': params['roa_weight'], 'direction': 1},
                        'profit_margin': {'weight': params['profit_margin_weight'], 'direction': 1},
                        'debt_ratio': {'weight': params['debt_ratio_weight'], 'direction': -1}
                    }
                }
            }
            
            # 生成交易信號（靜默模式）
            import sys
            from io import StringIO
            old_stdout = sys.stdout
            sys.stdout = StringIO()
            
            try:
                signals = strategy.generate_signals(
                    start_date=self.start_date,
                    end_date=self.end_date,
                    rebalance_freq=params['rebalance_freq'],
                    top_n=params['top_n']
                )
            finally:
                sys.stdout = old_stdout
            
            if signals.empty:
                return -1000.0, {}
            
            # 回測
            backtest = MultiFactorBacktest()
            
            old_stdout = sys.stdout
            sys.stdout = StringIO()
            
            try:
                results = backtest.run(signals_df=signals)
            finally:
                sys.stdout = old_stdout
            
            # 提取指標（從 Series 轉換為標量）
            metrics_series = results.get('metrics')
            if metrics_series is None or len(metrics_series) == 0:
                return -1000.0, {}
            
            # 解析字符串格式的指標
            def parse_percent(s):
                """解析百分比字符串"""
                if isinstance(s, str):
                    return float(s.replace('%', '').replace(',', ''))
                return float(s) if s else 0.0
            
            def parse_number(s):
                """解析數值字符串"""
                if isinstance(s, str):
                    return float(s.replace(',', ''))
                return float(s) if s else 0.0
            
            metrics = {
                'annual_return': parse_percent(metrics_series.get('年化報酬率', '0%')),
                'sharpe_ratio': parse_number(metrics_series.get('夏普比率', '0')),
                'max_drawdown': parse_percent(metrics_series.get('最大回撤', '0%')),
                'win_rate': parse_percent(metrics_series.get('勝率', '0%')),
                'total_return': parse_percent(metrics_series.get('總報酬率', '0%')),
                'volatility': parse_percent(metrics_series.get('波動率', '0%')),
                'trades': int(metrics_series.get('交易次數', 0))
            }
            
            # 計算適應度（多目標加權）
            annual_return = metrics.get('annual_return', 0)
            sharpe_ratio = metrics.get('sharpe_ratio', 0)
            max_drawdown = metrics.get('max_drawdown', 0)
            win_rate = metrics.get('win_rate', 0)
            
            # 適應度函數：年化報酬 + 夏普比率 - 回撤懲罰
            fitness = (
                annual_return * 0.5 +  # 年化報酬權重 50%
                sharpe_ratio * 10 * 0.3 +  # 夏普比率權重 30%（放大 10 倍）
                max(0, 10 + max_drawdown) * 0.1 +  # 回撤懲罰 10%（回撤越小越好）
                win_rate * 0.1  # 勝率權重 10%
            )
            
            # 約束條件：年化報酬必須 > 5%，夏普比率 > 0.5（降低約束以便初期探索）
            if annual_return < 5 or sharpe_ratio < 0.5:
                fitness *= 0.7  # 輕度懲罰
            
            return fitness, metrics
            
        except Exception as e:
            print(f"評估失敗: {e}")
            return -1000.0, {}
    
    def crossover(self, parent1: np.ndarray, parent2: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """交叉"""
        if np.random.random() > self.crossover_rate:
            return parent1.copy(), parent2.copy()
        
        # 單點交叉
        point = np.random.randint(1, len(parent1))
        child1 = np.concatenate([parent1[:point], parent2[point:]])
        child2 = np.concatenate([parent2[:point], parent1[point:]])
        
        return child1, child2
    
    def mutate(self, individual: np.ndarray) -> np.ndarray:
        """突變"""
        mutated = individual.copy()
        param_names = list(self.param_ranges.keys())
        
        for i in range(len(mutated) - 1):  # 除了最後一個（調倉頻率）
            if np.random.random() < self.mutation_rate:
                param_name = param_names[i]
                low, high = self.param_ranges[param_name]
                
                if param_name in ['top_n', 'min_factors']:
                    # 整數參數
                    mutated[i] = float(np.random.randint(low, high + 1))
                else:
                    # 連續參數：高斯突變
                    mutated[i] += np.random.normal(0, (high - low) * 0.1)
                    mutated[i] = np.clip(mutated[i], low, high)
        
        # 調倉頻率突變
        if np.random.random() < self.mutation_rate:
            mutated[-1] = float(np.random.randint(0, len(self.rebalance_freq_options)))
        
        return mutated
    
    def select_parents(self, population: List[np.ndarray], fitness_scores: List[float]) -> List[np.ndarray]:
        """
        選擇父代（錦標賽選擇）
        
        Args:
            population: 族群
            fitness_scores: 適應度分數
        
        Returns:
            選中的父代
        """
        parents = []
        tournament_size = 3
        
        for _ in range(len(population)):
            # 隨機選擇 tournament_size 個個體
            tournament_idx = np.random.choice(len(population), tournament_size, replace=False)
            tournament_fitness = [fitness_scores[i] for i in tournament_idx]
            
            # 選擇最佳個體
            winner_idx = tournament_idx[np.argmax(tournament_fitness)]
            parents.append(population[winner_idx].copy())
        
        return parents
    
    def optimize(self) -> Dict:
        """
        執行優化
        
        Returns:
            最佳參數和指標
        """
        print("=" * 80)
        print("多因子策略參數優化")
        print("=" * 80)
        print(f"回測期間: {self.start_date.date()} ~ {self.end_date.date()}")
        print(f"族群大小: {self.population_size}")
        print(f"代數: {self.generations}")
        print(f"突變率: {self.mutation_rate}")
        print(f"交叉率: {self.crossover_rate}")
        print(f"並行進程: {self.workers}")
        print("=" * 80)
        
        # 初始化族群
        print("\n初始化族群...")
        population = [self.create_individual() for _ in range(self.population_size)]
        
        # 進化
        for generation in range(self.generations):
            print(f"\n【第 {generation + 1}/{self.generations} 代】")
            
            # 評估適應度（並行）
            print("  評估適應度...")
            
            if self.workers > 1:
                with mp.Pool(self.workers) as pool:
                    results = pool.map(self.evaluate_individual, population)
            else:
                results = [self.evaluate_individual(ind) for ind in population]
            
            fitness_scores = [r[0] for r in results]
            metrics_list = [r[1] for r in results]
            
            # 記錄最佳個體
            max_idx = np.argmax(fitness_scores)
            generation_best_fitness = fitness_scores[max_idx]
            generation_best_metrics = metrics_list[max_idx]
            
            if generation_best_fitness > self.best_fitness:
                self.best_fitness = generation_best_fitness
                self.best_individual = population[max_idx].copy()
                self.best_metrics = generation_best_metrics
            
            # 統計
            avg_fitness = np.mean(fitness_scores)
            
            print(f"  最佳適應度: {generation_best_fitness:.4f}")
            print(f"  平均適應度: {avg_fitness:.4f}")
            print(f"  年化報酬: {generation_best_metrics.get('annual_return', 0):.2f}%")
            print(f"  夏普比率: {generation_best_metrics.get('sharpe_ratio', 0):.4f}")
            print(f"  最大回撤: {generation_best_metrics.get('max_drawdown', 0):.2f}%")
            
            # 記錄歷史
            self.history.append({
                'generation': generation + 1,
                'best_fitness': generation_best_fitness,
                'avg_fitness': avg_fitness,
                'best_metrics': generation_best_metrics
            })
            
            # 選擇父代
            parents = self.select_parents(population, fitness_scores)
            
            # 生成下一代
            next_population = []
            
            # 精英保留（保留最佳個體）
            next_population.append(population[max_idx].copy())
            
            # 交叉和突變
            while len(next_population) < self.population_size:
                # 隨機選擇兩個父代
                parent1 = parents[np.random.randint(len(parents))]
                parent2 = parents[np.random.randint(len(parents))]
                
                # 交叉
                child1, child2 = self.crossover(parent1, parent2)
                
                # 突變
                child1 = self.mutate(child1)
                child2 = self.mutate(child2)
                
                next_population.append(child1)
                if len(next_population) < self.population_size:
                    next_population.append(child2)
            
            population = next_population
        
        # 輸出最佳結果
        print("\n" + "=" * 80)
        print("優化完成！")
        print("=" * 80)
        
        best_params = self.decode_individual(self.best_individual)
        
        print("\n【最佳參數】")
        print("-" * 80)
        print(f"適應度: {self.best_fitness:.4f}")
        print(f"\n因子大類權重:")
        print(f"  動能因子: {best_params['momentum_weight']:.1%}")
        print(f"  價值因子: {best_params['value_weight']:.1%}")
        print(f"  質量因子: {best_params['quality_weight']:.1%}")
        
        print(f"\n動能子因子權重:")
        print(f"  return_3m: {best_params['return_3m_weight']:.1%}")
        print(f"  return_6m: {best_params['return_6m_weight']:.1%}")
        print(f"  return_12m: {best_params['return_12m_weight']:.1%}")
        print(f"  volatility: {best_params['volatility_weight']:.1%}")
        print(f"  RSI: {best_params['rsi_weight']:.1%}")
        
        print(f"\n價值子因子權重:")
        print(f"  PE: {best_params['pe_weight']:.1%}")
        print(f"  PB: {best_params['pb_weight']:.1%}")
        print(f"  earnings_yield: {best_params['earnings_yield_weight']:.1%}")
        
        print(f"\n質量子因子權重:")
        print(f"  ROE: {best_params['roe_weight']:.1%}")
        print(f"  ROA: {best_params['roa_weight']:.1%}")
        print(f"  profit_margin: {best_params['profit_margin_weight']:.1%}")
        print(f"  debt_ratio: {best_params['debt_ratio_weight']:.1%}")
        
        print(f"\n交易參數:")
        print(f"  持股數量: {best_params['top_n']}")
        print(f"  調倉頻率: {best_params['rebalance_freq']}")
        print(f"  最少因子數: {best_params['min_factors']}")
        
        print(f"\n【回測指標】")
        print("-" * 80)
        for metric, value in self.best_metrics.items():
            if isinstance(value, (int, float)):
                print(f"  {metric}: {value:.2f}{'%' if 'return' in metric or 'drawdown' in metric or 'rate' in metric else ''}")
        
        return {
            'params': best_params,
            'metrics': self.best_metrics,
            'fitness': self.best_fitness,
            'history': self.history
        }


def main():
    """主函數"""
    import argparse
    
    parser = argparse.ArgumentParser(description='多因子策略參數優化')
    parser.add_argument('--start-date', type=str, default='2024-01-01', help='開始日期')
    parser.add_argument('--end-date', type=str, default='2024-12-31', help='結束日期')
    parser.add_argument('--population', type=int, default=50, help='族群大小')
    parser.add_argument('--generations', type=int, default=30, help='代數')
    parser.add_argument('--mutation-rate', type=float, default=0.15, help='突變率')
    parser.add_argument('--crossover-rate', type=float, default=0.7, help='交叉率')
    parser.add_argument('--workers', type=int, default=4, help='並行進程數')
    parser.add_argument('--output', type=str, default='results/optimization_results.json', help='輸出文件')
    
    args = parser.parse_args()
    
    # 解析日期
    start_date = datetime.strptime(args.start_date, '%Y-%m-%d')
    end_date = datetime.strptime(args.end_date, '%Y-%m-%d')
    
    # 創建優化器
    optimizer = ParameterOptimizer(
        start_date=start_date,
        end_date=end_date,
        population_size=args.population,
        generations=args.generations,
        mutation_rate=args.mutation_rate,
        crossover_rate=args.crossover_rate,
        workers=args.workers
    )
    
    # 執行優化
    results = optimizer.optimize()
    
    # 保存結果
    output_path = Path(project_root) / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 準備可序列化的結果
    serializable_results = {
        'params': results['params'],
        'metrics': results['metrics'],
        'fitness': float(results['fitness']),
        'start_date': start_date.isoformat(),
        'end_date': end_date.isoformat(),
        'population_size': args.population,
        'generations': args.generations,
        'history': [
            {
                'generation': h['generation'],
                'best_fitness': float(h['best_fitness']),
                'avg_fitness': float(h['avg_fitness']),
                'best_metrics': h['best_metrics']
            }
            for h in results['history']
        ]
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(serializable_results, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 結果已保存: {output_path}")
    print("\n✅ 優化完成！")


if __name__ == '__main__':
    main()
