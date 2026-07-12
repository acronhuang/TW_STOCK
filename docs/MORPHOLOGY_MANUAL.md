# 蔡森形態學使用手冊

**版本**: v2.1.0  
**最後更新**: 2026-02-23  
**作者**: Ming

---

## 目錄

- [1. 快速開始](#1-快速開始)
- [2. 核心形態說明](#2-核心形態說明)
- [3. API 使用指南](#3-api-使用指南)
- [4. 實戰範例](#4-實戰範例)
- [5. 參數調優](#5-參數調優)
- [6. 常見問題](#6-常見問題)

---

## 1. 快速開始

### 1.1. 安裝

形態學模組已整合在 `src/morphology/` 中，無需額外安裝。

```bash
# 確認模組可用
cd /Users/ming/Desktop/Stock/tw-stock-analysis
python3 -c "from src.morphology import PatternDetector; print('✓ 模組正常')"
```

### 1.2. 3 分鐘上手

```python
import pandas as pd
from src.morphology import PatternDetector

# 1. 準備數據（從 MongoDB 讀取）
from pymongo import MongoClient
client = MongoClient('mongodb://localhost:27017/')
db = client['tw_stock_analysis']

stock_id = "2330"
data = list(db.stock_price.find(
    {'stock_id': stock_id},
    {'_id': 0, 'date': 1, 'open': 1, 'high': 1, 'low': 1, 'close': 1, 'volume': 1}
).sort('date', 1).limit(100))

df = pd.DataFrame(data)
df['date'] = pd.to_datetime(df['date'])
df.set_index('date', inplace=True)

# 2. 初始化偵測器
detector = PatternDetector()

# 3. 執行偵測
results = detector.detect_all(df, stock_id=stock_id)

# 4. 查看結果
print(detector.generate_summary(df, stock_id=stock_id))

# 5. 獲取綜合評分
score = detector.calculate_overall_score(df, lookback_days=5)
print(f"\n綜合評分: {score:.3f}")
```

**輸出範例**:
```
======================================================================
形態偵測報告 - 2330
======================================================================
數據期間: 2024-01-01 ~ 2024-06-30
綜合評分: 0.756

----------------------------------------------------------------------
各形態偵測結果:
----------------------------------------------------------------------
✓ bottom_reversal          | 出現次數:   2 | 評分: 0.850
    最近一次: {'date': '2024-05-15', 'support_line': 580, ...}
✗ w_bottom                 | 出現次數:   0 | 評分: 0.000
✓ neckline_breakout        | 出現次數:   1 | 評分: 0.720
✓ volume_surge             | 出現次數:   3 | 評分: 0.680
✗ volume_price_divergence  | 出現次數:   0 | 評分: 0.000
======================================================================
```

---

## 2. 核心形態說明

### 2.1. 破底翻 (Bottom Reversal)

**定義**: 股價跌破支撐線後，於 5 日內帶量收復。

**特徵**:
- ✅ 跌破前波低點（支撐線）
- ✅ 快速收復（5 日內）
- ✅ 成交量放大 1.5 倍以上
- ✅ 收盤站回支撐線 +2%

**應用場景**:
- **進場**: 確認收復後的次日開盤
- **止損**: 支撐線 -2%（或進場價 -5%，取較大者）
- **適合**: 急跌後的 V 型反轉

**風險**:
- ⚠️ 可能是「假跌破」（洗盤）
- ⚠️ 需確認大盤不是系統性風險

**程式碼**:
```python
from src.morphology import detect_bottom_reversal

signal, details = detect_bottom_reversal(
    df,
    window=20,           # 支撐線計算週期
    recovery_days=5,     # 允許收復天數
    volume_ratio=1.5     # 成交量放大倍數
)

# 查看最近一次破底翻
if not details.empty:
    latest = details.iloc[-1]
    print(f"支撐線: {latest['support_line']}")
    print(f"收復價: {latest['recovery_price']}")
    print(f"評分: {latest['pattern_score']}")
```

---

### 2.2. 雙底 (W Bottom)

**定義**: 形成兩個低點，第二底不破第一底，且突破頸線。

**特徵**:
- ✅ 兩個低點間隔 10-40 天
- ✅ 第二底 ≥ 第一底 × 0.98（不破 -2%）
- ✅ 突破頸線 +3%
- ✅ 突破時成交量放大 1.5 倍

**應用場景**:
- **進場**: 突破頸線確認後
- **止損**: 頸線 -3%
- **目標價**: 頸線 + (頸線 - 底部)
- **適合**: 中期底部確認

**形態強度判斷**:
- **優**: 兩底對稱（價差 < 2%），突破爆量（>2 倍）
- **良**: 第二底略高，突破放量（1.5 倍）
- **差**: 第二底接近第一底，突破縮量

**程式碼**:
```python
from src.morphology import detect_w_bottom, calculate_w_bottom_target

signal, details = detect_w_bottom(
    df,
    min_gap=10,
    max_gap=40,
    tolerance=0.02,
    breakout_threshold=1.03
)

# 計算理論目標價
if not details.empty:
    latest = details.iloc[-1]
    target = calculate_w_bottom_target(
        neckline=latest['neckline'],
        second_bottom=latest['second_bottom_price']
    )
    print(f"理論目標價: {target:.2f}")
```

---

### 2.3. 頸線突破 (Neckline Breakout)

**定義**: 突破過去 60 日高點（頸線），且振幅 > 3%，爆量 2 倍。

**特徵**:
- ✅ 突破 60 日高點 +3%
- ✅ 當日振幅 > 3%
- ✅ 成交量爆量 2 倍
- ✅ 連續 2 日站穩（避免假突破）

**應用場景**:
- **進場**: 確認突破後
- **止損**: 頸線 -5%
- **適合**: 長期盤整後的突破

**假突破判斷**:
- ❌ 突破後 5 日內跌回頸線 → 假突破
- ❌ 突破當日振幅 < 3% → 力道不足
- ❌ 成交量未放大 → 可能是騙線

**程式碼**:
```python
from src.morphology import detect_neckline_breakout

signal, details = detect_neckline_breakout(
    df,
    window=60,
    breakout_threshold=1.03,
    amplitude_threshold=0.03,
    volume_ratio=2.0
)

# 檢查整理天數
if not details.empty:
    latest = details.iloc[-1]
    print(f"整理天數: {latest['consolidation_days']}")
    print(f"振幅: {latest['amplitude']:.2%}")
```

---

### 2.4. 量價噴出 (Volume Surge)

**定義**: 成交量爆量 3 倍，且突破 20 日高點，當日漲幅 > 5%。

**特徵**:
- ✅ 成交量 > 5 日均量 × 3
- ✅ 突破 20 日高點
- ✅ 當日漲幅 > 5%

**應用場景**:
- **進場**: 不建議追高，等回測
- **出場**: 獲利 15% 後啟動移動止盈
- **適合**: 已持有部位，加碼或減碼參考

**風險**:
- ⚠️ 一日行情，容易追高套牢
- ⚠️ 需確認是否為主力倒貨

**程式碼**:
```python
from src.morphology import detect_volume_surge

signal, details = detect_volume_surge(
    df,
    volume_ratio=3.0,
    price_threshold=1.05
)
```

---

### 2.5. 量價背離 (Volume-Price Divergence)

**定義**: 股價創新高但成交量未創新高（負背離，看跌）。

**特徵**:
- ❌ 股價創 60 日新高
- ❌ 成交量低於 5 日均量
- ❌ 連續 2 日出現

**應用場景**:
- **出場訊號**: 已持有部位，考慮減倉 50%
- **不進場**: 候選股出現背離，排除
- **適合**: 出場判斷，保護利潤

**程式碼**:
```python
from src.morphology import detect_volume_price_divergence

signal, details = detect_volume_price_divergence(
    df,
    window=60,
    consecutive_days=2
)

# 檢查警示等級
if not details.empty:
    latest = details.iloc[-1]
    print(f"警示等級: {latest['warning_level']}")
    print(f"背離評分: {latest['divergence_score']}")
```

---

## 3. API 使用指南

### 3.1. PatternDetector（主類別）

**初始化**:
```python
from src.morphology import PatternDetector

# 預設：啟用所有形態
detector = PatternDetector()

# 自訂：只啟用部分形態
detector = PatternDetector(
    enable_patterns=['bottom_reversal', 'w_bottom']
)

# 自訂權重
detector = PatternDetector(
    custom_weights={
        'bottom_reversal': 0.40,
        'w_bottom': 0.35,
        'neckline_breakout': 0.25
    }
)
```

**核心方法**:

#### 3.1.1. `detect_all()` - 偵測所有形態

```python
results = detector.detect_all(df, stock_id="2330")

# 返回格式
{
    'bottom_reversal': {
        'detected': True,
        'signal': pd.Series,  # Boolean，標記出現日期
        'details': pd.DataFrame,  # 詳細資訊
        'count': 2,
        'latest': {...},  # 最近一次形態
        'score': 0.85
    },
    ...
}
```

#### 3.1.2. `get_latest_patterns()` - 獲取最近形態

```python
recent = detector.get_latest_patterns(
    df,
    lookback_days=5,  # 回溯 5 天
    min_score=0.5     # 最低評分 0.5
)

# 返回格式
{
    'bottom_reversal': {
        'detected': True,
        'score': 0.85,
        'count': 1,
        'details': {...}
    }
}
```

#### 3.1.3. `calculate_overall_score()` - 計算綜合評分

```python
score = detector.calculate_overall_score(df, lookback_days=5)
# 返回 0.0-1.0 之間的評分
```

#### 3.1.4. `filter_stocks()` - 批量過濾股票

```python
# 準備多支股票數據
stocks_data = {
    '2330': df_2330,
    '2317': df_2317,
    '2454': df_2454
}

# 過濾
filtered = detector.filter_stocks(
    stocks_data,
    min_patterns=1,      # 至少 1 個形態
    min_score=0.6,       # 綜合評分 > 0.6
    lookback_days=5
)

# 返回 [(股票代碼, 評分, 形態詳情), ...]
for stock_id, score, patterns in filtered:
    print(f"{stock_id}: {score:.3f}")
```

---

### 3.2. PatternScorer（評分器）

**倉位權重計算**:

```python
from src.morphology import calculate_position_weight

# 基礎權重 10%，形態評分 0.85，最多加到 12%
weight = calculate_position_weight(
    base_weight=0.10,
    pattern_score=0.85,
    max_boost=1.2
)

print(f"調整後權重: {weight:.2%}")  # 11.7%
```

**生成報告**:

```python
from src.morphology import generate_pattern_report

patterns = detector.detect_all(df)
report = generate_pattern_report(patterns, include_details=True)
print(report)
```

---

## 4. 實戰範例

### 4.1. 範例 1: 單支股票形態分析

```python
import pandas as pd
from pymongo import MongoClient
from src.morphology import PatternDetector

# 連接 MongoDB
client = MongoClient('mongodb://localhost:27017/')
db = client['tw_stock_analysis']

def analyze_stock(stock_id, days=120):
    """分析單支股票的形態"""
    
    # 讀取數據
    data = list(db.stock_price.find(
        {'stock_id': stock_id},
        {'_id': 0, 'date': 1, 'open': 1, 'high': 1, 'low': 1, 'close': 1, 'volume': 1}
    ).sort('date', -1).limit(days))
    
    if not data:
        print(f"查無數據: {stock_id}")
        return None
    
    df = pd.DataFrame(data)
    df['date'] = pd.to_datetime(df['date'])
    df.set_index('date', inplace=True)
    df = df.sort_index()
    
    # 偵測形態
    detector = PatternDetector()
    results = detector.detect_all(df, stock_id=stock_id)
    
    # 計算綜合評分
    score = detector.calculate_overall_score(df, lookback_days=5)
    
    # 生成報告
    print(detector.generate_summary(df, stock_id=stock_id))
    
    # 判斷是否值得進場
    if score >= 0.7:
        recent = detector.get_latest_patterns(df, lookback_days=5)
        print(f"\n🟢 推薦進場！綜合評分: {score:.3f}")
        for pattern, data in recent.items():
            print(f"  ✓ {pattern}: {data['score']:.3f}")
    elif score >= 0.5:
        print(f"\n🟡 可觀察，評分: {score:.3f}")
    else:
        print(f"\n🔴 不推薦，評分: {score:.3f}")
    
    return score, results

# 執行分析
analyze_stock("2330")
```

---

### 4.2. 範例 2: 批量篩選候選股

```python
from src.morphology import PatternDetector
from pymongo import MongoClient
import pandas as pd

def filter_candidates(stock_list, top_n=10):
    """從候選股中篩選出形態最佳的 top N"""
    
    client = MongoClient('mongodb://localhost:27017/')
    db = client['tw_stock_analysis']
    
    # 讀取所有股票數據
    stocks_data = {}
    for stock_id in stock_list:
        data = list(db.stock_price.find(
            {'stock_id': stock_id}
        ).sort('date', -1).limit(120))
        
        if not data:
            continue
        
        df = pd.DataFrame(data)
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        df = df.sort_index()
        
        stocks_data[stock_id] = df
    
    # 初始化偵測器
    detector = PatternDetector()
    
    # 批量過濾
    filtered = detector.filter_stocks(
        stocks_data,
        min_patterns=1,
        min_score=0.6,
        lookback_days=5
    )
    
    # 顯示結果
    print(f"\n找到 {len(filtered)} 支符合條件的股票：")
    print("-" * 70)
    
    for i, (stock_id, score, patterns) in enumerate(filtered[:top_n], 1):
        print(f"{i}. {stock_id} | 評分: {score:.3f} | 形態數: {len(patterns)}")
        for pattern, data in patterns.items():
            print(f"   - {pattern}: {data['score']:.3f}")
    
    return filtered[:top_n]

# 使用範例
candidates = ['2330', '2317', '2454', '2308', '2382']  # 30 支候選股
top_stocks = filter_candidates(candidates, top_n=10)
```

---

### 4.3. 範例 3: 整合到 v2.0 策略

```python
"""
將形態學整合到 v2.0 多因子策略
"""

def integrated_selection_v21(rebalance_date, top_n=30, final_n=10):
    """
    v2.1 選股流程：17 因子 → 30 支候選 → 形態過濾 → 10 支
    
    Args:
        rebalance_date: 調倉日期
        top_n: 候選股數量（17 因子選出）
        final_n: 最終持股數量（形態過濾後）
    
    Returns:
        List[Tuple]: [(股票代碼, 綜合評分, 形態詳情), ...]
    """
    from src.strategy.multifactor_strategy_v2 import MultiFactorStrategy
    from src.morphology import PatternDetector
    
    # Step 1: 17 因子選股（30 支候選）
    strategy = MultiFactorStrategy()
    candidates = strategy.select_stocks(rebalance_date, top_n=top_n)
    
    print(f"17 因子選出 {len(candidates)} 支候選股")
    
    # Step 2: 讀取候選股數據
    stocks_data = {}
    for stock_id, factor_score in candidates:
        df = get_stock_data(stock_id, days=120)  # 自訂函數
        if df is not None:
            stocks_data[stock_id] = df
    
    # Step 3: 形態學過濾
    detector = PatternDetector()
    filtered = detector.filter_stocks(
        stocks_data,
        min_patterns=1,
        min_score=0.5,
        lookback_days=5
    )
    
    print(f"形態學過濾後剩 {len(filtered)} 支")
    
    # Step 4: 選出 final_n 支
    final_stocks = filtered[:final_n]
    
    # Step 5: 計算倉位權重
    from src.morphology import calculate_position_weight
    
    positions = []
    for stock_id, pattern_score, patterns in final_stocks:
        base_weight = 1.0 / final_n  # 等權重
        adjusted_weight = calculate_position_weight(
            base_weight, pattern_score, max_boost=1.2
        )
        positions.append((stock_id, adjusted_weight, pattern_score))
    
    # 歸一化權重
    total_weight = sum(w for _, w, _ in positions)
    positions = [(s, w/total_weight, p) for s, w, p in positions]
    
    return positions

# 執行
positions = integrated_selection_v21('2024-06-30', top_n=30, final_n=10)
for stock_id, weight, score in positions:
    print(f"{stock_id}: {weight:.2%} (形態評分 {score:.3f})")
```

---

## 5. 參數調優

### 5.1. 形態靈敏度調整

**場景 1: 嚴格模式（減少假訊號）**

```python
detector = PatternDetector()

# 破底翻：更嚴格
signal, details = detect_bottom_reversal(
    df,
    window=20,
    recovery_days=3,      # 縮短到 3 天（更快收復）
    volume_ratio=2.0,     # 提高到 2 倍（更大量）
    recovery_threshold=1.03  # 提高到 +3%
)
```

**場景 2: 寬鬆模式（增加機會）**

```python
# 破底翻：更寬鬆
signal, details = detect_bottom_reversal(
    df,
    window=20,
    recovery_days=7,      # 延長到 7 天
    volume_ratio=1.2,     # 降低到 1.2 倍
    recovery_threshold=1.01  # 降低到 +1%
)
```

### 5.2. 權重優化

**根據回測結果調整權重**：

```python
# 假設破底翻勝率最高，提高權重
detector = PatternDetector(
    custom_weights={
        'bottom_reversal': 0.40,      # 原 0.30
        'w_bottom': 0.25,              # 原 0.30
        'neckline_breakout': 0.25,   # 原 0.25
        'volume_surge': 0.10          # 不變
    }
)
```

### 5.3. 最低評分閾值

```python
# 嚴格篩選：只要評分 > 0.7 的
recent = detector.get_latest_patterns(
    df,
    lookback_days=5,
    min_score=0.7  # 提高閾值
)
```

---

## 6. 常見問題

### Q1: 為什麼有時候沒有偵測到形態？

**A**: 可能原因：
1. 數據不足（需至少 60-120 日數據）
2. 參數設定太嚴格
3. 該股票確實沒有明顯形態

**解決方案**:
```python
# 檢查數據長度
print(f"數據長度: {len(df)} 天")

# 降低門檻
signal, details = detect_bottom_reversal(
    df,
    volume_ratio=1.2,  # 降低成交量要求
    recovery_threshold=1.01  # 降低收復幅度
)
```

---

### Q2: 形態評分如何解讀？

**A**: 評分範圍 0-1：
- **0.8-1.0**: 優秀（A），強烈進場訊號
- **0.6-0.8**: 良好（B），可進場
- **0.4-0.6**: 普通（C），謹慎觀察
- **0.2-0.4**: 不佳（D），不建議
- **0.0-0.2**: 極差（F），避開

---

### Q3: 可以同時偵測多種形態嗎？

**A**: 可以，且應該這樣做！

```python
# 同時出現多種形態，評分更高
recent = detector.get_latest_patterns(df, lookback_days=5)

if len(recent) >= 2:
    print("✓ 多重形態確認，可信度高！")
```

---

### Q4: 如何處理假突破？

**A**: 使用確認機制：

```python
from src.morphology import detect_neckline_breakout, detect_false_breakout

signal, details = detect_neckline_breakout(
    df,
    confirmation_days=3  # 連續 3 日站穩才確認
)

# 事後檢查假突破
if not details.empty:
    breakout_idx = df.index.get_loc(details.index[-1])
    is_false = detect_false_breakout(df, breakout_idx, details.iloc[-1]['neckline'])
    
    if is_false:
        print("⚠️ 假突破，不進場！")
```

---

### Q5: 形態學能否用於出場判斷？

**A**: 絕對可以！這是重點：

```python
from src.morphology import check_pattern_breakdown

# 假設已持有 2330，進場價 600，支撐線 580
current_price = 570
is_broken, reason = check_pattern_breakdown(
    current_price=570,
    support_line=580,
    entry_price=600,
    recent_closes=df['close'].tail(3),
    recent_volumes=df['volume'].tail(3)
)

if is_broken:
    print(f"⚠️ 形態破壞：{reason}，立即出場！")
```

---

### Q6: 如何與 FinMind 數據整合？

**A**: 參考 PRD v2.1 的數據結構設計，將形態特徵存入 PostgreSQL：

```sql
ALTER TABLE daily_market_data
ADD COLUMN is_bottom_reversal BOOLEAN DEFAULT FALSE,
ADD COLUMN is_w_bottom BOOLEAN DEFAULT FALSE,
ADD COLUMN pattern_score NUMERIC(3, 2);
```

```python
# 每日計算形態並存儲
def daily_pattern_calculation():
    detector = PatternDetector()
    
    for stock_id in get_all_stocks():
        df = get_stock_data(stock_id, days=120)
        results = detector.detect_all(df)
        
        # 更新資料庫
        for pattern, data in results.items():
            if data['detected']:
                update_database(stock_id, pattern, data)
```

---

## 附錄 A: 完整範例腳本

**scripts/example_morphology_analysis.py**:

```python
#!/usr/bin/env python3
"""
形態學分析完整範例
"""

import pandas as pd
from pymongo import MongoClient
from src.morphology import PatternDetector, generate_pattern_report

def main():
    # 連接資料庫
    client = MongoClient('mongodb://localhost:27017/')
    db = client['tw_stock_analysis']
    
    # 分析台積電
    stock_id = "2330"
    
    # 讀取 120 天數據
    data = list(db.stock_price.find(
        {'stock_id': stock_id},
        {'_id': 0, 'date': 1, 'open': 1, 'high': 1, 'low': 1, 'close': 1, 'volume': 1}
    ).sort('date', -1).limit(120))
    
    df = pd.DataFrame(data)
    df['date'] = pd.to_datetime(df['date'])
    df.set_index('date', inplace=True)
    df = df.sort_index()
    
    # 初始化偵測器
    detector = PatternDetector()
    
    # 執行偵測
    results = detector.detect_all(df, stock_id=stock_id)
    
    # 生成報告
    print(detector.generate_summary(df, stock_id=stock_id))
    
    # 獲取最近 5 天形態
    recent = detector.get_latest_patterns(df, lookback_days=5, min_score=0.5)
    
    if recent:
        print("\n✓ 發現以下形態（近 5 天）：")
        for pattern, data in recent.items():
            print(f"  - {pattern}: 評分 {data['score']:.3f}")
    else:
        print("\n✗ 近 5 天未發現符合條件的形態")

if __name__ == "__main__":
    main()
```

---

**結束** | 有任何問題請參考 [PRD v2.1](PRD_v2.1_FinMind_Morphology.md)
