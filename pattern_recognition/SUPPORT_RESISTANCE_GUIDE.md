# 支撐壓力與頸線識別系統 - 完整指南

**版本**: v2.2
**更新日期**: 2026-02-24
**新增功能**: 精確的支撐壓力與頸線量化識別

---

## 🎯 系統概述

基於蔡森形態學理論，我們實作了精確的量化邏輯來識別：

1. **轉折點識別** - ZigZag演算法過濾隨機波動
2. **水平頸線** - W底/M頭的關鍵轉折線
3. **趨勢切線** - 破切分析（多方/空方）
4. **支撐壓力** - 強度評估與觸碰次數統計
5. **突破偵測** - 量價配合的有效突破

---

## 📐 理論基礎

### 1. 量化定義對照表

| 元素 | 蔡森定義（感性） | 程式邏輯（理性） |
|------|---------------|---------------|
| **支撐線** | 股價跌不下去的點連線 | 連結兩個以上局部最低點，斜率≈0 |
| **壓力線** | 股價漲不動的點連線 | 連結兩個以上局部最高點，斜率≈0 |
| **下降切線** | 連結高點的斜線 | 連結H1, H2，且H2<H1（負斜率） |
| **頸線** | 型態完成的關鍵轉折水平線 | W底：兩底間最高點；M頭：兩頂間最低點 |

### 2. 轉折點識別邏輯

**方法1: argrelextrema**
- 參數：order=5（左右各5根K線）
- 優點：快速、簡單
- 缺點：可能包含小波動

**方法2: ZigZag演算法**
- 參數：min_change_pct=0.05（5%最小波動）
- 優點：過濾隨機噪音，只保留顯著轉折
- 缺點：較慢

### 3. 突破判定標準

**有效突破條件**:
1. **實體突破**: 收盤價必須 > 頸線 × 1.005（0.5%以上）
2. **量能背書**: 突破日成交量 > 前5日平均 × 1.5

---

## 🚀 快速使用

### 基礎測試

```bash
# 測試所有功能（台積電）
python3 pattern_recognition/test_support_resistance.py --symbol 2330 --all

# 僅測試轉折點識別
python3 pattern_recognition/test_support_resistance.py --symbol 2330 --pivots

# 僅測試頸線識別
python3 pattern_recognition/test_support_resistance.py --symbol 2330 --necklines

# 僅測試趨勢線（破切分析）
python3 pattern_recognition/test_support_resistance.py --symbol 2330 --trendlines

# 僅測試支撐壓力
python3 pattern_recognition/test_support_resistance.py --symbol 2330 --sr
```

### Python API 使用

```python
from pattern_recognition.support_resistance import (
    PivotIdentifier,
    NecklineDetector,
    TrendlineDetector,
    SupportResistanceDetector
)

# 1. 轉折點識別
identifier = PivotIdentifier(order=5, threshold=0.02)
highs, lows = identifier.find_pivots(df)

# 或使用ZigZag
zigzag_pivots = identifier.find_zigzag_pivots(df, min_change_pct=0.05)

# 2. 頸線識別
detector = NecklineDetector(tolerance=0.03)
all_pivots = highs + lows
all_pivots.sort(key=lambda x: x.index)

# W底頸線
w_necklines = detector.detect_w_bottom_neckline(df, all_pivots)

# M頭頸線
m_necklines = detector.detect_m_top_neckline(df, all_pivots)

# 3. 趨勢線識別
trendline_detector = TrendlineDetector(min_points=2)

# 下降趨勢線（多方破切機會）
desc_lines = trendline_detector.detect_descending_trendline(df, all_pivots)

# 上升趨勢線（空方破切風險）
asc_lines = trendline_detector.detect_ascending_trendline(df, all_pivots)

# 4. 支撐壓力識別
sr_detector = SupportResistanceDetector(tolerance=0.01, min_touches=2)
levels = sr_detector.detect_levels(df, all_pivots, lookback=100)
```

---

## 📊 輸出範例

### 1. 轉折點識別

```
方法1: argrelextrema
  找到 4 個高點
  找到 5 個低點

  最近5個高點:
    2026-01-29 │ $1835.00
    2025-12-11 │ $1515.00
    2025-08-13 │ $1200.00
    2025-07-03 │ $1105.00

  最近5個低點:
    2026-02-06 │ $1740.00
    2025-12-18 │ $1415.00
    2025-11-24 │ $1375.00
    2025-10-23 │ $1435.00
    2025-06-23 │ $1015.00

方法2: ZigZag (5%波動)
  找到 1 個顯著轉折點

  最近10個轉折點:
    🔺 2025-06-20 │ $1055.00
```

### 2. 頸線識別

```
W底頸線:
  找到 1 個W底頸線

  1. 頸線價格: $1515.00 │ ✅ 已突破
     左底索引: 107 │ 中峰索引: 120 │ 右底索引: 125
     突破日期: 2025-12-29
```

### 3. 趨勢線識別

