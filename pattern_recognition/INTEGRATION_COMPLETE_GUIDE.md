# 🎯 多時間週期分析系統 - 完整整合指南

## ✅ 整合完成摘要

**日期**: 2026-02-14  
**版本**: 2.0.0 - 完整整合版  
**狀態**: ✅ 生產就緒

---

## 📋 更新內容

### 1. 新增時間週期支援 ⏰

現在支援 **8 種時間週期**：

| 代碼 | 名稱 | 最小週期 | 建議資料天數 | 適用場景 |
|------|------|---------|------------|---------|
| D | 日線 | 60 | 120 | 短線操作 |
| W | 週線 | 20 | 500 | 波段交易 |
| M | 月線 | 20 | 1200 | 中期投資 |
| Q | 季線 | 12 | 2500 | 季度佈局 |
| 6M | 半年線 | 6 | 3600 | 半年趨勢 |
| Y | 年線 | 3 | 2500 | 年度規劃 |
| **5Y** | **5年線** | **5** | **12500** | **長期趨勢** |
| **10Y** | **10年線** | **10** | **25000** | **超長期趨勢** |

### 2. 核心檔案 📁

#### 新增檔案

```
pattern_recognition/
├── integrated_multi_timeframe.py  # 整合式多時間週期掃描器 (NEW)
└── pattern_cli.py                 # 已整合多時間週期命令 (UPDATED)
```

#### 核心功能類別

```python
# TimeframeManager - 時間週期管理器
TimeframeManager.get_config('5Y')    # 取得5年線配置
TimeframeManager.get_all_codes()     # 取得所有時間週期代碼

# TimeframeConverter - 時間週期轉換器
converter.convert_to_timeframe(df, '5Y')  # 轉換為5年線

# IntegratedMultiTimeframeScanner - 整合式掃描器
scanner.scan_multi_timeframe('2330', ['D', 'W', 'M', '5Y', '10Y'])
```

---

## 🚀 使用指南

### 基礎用法

#### 1. 列出所有支援的時間週期

```bash
# 方法1: 使用獨立模組
python3 pattern_recognition/integrated_multi_timeframe.py --list-timeframes

# 方法2: 使用CLI（整合版）
python3 pattern_recognition/pattern_cli.py multi --list-timeframes
```

**輸出**:
```
支援的時間週期:
============================================================
D     - 日線       (最小週期: 60, 建議資料:   120 天)
W     - 週線       (最小週期: 20, 建議資料:   500 天)
M     - 月線       (最小週期: 20, 建議資料:  1200 天)
Q     - 季線       (最小週期: 12, 建議資料:  2500 天)
6M    - 半年線      (最小週期:  6, 建議資料:  3600 天)
Y     - 年線       (最小週期:  3, 建議資料:  2500 天)
5Y    - 5年線      (最小週期:  5, 建議資料: 12500 天)
10Y   - 10年線     (最小週期: 10, 建議資料: 25000 天)
============================================================
```

#### 2. 分析單一股票（日線+週線+月線）

```bash
# 使用CLI（推薦）
python3 pattern_recognition/pattern_cli.py multi 2330 -t D W M

# 使用獨立模組
python3 pattern_recognition/integrated_multi_timeframe.py -s 2330 -t D W M
```

#### 3. 完整時間週期分析（包含5年線和10年線）

```bash
python3 pattern_recognition/pattern_cli.py multi 2330 -t D W M Q Y 5Y 10Y
```

**注意**: 5年線和10年線需要更長的歷史資料：
- **5年線**: 至少需要 **25 年** 的資料（5個週期 × 5年）
- **10年線**: 至少需要 **50 年** 的資料（10個週期 × 10年）

### 進階用法

#### 1. 波段交易者組合（推薦）

```bash
# 日線找進場點，週線確認趨勢，月線看大方向
python3 pattern_recognition/pattern_cli.py multi 2330 -t D W M
```

#### 2. 長期投資者組合

