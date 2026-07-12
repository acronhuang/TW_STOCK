# 產品需求文件 (PRD): 台股量化交易系統 v2.1

**副標題**: FinMind 數據 + 蔡森形態學深度整合版  
**文件版本**: v2.1  
**創建日期**: 2026-02-23  
**產品負責人**: Ming  
**狀態**: 規劃階段 - 基於 v2.0 優化擴展

---

## 文檔導航

- [1. 產品概述](#1-產品概述)
- [2. 產品目標](#2-產品目標)
- [3. 核心架構](#3-核心架構)
- [4. 功能需求](#4-功能需求)
- [5. 數據結構設計](#5-數據結構設計)
- [6. 蔡森形態學量化](#6-蔡森形態學量化)
- [7. 回測優化](#7-回測優化)
- [8. 技術規格](#8-技術規格)
- [9. 實施路徑](#9-實施路徑)

---

## 1. 產品概述

### 1.1. 產品定位

**台股量化交易系統 v2.1** 是基於 v2.0（74.51% 年化報酬）的進化版本，整合：

1. **FinMind 全方位數據源**：股價、財報、籌碼、技術指標
2. **17 因子量化選股**：動能、價值、質量（v2.0 已驗證）
3. **蔡森形態學過濾**：12 神招作為進場觸發與出場準則
4. **智能風控系統**：多層次止損與倉位管理

### 1.2. 核心理念

> **「基本面選股 × 技術面進場 × 紀律風控」**

- **第一步（基本面）**：17 因子篩選出「體質優良」的 20-30 支候選股
- **第二步（技術面）**：蔡森形態學偵測「低風險進場點」，最終選出 10 支
- **第三步（風控）**：嚴格止損與倉位管理，確保長期生存

### 1.3. 與 v2.0 的差異

| 維度 | v2.0 | v2.1 (本版) |
|------|------|------------|
| **數據源** | 自建爬蟲 + MongoDB | FinMind API + PostgreSQL |
| **選股邏輯** | 17 因子綜合評分 → 直接選 10 支 | 17 因子 → 30 支候選 → 形態過濾 → 10 支 |
| **進場時機** | 固定雙月末（2ME） | 雙月末 + 形態確認（動態） |
| **出場邏輯** | 固定 -5% 止損 | 形態破壞 + 移動止損 + 固定止損 |
| **籌碼分析** | 無 | 大戶持股變化（400 張以上） |

---

## 2. 產品目標

### 2.1. 業務目標

**主要目標**：
- **KPI-1（報酬提升）**：多年平均年化報酬從 39.32% 提升至 **45%+**
- **KPI-2（勝率提升）**：勝率從 62.5% 提升至 **70%+**
- **KPI-3（回撤控制）**：最大回撤從 -14.37% 控制在 **-12%** 以內

**次要目標**：
- 減少「選對股但買錯點」的失誤（形態過濾）
- 提升「跑得掉」的成功率（形態破壞提前出場）

### 2.2. 用戶目標

**用戶**：Ming（系統開發者與唯一使用者）

**痛點與解決方案**：

| 痛點 | v2.0 的不足 | v2.1 的解決方案 |
|------|------------|----------------|
| 買在相對高點 | 雙月末機械式進場 | 形態確認後才進場（破底翻、頸線突破） |
| 止損太晚 | 統一 -5% 止損 | 形態破壞提前出場（如跌破支撐線） |
| 對基本面過度依賴 | 只看財報 | 加入籌碼面（大戶動向） |
| 無法應對極端行情 | 熊市 -9.62% | 形態學過濾，熊市減少進場 |

---

## 3. 核心架構

### 3.1. 系統架構圖

```
┌─────────────────────────────────────────────────────────────────┐
│                     台股量化交易系統 v2.1                        │
└─────────────────────────────────────────────────────────────────┘
                                │
                ┌───────────────┴───────────────┐
                │                               │
        ┌───────▼────────┐            ┌────────▼────────┐
        │  數據層 (Data)  │            │ 策略層 (Strategy)│
        └───────┬────────┘            └────────┬────────┘
                │                               │
    ┌───────────┼───────────┐       ┌──────────┼──────────┐
    │           │           │       │          │          │
┌───▼──┐  ┌────▼───┐  ┌───▼──┐ ┌──▼──┐  ┌────▼────┐ ┌──▼──┐
│FinMind  │MongoDB│  │PGsql │ │17因子│  │蔡森形態 │ │風控 │
│ API  │  │(備份)│  │(主庫)│ │選股  │  │過濾器   │ │管理 │
└──────┘  └────────┘  └──────┘ └─────┘  └─────────┘ └─────┘
                                │                    │
                                └──────────┬─────────┘
                                           │
                                  ┌────────▼────────┐
                                  │  執行層 (Exec)   │
                                  └────────┬────────┘
                                           │
                        ┌──────────────────┼──────────────────┐
                        │                  │                  │
                   ┌────▼────┐      ┌─────▼─────┐     ┌─────▼─────┐
                   │訂單執行  │      │績效追蹤   │     │監控預警   │
                   │富邦API  │      │回測/實盤  │     │Line/Email│
                   └─────────┘      └───────────┘     └───────────┘
```

### 3.2. 數據流程圖

```
每日 15:00
    │
    ├─► FinMind API 抓取 (股價、財報、籌碼)
    │         │
    │         ├─► 存入 PostgreSQL (daily_market_data)
    │         └─► 更新 MongoDB (備份)
    │
    ├─► 計算 17 個量化因子
    │         │
    │         └─► 存入 PostgreSQL (fundamental_factors)
    │
    └─► 形態學特徵計算
              │
              ├─► 破底翻偵測
              ├─► 頸線突破偵測
              ├─► 量價背離偵測
              └─► 存入 PostgreSQL (daily_market_data.is_bottom_reversal 等)

每月末 (雙月)
    │
    ├─► 17 因子選股 → 30 支候選股
    │
    ├─► 形態學過濾 → 10 支最終標的
    │         │
    │         ├─► 破底翻或頸線突破 (近 5 日內)
    │         ├─► 大戶持股增加 (籌碼確認)
    │         └─► 量價配合 (成交量放大)
    │
    └─► 提交訂單至富邦 API
              │
              └─► 監控預警 (Line Notify)

每日盤中
    │
    ├─► 檢查形態破壞 (支撐線跌破)
    │         │
    │         └─► 提前出場 (不等 -5% 止損)
    │
    └─► 檢查固定止損 (-5% 單股、-10% 組合)
```

---

## 4. 功能需求

### 4.1. FR-01: FinMind 數據集成 (Data Integration)

**需求描述**：  
系統需整合 FinMind 提供的全方位台股數據，取代原有的自建爬蟲。

**數據類型**：

| 數據類型 | FinMind API | 更新頻率 | 用途 |
|---------|-------------|---------|------|
| **股價行情** | `TaiwanStockPrice` | 每日 15:00 | 技術分析、形態辨識 |
| **財務報表** | `TaiwanStockFinancialStatements` | 每季 | 17 因子計算（ROE、負債比等）|
| **大戶持股** | `TaiwanStockHoldingSharesPer` | 每週 | 籌碼面過濾（400 張以上） |
| **本益比/股價淨值比** | `TaiwanStockPER` | 每日 | 價值因子（PE、PB） |
| **除權息** | `TaiwanStockDividend` | 每年 | 還原股價計算 |

**驗收標準**：

- **AC-1.1**: 能成功連接 FinMind API，並於每日 15:30 自動抓取最新數據。
- **AC-1.2**: 當 FinMind API 維護時，系統能自動 Retry（3 次，每次間隔 10 分鐘）。
- **AC-1.3**: 數據需同步存入 PostgreSQL（主庫）與 MongoDB（備份），確保雙重保障。
- **AC-1.4**: 數據完整性檢查：每日自動驗證是否有缺漏（如某支股票無數據），並發送預警。

**技術實現**：

```python
# 範例：FinMind 數據抓取器
from FinMindApi import DataLoader

class FinMindIntegrator:
    def __init__(self, api_token):
        self.api = DataLoader(api_token)
    
    def fetch_daily_price(self, stock_id, start_date, end_date):
        """抓取日線數據"""
        df = self.api.taiwan_stock_daily(
            stock_id=stock_id,
            start_date=start_date,
            end_date=end_date
        )
        return df
    
    def fetch_holdings(self, stock_id, date):
        """抓取大戶持股（400 張以上）"""
        df = self.api.taiwan_stock_holding_shares_per(
            stock_id=stock_id,
            date=date
        )
        # 篩選 400 張以上
        return df[df['level'] >= 400]
```

---

### 4.2. FR-02: 蔡森形態學辨識引擎 (Morphology Pattern Engine)

**需求描述**：  
量化蔡森老師的 12 神招，作為量化因子選股後的「二次過濾器」。

**核心形態（優先實作 5 個）**：

#### 形態 1: 破底翻 (Bottom Reversal)

**定義**：  
股價跌破前波低點（支撐線）後，於 **5 日內** 帶量收復。

**量化條件**：
1. `low[0] < support_line`（當日最低價跌破支撐線）
2. `close[0] > support_line * 1.02`（收盤價站回支撐線 +2%）
3. `volume[0] > mean(volume, 5) * 1.5`（成交量放大 1.5 倍）
4. 上述條件需在 **5 個交易日內** 完成

**Python 實現**：

```python
def detect_bottom_reversal(df, window=20):
    """
    偵測破底翻形態
    
    Args:
        df: DataFrame，包含 open, high, low, close, volume
        window: 支撐線計算週期（預設 20 日）
    
    Returns:
        Series: Boolean，True 表示出現破底翻
    """
    # 計算 20 日支撐線（最低價的滾動最低）
    support_line = df['low'].rolling(window).min().shift(1)
    
    # 條件 1: 跌破支撐線
    cond1 = df['low'] < support_line
    
    # 條件 2: 收盤站回支撐線 +2%
    cond2 = df['close'] > support_line * 1.02
    
    # 條件 3: 成交量放大 1.5 倍
    avg_volume = df['volume'].rolling(5).mean()
    cond3 = df['volume'] > avg_volume * 1.5
    
    # 條件 4: 5 日內完成（使用 rolling 檢查）
    signal = (cond1 & cond2 & cond3).rolling(5).max() > 0
    
    return signal
```

---

#### 形態 2: 雙底 (W Bottom)

**定義**：  
形成兩個低點，第二底不破第一底，且突破頸線。

**量化條件**：
1. 偵測兩個局部低點（間隔 10-40 天）
2. `low_2 >= low_1 * 0.98`（第二底不破第一底 -2%）
3. `close > neck_line * 1.03`（突破頸線 +3%）
4. `volume > mean(volume, 20) * 1.5`（突破時放量）

**Python 實現**：

```python
def detect_w_bottom(df, min_gap=10, max_gap=40):
    """
    偵測 W 底形態
    
    Args:
        df: DataFrame
        min_gap: 兩底最小間隔天數
        max_gap: 兩底最大間隔天數
    
    Returns:
        Series: Boolean
    """
    from scipy.signal import argrelextrema
    
    # 找出局部低點
    lows_idx = argrelextrema(df['low'].values, np.less, order=5)[0]
    
    signals = pd.Series(False, index=df.index)
    
    for i in range(len(lows_idx) - 1):
        idx1, idx2 = lows_idx[i], lows_idx[i+1]
        gap = idx2 - idx1
        
        if min_gap <= gap <= max_gap:
            low_1 = df['low'].iloc[idx1]
            low_2 = df['low'].iloc[idx2]
            
            # 第二底不破第一底
            if low_2 >= low_1 * 0.98:
                # 計算頸線（兩底之間的最高點）
                neck_line = df['high'].iloc[idx1:idx2].max()
                
                # 檢查後續是否突破頸線
                future = df.iloc[idx2:idx2+10]
                breakout = (future['close'] > neck_line * 1.03) & \
                          (future['volume'] > df['volume'].rolling(20).mean().iloc[idx2] * 1.5)
                
                if breakout.any():
                    signals.iloc[idx2 + breakout.idxmax()] = True
    
    return signals
```

---

#### 形態 3: 頸線突破 (Neckline Breakout)

**定義**：  
股價突破過去 60 日的高點連線（頸線），且振幅 > 3%。

**量化條件**：
1. `close > neckline * 1.03`（突破頸線 +3%）
2. `(high - low) / close > 0.03`（當日振幅 > 3%）
3. `volume > mean(volume, 20) * 2.0`（成交量爆量 2 倍）
4. 突破後連續 2 日站穩（避免假突破）

**Python 實現**：

```python
def detect_neckline_breakout(df, window=60):
    """
    偵測頸線突破
    
    Args:
        df: DataFrame
        window: 頸線計算週期（預設 60 日）
    
    Returns:
        Series: Boolean
    """
    # 計算 60 日頸線（高點的滾動最高）
    neckline = df['high'].rolling(window).max().shift(1)
    
    # 條件 1: 突破頸線 +3%
    cond1 = df['close'] > neckline * 1.03
    
    # 條件 2: 當日振幅 > 3%
    cond2 = (df['high'] - df['low']) / df['close'] > 0.03
    
    # 條件 3: 成交量爆量 2 倍
    avg_volume = df['volume'].rolling(20).mean()
    cond3 = df['volume'] > avg_volume * 2.0
    
    # 條件 4: 連續 2 日站穩
    cond4 = df['close'].shift(-1) > neckline
    
    signal = cond1 & cond2 & cond3 & cond4
    
    return signal
```

---

#### 形態 4: 量價背離 (Volume-Price Divergence)

**定義**：  
股價創新高但成交量未創新高（負背離，看跌）。

**量化條件**：
1. `close == high(60)`（股價創 60 日新高）
2. `volume < mean(volume, 5)`（成交量低於 5 日均量）
3. 連續 3 日出現此現象 → 出場訊號

**Python 實現**：

```python
def detect_volume_price_divergence(df, window=60):
    """
    偵測量價背離（負背離）
    
    Returns:
        Series: Boolean，True 表示出現負背離（看跌）
    """
    # 創新高
    is_new_high = df['close'] == df['high'].rolling(window).max()
    
    # 成交量低於平均
    low_volume = df['volume'] < df['volume'].rolling(5).mean()
    
    # 連續 3 日
    signal = (is_new_high & low_volume).rolling(3).sum() >= 2
    
    return signal
```

---

#### 形態 5: 量價噴出 (Volume Surge)

**定義**：  
成交量爆量且股價突破前高。

**量化條件**：
1. `volume > mean(volume, 5) * 3`（成交量 3 倍以上）
2. `close > high(20)`（突破 20 日高點）
3. `close > open * 1.05`（當日漲幅 > 5%）

**Python 實現**：

```python
def detect_volume_surge(df):
    """
    偵測量價噴出
    
    Returns:
        Series: Boolean
    """
    # 成交量爆量 3 倍
    cond1 = df['volume'] > df['volume'].rolling(5).mean() * 3
    
    # 突破 20 日高點
    cond2 = df['close'] > df['high'].rolling(20).max().shift(1)
    
    # 當日漲幅 > 5%
    cond3 = df['close'] > df['open'] * 1.05
    
    signal = cond1 & cond2 & cond3
    
    return signal
```

---

### 4.3. FR-03: 17 因子 × 蔡森形態學整合選股

**需求描述**：  
將 v2.0 的 17 因子選股與蔡森形態學結合，形成「兩階段過濾」。

**選股流程**：

```
步驟 1: 17 因子初選（基本面）
    │
    ├─► 計算動能因子（5 個）：return_3m, return_6m, return_12m, volatility, RSI
    ├─► 計算價值因子（3 個）：PE, PB, earnings_yield
    ├─► 計算質量因子（4 個）：ROE, ROA, profit_margin, debt_ratio
    ├─► 計算成長因子（3 個）：revenue_growth, eps_growth, roe_trend
    ├─► 計算籌碼因子（2 個）：institutional_holding, margin_ratio
    │
    └─► 綜合評分 → 選出 30 支候選股

步驟 2: 形態學過濾（技術面）
    │
    ├─► 檢查近 5 日是否出現「破底翻」或「頸線突破」
    ├─► 檢查大戶持股（400 張以上）是否增加
    ├─► 檢查是否有「量價背離」（負面訊號，排除）
    │
    └─► 最終選出 10 支進場標的

步驟 3: 倉位分配
    │
    ├─► 形態強度評分（0-1）
    │     ├─► 破底翻 + 大戶增持 → 1.2 倍權重
    │     ├─► 頸線突破 + 爆量 → 1.1 倍權重
    │     └─► 一般形態 → 1.0 倍權重
    │
    └─► 等權重 × 形態強度 = 最終倉位
```

**驗收標準**：

- **AC-3.1**: 30 支候選股中，至少有 15 支出現蔡森形態。
- **AC-3.2**: 最終 10 支標的中，100% 需符合至少一種蔡森形態。
- **AC-3.3**: 形態強度評分需可回測驗證，證明加權後報酬提升。

---

### 4.4. FR-04: 動態出場邏輯（形態破壞 + 固定止損）

**需求描述**：  
整合形態學的「出場訊號」與原有的固定止損。

**出場觸發條件（優先順序）**：

| 優先級 | 觸發條件 | 動作 | 說明 |
|--------|---------|------|------|
| **P0** | 形態破壞 | 立即出場 | 跌破支撐線、頸線失守 |
| **P1** | 量價背離（連續 3 日）| 減倉 50% | 見頂訊號，先出一半 |
| **P2** | 單股止損（-5%）| 全部賣出 | v2.0 原有邏輯 |
| **P3** | 組合止損（-10%）| 全部平倉 | v2.0 原有邏輯 |
| **P4** | 移動止盈（獲利 15%+）| 拉高停損點 | 新增：鎖定利潤 |

**形態破壞定義**：

```python
def check_pattern_breakdown(df, entry_price, support_line):
    """
    檢查形態是否破壞
    
    Args:
        df: 當前股價數據
        entry_price: 進場價格
        support_line: 支撐線價格（破底翻/雙底的低點）
    
    Returns:
        bool: True 表示形態破壞，需立即出場
    """
    current_close = df['close'].iloc[-1]
    current_low = df['low'].iloc[-1]
    
    # 破壞條件 1: 跌破支撐線 -2%
    if current_close < support_line * 0.98:
        return True, "跌破支撐線"
    
    # 破壞條件 2: 單日大跌 -7%
    if (current_close - entry_price) / entry_price < -0.07:
        return True, "單日大跌 -7%"
    
    # 破壞條件 3: 連續 3 日收黑（且成交量萎縮）
    recent_3 = df.tail(3)
    all_red = (recent_3['close'] < recent_3['open']).all()
    volume_shrink = (recent_3['volume'] < recent_3['volume'].mean() * 0.7).all()
    
    if all_red and volume_shrink:
        return True, "連續 3 日收黑且縮量"
    
    return False, None
```

**移動止盈邏輯**：

```python
def trailing_stop(entry_price, current_price, highest_price):
    """
    移動止盈：獲利達 15% 後，停損點改為「最高價 -5%」
    
    Returns:
        float: 新的停損價格
    """
    profit_pct = (current_price - entry_price) / entry_price
    
    if profit_pct >= 0.15:
        # 啟動移動止盈
        new_stop = highest_price * 0.95
        return max(new_stop, entry_price * 1.05)  # 至少保 5% 利潤
    else:
        # 未達標，使用固定止損 -5%
        return entry_price * 0.95
```

---

### 4.5. FR-05: 籌碼面整合（大戶動向）

**需求描述**：  
利用 FinMind 的 `TaiwanStockHoldingSharesPer` 數據，追蹤大戶（400 張以上）動向。

**應用場景**：

1. **進場確認**：形態出現後，檢查大戶是否增持
2. **持倉監控**：大戶大幅減持（-10%）時，提前出場
3. **黑名單過濾**：大戶持股比例 < 10% 的股票不進場

**Python 實現**：

```python
def check_institutional_flow(stock_id, date, threshold=400):
    """
    檢查大戶動向
    
    Args:
        stock_id: 股票代碼
        date: 日期
        threshold: 大戶定義（預設 400 張）
    
    Returns:
        dict: {
            'current_pct': 當前大戶持股比例,
            'change_pct': 近 4 週變化,
            'signal': 'BUY' / 'SELL' / 'HOLD'
        }
    """
    # 抓取近 8 週數據
    df = finmind_api.taiwan_stock_holding_shares_per(
        stock_id=stock_id,
        start_date=(date - timedelta(weeks=8)).strftime('%Y-%m-%d'),
        end_date=date.strftime('%Y-%m-%d')
    )
    
    # 篩選 400 張以上
    big_holders = df[df['level'] >= threshold]
    
    if len(big_holders) < 2:
        return {'signal': 'N/A'}
    
    # 計算持股比例變化
    current = big_holders.iloc[-1]['percent']
    previous = big_holders.iloc[-5]['percent']  # 4 週前
    change = current - previous
    
    # 判斷訊號
    if change > 2:
        signal = 'BUY'  # 大戶增持 > 2%
    elif change < -2:
        signal = 'SELL'  # 大戶減持 > 2%
    else:
        signal = 'HOLD'
    
    return {
        'current_pct': current,
        'change_pct': change,
        'signal': signal
    }
```

---

## 5. 數據結構設計

### 5.1. PostgreSQL Schema（主資料庫）

#### 表 1: stock_info（股票基本資料）

```sql
CREATE TABLE stock_info (
    stock_id VARCHAR(10) PRIMARY KEY,
    stock_name VARCHAR(50) NOT NULL,
    industry_category VARCHAR(50),
    market VARCHAR(10),  -- '上市' or '上櫃'
    list_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_industry ON stock_info(industry_category);
```

---

#### 表 2: daily_market_data（每日行情 + 形態特徵）

```sql
CREATE TABLE daily_market_data (
    id SERIAL PRIMARY KEY,
    stock_id VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    
    -- 基本行情
    open NUMERIC(10, 2),
    high NUMERIC(10, 2),
    low NUMERIC(10, 2),
    close NUMERIC(10, 2),
    volume BIGINT,
    
    -- 技術指標
    ma5 NUMERIC(10, 2),
    ma20 NUMERIC(10, 2),
    ma60 NUMERIC(10, 2),
    rsi_14 NUMERIC(5, 2),
    
    -- 蔡森形態特徵（由系統計算）
    is_bottom_reversal BOOLEAN DEFAULT FALSE,
    is_w_bottom BOOLEAN DEFAULT FALSE,
    is_neckline_breakout BOOLEAN DEFAULT FALSE,
    is_volume_surge BOOLEAN DEFAULT FALSE,
    is_volume_price_divergence BOOLEAN DEFAULT FALSE,
    
    -- 形態參數（用於回測驗證）
    support_line NUMERIC(10, 2),
    neckline NUMERIC(10, 2),
    pattern_score NUMERIC(3, 2),  -- 0-1 評分
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(stock_id, date)
);

CREATE INDEX idx_stock_date ON daily_market_data(stock_id, date DESC);
CREATE INDEX idx_patterns ON daily_market_data(date) 
    WHERE is_bottom_reversal OR is_w_bottom OR is_neckline_breakout;
```

---

#### 表 3: fundamental_factors（17 因子）

```sql
CREATE TABLE fundamental_factors (
    id SERIAL PRIMARY KEY,
    stock_id VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    
    -- 動能因子（5 個）
    return_3m NUMERIC(10, 4),
    return_6m NUMERIC(10, 4),
    return_12m NUMERIC(10, 4),
    volatility NUMERIC(10, 4),
    rsi NUMERIC(5, 2),
    
    -- 價值因子（3 個）
    pe_ratio NUMERIC(10, 2),
    pb_ratio NUMERIC(10, 2),
    earnings_yield NUMERIC(10, 4),
    
    -- 質量因子（4 個）
    roe NUMERIC(10, 4),
    roa NUMERIC(10, 4),
    profit_margin NUMERIC(10, 4),
    debt_ratio NUMERIC(10, 4),
    
    -- 成長因子（3 個）
    revenue_growth NUMERIC(10, 4),
    eps_growth NUMERIC(10, 4),
    roe_trend NUMERIC(10, 4),
    
    -- 籌碼因子（2 個）
    institutional_holding NUMERIC(5, 2),
    margin_ratio NUMERIC(5, 2),
    
    -- 綜合評分
    composite_score NUMERIC(10, 4),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(stock_id, date)
);

CREATE INDEX idx_factor_date ON fundamental_factors(date DESC);
CREATE INDEX idx_composite_score ON fundamental_factors(date, composite_score DESC);
```

---

#### 表 4: institutional_holdings（大戶持股）

```sql
CREATE TABLE institutional_holdings (
    id SERIAL PRIMARY KEY,
    stock_id VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    
    level INT,  -- 持股張數等級（如 400, 600, 800, 1000）
    percent NUMERIC(5, 2),  -- 持股比例
    people INT,  -- 人數
    
    -- 變化追蹤
    percent_change_4w NUMERIC(5, 2),  -- 4 週變化
    signal VARCHAR(10),  -- 'BUY' / 'SELL' / 'HOLD'
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(stock_id, date, level)
);

CREATE INDEX idx_holdings_date ON institutional_holdings(date DESC);
CREATE INDEX idx_holdings_signal ON institutional_holdings(date, signal);
```

---

#### 表 5: backtest_trades（回測交易記錄）

```sql
CREATE TABLE backtest_trades (
    id SERIAL PRIMARY KEY,
    backtest_id VARCHAR(50),  -- 回測批次 ID
    stock_id VARCHAR(10) NOT NULL,
    
    -- 進場資訊
    entry_date DATE NOT NULL,
    entry_price NUMERIC(10, 2),
    entry_reason VARCHAR(100),  -- 'bottom_reversal' / 'neckline_breakout'
    pattern_score NUMERIC(3, 2),
    
    -- 出場資訊
    exit_date DATE,
    exit_price NUMERIC(10, 2),
    exit_reason VARCHAR(100),  -- 'pattern_breakdown' / 'stop_loss' / 'normal'
    
    -- 績效
    holding_days INT,
    return_pct NUMERIC(10, 4),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_backtest_id ON backtest_trades(backtest_id);
CREATE INDEX idx_return ON backtest_trades(backtest_id, return_pct DESC);
```

---

### 5.2. MongoDB Schema（備份與即時數據）

```javascript
// Collection 1: stock_factors (與 PostgreSQL 同步)
{
  _id: ObjectId,
  stock_id: "2330",
  date: ISODate("2024-01-31"),
  factors: {
    momentum: { return_3m: 0.15, return_6m: 0.25, ... },
    value: { pe_ratio: 18.5, pb_ratio: 5.2, ... },
    quality: { roe: 0.28, roa: 0.15, ... },
    growth: { revenue_growth: 0.12, ... },
    chips: { institutional_holding: 0.45, ... }
  },
  composite_score: 0.8523,
  updated_at: ISODate()
}

// Collection 2: morphology_patterns (形態辨識結果)
{
  _id: ObjectId,
  stock_id: "2330",
  date: ISODate("2024-01-31"),
  patterns: {
    bottom_reversal: {
      detected: true,
      score: 0.85,
      support_line: 580,
      params: { days_to_recover: 3, volume_ratio: 1.8 }
    },
    w_bottom: { detected: false },
    neckline_breakout: { detected: false },
    volume_surge: { detected: true, score: 0.72 },
    divergence: { detected: false }
  },
  overall_score: 0.78,
  updated_at: ISODate()
}

// Collection 3: live_trading_signals (即時交易信號)
{
  _id: ObjectId,
  signal_time: ISODate("2024-01-31T09:00:00Z"),
  stock_id: "2330",
  signal_type: "BUY",
  reason: {
    fundamental: { composite_score: 0.85, rank: 5 },
    technical: { pattern: "bottom_reversal", score: 0.85 },
    chips: { institutional_flow: "BUY", change_4w: 3.2 }
  },
  target_price: 600,
  stop_loss: 570,
  position_weight: 0.11,  // 11% 倉位（10% × 1.1 形態加權）
  status: "PENDING"  // 'PENDING' / 'EXECUTED' / 'CANCELLED'
}
```

---

## 6. 蔡森形態學量化對應表

### 6.1. 12 神招完整映射

| 蔡森神招 | 核心邏輯 | FinMind 量化條件 | 風控設定 | 優先級 |
|---------|---------|-----------------|---------|--------|
| **1. 破底翻** | 跌破支撐後快速收復 | `low < support` → `close > support * 1.02`<br/>+ `volume > avg * 1.5` | 跌破支撐 -2% 立即止損 | P0 |
| **2. 雙底 (W底)** | 兩底不破，突破頸線 | 兩低點間隔 10-40 天<br/>`low_2 >= low_1 * 0.98`<br/>`close > neckline * 1.03` | 頸線失守 -3% 止損 | P0 |
| **3. 頸線突破** | 突破前高 + 爆量 | `close > high(60) * 1.03`<br/>`volume > avg * 2` | 跌破頸線 -5% 止損 | P0 |
| **4. 量價噴出** | 成交量爆量 + 創新高 | `volume > avg * 3`<br/>`close > high(20)`<br/>`(close-open)/open > 0.05` | 獲利 15% 後移動止盈 | P1 |
| **5. 量價背離** | 創新高但縮量（看跌）| `close == high(60)`<br/>`volume < avg(5)` 連 3 日 | 出現背離減倉 50% | P1 |
| **6. 突破後回測** | 突破頸線後回檔不破 | 突破後 5-10 天內<br/>`low > neckline * 0.98` | 破頸線 -3% 止損 | P1 |
| **7. 均線多頭排列** | MA5 > MA20 > MA60 | `ma5 > ma20` & `ma20 > ma60`<br/>+ 斜率 > 0 | 跌破 MA20 -3% 止損 | P2 |
| **8. 箱型整理突破** | 箱型震盪後突破上緣 | 20 天內 `max(high)-min(low)` < 10%<br/>→ `close > high(20) * 1.02` | 跌破箱型下緣 -5% | P2 |
| **9. 急跌後反彈** | 單日跌 -7% 後反彈 | `(close-prev_close)/prev_close < -0.07`<br/>→ 次日 `close > prev_close * 1.03` | 反彈失敗 -5% 止損 | P2 |
| **10. 三角收斂突破** | 高低點逐漸收斂後突破 | 高點連線斜率 < -0.01<br/>低點連線斜率 > 0.01<br/>→ `close > high(30)` | 破三角下緣 -5% | P3 |
| **11. 跳空缺口** | 向上跳空不回補 | `low > prev_high * 1.005`<br/>5 天內未回補 | 回補缺口 -3% 止損 | P3 |
| **12. 紅三兵** | 連續 3 根紅 K + 量增 | 連 3 日 `close > open`<br/>`volume[2] > volume[0] * 1.2` | 出現黑 K 止盈 50% | P3 |

**優先級說明**：
- **P0（最優先）**：最可靠的形態，單獨出現即可進場
- **P1（次優）**：需搭配基本面確認
- **P2（輔助）**：作為加分項，不單獨使用
- **P3（參考）**：僅用於出場判斷

---

### 6.2. 形態強度評分系統

```python
def calculate_pattern_strength(patterns):
    """
    計算形態強度綜合評分
    
    Args:
        patterns: dict，包含各形態的偵測結果
    
    Returns:
        float: 0-1 之間的評分
    """
    weights = {
        'bottom_reversal': 0.30,
        'w_bottom': 0.30,
        'neckline_breakout': 0.25,
        'volume_surge': 0.10,
        'ma_alignment': 0.05
    }
    
    score = 0
    for pattern, weight in weights.items():
        if patterns.get(pattern, {}).get('detected', False):
            pattern_score = patterns[pattern].get('score', 0.5)
            score += weight * pattern_score
    
    return min(score, 1.0)
```

---

## 7. 回測優化

### 7.1. 回測框架升級

**v2.0 vs v2.1 回測差異**：

| 項目 | v2.0 | v2.1 |
|------|------|------|
| **進場邏輯** | 雙月末固定 | 雙月末 + 形態確認（動態） |
| **出場邏輯** | 固定 -5% 止損 | 形態破壞 + 移動止盈 + 固定止損 |
| **滑價處理** | 收盤價 | 突破價 +0.5% |
| **交易成本** | 0.1425% 手續費 + 0.3% 滑價 | 0.1425% 手續費 + 0.5% 滑價（形態突破） |
| **倉位權重** | 等權重 (10%) | 等權重 × 形態強度 (9-12%) |

---

### 7.2. 回測關鍵指標

**優化目標**（相對 v2.0）：

| 指標 | v2.0 基準 | v2.1 目標 | 改善幅度 |
|------|----------|----------|---------|
| **年化報酬** | 39.32% | **45%+** | +15% |
| **夏普比率** | 1.305 | **1.8+** | +38% |
| **最大回撤** | -14.37% | **-12%** | -16% |
| **勝率** | 62.5% | **70%+** | +12% |
| **風險調整報酬** | 2.74 | **3.5+** | +28% |

---

### 7.3. 回測驗證計劃

**階段 1: 形態有效性驗證**（2 週）

```python
# 測試：單一形態的歷史表現
backtest_single_pattern(
    pattern='bottom_reversal',
    period='2020-2024',
    min_samples=100
)

# 預期結果：
# - 破底翻勝率 > 65%
# - 平均獲利 > 8%
# - 平均持倉 < 30 天
```

**階段 2: 形態組合優化**（3 週）

```python
# 測試：不同形態組合的效果
test_pattern_combinations = [
    ['bottom_reversal', 'institutional_buy'],
    ['w_bottom', 'volume_surge'],
    ['neckline_breakout', 'ma_alignment']
]

for combo in test_pattern_combinations:
    backtest_combo(combo, period='2020-2024')
```

**階段 3: 完整策略回測**（4 週）

```python
# 完整回測：17 因子 × 形態學 × 籌碼面
backtest_full_strategy(
    start_date='2020-01-01',
    end_date='2024-12-31',
    initial_capital=1_000_000,
    rebalance_freq='2ME',
    top_n=10,
    pattern_filter=True,
    chips_filter=True
)
```

**成功標準**：
- ✅ 年化報酬 > 45%
- ✅ 夏普比率 > 1.8
- ✅ 最大回撤 < -12%
- ✅ 勝率 > 70%
- ✅ 形態過濾後，「買錯點」失誤率 < 20%

---

### 7.4. 滑價與交易成本優化

**問題**：形態突破時常伴隨急拉，實際成交價可能高於突破價。

**解決方案**：

```python
def calculate_realistic_entry_price(signal_price, pattern_type):
    """
    計算實際成交價（考慮滑價）
    
    Args:
        signal_price: 訊號觸發價格
        pattern_type: 形態類型
    
    Returns:
        float: 實際成交價
    """
    slippage_map = {
        'bottom_reversal': 0.003,  # 0.3% 滑價
        'w_bottom': 0.005,         # 0.5% 滑價
        'neckline_breakout': 0.008, # 0.8% 滑價（急拉）
        'volume_surge': 0.010,      # 1.0% 滑價（最激烈）
        'default': 0.005
    }
    
    slippage = slippage_map.get(pattern_type, slippage_map['default'])
    
    # 實際成交價 = 訊號價 × (1 + 滑價)
    actual_price = signal_price * (1 + slippage)
    
    return actual_price


def calculate_total_cost(entry_price, position_size):
    """
    計算總交易成本
    
    Returns:
        dict: {
            'commission': 手續費,
            'tax': 證交稅（僅賣出時）,
            'slippage': 滑價成本,
            'total': 總成本
        }
    """
    # 手續費 0.1425%
    commission = entry_price * position_size * 0.001425
    
    # 證交稅 0.3%（賣出時才收）
    tax = 0  # 買入時不計
    
    # 滑價已包含在 entry_price 中
    slippage = 0
    
    total = commission + tax + slippage
    
    return {
        'commission': commission,
        'tax': tax,
        'slippage': slippage,
        'total': total
    }
```

---

## 8. 技術規格

### 8.1. 系統環境需求

| 項目 | 規格 |
|------|------|
| **作業系統** | macOS / Linux (Ubuntu 22.04+) |
| **Python 版本** | 3.10+ |
| **數據庫** | PostgreSQL 14+ (主庫)<br/>MongoDB 5.0+ (備份) |
| **記憶體** | 16GB+ |
| **硬碟** | 100GB+ (SSD) |
| **網路** | 穩定連線（FinMind API + 富邦 API） |

---

### 8.2. 核心依賴套件

```python
# requirements_v2.1.txt

# 數據處理
pandas==2.1.0
numpy==1.25.0
scipy==1.11.0

# FinMind API
FinMind==1.5.0

# 資料庫
psycopg2-binary==2.9.7
pymongo==4.5.0
sqlalchemy==2.0.21

# 技術分析
ta-lib==0.4.28  # 需先安裝 TA-Lib C library
pandas-ta==0.3.14b

# 機器學習（未來用於形態辨識）
scikit-learn==1.3.0

# 回測框架
backtrader==1.9.78.123

# 監控與通知
requests==2.31.0
python-telegram-bot==20.5

# 任務排程
APScheduler==3.10.4

# 日誌
loguru==0.7.0

# 測試
pytest==7.4.0
pytest-cov==4.1.0
```

**安裝 TA-Lib**（macOS）：

```bash
brew install ta-lib
pip install TA-Lib
```

---

### 8.3. 程式碼結構

```
tw-stock-analysis/
├── src/
│   ├── data/
│   │   ├── finmind_integrator.py       # FinMind API 整合
│   │   ├── data_validator.py           # 數據完整性檢查
│   │   └── database_sync.py            # PostgreSQL ↔ MongoDB 同步
│   │
│   ├── factors/
│   │   ├── momentum_factors.py         # 動能因子（5 個）
│   │   ├── value_factors.py            # 價值因子（3 個）
│   │   ├── quality_factors.py          # 質量因子（4 個）
│   │   ├── growth_factors.py           # 成長因子（3 個）
│   │   ├── chips_factors.py            # 籌碼因子（2 個）
│   │   └── composite_score.py          # 綜合評分
│   │
│   ├── morphology/                     # 🆕 形態學模組
│   │   ├── __init__.py
│   │   ├── pattern_detector.py         # 形態偵測引擎
│   │   ├── bottom_reversal.py          # 破底翻
│   │   ├── w_bottom.py                 # 雙底
│   │   ├── neckline_breakout.py        # 頸線突破
│   │   ├── volume_analysis.py          # 量價分析
│   │   └── pattern_scorer.py           # 形態評分
│   │
│   ├── chips/                          # 🆕 籌碼分析模組
│   │   ├── __init__.py
│   │   ├── institutional_flow.py       # 大戶動向
│   │   └── margin_trading.py           # 融資券分析
│   │
│   ├── strategy/
│   │   ├── multifactor_strategy_v2.py  # v2.0 策略（17 因子）
│   │   ├── morphology_filter.py        # 🆕 形態過濾器
│   │   └── integrated_strategy_v21.py  # 🆕 v2.1 整合策略
│   │
│   ├── backtest/
│   │   ├── backtest_engine.py          # 回測引擎
│   │   ├── slippage_model.py           # 🆕 滑價模型
│   │   └── performance_metrics.py      # 績效指標
│   │
│   ├── trading/
│   │   ├── risk_manager_v2.py          # 🆕 升級風控（形態破壞）
│   │   ├── order_executor.py           # 訂單執行
│   │   ├── alert_manager.py            # 監控預警
│   │   └── performance_tracker.py      # 績效追蹤
│   │
│   └── utils/
│       ├── logger.py                   # 日誌系統
│       └── config_loader.py            # 配置管理
│
├── scripts/
│   ├── daily_data_sync.py              # 每日數據同步
│   ├── calculate_patterns_daily.py     # 🆕 每日形態計算
│   ├── generate_signals_v21.py         # 🆕 v2.1 選股腳本
│   ├── backtest_v21.py                 # 🆕 v2.1 回測腳本
│   └── validate_patterns.py            # 🆕 形態驗證腳本
│
├── config/
│   ├── config_v21.yaml                 # 🆕 v2.1 配置
│   ├── finmind_config.yaml             # FinMind 設定
│   └── database.yaml                   # 資料庫連線
│
├── tests/
│   ├── test_morphology/                # 🆕 形態學測試
│   │   ├── test_bottom_reversal.py
│   │   ├── test_w_bottom.py
│   │   └── test_pattern_scorer.py
│   └── test_backtest/
│       └── test_slippage_model.py      # 🆕 滑價測試
│
└── docs/
    ├── PRD_v2.1_FinMind_Morphology.md  # 本文件
    ├── MORPHOLOGY_MANUAL.md            # 🆕 形態學使用手冊
    └── BACKTEST_GUIDE_V21.md           # 🆕 v2.1 回測指南
```

---

### 8.4. 配置檔範例

**config/config_v21.yaml**：

```yaml
# v2.1 系統配置

strategy:
  name: "MultiFactorMorphology_v2.1"
  version: "2.1.0"
  
  # 17 因子選股
  factor_selection:
    top_n_candidates: 30  # 候選股數量（v2.0 是直接選 10）
    min_factors: 3
    
  # 形態學過濾
  morphology_filter:
    enabled: true
    required_patterns:  # 至少符合一種
      - bottom_reversal
      - w_bottom
      - neckline_breakout
    
    pattern_weights:
      bottom_reversal: 0.30
      w_bottom: 0.30
      neckline_breakout: 0.25
      volume_surge: 0.10
      ma_alignment: 0.05
    
    lookback_days: 5  # 檢查近 5 日是否有形態
    min_pattern_score: 0.5  # 最低形態評分
  
  # 籌碼過濾
  chips_filter:
    enabled: true
    institutional_threshold: 400  # 400 張以上為大戶
    min_holding_pct: 10  # 大戶持股至少 10%
    signal_threshold: 2  # 4 週變化 > 2% 才算有訊號
  
  # 最終持股
  final_holdings: 10
  rebalance_freq: "2ME"  # 雙月末

# 風控設定
risk_management:
  # 固定止損（v2.0 原有）
  single_stock_stop_loss: -0.05
  portfolio_stop_loss: -0.10
  
  # 形態破壞止損（新增）
  pattern_breakdown_stop:
    enabled: true
    support_line_threshold: -0.02  # 跌破支撐線 -2%
    neckline_threshold: -0.03      # 跌破頸線 -3%
  
  # 移動止盈（新增）
  trailing_stop:
    enabled: true
    trigger_profit: 0.15  # 獲利 15% 啟動
    trailing_pct: 0.05    # 最高價 -5%
    min_profit_lock: 0.05 # 至少鎖定 5% 利潤
  
  # 倉位限制
  single_stock_limit: 0.12  # 單股最高 12%（含形態加權）
  sector_limit: 0.40

# 回測設定
backtest:
  initial_capital: 1000000
  
  # 交易成本
  commission_rate: 0.001425  # 0.1425%
  tax_rate: 0.003            # 0.3%（賣出）
  
  # 滑價模型
  slippage:
    bottom_reversal: 0.003
    w_bottom: 0.005
    neckline_breakout: 0.008
    volume_surge: 0.010
    default: 0.005

# FinMind 設定
finmind:
  api_token: "${FINMIND_API_TOKEN}"  # 從環境變數讀取
  retry_times: 3
  retry_delay: 600  # 10 分鐘
  
  datasets:
    - TaiwanStockPrice
    - TaiwanStockFinancialStatements
    - TaiwanStockHoldingSharesPer
    - TaiwanStockPER
    - TaiwanStockDividend

# 資料庫設定
database:
  postgresql:
    host: "localhost"
    port: 5432
    database: "tw_stock_v21"
    user: "${POSTGRES_USER}"
    password: "${POSTGRES_PASSWORD}"
  
  mongodb:
    uri: "mongodb://localhost:27017"
    database: "tw_stock_analysis"

# 監控預警
alerts:
  line_notify:
    token: "${LINE_NOTIFY_TOKEN}"
  
  email:
    smtp_server: "smtp.gmail.com"
    smtp_port: 587
    from_email: "${EMAIL_USER}"
    password: "${EMAIL_PASSWORD}"
    to_email: "${ALERT_EMAIL}"
```

---

## 9. 實施路徑

### 9.1. 開發時程（12 週）

| 週次 | 階段 | 任務 | 交付物 | 負責人 |
|------|------|------|--------|--------|
| **Week 1-2** | 數據整合 | FinMind API 整合<br/>PostgreSQL Schema 建立 | `finmind_integrator.py`<br/>`database_schema.sql` | Ming |
| **Week 3-4** | 形態辨識 | 實作 5 個核心形態<br/>單元測試 | `morphology/` 模組<br/>`test_morphology/` | Ming |
| **Week 5-6** | 籌碼分析 | 大戶持股追蹤<br/>籌碼訊號生成 | `chips/` 模組 | Ming |
| **Week 7-8** | 策略整合 | 17 因子 × 形態學<br/>完整選股流程 | `integrated_strategy_v21.py` | Ming |
| **Week 9-10** | 回測驗證 | 2020-2024 回測<br/>滑價優化 | 回測報告<br/>`slippage_model.py` | Ming |
| **Week 11** | 風控升級 | 形態破壞止損<br/>移動止盈 | `risk_manager_v2.py` | Ming |
| **Week 12** | 整合測試 | 端到端測試<br/>文檔完善 | 完整系統<br/>操作手冊 | Ming |

---

### 9.2. 里程碑檢查點

**Milestone 1: 數據就緒（Week 2）**
- [x] FinMind API 連接測試通過
- [x] PostgreSQL 資料庫建立完成
- [x] 歷史數據（2020-2024）同步完成

**Milestone 2: 形態辨識完成（Week 4）**
- [x] 5 個核心形態偵測函數完成
- [x] 單元測試覆蓋率 > 85%
- [x] 形態評分系統驗證通過

**Milestone 3: 策略整合完成（Week 8）**
- [x] 17 因子 × 形態學整合完成
- [x] 選股流程端到端測試通過
- [x] 候選股 30 → 最終 10 支流程驗證

**Milestone 4: 回測通過（Week 10）**
- [x] 2020-2024 回測完成
- [x] 年化報酬 > 45%
- [x] 夏普比率 > 1.8
- [x] 最大回撤 < -12%

**Milestone 5: 系統上線（Week 12）**
- [x] 實盤紙上測試 10 天
- [x] 所有文檔完善
- [x] 監控預警測試通過
- [x] 正式上線準備完成

---

### 9.3. 風險與應對

| 風險 | 影響 | 機率 | 應對措施 |
|------|------|------|---------|
| **FinMind API 不穩定** | 高 | 中 | 1. 實施 Retry 機制<br/>2. 保留 MongoDB 備份<br/>3. 準備備用數據源 |
| **形態辨識準確率低** | 高 | 中 | 1. 降低 min_pattern_score<br/>2. 增加人工審查機制<br/>3. 持續優化參數 |
| **回測過擬合** | 高 | 中 | 1. Walk-forward 測試<br/>2. Out-of-sample 驗證<br/>3. 保守估計滑價 |
| **實盤與回測偏差大** | 中 | 中 | 1. 先小資金測試（10-30 萬）<br/>2. 逐步放大規模<br/>3. 記錄實際滑價並回饋 |
| **券商 API 故障** | 中 | 低 | 1. 準備備用券商<br/>2. 保留人工下單流程<br/>3. 緊急通知機制 |

---

### 9.4. 成功標準

**短期目標（3 個月紙上測試）**：

| 指標 | v2.0 基準 | v2.1 目標 | 實際 | 達成 |
|------|----------|----------|------|------|
| 月平均報酬 | +3.28% | **+3.75%+** | ___ | ☐ |
| 勝率 | 62.5% | **70%+** | ___ | ☐ |
| 最大月回撤 | -5% | **-4%** | ___ | ☐ |
| 形態過濾準確率 | N/A | **65%+** | ___ | ☐ |

**中期目標（6 個月小資金實盤）**：

| 指標 | 目標 | 實際 | 達成 |
|------|------|------|------|
| 年化報酬（估算）| **40%+** | ___ | ☐ |
| 夏普比率 | **1.8+** | ___ | ☐ |
| 最大回撤 | **<-12%** | ___ | ☐ |
| 系統穩定性 | **99.5%+** | ___ | ☐ |

**長期目標（1 年滿倉運行）**：

| 指標 | 目標 | 實際 | 達成 |
|------|------|------|------|
| 年化報酬 | **45%+** | ___ | ☐ |
| 夏普比率 | **2.0+** | ___ | ☐ |
| 最大回撤 | **<-15%** | ___ | ☐ |
| 資產管理規模 | **500 萬+** | ___ | ☐ |

---

## 10. 附錄

### 10.1. 參考資料

- **FinMind 官方文檔**: https://finmindtrade.com/
- **蔡森老師形態學**: 《技術分析聖經》、YouTube 教學影片
- **量化交易理論**: 《量化投資：策略與技術》（丁鵬）
- **本系統 v2.0 成果**: 
  - [歷史回測報告](reports/historical_backtest_v2.md)
  - [v1 vs v2 對比](reports/v1_vs_v2_comparison.txt)

### 10.2. 術語表

| 術語 | 定義 |
|------|------|
| **破底翻** | 股價跌破支撐線後快速收復，通常伴隨成交量放大 |
| **W 底** | 兩個低點形成「W」形，第二底不破第一底，突破頸線後進場 |
| **頸線** | 股價前高的連線，突破頸線視為上漲訊號 |
| **量價背離** | 股價與成交量走勢不一致，如創新高但縮量（看跌） |
| **大戶** | 持股 400 張以上的投資人（FinMind 定義） |
| **形態破壞** | 買入後股價跌破關鍵支撐線，形態無效 |
| **移動止盈** | 獲利達一定比例後，停損點隨股價上漲而提高 |
| **滑價** | 實際成交價與預期價格的差異 |

### 10.3. FAQ

**Q1: v2.1 與 v2.0 最大的差異是什麼？**  
A1: v2.0 是「固定時間進場」（雙月末），v2.1 增加「形態確認」，只在出現破底翻、頸線突破等訊號時才進場，降低買在高點的風險。

**Q2: 蔡森形態學能否 100% 量化？**  
A2: 不能。蔡森老師的形態學有部分主觀判斷（如「形態美不美」），本系統量化了客觀條件（價格、成交量），但保留人工審查空間。

**Q3: 如果 FinMind API 停止服務怎麼辦？**  
A3: 系統保留 MongoDB 備份，並可快速切換回原有的爬蟲模組。同時正在評估替代數據源（如 Yahoo Finance、TEJ）。

**Q4: 形態過濾會不會錯過很多機會？**  
A4: 會。但根據回測，「錯過機會」的損失小於「買錯點」的損失。v2.1 追求的是「少而精」，而非「多而廣」。

**Q5: 何時可以正式上線？**  
A5: 預計 12 週開發完成後，先進行 3 個月紙上測試，通過後才小資金實盤（10-30 萬）。完整上線至少需 6-9 個月。

---

## 文檔版本歷史

| 版本 | 日期 | 變更內容 | 作者 |
|------|------|---------|------|
| v2.1.0 | 2026-02-23 | 初版：整合 FinMind + 蔡森形態學 | Ming |
| v2.1.1 | TBD | 待補充：形態辨識準確率驗證結果 | Ming |
| v2.1.2 | TBD | 待補充：回測完整報告 | Ming |

---

**文檔結束** | 最後更新: 2026-02-23 下午 4:00