```
上升趨勢線（空方破切風險）:
  找到 2 條上升趨勢線

  1. 斜率: 2.2222 │ 截距: 1137.22 │ ⏳ 未跌破
     起始: 2025-11-24 → 2025-12-18
     當前價格: $1915.00 │ 趨勢線價格: $1499.44 │ 距離: +27.71%
```

### 4. 支撐壓力

```
當前價格: $1915.00

壓力位 (Resistance) - 共 3 個:
  1. $1950.00 │ 🔥 強度: 4 │ ⏳ 未突破 │ 距離: +1.8%
  2. $1920.00 │ ✅ 強度: 2 │ ⏳ 未突破 │ 距離: +0.3%
  3. $1880.00 │ ✅ 強度: 2 │ ✅ 已突破 │ 距離: -1.8%

支撐位 (Support) - 共 4 個:
  1. $1850.00 │ 🔥 強度: 3 │ ⏳ 未跌破 │ 距離: +3.5%
  2. $1780.00 │ ✅ 強度: 2 │ ⏳ 未跌破 │ 距離: +7.6%
  3. $1740.00 │ ✅ 強度: 2 │ ⏳ 未跌破 │ 距離: +10.1%
  4. $1650.00 │ 🔥 強度: 4 │ ⏳ 未跌破 │ 距離: +16.1%
```

---

## ⚙️ 參數調校指南

### 1. PivotIdentifier (轉折點識別)

```python
PivotIdentifier(
    order=5,           # 局部極值窗口（5=左右各5根K線）
    threshold=0.02     # 價格變動閾值（2%）
)
```

**建議設定**:
- 日線: order=5, threshold=0.02
- 週線: order=3, threshold=0.03
- 月線: order=2, threshold=0.05

### 2. NecklineDetector (頸線識別)

```python
NecklineDetector(
    tolerance=0.03     # 兩底/頂價格容忍度（3%）
)
```

**建議設定**:
- 嚴格: tolerance=0.02
- 標準: tolerance=0.03
- 寬鬆: tolerance=0.05

### 3. TrendlineDetector (趨勢線)

```python
TrendlineDetector(
    min_points=2       # 最少需要的點數
)
```

**建議設定**:
- 快速識別: min_points=2
- 穩健識別: min_points=3

### 4. SupportResistanceDetector (支撐壓力)

```python
SupportResistanceDetector(
    tolerance=0.01,    # 價格聚類容忍度（1%）
    min_touches=2      # 最少觸碰次數
)
```

**建議設定**:
- 精確: tolerance=0.01, min_touches=3
- 標準: tolerance=0.01, min_touches=2
- 寬鬆: tolerance=0.02, min_touches=2

---

## 💡 實戰應用

### 案例1: W底突破進場

```python
# 1. 找轉折點
identifier = PivotIdentifier()
highs, lows = identifier.find_pivots(df)

# 2. 識別W底頸線
detector = NecklineDetector()
w_necklines = detector.detect_w_bottom_neckline(df, highs + lows)

# 3. 找已突破且量能確認的頸線
for neck in w_necklines:
    if neck.is_broken and neck.breakout_volume_confirmed:
        print(f"✅ 進場機會！")
        print(f"   頸線: ${neck.price:.2f}")
        print(f"   突破日期: {neck.breakout_date}")

        # 計算目標價（1:1測幅）
        height = neck.price - df.iloc[neck.left_pivot]['low']
        target_1 = neck.price + height
        print(f"   目標價: ${target_1:.2f}")
```

### 案例2: 破切交易

```python
# 1. 識別下降趨勢線
trendline_detector = TrendlineDetector()
desc_lines = trendline_detector.detect_descending_trendline(df, all_pivots)

# 2. 找剛突破的趨勢線
for line in desc_lines:
    if line.is_broken:
        # 計算最近突破（檢查最近3根K線）
        current_idx = len(df) - 1

        for i in range(max(0, current_idx-3), current_idx+1):
            price_at_i = df.iloc[i]['close']
            trendline_price = line.slope * i + line.intercept

            if price_at_i > trendline_price:
                print(f"🔥 破切機會！")
                print(f"   突破點: 第 {i} 根K線")
                print(f"   突破價格: ${price_at_i:.2f}")
                break
```

### 案例3: 支撐壓力分析

```python
# 1. 識別支撐壓力
sr_detector = SupportResistanceDetector()
levels = sr_detector.detect_levels(df, all_pivots)

# 2. 找當前價格附近的關鍵水平
current_price = df.iloc[-1]['close']

# 最近的壓力
resistances = [l for l in levels if l.type == 'resistance' and l.price > current_price]
resistances.sort(key=lambda x: x.price)

if resistances:
    nearest_resistance = resistances[0]
    distance_pct = ((nearest_resistance.price - current_price) / current_price) * 100

    print(f"最近壓力: ${nearest_resistance.price:.2f}")
    print(f"距離: {distance_pct:.1f}%")
    print(f"強度: {nearest_resistance.strength}")

# 最近的支撐
supports = [l for l in levels if l.type == 'support' and l.price < current_price]
supports.sort(key=lambda x: x.price, reverse=True)

if supports:
    nearest_support = supports[0]
    distance_pct = ((current_price - nearest_support.price) / nearest_support.price) * 100

    print(f"最近支撐: ${nearest_support.price:.2f}")
    print(f"距離: {distance_pct:.1f}%")
    print(f"強度: {nearest_support.strength}")
```