```bash
# 月線+季線+年線+5年線
python3 pattern_recognition/pattern_cli.py multi 2330 -t M Q Y 5Y
```

#### 3. 超長期趨勢分析

```bash
# 年線+5年線+10年線（需要50年以上資料）
python3 pattern_recognition/pattern_cli.py multi 2330 -t Y 5Y 10Y
```

---

## 📊 輸出報告解讀

### 報告結構

```
================================================================================
📊 多時間週期分析報告 - 2330
================================================================================
掃描時間: 2026-02-14 20:23:37
檢測形態總數: 4

【日線】
  ✅ 週期數: 158
  💰 最新價格: 1915.00 (2026-02-14)
  📈 均線位置: 強勢多頭
  📊 趨勢方向: 上升 (+2.61/期)
  🎯 檢測到 3 個形態:
     1. W底 📈 多頭
        目標1: 1857.50, 目標2: 1935.00
        信心度: 85%
     2. 假突破 📉 空頭
        目標1: 1715.00
        信心度: 79%
     3. 頭肩底 📈 多頭
        目標1: 1990.00, 目標2: 2145.00
        信心度: 86%

【5年線】
  ❌ 資料不足（需要5個週期，僅有3個）

================================================================================
🔄 多時間週期共振分析
================================================================================
共振強度: 50%
信號方向: 分歧
共振等級: 信號分歧
多頭信號: 2/4 (50%)
空頭信號: 2/4 (50%)

💡 操作建議: 觀望
================================================================================
```

### 關鍵指標說明

#### 1. 均線位置
- **強勢多頭**: 收盤價 > MA5 > MA10 > MA20 > MA60
- **多頭**: 收盤價 > MA5 > MA10 > MA20
- **盤整**: 均線糾結
- **空頭**: MA5 < MA10 < MA20 < 收盤價
- **強勢空頭**: MA60 < MA20 < MA10 < MA5 < 收盤價

#### 2. 趨勢方向
- **上升 (+2.61/期)**: MA20每週期平均上漲2.61元
- **下降 (-1.23/期)**: MA20每週期平均下跌1.23元
- **盤整**: MA20走平

#### 3. 共振強度
- **≥ 80%**: 🔥 **強勢共振** → 正常倉位
- **≥ 60%**: ✅ **一般共振** → 減半倉位
- **< 60%**: ⚠️  **信號分歧** → 觀望或小倉

---

## 💡 操作策略

### 策略1: 大週期確認，小週期進場（推薦）

```bash
# Step 1: 查看月線/季線大趨勢
python3 pattern_recognition/pattern_cli.py multi 2330 -t M Q

# Step 2: 如果大週期多頭，用日線找進場點
python3 pattern_recognition/pattern_cli.py multi 2330 -t D

# Step 3: 用週線確認
python3 pattern_recognition/pattern_cli.py multi 2330 -t W
```

### 策略2: 時間週期共振過濾

```bash
# 同時分析日線、週線、月線
python3 pattern_recognition/pattern_cli.py multi 2330 -t D W M

# 觀察共振強度:
# - 強勢共振 (≥80%) → 可以進場
# - 一般共振 (≥60%) → 減半倉位
# - 信號分歧 (<60%) → 觀望
```

### 策略3: 長期價值投資

```bash
# 使用5年線和10年線（需要充足歷史資料）
python3 pattern_recognition/pattern_cli.py multi 2330 -t Y 5Y 10Y

# 關注:
# - 5年線趨勢方向（長期成長性）
# - 10年線支撐/壓力（歷史關鍵位置）
# - 年線與5年線交叉（超級趨勢轉折）
```

---

## 🔧 程式化使用

### Python API

