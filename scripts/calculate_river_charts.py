#!/usr/bin/env python3
"""
河流圖計算系統
計算 PE/PB 歷史百分位數,用於估價參考
"""

import pymongo
from datetime import datetime, timedelta
from typing import Dict, List
import numpy as np

class RiverChartCalculator:
    def __init__(self):
        self.db = pymongo.MongoClient('mongodb://localhost:27017/')['tw_stock_analysis']
        
    def calculate_pe_river_chart(
        self, 
        stock_id: str, 
        years: int = 5,
        percentiles: List[int] = [5, 25, 50, 75, 95]
    ) -> Dict:
        """
        計算本益比河流圖
        
        參數:
            stock_id: 股票代碼
            years: 歷史年數
            percentiles: 百分位數列表
            
        返回:
            {
                'stock_id': 股票代碼,
                'metric': 'PE',
                'current_value': 當前PE,
                'current_percentile': 當前所在百分位,
                'percentile_bands': {5: 10.5, 25: 15.2, ...},
                'assessment': 估價評估,
                'historical_data': [...],
                'stats': {min, max, mean, median, std}
            }
        """
        # 取得歷史資料
        end_date = datetime.now()
        start_date = end_date - timedelta(days=years*365)
        
        # MongoDB 查詢使用 datetime 而非字串
        historical = list(self.db['stock_per_pbr'].find({
            'symbol': stock_id,
            'date': {
                '$gte': start_date,
                '$lte': end_date
            }
        }).sort('date', 1))
        
        if not historical:
            return {
                'error': '無歷史PE資料',
                'stock_id': stock_id
            }
        
        # 提取PE值
        pe_values = []
        valid_data = []
        
        for record in historical:
            try:
                # 支援兩種欄位名稱格式
                pe = float(record.get('PER', record.get('per', 0)))
                if 0 < pe < 100:  # 過濾異常值
                    pe_values.append(pe)
                    valid_data.append({
                        'date': record['date'] if isinstance(record['date'], str) else record['date'].strftime('%Y-%m-%d'),
                        'pe': pe,
                        'price': record.get('ClosingPrice', record.get('price', 0))
                    })
            except:
                continue
        
        if len(pe_values) < 10:
            return {
                'error': '歷史資料不足',
                'stock_id': stock_id,
                'data_points': len(pe_values)
            }
        
        # 計算百分位數帶
        percentile_bands = {}
        for p in percentiles:
            percentile_bands[str(p)] = round(float(np.percentile(pe_values, p)), 2)
        
        # 當前PE
        current_pe = pe_values[-1]
        
        # 計算當前PE所在百分位
        current_percentile = (sum(1 for pe in pe_values if pe < current_pe) / len(pe_values)) * 100
        
        # 估價評估
        assessment = self._assess_valuation(current_percentile)
        
        # 統計數據
        stats = {
            'min': round(float(min(pe_values)), 2),
            'max': round(float(max(pe_values)), 2),
            'mean': round(float(np.mean(pe_values)), 2),
            'median': round(float(np.median(pe_values)), 2),
            'std': round(float(np.std(pe_values)), 2),
            'data_points': len(pe_values)
        }
        
        return {
            'stock_id': stock_id,
            'metric': 'PE (本益比)',
            'years': years,
            'current_value': round(current_pe, 2),
            'current_percentile': round(current_percentile, 1),
            'percentile_bands': percentile_bands,
            'assessment': assessment,
            'stats': stats,
            'historical_data': valid_data[-100:],  # 只保留最近100筆
            'timestamp': datetime.now().isoformat()
        }
    
    def calculate_pb_river_chart(
        self, 
        stock_id: str, 
        years: int = 5,
        percentiles: List[int] = [5, 25, 50, 75, 95]
    ) -> Dict:
        """
        計算股價淨值比河流圖
        """
        # 取得歷史資料
        end_date = datetime.now()
        start_date = end_date - timedelta(days=years*365)
        
        # MongoDB 查詢使用 datetime 而非字串
        historical = list(self.db['stock_per_pbr'].find({
            'symbol': stock_id,
            'date': {
                '$gte': start_date,
                '$lte': end_date
            }
        }).sort('date', 1))
        
        if not historical:
            return {
                'error': '無歷史PB資料',
                'stock_id': stock_id
            }
        
        # 提取PB值
        pb_values = []
        valid_data = []
        
        for record in historical:
            try:
                # 支援兩種欄位名稱格式
                pb = float(record.get('PBR', record.get('pbr', 0)))
                if 0 < pb < 20:  # 過濾異常值
                    pb_values.append(pb)
                    valid_data.append({
                        'date': record['date'] if isinstance(record['date'], str) else record['date'].strftime('%Y-%m-%d'),
                        'pb': pb,
                        'price': record.get('ClosingPrice', record.get('price', 0))
                    })
            except:
                continue
        
        if len(pb_values) < 10:
            return {
                'error': '歷史資料不足',
                'stock_id': stock_id,
                'data_points': len(pb_values)
            }
        
        # 計算百分位數帶
        percentile_bands = {}
        for p in percentiles:
            percentile_bands[str(p)] = round(float(np.percentile(pb_values, p)), 2)
        
        # 當前PB
        current_pb = pb_values[-1]
        
        # 計算當前PB所在百分位
        current_percentile = (sum(1 for pb in pb_values if pb < current_pb) / len(pb_values)) * 100
        
        # 估價評估
        assessment = self._assess_valuation(current_percentile)
        
        # 統計數據
        stats = {
            'min': round(float(min(pb_values)), 2),
            'max': round(float(max(pb_values)), 2),
            'mean': round(float(np.mean(pb_values)), 2),
            'median': round(float(np.median(pb_values)), 2),
            'std': round(float(np.std(pb_values)), 2),
            'data_points': len(pb_values)
        }
        
        return {
            'stock_id': stock_id,
            'metric': 'PB (股價淨值比)',
            'years': years,
            'current_value': round(current_pb, 2),
            'current_percentile': round(current_percentile, 1),
            'percentile_bands': percentile_bands,
            'assessment': assessment,
            'stats': stats,
            'historical_data': valid_data[-100:],
            'timestamp': datetime.now().isoformat()
        }
    
    def calculate_dividend_yield_river_chart(
        self, 
        stock_id: str, 
        years: int = 5,
        percentiles: List[int] = [5, 25, 50, 75, 95]
    ) -> Dict:
        """
        計算殖利率河流圖
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=years*365)
        
        # MongoDB 查詢使用 datetime 而非字串
        historical = list(self.db['stock_per_pbr'].find({
            'symbol': stock_id,
            'date': {
                '$gte': start_date,
                '$lte': end_date
            }
        }).sort('date', 1))
        
        if not historical:
            return {
                'error': '無歷史殖利率資料',
                'stock_id': stock_id
            }
        
        # 提取殖利率值
        yield_values = []
        valid_data = []
        
        for record in historical:
            try:
                # 支援兩種欄位名稱格式
                dy = float(record.get('yield', record.get('dividend_yield', 0)))
                if 0 < dy < 15:  # 過濾異常值
                    yield_values.append(dy)
                    valid_data.append({
                        'date': record['date'] if isinstance(record['date'], str) else record['date'].strftime('%Y-%m-%d'),
                        'dividend_yield': dy,
                        'price': record.get('ClosingPrice', record.get('price', 0))
                    })
            except:
                continue
        
        if len(yield_values) < 10:
            return {
                'error': '歷史資料不足',
                'stock_id': stock_id,
                'data_points': len(yield_values)
            }
        
        # 計算百分位數帶
        percentile_bands = {}
        for p in percentiles:
            percentile_bands[str(p)] = round(float(np.percentile(yield_values, p)), 2)
        
        # 當前殖利率
        current_yield = yield_values[-1]
        
        # 計算當前殖利率所在百分位
        current_percentile = (sum(1 for dy in yield_values if dy < current_yield) / len(yield_values)) * 100
        
        # 估價評估 (殖利率越高越便宜,與PE/PB相反)
        assessment = self._assess_valuation_reverse(current_percentile)
        
        # 統計數據
        stats = {
            'min': round(float(min(yield_values)), 2),
            'max': round(float(max(yield_values)), 2),
            'mean': round(float(np.mean(yield_values)), 2),
            'median': round(float(np.median(yield_values)), 2),
            'std': round(float(np.std(yield_values)), 2),
            'data_points': len(yield_values)
        }
        
        return {
            'stock_id': stock_id,
            'metric': '殖利率',
            'years': years,
            'current_value': round(current_yield, 2),
            'current_percentile': round(current_percentile, 1),
            'percentile_bands': percentile_bands,
            'assessment': assessment,
            'stats': stats,
            'historical_data': valid_data[-100:],
            'timestamp': datetime.now().isoformat()
        }
    
    def _assess_valuation(self, percentile: float) -> str:
        """估價評估 (PE/PB用)"""
        if percentile < 5:
            return '極度便宜 🟢🟢🟢'
        elif percentile < 25:
            return '便宜 🟢🟢'
        elif percentile < 50:
            return '略便宜 🟢'
        elif percentile < 75:
            return '合理 ⚪'
        elif percentile < 95:
            return '略貴 🔴'
        else:
            return '昂貴 🔴🔴'
    
    def _assess_valuation_reverse(self, percentile: float) -> str:
        """估價評估 (殖利率用,越高越便宜)"""
        if percentile > 95:
            return '極度便宜 🟢🟢🟢'
        elif percentile > 75:
            return '便宜 🟢🟢'
        elif percentile > 50:
            return '略便宜 🟢'
        elif percentile > 25:
            return '合理 ⚪'
        elif percentile > 5:
            return '略貴 🔴'
        else:
            return '昂貴 🔴🔴'
    
    def calculate_all_river_charts(self, stock_id: str, years: int = 5) -> Dict:
        """計算所有河流圖"""
        return {
            'stock_id': stock_id,
            'pe_river': self.calculate_pe_river_chart(stock_id, years),
            'pb_river': self.calculate_pb_river_chart(stock_id, years),
            'yield_river': self.calculate_dividend_yield_river_chart(stock_id, years),
            'timestamp': datetime.now().isoformat()
        }
    
    def generate_river_chart_report(self, stock_id: str, years: int = 5) -> str:
        """生成河流圖報告"""
        data = self.calculate_all_river_charts(stock_id, years)
        
        report = []
        report.append("=" * 80)
        report.append(f"📊 河流圖分析報告: {stock_id}")
        report.append("=" * 80)
        report.append(f"歷史期間: {years} 年")
        report.append("")
        
        # PE 河流圖
        pe = data['pe_river']
        if 'error' not in pe:
            report.append("📈 本益比 (PE) 河流圖")
            report.append("-" * 80)
            report.append(f"當前 PE: {pe['current_value']}")
            report.append(f"百分位數: {pe['current_percentile']}%")
            report.append(f"評估: {pe['assessment']}")
            report.append(f"\n歷史百分位數帶:")
            for p, v in sorted(pe['percentile_bands'].items()):
                report.append(f"  {p:2d}%: {v:6.2f}")
            report.append(f"\n統計數據:")
            report.append(f"  最小值: {pe['stats']['min']}")
            report.append(f"  最大值: {pe['stats']['max']}")
            report.append(f"  平均值: {pe['stats']['mean']}")
            report.append(f"  中位數: {pe['stats']['median']}")
            report.append(f"  標準差: {pe['stats']['std']}")
            report.append(f"  資料點數: {pe['stats']['data_points']}")
        else:
            report.append(f"📈 本益比: {pe.get('error', '無資料')}")
        
        # PB 河流圖
        report.append("\n" + "=" * 80)
        pb = data['pb_river']
        if 'error' not in pb:
            report.append("📈 股價淨值比 (PB) 河流圖")
            report.append("-" * 80)
            report.append(f"當前 PB: {pb['current_value']}")
            report.append(f"百分位數: {pb['current_percentile']}%")
            report.append(f"評估: {pb['assessment']}")
            report.append(f"\n歷史百分位數帶:")
            for p, v in sorted(pb['percentile_bands'].items()):
                report.append(f"  {p:2d}%: {v:6.2f}")
            report.append(f"\n統計數據:")
            report.append(f"  最小值: {pb['stats']['min']}")
            report.append(f"  最大值: {pb['stats']['max']}")
            report.append(f"  平均值: {pb['stats']['mean']}")
            report.append(f"  中位數: {pb['stats']['median']}")
            report.append(f"  標準差: {pb['stats']['std']}")
            report.append(f"  資料點數: {pb['stats']['data_points']}")
        else:
            report.append(f"📈 股價淨值比: {pb.get('error', '無資料')}")
        
        # 殖利率河流圖
        report.append("\n" + "=" * 80)
        dy = data['yield_river']
        if 'error' not in dy:
            report.append("📈 殖利率河流圖")
            report.append("-" * 80)
            report.append(f"當前殖利率: {dy['current_value']}%")
            report.append(f"百分位數: {dy['current_percentile']}%")
            report.append(f"評估: {dy['assessment']}")
            report.append(f"\n歷史百分位數帶:")
            for p, v in sorted(dy['percentile_bands'].items()):
                report.append(f"  {p:2d}%: {v:6.2f}%")
            report.append(f"\n統計數據:")
            report.append(f"  最小值: {dy['stats']['min']}%")
            report.append(f"  最大值: {dy['stats']['max']}%")
            report.append(f"  平均值: {dy['stats']['mean']}%")
            report.append(f"  中位數: {dy['stats']['median']}%")
            report.append(f"  標準差: {dy['stats']['std']}%")
            report.append(f"  資料點數: {dy['stats']['data_points']}")
        else:
            report.append(f"📈 殖利率: {dy.get('error', '無資料')}")
        
        report.append("\n" + "=" * 80)
        
        return "\n".join(report)
    
    def batch_calculate(self, stock_ids: List[str], years: int = 5, save_to_db: bool = True) -> List[Dict]:
        """批量計算河流圖"""
        results = []
        
        for stock_id in stock_ids:
            try:
                result = self.calculate_all_river_charts(stock_id, years)
                results.append(result)
                
                if save_to_db:
                    # 儲存 PE 河流圖
                    if 'error' not in result['pe_river']:
                        self.db['river_charts'].update_one(
                            {'stock_id': stock_id, 'metric': 'PE'},
                            {'$set': result['pe_river']},
                            upsert=True
                        )
                    
                    # 儲存 PB 河流圖
                    if 'error' not in result['pb_river']:
                        self.db['river_charts'].update_one(
                            {'stock_id': stock_id, 'metric': 'PB'},
                            {'$set': result['pb_river']},
                            upsert=True
                        )
                    
                    # 儲存殖利率河流圖
                    if 'error' not in result['yield_river']:
                        self.db['river_charts'].update_one(
                            {'stock_id': stock_id, 'metric': 'YIELD'},
                            {'$set': result['yield_river']},
                            upsert=True
                        )
                
                print(f"✅ {stock_id}: 河流圖計算完成")
            except Exception as e:
                print(f"❌ {stock_id}: {str(e)}")
        
        return results


def main():
    """測試範例"""
    calculator = RiverChartCalculator()
    
    # 測試股票
    test_stocks = ['2330', '2317', '2454']
    
    print("=" * 80)
    print("📊 河流圖計算系統")
    print("=" * 80)
    
    for stock_id in test_stocks:
        print(f"\n{calculator.generate_river_chart_report(stock_id, years=5)}")
        
        # 儲存到資料庫
        result = calculator.calculate_all_river_charts(stock_id, years=5)
        
        if 'error' not in result['pe_river']:
            calculator.db['river_charts'].update_one(
                {'stock_id': stock_id, 'metric': 'PE'},
                {'$set': result['pe_river']},
                upsert=True
            )
        
        if 'error' not in result['pb_river']:
            calculator.db['river_charts'].update_one(
                {'stock_id': stock_id, 'metric': 'PB'},
                {'$set': result['pb_river']},
                upsert=True
            )
        
        if 'error' not in result['yield_river']:
            calculator.db['river_charts'].update_one(
                {'stock_id': stock_id, 'metric': 'YIELD'},
                {'$set': result['yield_river']},
                upsert=True
            )
    
    print("\n" + "=" * 80)
    print("✅ 計算完成並已儲存至 river_charts 集合")
    print("=" * 80)


if __name__ == '__main__':
    main()