---

## 🔄 整合到現有系統

### ✅ 已整合到多時間週期掃描器

**版本**: v2.0.0 起，支撐壓力與頸線識別模組已完整整合到 `multi_timeframe_scanner.py`。

**整合功能**:
1. **自動驗證形態信號** - 掃描時自動執行頸線驗證
2. **信心度提升** - W底/M頭匹配時提高信心度 +5%
3. **量能確認加成** - 突破且量能確認再 +3%
4. **支撐壓力資訊** - 日誌顯示檢測到的支撐壓力數量

**使用方式**:
```bash
# 直接使用 multi_timeframe_scanner.py 即可自動享有雙重驗證
python3 pattern_recognition/multi_timeframe_scanner.py --symbol 2330 --timeframes D W M --show-suggestion
```

**輸出範例**:
```
2026-02-24 18:52:56,608 - INFO - 找到 9 個高點, 11 個低點
2026-02-24 18:52:56,609 - INFO - 找到 1 個W底頸線
2026-02-24 18:52:56,609 - INFO - 找到 0 個M頭頸線
2026-02-24 18:52:56,609 - INFO - 找到 1 個支撐壓力水平
2026-02-24 18:52:56,609 - INFO - 時間週期 D: 找到 10 個形態信號 (頸線驗證: 1, 支撐: 1, 壓力: 0)
```

---

### 手動整合範例（高級用戶）

如果您想在自己的程式碼中手動整合，可以參考以下範例：

```python
from pattern_recognition.patterns_12_masters import Pattern12Masters
from pattern_recognition.support_resistance import (
    PivotIdentifier,
    NecklineDetector
)

# 1. 先用12神招找形態
pattern_detector = Pattern12Masters()
signals = pattern_detector.scan_all_patterns(df, symbol)

# 2. 用頸線模組驗證
identifier = PivotIdentifier()
highs, lows = identifier.find_pivots(df)

neckline_detector = NecklineDetector()
w_necklines = neckline_detector.detect_w_bottom_neckline(df, highs + lows)

# 3. 雙重確認
for signal in signals:
    if signal.pattern_name == 'W底':
        # 檢查是否有對應的頸線確認
        for neck in w_necklines:
            if abs(neck.price - signal.neckline) / signal.neckline < 0.02:
                print(f"✅ 雙重確認: W底 + 頸線驗證")
                signal.confidence += 0.05  # 提高信心度
```

---

## 📚 數據結構說明

### PivotPoint (轉折點)

```python
@dataclass
class PivotPoint:
    index: int          # 在DataFrame中的索引
    date: datetime      # 日期
    price: float        # 價格
    type: str          # 'high' or 'low'
    strength: int = 0   # 強度（觸碰次數）
```

### Neckline (頸線)

```python
@dataclass
class Neckline:
    price: float                    # 頸線價格
    type: str                       # 'W_bottom' or 'M_top'
    left_pivot: int                 # 左側轉折點索引
    middle_pivot: int               # 中間轉折點索引
    right_pivot: int                # 右側轉折點索引
    is_broken: bool = False         # 是否已突破
    breakout_date: Optional[datetime] = None
    breakout_volume_confirmed: bool = False
```

### Trendline (趨勢線)

```python
@dataclass
class Trendline:
    slope: float        # 斜率
    intercept: float    # 截距
    type: str          # 'ascending' or 'descending'
    points: List[int]  # 用於擬合的點索引
    start_date: datetime
    end_date: datetime
    is_broken: bool = False
```

### SupportResistance (支撐壓力)

```python
@dataclass
class SupportResistance:
    price: float           # 價格水平
    type: str             # 'support' or 'resistance'
    strength: int         # 強度（觸碰次數）
    touches: List[int]    # 觸碰點的索引列表
    first_date: datetime  # 首次出現日期
    last_date: datetime   # 最後觸碰日期
    is_broken: bool = False
```

---

## ⚠️ 注意事項

1. **數據量要求**
   - 至少需要60根K線
   - 建議使用100-250根K線以獲得更準確的結果

2. **參數調整**
   - 不同股票波動特性不同，需要調整參數
   - 大型權值股建議threshold=0.02
   - 小型股建議threshold=0.03-0.05

3. **突破確認**
   - 突破需要量能配合，否則可能是假突破
   - 建議觀察3-5根K線確認不回破

4. **多時間週期驗證**
   - 日線突破最好有週線確認
   - 週線突破可信度更高

---

## 🔮 未來功能

- [ ] 可視化圖表（在K線上繪製頸線、趨勢線）
- [ ] 自動交易信號（整合到全市場掃描）
- [ ] 回測系統（驗證突破策略績效）
- [ ] 多週期驗證（日線+週線雙重確認）

---

**版本**: v2.2
**最後更新**: 2026-02-24
**維護者**: Ming

**祝您使用新功能愉快！📊📈**
