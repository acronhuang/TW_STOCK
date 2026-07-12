# SenVision 量化形態選股系統 - 系統架構

## 📋 系統概述

**SenVision** 是基於蔡森形態學理論的台股自動化技術分析系統，實現 12 種經典形態的自動識別與量化交易信號。

**核心價值**：
- 🤖 **自動化**：利用 FinMind API 取代人工手動翻圖
- 📊 **量化**：精確定義「頸線」、「突破」與「測幅」
- 🎯 **預測**：自動計算 1:1 漲跌目標價，輔助風控

---

## 🏗️ 系統架構

```
┌─────────────────────────────────────────────────────────────┐
│                   SenVision 量化形態選股系統                  │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  數據層 (Data Layer)                                         │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  FinMind API               MongoDB Database                 │
│  ┌──────────────┐         ┌──────────────────┐             │
│  │ 日K線數據    │  ─────> │ stock_price      │             │
│  │ 還原股價     │         │ • open, high     │             │
│  │ 成交量       │         │ • low, close     │             │
│  └──────────────┘         │ • volume         │             │
│                            │ • adj_close      │             │
│  ┌──────────────┐         └──────────────────┘             │
│  │ 股票基本資訊 │  ─────> ┌──────────────────┐             │
│  │ 產業分類     │         │ taiwan_stock_info│             │
│  └──────────────┘         └──────────────────┘             │
│                                                               │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  核心引擎 (Core Engine)                                      │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  1. ZigZag 轉折點提取引擎                                    │
│     ┌──────────────────────────────────────────┐           │
│     │ • 識別區間高點 (Peak)                     │           │
│     │ • 識別區間低點 (Trough)                   │           │
│     │ • 可配置閾值 (threshold: 3-5%)            │           │
│     │ • 返回轉折點序列                           │           │
│     └──────────────────────────────────────────┘           │
│                                                               │
│  2. 形態識別引擎 (12 神招)                                   │
│     ┌──────────────────────────────────────────┐           │
│     │ A. 底部反轉類 (Bullish Reversal)          │           │
│     │    • W底 (Double Bottom)                  │           │
│     │    • 頭肩底 (Head & Shoulders Bottom)     │           │
│     │    • 破底翻 (Failed Breakdown)            │           │
│     │                                            │           │
│     │ B. 頭部反轉類 (Bearish Reversal)          │           │
│     │    • M頭 (Double Top)                     │           │
│     │    • 頭肩頂 (Head & Shoulders Top)        │           │
│     │    • 破天翻 (Failed Breakout)             │           │
│     │                                            │           │
│     │ C. 趨勢突破類 (Breakout)                  │           │
│     │    • 破切 (Trendline Break)               │           │
│     │    • 旗型 (Flag Pattern)                  │           │
│     │    • 三角收斂 (Triangle Convergence)      │           │
│     │    • 箱型突破 (Box Breakout)              │           │
│     └──────────────────────────────────────────┘           │
│                                                               │
│  3. 趨勢線擬合模組                                           │
│     ┌──────────────────────────────────────────┐           │
│     │ • 連結至少 2 個轉折點                     │           │
│     │ • 計算斜率與截距                           │           │
│     │ • 判斷上升/下降/水平趨勢                  │           │
│     └──────────────────────────────────────────┘           │
│                                                               │
│  4. 量能分析模組                                             │
│     ┌──────────────────────────────────────────┐           │
│     │ • 5日均量、20日均量                        │           │
│     │ • 凹洞量識別 (Volume Dip)                 │           │
│     │ • 突破量確認 (Volume Spike > 1.5x)        │           │
│     └──────────────────────────────────────────┘           │
│                                                               │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  測幅與風控模組 (Risk Management)                            │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  1. 目標價計算                                               │
│     多方目標 = 頸線 + (頸線 - 形態最低點)                    │
│     空方目標 = 頸線 - (形態最高點 - 頸線)                    │
│                                                               │
│  2. 停損價計算                                               │
│     多方停損 = 頸線下方 3% 或右底低點                        │
│     空方停損 = 頸線上方 3% 或右肩高點                        │
│                                                               │
│  3. 風報比篩選                                               │
│     Risk/Reward = (目標價-現價) / (現價-停損價)              │
│     過濾條件: R/R >= 2.0                                     │
│                                                               │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  輸出層 (Output Layer)                                       │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  1. 掃描報表                                                 │
│     • 成型中：距離頸線 < 2%                                  │
│     • 剛突破：當日突破頸線/切線                              │
│     • 測幅進度：實時監控達標率                               │
│                                                               │
│  2. 視覺化圖表                                               │
│     • K線圖 + 頸線標註                                       │
│     • 趨勢線繪製                                             │
│     • 形態標籤 (W-Bottom, Breakout)                         │
│     • 目標價/停損價標示                                      │
│                                                               │
│  3. 通知系統                                                 │
│     • Line Bot 即時推播                                      │
│     • Email 每日報告                                         │
│     • Dashboard Web UI                                       │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔬 核心算法

### 1. ZigZag 轉折點提取

**目的**：濾除價格雜訊，提取有意義的轉折點

**算法**：
```python
def zigzag(prices: np.array, threshold: float = 0.05) -> List[Peak]:
    """
    Args:
        prices: 價格序列 (high, low, close)
        threshold: 最小變動幅度 (預設 5%)
    
    Returns:
        peaks: [(index, price, type), ...]
               type: 'H' (High) or 'L' (Low)
    """
    peaks = []
    last_peak_price = prices[0]
    last_peak_type = None
    
    for i, price in enumerate(prices):
        # 判斷是否形成有效轉折
        if last_peak_type is None:
            # 初始化
            ...
        elif last_peak_type == 'H':
            # 目前在高點，尋找低點
            if (last_peak_price - price) / last_peak_price >= threshold:
                peaks.append((i, price, 'L'))
                last_peak_price = price
                last_peak_type = 'L'
        else:  # last_peak_type == 'L'
            # 目前在低點，尋找高點
            if (price - last_peak_price) / last_peak_price >= threshold:
                peaks.append((i, price, 'H'))
                last_peak_price = price
                last_peak_type = 'H'
    
    return peaks
