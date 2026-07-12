# 破底翻（Broken Bottom Reversal）- 專業演算法實作指南

## 📋 演算法概述

**破底翻（Broken Bottom Reversal）** 是一種強大的多頭反轉訊號，通常被視為主力的「甩轎」或「洗盤」動作。本文檔詳細說明完整的演算法實作邏輯。

**型態代碼**: 2  
**型態類型**: bullish（多頭）  
**信號類型**: buy（買入）  
**基礎信心度**: 75-90%

---

## 🔄 四階段演算法邏輯

### 階段1: 盤整區間建立 (Consolidation Phase)

#### 目標
識別股價在一段時間內的盤整區間，確定下緣支撐線與上緣頸線。

#### 參數設定
```python
lookback_window = 30-60天  # 盤整區間觀察期
consolidation_window = 30天  # 盤整區間長度
```

#### 演算法邏輯

**1. 下緣支撐線（Support Line）計算**
```python
# 使用10-20百分位的低點（反覆測試的底部）
support_line = np.percentile(consolidation_lows, 15)
```

**範例**:
- 觀察期低點: [20.1, 20.3, 19.9, 20.2, 20.0, 19.8, 20.1]
- 15%百分位 = 19.9（下緣支撐線）

**2. 上緣頸線（Resistance Line）計算**
```python
# 使用80-90百分位的高點（盤整區高點連線）
resistance_line = np.percentile(consolidation_highs, 85)
```

**範例**:
- 觀察期高點: [22.1, 22.3, 21.9, 22.2, 22.0, 21.8, 22.1]
- 85%百分位 = 22.2（上緣頸線）

#### 盤整區有效性檢查

**條件1: 盤整區寬度**
```python
consolidation_range = resistance_line - support_line
mid_price = (resistance_line + support_line) / 2
range_pct = (consolidation_range / mid_price) * 100

# 盤整區寬度應在5-20%之間
if range_pct < 5 or range_pct > 20:
    continue  # 非有效盤整區
```

**範例**:
- 支撐線: 19.9
- 頸線: 22.2
- 中價: (19.9 + 22.2) / 2 = 21.05
- 寬度: (22.2 - 19.9) / 21.05 = 10.9% ✅ 有效

**條件2: 盤整時間比例**
```python
# 確認多數時間在盤整區內（70%以上）
in_range_count = sum(
    (close >= support_line * 0.98) & 
    (close <= resistance_line * 1.02)
)
in_range_ratio = in_range_count / total_periods

if in_range_ratio < 0.7:
    continue  # 非有效盤整區
```

---

### 階段2: 破底訊號偵測 (False Breakdown)

#### 目標
偵測股價跌破盤整區下緣的動作，這是主力的「甩轎」動作。

#### 演算法邏輯

**破底條件**
```python
# 收盤價跌破下緣支撐3%
if close[i] < support_line * 0.97:
    breakdown_confirmed = True
    breakdown_idx = i
    breakdown_low = low[i]
```

**範例場景**:
```
支撐線: 20.00
破底K線: 收盤 19.40 (跌破3%)
破底最低: 19.29
```

#### 底部最低點記錄
```python
# 破底前後3天內的最低點
bottom_low = min(low[breakdown_idx-3:breakdown_idx+4])
```

#### 形態意義
- **主力甩轎**: 刻意跌破支撐，製造恐慌
- **清洗浮額**: 讓散戶在破位時止損出場
- **測試籌碼**: 觀察市場承接力道

---

### 階段3: 翻升站回確認 (Reclaiming Support) ★核心★

#### 目標
這是破底翻形態的核心！必須偵測到股價迅速收復失土。

#### 關鍵條件

**核心邏輯**
```python
# 在破底後5-10根K線內
for i in range(breakdown_idx + 1, breakdown_idx + 10):
    # 核心條件: 當前收盤 > 支撐線 且 前一根 < 支撐線
    if close[i] > support_line and close[i-1] < support_line:
        reclaim_confirmed = True
        reclaim_idx = i
        break
```

**範例場景**:
```
Day 1: 破底 19.40 (< 20.00支撐)
Day 2: 繼續弱 19.55 (< 20.00支撐)
Day 3: 翻升 20.30 (> 20.00支撐) ✅ 站回確認！
Day 4: 持穩 20.45
Day 5: 續強 20.80
```

