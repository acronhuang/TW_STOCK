# 📐 頸線抓取技術指南

## 目錄
1. [什麼是頸線？](#什麼是頸線)
2. [各型態的頸線定義](#各型態的頸線定義)
3. [程式實作方式](#程式實作方式)
4. [實戰案例](#實戰案例)

---

## 什麼是頸線？

**頸線（Neckline）** 是技術分析中的關鍵支撐/壓力線，主要用於：
- 確認型態完成
- 設定進場點
- 計算目標價
- 設定停損點

---

## 各型態的頸線定義

### 1️⃣ W底（Double Bottom）
```
價格
 ↑
 │     ╱╲            ╱╲
 │    ╱  ╲          ╱  ╲
 │   ╱    ╲  頸線  ╱    ╲
 │  ╱      ========       ╲
 │ ╱底1          底2       ╲
 └──────────────────────────→ 時間
```

**頸線抓取方式**：
- **定義**：兩個低點之間的反彈高點連線
- **計算**：取兩個底部之間的最高價（high.max()）
- **確認**：股價突破頸線才確認型態

```python
# 程式碼實作
# 找到兩個底部
bottom1 = low[bottom1_idx]
bottom2 = low[bottom2_idx]

# 計算頸線（兩底之間的高點）
neckline_segment = high[bottom1_idx:bottom2_idx]
neckline = neckline_segment.max()

# 突破確認
if current_price > neckline * 0.98:  # 突破頸線（允許2%誤差）
    confirmed = True
```

---

### 2️⃣ M頭（Double Top）
```
價格
 ↑  頂1           頂2
 │   ╲╱            ╲╱
 │    ╲            ╱
 │     ========頸線=======
 │      ╲        ╱
 │       ╲      ╱
 └──────────────────────────→ 時間
```

**頸線抓取方式**：
- **定義**：兩個高點之間的回檔低點連線
- **計算**：取兩個頂部之間的最低價（low.min()）
- **確認**：股價跌破頸線才確認型態

```python
# 程式碼實作
# 找到兩個頭部
top1 = high[top1_idx]
top2 = high[top2_idx]

# 計算頸線（兩頭之間的低點）
neckline_segment = low[top1_idx:top2_idx]
neckline = neckline_segment.min()

# 跌破確認
if current_price < neckline * 1.02:  # 跌破頸線（允許2%誤差）
    confirmed = True
```

---

### 3️⃣ 頭肩底（Head and Shoulders Bottom）
```
價格
 ↑
 │  肩1    頸線(高點連線)    肩2
 │   ╲    ===============    ╱
 │    ╲  ╱              ╲  ╱
 │     ╲╱                ╲╱
 │     底     頭部(最低)   底
 └──────────────────────────→ 時間
```

**頸線抓取方式**：
- **定義**：左肩與右肩之間的高點連線
- **計算**：取左肩到右肩之間的最高價
- **關鍵**：頸線是「阻力線」，突破後轉為支撐

```python
# 程式碼實作
# 找到三個低點
left_shoulder = segment[lows_idx[0]]
head = segment[lows_idx[1]]           # 最低點
right_shoulder = segment[lows_idx[2]]

# 計算頸線（左肩到右肩之間的高點連線）
neckline_segment = high[lows_idx[0]:lows_idx[2]]
neckline = neckline_segment.max()

# 特徵驗證
assert head < left_shoulder  # 頭部最低
assert head < right_shoulder
assert abs(left_shoulder - right_shoulder) / left_shoulder < 0.05  # 兩肩高度接近

# 突破確認
if current_price > neckline * 0.98:
    confirmed = True
```

**目標價計算**：
```python
height = neckline - head  # 頭部到頸線的距離
target1 = neckline + height
target2 = target1 + height
```

---

### 4️⃣ 頭肩頂（Head and Shoulders Top）
```
價格
 ↑      頭部(最高)
 │       ╱╲
 │  肩1  ╱  ╲  肩2
 │   ╲╱      ╲╱
 │    頂      頂
 │  ===============頸線(低點連線)
 └──────────────────────────→ 時間
```

**頸線抓取方式**：
- **定義**：左肩與右肩之間的低點連線
- **計算**：取左肩到右肩之間的最低價
- **關鍵**：頸線是「支撐線」，跌破後轉為壓力

```python
# 程式碼實作
# 找到三個高點
left_shoulder = segment[highs_idx[0]]
head = segment[highs_idx[1]]          # 最高點
right_shoulder = segment[highs_idx[2]]

# 計算頸線（左肩到右肩之間的低點連線）
neckline_segment = low[highs_idx[0]:highs_idx[2]]
neckline = neckline_segment.min()

# 特徵驗證
assert head > left_shoulder  # 頭部最高
assert head > right_shoulder
assert abs(left_shoulder - right_shoulder) / left_shoulder < 0.05  # 兩肩高度接近

# 跌破確認
if current_price < neckline * 1.02:
    confirmed = True
```

**目標價計算**：
```python
height = head - neckline  # 頭部到頸線的距離
target1 = neckline - height
target2 = target1 - height
```

---

### 5️⃣ 破底翻/破頂翻

**破底翻（Bottom Reversal）**：
```
價格
 ↑        突破
 │         ╱
 │  頸線 ══╱══ ← 前低點
 │       ╱
 │      ╱ ← 假跌破後反轉
 │     V
 └──────────────────────────→ 時間
```

**頸線**：前一個重要低點的價位

```python
# 找到前低點
prev_lows = []
for j in range(max(0, i-20), i):
    if low[j] == low[max(0, j-3):min(len(low), j+4)].min():
        prev_lows.append(low[j])

neckline = min(prev_lows) if prev_lows else low[i-20:i].min()

# 突破確認
if current_price > neckline * 1.02:  # 站上前低
    confirmed = True
```

---

### 6️⃣ 假突破

```
價格
 ↑     假突破
 │       ╱╲ ← 突破後快速回落
 │      ╱  ╲
 │  ═══╱════╲═══ 頸線（整理區上緣）
 │    │整理區│
 │  ═══════════ 支撐
 └──────────────────────────→ 時間
```

**頸線抓取方式**：
- **定義**：整理區的上緣（80%分位）
- **計算**：使用 percentile 方法

```python
# 確定整理區域
resistance = high[i-window:i].max()  # 絕對高點
neckline = np.percentile(high[i-window:i], 80)  # 80%分位線

# 檢查假突破
if high[breakout_idx] > resistance * 1.02:  # 突破
    if close[k] < neckline:  # 快速回落跌破頸線
        confirmed = True
```

---

### 7️⃣ 旗形整理（上飄/下飄旗形）

**下飄旗形（Bullish Flag）**：
```
價格
 ↑
 │      突破 ↗
 │     ╱╱╱╱  ← 旗桿頂端
 │    ╱    ╲  頸線
 │   ╱旗桿  ╲  ↘ 旗面（下飄整理）
 │  ╱       ╲╲
 │ ╱
 └──────────────────────────→ 時間
```

**頸線**：旗形整理的上緣趨勢線

```python
# 計算旗形上緣（頸線）
flag_highs = high[flag_start:flag_end]
x = np.arange(len(flag_highs))
upper_line = np.polyfit(x, flag_highs, 1)[0] * len(flag_highs) + \
             np.polyfit(x, flag_highs, 1)[1]

neckline = upper_line

# 突破確認
if current_price > neckline * 1.02:
    confirmed = True
```

---

### 8️⃣ 收斂三角形

```
價格
 ↑     
 │  ╲          ╱  ← 高點下降趨勢線
 │   ╲  頸線  ╱
 │    ╲══════╱ ← 收斂突破點
 │     ╲    ╱
 │      ╲  ╱  ← 低點上升趨勢線
 └──────────────────────────→ 時間
```

**頸線**：收斂三角形的上邊線（突破位置）

```python
# 計算收斂三角形的上邊線
highs = []
for i in range(len(df) - lookback, len(df), 5):
    highs.append(high[i:min(i+5, len(df))].max())

# 頸線 = 最後的高點趨勢線
upper_line = highs[-1]
neckline = upper_line

# 突破確認
if current_price > neckline * 0.98:
    confirmed = True
```

---

## 程式實作重點

### 💡 頸線計算的共通原則

1. **多頭型態（買入）**：
   - 頸線是「阻力線」
   - 突破頸線 = 確認信號
   - 頸線 = 兩個低點之間的高點

2. **空頭型態（賣出）**：
   - 頸線是「支撐線」
   - 跌破頸線 = 確認信號
   - 頸線 = 兩個高點之間的低點

3. **容錯機制**：
   ```python
   # 多頭突破：允許2%誤差
   if current_price > neckline * 0.98:
       confirmed = True
   
   # 空頭跌破：允許2%誤差
   if current_price < neckline * 1.02:
       confirmed = True
   ```

4. **目標價計算**：
   ```python
   # 測量高度（頂到頸線或底到頸線）
   height = abs(extreme_point - neckline)
   
   # 多頭目標
   target1 = neckline + height
   target2 = target1 + height
   
   # 空頭目標
   target1 = neckline - height
   target2 = target1 - height
   ```

---

## 實戰案例

### 案例1：台積電（2330）W底頸線

```python
# 實際資料（簡化）
dates = ['2026-01-10', '2026-01-15', '2026-01-20', '2026-01-25', '2026-02-01']
low =   [1850,         1840,         1870,         1845,         1880]
high =  [1890,         1900,         1920,         1895,         1935]

# 找兩個底部
bottom1_idx = 1  # 1840
bottom2_idx = 3  # 1845

# 計算頸線（兩底之間的高點）
neckline = max(high[1:4])  # = 1920

# 當前價 1935 > 1920
# ✅ 確認突破，W底成立

# 計算目標價
height = neckline - min(low[1], low[3])  # 1920 - 1840 = 80
target1 = neckline + height  # 1920 + 80 = 2000
```

### 案例2：聯電（2303）頭肩頂頸線

```python
# 實際資料
dates = ['2026-01-05', '2026-01-12', '2026-01-19', '2026-01-26', '2026-02-02']
high =  [55.0,         58.0,         56.0,         54.0,         52.0]
low =   [52.0,         54.0,         52.5,         51.0,         49.0]

# 找三個高點
left_shoulder = 55.0   # 左肩
head = 58.0            # 頭部（最高）
right_shoulder = 56.0  # 右肩

# 計算頸線（左肩到右肩之間的低點）
neckline = min(low[0:3])  # = 52.0

# 當前價 49.0 < 52.0
# ✅ 確認跌破，頭肩頂成立

# 計算目標價
height = head - neckline  # 58 - 52 = 6
target1 = neckline - height  # 52 - 6 = 46
```

---

## 視覺化範例

您可以使用以下腳本查看頸線：

```bash
# 查看單一股票的型態與頸線
python3 pattern_recognition/test_single_stock.py --symbol 2330

# 生成帶有頸線標記的圖表
python3 scripts/chart_with_patterns.py --symbol 2330 --show-neckline
```

---

## 總結

### ✅ 頸線抓取檢查清單

- [ ] 確認型態類型（多頭/空頭）
- [ ] 找到關鍵點位（頭、肩、底）
- [ ] 計算頸線位置
- [ ] 驗證突破/跌破（2%容錯）
- [ ] 計算目標價（高度投射）
- [ ] 設定停損點（頸線±7%）

### 📊 頸線的重要性

1. **進場依據**：突破/跌破頸線才確認型態
2. **目標價計算**：測量高度 = 極值到頸線距離
3. **停損設定**：頸線是關鍵支撐/壓力
4. **風險管理**：計算風險報酬比的基準

---

## 參考資料

- 程式碼：`pattern_recognition/patterns_12_masters.py`
- 測試腳本：`pattern_recognition/test_single_stock.py`
- 掃描工具：`pattern_recognition/quick_scan.py`

---

**最後更新**：2026-02-14  
**版本**：v1.0  
**作者**：形態學12神招系統