```python
from pattern_recognition.integrated_multi_timeframe import (
    IntegratedMultiTimeframeScanner,
    TimeframeManager
)

# 初始化掃描器
scanner = IntegratedMultiTimeframeScanner()

# 掃描多時間週期
result = scanner.scan_multi_timeframe(
    symbol='2330',
    timeframes=['D', 'W', 'M', 'Q', 'Y', '5Y', '10Y']
)

# 列印報告
scanner.print_report(result)

# 取得共振分析
resonance = result['resonance']
print(f"共振強度: {resonance['strength']:.0%}")
print(f"操作建議: {resonance['recommendation']}")

# 取得各時間週期結果
for tf, tf_result in result['timeframes'].items():
    if tf_result['success']:
        print(f"{tf}: {tf_result['ma_position']} - {tf_result['pattern_count']}個形態")
```

### 批次掃描

```python
# 掃描多支股票
symbols = ['2330', '2317', '2454', '2882', '2891']
results = {}

for symbol in symbols:
    result = scanner.scan_multi_timeframe(
        symbol=symbol,
        timeframes=['D', 'W', 'M']
    )
    results[symbol] = result
    
    # 只顯示強勢共振的股票
    if result['resonance']['strength'] >= 0.8:
        print(f"\n🔥 {symbol} 強勢共振！")
        scanner.print_report(result)
```

---

## 📈 實戰案例

### 案例1: 2330 台積電完整分析

```bash
python3 pattern_recognition/pattern_cli.py multi 2330 -t D W M Q Y
```

**分析重點**:
1. **日線**: 檢測短期形態（W底、假突破等）
2. **週線**: 確認波段趨勢（強勢多頭）
3. **月線**: 判斷中期方向（上升趨勢）
4. **季線**: 觀察季度表現
5. **年線**: 長期趨勢判斷

**決策流程**:
```
月線趨勢向上 ✅
  └→ 週線強勢多頭 ✅
      └→ 日線回檔整理 ✅
          └→ 等待日線形態突破
              └→ ✅ 進場
```

### 案例2: 長期趨勢確認

```bash
# 需要充足的歷史資料
python3 pattern_recognition/pattern_cli.py multi 2330 -t Y 5Y 10Y
```

**觀察重點**:
- **10年線**: 超長期支撐/壓力
- **5年線**: 長期趨勢方向
- **年線**: 當前年度表現
- **交叉信號**: 年線與5年線交叉 = 重大趨勢轉折

---

## ⚠️ 注意事項

### 1. 資料要求

| 時間週期 | 最小週期數 | 建議資料量 | 資料年數 |
|---------|----------|----------|---------|
| 日線 (D) | 60 | 120天 | 0.5年 |
| 週線 (W) | 20 | 500天 | 2年 |
| 月線 (M) | 20 | 1200天 | 5年 |
| 季線 (Q) | 12 | 2500天 | 10年 |
| 年線 (Y) | 3 | 2500天 | 10年 |
| **5年線 (5Y)** | **5** | **12500天** | **25年** ⚠️ |
| **10年線 (10Y)** | **10** | **25000天** | **50年** ⚠️ |

### 2. 常見問題

#### Q1: 為什麼5年線和10年線顯示"資料不足"？

**A**: 5年線和10年線需要非常長的歷史資料：
- **5年線**: 需要至少 **25年** 的日線資料
- **10年線**: 需要至少 **50年** 的日線資料

**解決方案**:
1. 使用更長歷史的股票（如台積電、金融股）
2. 從證交所下載更完整的歷史資料
3. 改用季線(Q)或年線(Y)代替

#### Q2: 如何選擇合適的時間週期組合？

**A**: 根據交易風格選擇：

| 交易風格 | 推薦組合 | 原因 |
|---------|---------|-----|
| 當沖/短線 | D | 只看日線 |
| 波段交易 | D + W + M | 日線進場，週月線確認 |
| 中期投資 | W + M + Q | 週線操作，月季線確認 |
| 長期投資 | M + Q + Y | 月線進場，季年線確認 |
| 超長期 | Y + 5Y (+ 10Y) | 年線操作，5/10年線確認 |

#### Q3: 共振強度如何計算？