#### 站回後持穩檢查
```python
# 站回後5天內，至少70%時間維持在支撐線之上
stability_check_end = reclaim_idx + 5
stability_count = sum(close[reclaim_idx:stability_check_end] > support_line)
stability_ratio = stability_count / (stability_check_end - reclaim_idx)

if stability_ratio < 0.7:
    continue  # 站回不穩，可能是假訊號
```

#### 形態意義
- **難得的多頭止穩買進訊號**
- **主力護盤**: 快速收復表示有主力承接
- **底部確認**: 再次測試支撐後站穩

---

### 階段4: 突破上緣與進場邏輯 (Breakout & Entry)

#### 目標
當破底翻結構確立後，最終的攻擊訊號發生在突破盤整區上緣。

#### 進場時機判斷

**三種進場情境**

**情境1: 已突破頸線（最佳）**
```python
if current_price > resistance_line:
    breakout_confirmed = True
    entry_price = resistance_line
    confidence = base_confidence + 0.05
```

**情境2: 接近突破（預期）**
```python
if current_price > resistance_line * 0.95 and current_price > support_line:
    approaching_breakout = True
    entry_price = current_price
```

**情境3: 站回後整理（等待）**
```python
# 站回支撐但尚未接近頸線
# 此時不進場，繼續監控
```

#### 進場確認條件
```python
# 必須滿足以下條件之一
if breakout_confirmed or approaching_breakout:
    signal_valid = True
    
# 後續追蹤條件
# 買入後，股價不應再拉回跌破頸線
```

---

## 💰 波段計算與止損

### 等幅距離計算

**公式定義**
```python
# D = 頸線價格 - 底部最低點
equal_distance = resistance_line - bottom_low
```

**範例計算**:
```
頸線: 22.00
底部最低: 19.29
等幅距離 D = 22.00 - 19.29 = 2.71
```

### 目標價計算

**第一波滿足（目標1）**
```python
target_1 = resistance_line + equal_distance
```

**範例**:
```
突破點: 22.00
等幅距離: 2.71
目標1 = 22.00 + 2.71 = 24.71
```

**第二波滿足（目標2）**
```python
target_2 = resistance_line + (equal_distance * 2)
```

**範例**:
```
突破點: 22.00
等幅距離: 2.71
目標2 = 22.00 + (2.71 × 2) = 27.42
```

### 止損設定

**兩種止損選項**

**選項1: 頸線下方（支撐線）**
```python
stop_loss_option_1 = support_line * 0.97  # 支撐線下方3%
```

**選項2: 前一低點**
```python
stop_loss_option_2 = bottom_low * 0.98  # 前低下方2%
```

**最終止損**
```python
# 取較高者（較緊的止損）
stop_loss = max(stop_loss_option_1, stop_loss_option_2)
```

**範例**:
```
支撐線: 20.00
選項1 = 20.00 × 0.97 = 19.40

前低: 19.29
選項2 = 19.29 × 0.98 = 18.90

最終止損 = max(19.40, 18.90) = 19.40
```

### 續抱條件

**核心原則**
```python
# 頸線不破即續抱
hold_condition = current_price > support_line

# 若跌破頸線，視為形態失敗
if current_price < support_line * 0.97:
    exit_signal = True
```

---

## 📊 量能確認

### 量能檢查邏輯

**站回時量能**
```python
if volume is not None and reclaim_idx is not None:
    reclaim_volume = volume[reclaim_idx]
    avg_volume = mean(volume[reclaim_idx-20:reclaim_idx])
    
    # 站回時量能應放大（至少1.2倍）
    if reclaim_volume > avg_volume * 1.2:
        volume_confirmed = True
        confidence += 0.05
```

**突破時量能**
```python
if breakout_confirmed:
    breakout_volume = volume[-5:].mean()
    avg_volume = volume[-30:-5].mean()
    
    # 突破時量能應放大（至少1.3倍）
    if breakout_volume > avg_volume * 1.3:
        volume_confirmed = True
```

### 量能意義

- **站回放量**: 表示有資金承接
- **突破放量**: 確認攻擊意圖
- **縮量整理**: 籌碼穩定

---

## 🎯 信心度評估系統

### 基礎信心度
```python
confidence = 0.75  # 75%
```

### 加分項目

**1. 突破確認 (+5%)**
```python
if breakout_confirmed:
    confidence += 0.05
```

**2. 量能確認 (+5%)**
```python
if volume_confirmed:
    confidence += 0.05
```

**3. 站穩程度 (+3%)**
```python
if (current_price - support_line) / support_line > 0.05:
    confidence += 0.03  # 站穩5%以上
```

