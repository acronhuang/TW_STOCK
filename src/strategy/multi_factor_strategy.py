#!/usr/bin/env python3
"""
多因子選股策略
Multi-Factor Stock Selection Strategy

結合動能、價值、質量因子進行選股
使用因子排名加權計算綜合得分
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from pymongo import MongoClient

# 添加專案路徑
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class MultiFactorStrategy:
    """
    多因子選股策略
    
    策略邏輯：
    1. 計算每個股票在多個因子上的排名
    2. 對排名進行標準化（0-100分）
    3. 加權計算綜合得分
    4. 選擇得分最高的 N 支股票
    5. 等權重持有，每月調倉
    """
    
    def _fundamental_quality(self, date):
        """取 available_from <= date 的最近一期品質因子。

        必須用 available_from(法定公告期限)而非 period_end —— 用 period_end
        等於在財報還沒公告時就知道數字,那只是換個方式重蹈前視偏誤。
        """
        from datetime import datetime as _dt
        if isinstance(date, str):
            date = _dt.strptime(date[:10], "%Y-%m-%d")

        rows = self.db.fundamental_factors.aggregate([
            {"$match": {"available_from": {"$lte": date}}},
            {"$sort": {"stock_id": 1, "available_from": -1}},
            {"$group": {"_id": "$stock_id", "d": {"$first": "$$ROOT"}}},
        ])
        out = {}
        for r in rows:
            d = r["d"]
            out[str(r["_id"])] = {k: d.get(k) for k in
                                  ("roe", "roa", "profit_margin", "debt_ratio", "op_margin", "fcf_margin")}
        return out

    def update_config(self, factor_config: dict):
        """套用外部因子設定。

        integrated_strategy_v21.py:120 會呼叫本方法,但此方法過去並不存在 ——
        只因該處預設 factor_config=None 才沒被觸發(AttributeError 潛伏)。

        傳入的類別會覆蓋既有設定;若各類別權重總和不為 1,會自動正規化,
        避免呼叫端只調整部分類別時得到未預期的縮放。
        """
        if not factor_config:
            return
        for name, cfg in factor_config.items():
            if cfg is None:
                self.factor_config.pop(name, None)      # 傳 None 代表移除該類別
            else:
                self.factor_config[name] = cfg

        total = sum(c.get('weight', 0) for c in self.factor_config.values())
        if total > 0 and abs(total - 1.0) > 1e-9:
            for c in self.factor_config.values():
                c['weight'] = c.get('weight', 0) / total

    def __init__(self, 
                 mongo_uri_or_db = "mongodb://localhost:27017/",
                 db_name: str = "tw_stock_analysis"):
        """
        初始化策略
        
        Args:
            mongo_uri_or_db: MongoDB 連接字串或 Database 對象
            db_name: 資料庫名稱（如果傳入連接字串時使用）
        """
        # 支持傳入 Database 對象或 URI 字符串
        if isinstance(mongo_uri_or_db, str):
            self.client = MongoClient(mongo_uri_or_db)
            self.db = self.client[db_name]
        else:
            # 假設傳入的是 Database 對象
            self.db = mongo_uri_or_db
            self.client = None
        
        # 因子配置
        # quality 因子來源:'legacy'=stock_factors(常數,有前視偏誤)
        #                  'fundamental'=fundamental_factors(以 available_from 落後,正確)
        self.quality_source = 'fundamental'   # Config C:走PIT正確源(原legacy有前視偏誤)

        self.factor_config = {
            # 動能因子（權重 50%）
            'momentum': {
                'weight': 0.50,
                'factors': {
                    'return_3m': {'weight': 0.30, 'direction': 1},    # 3個月報酬率（正向）
                    'return_6m': {'weight': 0.25, 'direction': 1},    # 6個月報酬率（正向）
                    'return_12m': {'weight': 0.20, 'direction': 1},   # 12個月報酬率（正向）
                    'volatility_30d': {'weight': 0.15, 'direction': -1}, # 30日波動率（反向）
                    'rsi_14': {'weight': 0.10, 'direction': 0}         # RSI（中性，過濾極端值）
                }
            },
            # 價值因子（權重 30%）
            'value': {
                'weight': 0.30,
                'factors': {
                    'pe_ratio': {'weight': 0.40, 'direction': -1},     # 本益比（反向，低PE好）
                    'pb_ratio': {'weight': 0.35, 'direction': -1},     # 股價淨值比（反向）
                    'earnings_yield': {'weight': 0.25, 'direction': 1} # 盈餘收益率（正向）
                }
            },
            # 質量因子（權重 20%）
            'quality': {
                'weight': 0.20,
                'factors': {
                    # Config C（2026-07 多循環+含成本回測驗證）：op_margin 最強品質因子(t+5.29,單調)，
                    # fcf_margin 與價值正交(t+5.38)，roe 既有品質；原 roa/profit_margin/debt_ratio 較弱已汰換
                    'op_margin': {'weight': 0.40, 'direction': 1},     # 營益率（最強品質，正向）
                    'fcf_margin': {'weight': 0.30, 'direction': 1},    # 自由現金流率（正交補強，正向）
                    'roe': {'weight': 0.30, 'direction': 1}            # ROE（既有品質，正向）
                }
            }
        }
        
        self.name = "多因子選股策略"
    
    def calculate_factor_score(self, 
                               factors_df: pd.DataFrame,
                               factor_name: str,
                               direction: int) -> pd.Series:
        """
        計算單一因子得分（0-100）
        
        Args:
            factors_df: 因子數據 DataFrame
            factor_name: 因子名稱
            direction: 方向（1=正向，-1=反向，0=中性）
        
        Returns:
            因子得分 Series
        """
        if factor_name not in factors_df.columns:
            return pd.Series(50.0, index=factors_df.index)  # 預設中性分數
        
        values = factors_df[factor_name].copy()
        
        # 移除 None 和 NaN
        values = values.replace([np.inf, -np.inf], np.nan)
        
        if values.isna().all():
            return pd.Series(50.0, index=factors_df.index)
        
        # RSI 特殊處理（過濾超買超賣）
        if factor_name == 'rsi_14':
            # RSI 在 30-70 之間給高分，極端值給低分
            scores = values.copy()
            scores = 100 - 2 * abs(scores - 50)  # 中心點50分最高
            scores = scores.clip(0, 100)
            return scores.fillna(50.0)
        
        # 標準化為 0-100 分（百分位排名）
        if direction == 1:
            # 正向因子：值越大越好
            scores = values.rank(pct=True) * 100
        elif direction == -1:
            # 反向因子：值越小越好
            scores = (1 - values.rank(pct=True)) * 100
        else:
            # 中性因子
            scores = pd.Series(50.0, index=values.index)
        
        return scores.fillna(50.0)
    
    def calculate_composite_score(self, 
                                  date: datetime,
                                  min_factors: int = 3) -> pd.DataFrame:
        """
        計算綜合得分
        
        Args:
            date: 計算日期
            min_factors: 最少需要的有效因子數
        
        Returns:
            包含 symbol, score, valid_factors 的 DataFrame
        """
        # 獲取當日所有因子數據
        factors_cursor = self.db.stock_factors.find(
            {'date': date},
            {'_id': 0, 'symbol': 1, **{
                f: 1 for category in self.factor_config.values() 
                for f in category['factors'].keys()
            }}
        )
        
        factors_data = list(factors_cursor)
        
        if not factors_data:
            return pd.DataFrame(columns=['symbol', 'score', 'valid_factors'])
        
        # 確保 symbol 是字符串類型
        for record in factors_data:
            record['symbol'] = str(record['symbol'])
        
        factors_df = pd.DataFrame(factors_data).set_index('symbol')

        if self.quality_source == 'fundamental':
            # 以財報公告期限落後後的真實時間序列,覆蓋 stock_factors 裡的常數值
            qmap = self._fundamental_quality(date)
            for col in ('roe', 'roa', 'profit_margin', 'debt_ratio'):
                if col in factors_df.columns:
                    factors_df[col] = [
                        (qmap.get(sym) or {}).get(col) for sym in factors_df.index
                    ]

        # 計算每個因子的得分
        factor_scores = {}
        
        for category_name, category_config in self.factor_config.items():
            category_weight = category_config['weight']
            
            for factor_name, factor_config in category_config['factors'].items():
                factor_weight = factor_config['weight'] * category_weight
                direction = factor_config['direction']
                
                # 計算因子得分
                scores = self.calculate_factor_score(factors_df, factor_name, direction)
                
                factor_scores[factor_name] = {
                    'scores': scores,
                    'weight': factor_weight
                }
        
        # 計算加權綜合得分
        composite_scores = []
        valid_factors_count = []
        
        for symbol in factors_df.index:
            total_score = 0
            total_weight = 0
            valid_count = 0
            
            for factor_name, factor_data in factor_scores.items():
                score = factor_data['scores'].get(symbol, np.nan)
                weight = factor_data['weight']

                # 2026-07-19 修：原本直接 factors_df.loc[symbol, factor_name]，
                # 當該日查回來的個股全都沒有某因子時，factors_df 根本不會有這一欄
                # → KeyError（實測 backtest_integrated_v21 跑到 2023-08 的再平衡日崩潰）。
                # 欄位不存在 = 該因子當日不可用，應跳過而非中斷整場回測。
                if factor_name not in factors_df.columns:
                    continue

                if not np.isnan(score) and factors_df.loc[symbol, factor_name] is not None:
                    total_score += score * weight
                    total_weight += weight
                    valid_count += 1
            
            # 正規化得分
            if total_weight > 0 and valid_count >= min_factors:
                final_score = total_score / total_weight
            else:
                final_score = np.nan
            
            composite_scores.append(final_score)
            valid_factors_count.append(valid_count)
        
        result_df = pd.DataFrame({
            'symbol': factors_df.index,
            'score': composite_scores,
            'valid_factors': valid_factors_count
        })
        
        # 移除無效得分
        result_df = result_df[result_df['score'].notna()].copy()
        result_df = result_df.sort_values('score', ascending=False).reset_index(drop=True)
        
        return result_df
    
    def select_stocks(self,
                     date,
                     top_n: int = 20,
                     min_factors: int = 3) -> list[dict]:
        """
        選股
        
        Args:
            date: 選股日期（可以是 datetime 或字符串）
            top_n: 選擇前 N 支股票
            min_factors: 最少需要的有效因子數
        
        Returns:
            選中的股票列表，包含 stock_id 和 composite_score
        """
        # 處理日期格式
        if isinstance(date, str):
            date = pd.to_datetime(date)
        
        # 計算綜合得分
        scores_df = self.calculate_composite_score(date, min_factors)
        
        if scores_df.empty:
            return []
        
        # 選擇得分最高的股票
        selected = scores_df.head(top_n)
        
        # 轉換為字典列表
        result = []
        for _, row in selected.iterrows():
            result.append({
                'stock_id': str(row['symbol']),
                'composite_score': float(row['score']),
                'valid_factors': int(row['valid_factors'])
            })
        
        return result
    
    def generate_signals(self,
                        start_date: datetime,
                        end_date: datetime,
                        rebalance_freq: str = 'M',
                        top_n: int = 20) -> pd.DataFrame:
        """
        生成交易信號
        
        Args:
            start_date: 開始日期
            end_date: 結束日期
            rebalance_freq: 調倉頻率（'M'=月, 'Q'=季, 'Y'=年）
            top_n: 持有股票數
        
        Returns:
            交易信號 DataFrame
        """
        # 生成調倉日期
        rebalance_dates = pd.date_range(start=start_date, end=end_date, freq=rebalance_freq)
        
        signals = []
        
        print(f"\n{self.name} - 生成交易信號")
        print(f"期間: {start_date.date()} ~ {end_date.date()}")
        print(f"調倉頻率: {rebalance_freq}")
        print(f"持股數: {top_n}")
        print("-" * 80)
        
        for i, rebalance_date in enumerate(rebalance_dates, 1):
            # 選股
            selected_stocks = self.select_stocks(
                rebalance_date.to_pydatetime(),
                top_n=top_n
            )
            
            if not selected_stocks:
                print(f"[{i}/{len(rebalance_dates)}] {rebalance_date.date()}: 無可選股票")
                continue
            
            print(f"[{i}/{len(rebalance_dates)}] {rebalance_date.date()}: 選中 {len(selected_stocks)} 支股票")
            
            # 等權重配置
            weight = 1.0 / len(selected_stocks)
            
            for symbol in selected_stocks:
                signals.append({
                    'date': rebalance_date.to_pydatetime(),
                    'symbol': symbol,
                    'action': 'rebalance',
                    'weight': weight
                })
        
        signals_df = pd.DataFrame(signals)
        
        print("-" * 80)
        print(f"✅ 生成 {len(signals_df)} 條交易信號")
        
        return signals_df


def main():
    """主函數"""
    print("=" * 80)
    print("多因子選股策略")
    print("=" * 80)
    
    # 初始化策略
    strategy = MultiFactorStrategy()
    
    # 設定回測期間
    start_date = datetime(2024, 1, 1)
    end_date = datetime(2024, 12, 31)
    
    # 生成交易信號
    signals = strategy.generate_signals(
        start_date=start_date,
        end_date=end_date,
        rebalance_freq='M',  # 每月調倉
        top_n=20  # 持有 20 支股票
    )
    
    # 保存信號
    output_dir = Path(__file__).parent.parent / 'data'
    output_dir.mkdir(exist_ok=True)
    
    output_file = output_dir / 'multifactor_signals.csv'
    signals.to_csv(output_file, index=False, encoding='utf-8-sig')
    
    print(f"\n💾 交易信號已保存: {output_file}")
    
    # 顯示樣本
    print("\n" + "=" * 80)
    print("信號樣本（前 20 條）:")
    print("-" * 80)
    print(signals.head(20).to_string())
    
    # 統計信息
    print("\n" + "=" * 80)
    print("統計信息:")
    print("-" * 80)
    print(f"調倉次數: {signals['date'].nunique()}")
    print(f"涉及股票數: {signals['symbol'].nunique()}")
    print(f"平均每次持股數: {signals.groupby('date')['symbol'].count().mean():.1f}")
    
    # 最常被選中的股票
    top_selected = signals['symbol'].value_counts().head(10)
    print("\n最常被選中的股票 Top 10:")
    for symbol, count in top_selected.items():
        pct = count / signals['date'].nunique() * 100
        print(f"  {symbol}: {count} 次 ({pct:.1f}%)")
    
    print("\n" + "=" * 80)
    print("✅ 策略信號生成完成！")
    print("💡 下一步: 運行回測分析策略績效")
    print("=" * 80)


if __name__ == '__main__':
    main()