```

### 2. W 底識別

**定義**：
- 兩個低點 L1, L2 價格差距 < 3%
- 中間高點 H 定義為頸線
- 突破條件：收盤價 > 頸線 且 成交量 > 5日均量 × 1.5

**算法**：
```python
def detect_w_bottom(peaks: List[Peak]) -> Optional[Pattern]:
    """
    Args:
        peaks: ZigZag 轉折點序列
    
    Returns:
        pattern: {
            'type': 'W-Bottom',
            'L1': (date, price),
            'H': (date, price),  # 頸線
            'L2': (date, price),
            'neckline': price,
            'target': price,  # 頸線 + (頸線 - min(L1, L2))
            'stop_loss': price
        }
    """
    # 尋找 L-H-L 序列
    for i in range(len(peaks) - 2):
        if peaks[i].type == 'L' and peaks[i+1].type == 'H' and peaks[i+2].type == 'L':
            L1 = peaks[i]
            H = peaks[i+1]
            L2 = peaks[i+2]
            
            # 判斷條件：L1 與 L2 價格差距 < 3%
            price_diff = abs(L1.price - L2.price) / min(L1.price, L2.price)
            if price_diff <= 0.03:
                neckline = H.price
                target = neckline + (neckline - min(L1.price, L2.price))
                stop_loss = min(L1.price, L2.price) * 0.97
                
                return {
                    'type': 'W-Bottom',
                    'L1': L1,
                    'H': H,
                    'L2': L2,
                    'neckline': neckline,
                    'target': target,
                    'stop_loss': stop_loss
                }
    
    return None
```

### 3. 破切 (趨勢線突破)

**算法**：
```python
def detect_breakout(prices: pd.DataFrame, peaks: List[Peak]) -> Optional[Pattern]:
    """
    Args:
        prices: DataFrame with columns [date, close]
        peaks: 近期高點序列
    
    Returns:
        pattern: {
            'type': 'Breakout',
            'trendline': {'slope': m, 'intercept': b},
            'breakout_date': date,
            'breakout_price': price
        }
    """
    # 1. 連結近期至少 2 個高點
    highs = [p for p in peaks if p.type == 'H'][-3:]  # 取最近 3 個高點
    
    if len(highs) < 2:
        return None
    
    # 2. 擬合下降趨勢線 (線性回歸)
    x = np.array([h.index for h in highs])
    y = np.array([h.price for h in highs])
    m, b = np.polyfit(x, y, 1)
    
    # 3. 判斷是否為下降趨勢
    if m >= 0:
        return None  # 非下降趨勢
    
    # 4. 檢查最新價格是否突破趨勢線
    last_index = len(prices) - 1
    last_price = prices.iloc[-1]['close']
    trendline_price = m * last_index + b
    
    if last_price > trendline_price:
        return {
            'type': 'Breakout',
            'trendline': {'slope': m, 'intercept': b},
            'breakout_date': prices.iloc[-1]['date'],
            'breakout_price': last_price,
            'target': last_price * 1.1  # 簡化版測幅，實際需更複雜計算
        }
    
    return None