**4. 盤整區間適中 (+2%)**
```python
if 8 <= range_pct <= 15:
    confidence += 0.02  # 盤整區8-15%最佳
```

### 信心度上限
```python
confidence = min(confidence, 0.90)  # 最高90%
```

### 信心度分級

| 範圍 | 等級 | 操作建議 |
|------|------|---------|
| 85-90% | 極高 | 正常倉位 |
| 80-85% | 高 | 80%倉位 |
| 75-80% | 中等 | 50%倉位 |
| < 75% | 低 | 觀望 |

---

## 📈 完整演算法流程圖

```
開始
  │
  ├─→ 階段1: 建立盤整區間
  │     ├─ 計算支撐線（15%百分位）
  │     ├─ 計算頸線（85%百分位）
  │     ├─ 檢查盤整寬度（5-20%）
  │     └─ 檢查盤整比例（70%以上）
  │         │
  │         ├─ 有效 → 繼續
  │         └─ 無效 → 回到開始
  │
  ├─→ 階段2: 偵測破底訊號
  │     ├─ 檢查收盤價 < 支撐線 × 0.97
  │     ├─ 記錄破底K線索引
  │     └─ 記錄底部最低點
  │         │
  │         ├─ 破底確認 → 繼續
  │         └─ 未破底 → 回到開始
  │
  ├─→ 階段3: 確認翻升站回（核心）
  │     ├─ 在破底後5-10根K線內
  │     ├─ 檢查: 當前收盤 > 支撐線 && 前一根 < 支撐線
  │     ├─ 確認站回後持穩（70%以上）
  │     └─ 檢查量能放大（1.2倍）
  │         │
  │         ├─ 站回確認 → 繼續
  │         └─ 未站回 → 回到開始
  │
  ├─→ 階段4: 突破上緣
  │     ├─ 檢查當前價 vs 頸線
  │     ├─ 已突破 → 進場訊號
  │     ├─ 接近突破 → 預備訊號
  │     └─ 尚未接近 → 繼續監控
  │         │
  │         └─ 計算目標價與止損
  │
  └─→ 產生信號
        ├─ 計算等幅距離 D
        ├─ 目標1 = 頸線 + D
        ├─ 目標2 = 頸線 + 2D
        ├─ 止損 = max(支撐線×0.97, 前低×0.98)
        ├─ 計算信心度（75-90%）
        └─ 回傳 PatternSignal
```

---

## 🔬 實戰範例

### 範例1: 標準破底翻

**盤整階段（30天）**
```
日期        收盤   最低   最高
Day 1-10   20.5   20.0   21.0
Day 11-20  20.3   19.8   21.2
Day 21-30  20.4   20.1   20.9

→ 支撐線: 20.0
→ 頸線: 21.0
→ 盤整寬度: (21.0-20.0)/20.5 = 4.9% ⚠️ 略窄
```

**破底階段（3天）**
```
Day 31: 跌破 19.4 (< 20.0×0.97) ✅ 破底確認
Day 32: 最低 19.2
Day 33: 最低 19.1 (底部最低點)
```

**翻升階段（5天）**
```
Day 34: 收盤 19.6 (< 20.0) 尚未站回
Day 35: 收盤 20.3 (> 20.0) ✅ 站回確認！
Day 36: 收盤 20.5 持穩
Day 37: 收盤 20.7 續強
Day 38: 收盤 20.9 接近頸線

→ 站回後持穩: 4/5 = 80% ✅
```

**突破階段**
```
Day 39: 收盤 21.2 突破頸線 ✅

→ 等幅距離 D = 21.0 - 19.1 = 1.9
→ 目標1 = 21.0 + 1.9 = 22.9
→ 目標2 = 21.0 + 3.8 = 24.8
→ 止損 = max(20.0×0.97, 19.1×0.98) = max(19.4, 18.7) = 19.4
→ 進場價: 21.0
→ 風險報酬比 = (22.9-21.0)/(21.0-19.4) = 1.9/1.6 = 1.19:1
```

### 範例2: 破底翻（W底）變體

**W底結構（40天）**
```
第一底: Day 15, 低點 16.5
中間峰: Day 25, 高點 18.2 (頸線)
第二底: Day 35, 低點 16.2 (破第一底1.8%)

→ 破底幅度: (16.5-16.2)/16.5 = 1.8% ✅ 適中
```