**A**: 
```
共振強度 = 同方向信號數 / 總信號數

範例:
日線: 2個多頭形態, 1個空頭形態
週線: 1個多頭形態
月線: 無形態

總信號數 = 4
多頭信號 = 3
共振強度 = 3 / 4 = 75% (一般共振)
```

---

## 🎓 進階技巧

### 1. 時間週期過濾策略

```python
# 只採用大週期確認的小週期信號
def filter_by_major_timeframe(result):
    """只保留與大週期方向一致的信號"""
    major_tf = result['timeframes']['M']  # 月線為大週期
    major_direction = major_tf['ma_position']
    
    if '多頭' in major_direction:
        # 月線多頭，只看日線/週線的多頭形態
        return filter_bullish_only(result['timeframes']['D'])
    else:
        # 月線空頭，不進場
        return []
```

### 2. 動態倉位管理

```python
# 根據共振強度調整倉位
def calculate_position_size(resonance_strength, capital):
    """根據共振強度計算倉位"""
    if resonance_strength >= 0.8:
        return capital * 0.3  # 強勢共振: 30% 倉位
    elif resonance_strength >= 0.6:
        return capital * 0.15  # 一般共振: 15% 倉位
    else:
        return 0  # 信號分歧: 不進場
```

### 3. 自動化監控

```bash
# 建立 crontab 定時掃描
# 每天收盤後掃描重點股票
0 14 * * 1-5 cd /path/to/tw-stock-analysis && \
  python3 pattern_recognition/pattern_cli.py multi 2330 -t D W M >> logs/2330_multi.log
```

---

## 📚 相關文檔

1. **多時間週期指南**: `pattern_recognition/MULTI_TIMEFRAME_GUIDE.md`
2. **形態學12神招**: `pattern_recognition/PATTERN_DETECTION_GUIDE.md`
3. **進階交易邏輯**: `pattern_recognition/ADVANCED_TRADING_LOGIC_GUIDE.md`
4. **位置監控系統**: `pattern_recognition/POSITION_MONITOR_GUIDE.md`

---

## 🔄 版本歷史

### v2.0.0 (2026-02-14) - 完整整合版
- ✅ 新增 5年線 (5Y) 支援
- ✅ 新增 10年線 (10Y) 支援
- ✅ 整合到 pattern_cli.py
- ✅ 新增 `multi` 命令
- ✅ TimeframeManager 統一管理
- ✅ IntegratedMultiTimeframeScanner 整合掃描
- ✅ 完整共振分析

### v1.0.0 (2026-02-13)
- ✅ 支援日線/週線/月線/季線/半年線/年線
- ✅ 多時間週期轉換
- ✅ 形態識別整合
- ✅ 共振分析

---

## 🎯 快速參考

### 常用命令

```bash
# 列出支援的時間週期
python3 pattern_recognition/pattern_cli.py multi --list-timeframes

# 波段交易組合
python3 pattern_recognition/pattern_cli.py multi 2330 -t D W M

# 長期投資組合
python3 pattern_recognition/pattern_cli.py multi 2330 -t M Q Y

# 完整分析（需要充足資料）
python3 pattern_recognition/pattern_cli.py multi 2330 -t D W M Q Y 5Y 10Y
```

### 快速決策表

| 共振強度 | 信號等級 | 操作建議 | 倉位比例 |
|---------|---------|---------|---------|
| ≥ 80% | 🔥 強勢共振 | 買入 | 30% |
| 60-80% | ✅ 一般共振 | 買入 | 15% |
| < 60% | ⚠️ 信號分歧 | 觀望 | 0% |

---

## 💬 支援與回饋

如有問題或建議，請：
1. 查看文檔: `pattern_recognition/MULTI_TIMEFRAME_GUIDE.md`
2. 檢查日誌: `logs/`
3. 查看範例: 本文檔的實戰案例

---

**🎉 系統整合完成，祝您交易順利！**