```

---

## 📊 數據需求

### 已具備（從現有系統）

| 數據類型 | Collection | 字段 | 說明 |
|---------|-----------|------|------|
| 日K線 | `stock_price` | open, high, low, close, volume | 已有還原股價 |
| 股票資訊 | `taiwan_stock_info` | stock_id, stock_name, security_type | 已實現分類系統 |
| 股票分類 | - | SecurityType 枚舉 | 已過濾 ETF/權證 |

### 需新增

| 數據類型 | Collection | 字段 | 說明 |
|---------|-----------|------|------|
| ZigZag 轉折點 | `zigzag_peaks` | stock_id, date, price, type | 快取轉折點，避免重複計算 |
| 形態識別結果 | `pattern_signals` | stock_id, pattern_type, neckline, target, stop_loss, status | 儲存形態信號 |
| 趨勢線 | `trendlines` | stock_id, start_date, end_date, slope, intercept | 儲存擬合的趨勢線 |

---

## 🎯 開發階段規劃

### Phase 1: MVP (2-3 週)

**目標**：實現 W底 與 M頭 自動識別

- [x] 數據層準備（已完成，使用現有系統）
- [ ] ZigZag 算法實現
- [ ] W底識別引擎
- [ ] M頭識別引擎
- [ ] 測幅計算模組
- [ ] 簡易 CLI 掃描工具

**交付物**：
```bash
# 執行掃描
python3 src/senvision/scanner.py --pattern W-Bottom --days 60

# 輸出範例
找到 15 個 W底形態:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
股票   形態       頸線    目標價  風報比  狀態
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
2330   W-Bottom   585     620     2.5    成型中
2454   W-Bottom   1200    1350    3.1    剛突破
...
```

### Phase 2: 趨勢突破 (2-3 週)

- [ ] 趨勢線自動擬合
- [ ] 破切邏輯實現
- [ ] 旗型、三角收斂識別
- [ ] 凹洞量過濾機制
- [ ] Web Dashboard 初版

### Phase 3: 回測與優化 (3-4 週)

- [ ] 歷史形態回測系統
- [ ] 勝率統計（按產業/市值分組）
- [ ] 參數優化（ZigZag 閾值、風報比）
- [ ] Line Bot 通知系統

---

## 🔐 風控機制

### 1. 信號過濾條件

```python
FILTER_CONFIG = {
    'min_risk_reward_ratio': 2.0,      # 最低風報比
    'min_volume_ratio': 1.5,           # 突破量至少為 5 日均量的 1.5 倍
    'max_days_since_pattern': 5,       # 形態完成後 5 天內才有效
    'min_pattern_width_days': 20,      # 形態寬度至少 20 個交易日
    'exclude_security_types': ['Warrant', 'ETF']  # 排除權證、ETF
}
```

### 2. 停損機制

- **硬停損**：跌破停損價立即出場
- **移動停損**：達到目標價 50% 後，停損移至成本價
- **時間停損**：持有超過 30 天未達標，評估是否出場

### 3. 倉位管理

- 單一形態最大投入：總資金 10%
- 同類形態（如多個 W底）總計不超過：30%
- 同產業股票總計不超過：40%

---

## 📈 預期效益

### 效率提升

- **手動翻圖時間**：每日 2 小時 → **自動化 5 分鐘**
- **覆蓋範圍**：50 檔 → **全市場 2,000+ 檔**

### 策略優化

- **回測週期**：5 年歷史數據
- **預期勝率**：55-65%（基於蔡森理論的經驗值）
- **目標風報比**：> 2.0

---

## 🛠️ 技術棧

```python
# 核心依賴
numpy>=1.24.0       # 數值計算
pandas>=2.0.0       # 數據處理
scipy>=1.10.0       # 科學計算（趨勢線擬合）
pymongo>=4.6.0      # 數據庫存取

# 視覺化
matplotlib>=3.7.0   # 圖表繪製
plotly>=5.14.0      # 互動式圖表

# Web 服務
streamlit>=1.30.0   # Dashboard
fastapi>=0.109.0    # API 服務

# 通知
line-bot-sdk>=3.0.0 # Line 推播
```

---

## 📝 後續擴展

### 進階功能

1. **AI 輔助**：使用 LSTM 預測形態成功率
2. **多時框分析**：結合日線、週線形態
3. **產業輪動**：根據形態分布預測產業強弱
4. **社群整合**：PTT/Dcard 爬蟲，結合輿情分析

### 商業模式

- **個人版**：免費，限制每日掃描 10 次
- **專業版**：NT$ 3,000/月，無限掃描 + Line 推播
- **機構版**：客製化開發，API 整合

---

**文件版本**: v1.0  
**最後更新**: 2026-02-24  
**狀態**: 🔨 設計階段