**站回與突破**
```
Day 37: 收盤 16.8 (> 16.5) ✅ 站回第一底水平
Day 40: 收盤 18.5 (> 18.2) ✅ 突破頸線

→ 等幅距離 D = 18.2 - 16.2 = 2.0
→ 目標1 = 18.2 + 2.0 = 20.2
→ 目標2 = 18.2 + 4.0 = 22.2
```

---

## ⚠️ 常見陷阱與注意事項

### 陷阱1: 假破底翻

**特徵**:
- 破底後站回，但無法持穩
- 反覆跌破支撐線
- 量能萎縮

**辨識方法**:
```python
# 站回後持穩檢查
if stability_ratio < 0.7:
    # 可能是假破底翻
    continue
```

### 陷阱2: 盤整區定義不清

**問題**:
- 盤整區過窄（< 5%）或過寬（> 20%）
- 支撐線與頸線不明確

**解決方案**:
```python
# 嚴格檢查盤整區有效性
range_pct = (resistance_line - support_line) / mid_price * 100
if range_pct < 5 or range_pct > 20:
    continue
```

### 陷阱3: 破底幅度過大

**問題**:
- 跌破支撐超過10%
- 可能是趨勢轉空，而非洗盤

**解決方案**:
```python
# 破底幅度不應超過5-8%
breakdown_pct = (support_line - bottom_low) / support_line * 100
if breakdown_pct > 8:
    # 可能不是洗盤，而是真破底
    continue
```

### 陷阱4: 站回時間過長

**問題**:
- 破底後超過10根K線才站回
- 站回力道不足

**解決方案**:
```python
# 限制站回檢查視窗
reclaim_search_end = min(breakdown_idx + 10, len(df) - 1)
```

---

## 📊 績效評估標準

### 成功率預期

| 時間週期 | 預期成功率 | 平均報酬 |
|---------|----------|---------|
| 日線 | 65-75% | 8-15% |
| 週線 | 70-80% | 15-25% |
| 月線 | 75-85% | 25-40% |

### 風險報酬比

**最低標準**:
- 風險報酬比 ≥ 1.5:1
- 潛在獲利 ≥ 8%

**理想標準**:
- 風險報酬比 ≥ 2:1
- 潛在獲利 ≥ 12%

### 持有期間

**預期持有時間**:
- 到達目標1: 10-30個交易日
- 到達目標2: 30-60個交易日

---

## 🛠️ 程式實作檢查清單

### 階段1檢查項
- [ ] 盤整區視窗設定正確（30-60天）
- [ ] 支撐線計算（15%百分位）
- [ ] 頸線計算（85%百分位）
- [ ] 盤整寬度檢查（5-20%）
- [ ] 盤整時間比例檢查（≥70%）

### 階段2檢查項
- [ ] 破底條件判斷（< 支撐線 × 0.97）
- [ ] 破底索引記錄
- [ ] 底部最低點計算（破底前後3天）
- [ ] 破底幅度合理性檢查（≤8%）

### 階段3檢查項（核心）
- [ ] 站回條件判斷（當前 > 支撐 && 前一根 < 支撐）
- [ ] 站回時間視窗（破底後5-10根K線）
- [ ] 站回後持穩檢查（≥70%）
- [ ] 量能確認（放大1.2倍）

### 階段4檢查項
- [ ] 突破判斷（當前價 > 頸線）
- [ ] 接近突破判斷（當前價 > 頸線 × 0.95）
- [ ] 等幅距離計算
- [ ] 目標價計算（目標1、目標2）
- [ ] 止損設定（兩種選項取max）

### 信號回傳檢查項
- [ ] PatternSignal 所有欄位填寫完整
- [ ] 信心度計算正確（75-90%）
- [ ] 風險報酬比計算
- [ ] 日誌記錄完整

---

## 📚 參考文獻與延伸閱讀

### 技術分析經典
1. **《技術分析精解》** - 破底翻形態詳解
2. **《形態學12神招》** - 洗盤形態實戰
3. **《主力操盤手法》** - 甩轎動作解析

### 程式實作
- `patterns_12_masters.py` - 主要實作檔案
- `PATTERN_DETECTION_GUIDE.md` - 形態檢測指南
- `ADVANCED_TRADING_LOGIC_GUIDE.md` - 進階交易邏輯

---

## 📞 技術支援

如有演算法相關問題，請參考：
1. 程式碼註解：`_detect_false_breakdown()` 方法
2. 日誌輸出：檢查 logger.info 訊息
3. 測試案例：使用歷史資料驗證

---

**文檔版本**: 2.0.0  
**最後更新**: 2026-02-14  
**狀態**: ✅ 生產就緒
