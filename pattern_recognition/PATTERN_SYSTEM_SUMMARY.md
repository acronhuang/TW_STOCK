# 形態學12神招 - 完整系統建置報告

## 📊 專案概述

**專案名稱**: 形態學12神招 - 全市場型態掃描系統  
**建置日期**: 2026-02-13  
**版本**: 1.0.0  
**狀態**: ✅ 完成

---

## 🎯 系統特色

### 核心功能

1. **12種經典技術型態自動識別**
   - 6種多頭型態（買入信號）
   - 6種空頭型態（賣出信號）
   - 基於專業技術分析報告建立

2. **全市場並行掃描**
   - 支援多執行緒並行處理
   - 可掃描數千支股票
   - 效能優化設計

3. **精確計算系統**
   - 進場點、停損點、目標價
   - 風險報酬比分析
   - 潛在獲利率計算

4. **多維度篩選**
   - 依型態篩選
   - 依信心度篩選
   - 依風險報酬比篩選
   - 依潛在獲利率篩選

5. **多種輸出格式**
   - 文字報告
   - JSON格式
   - CSV匯出
   - MongoDB儲存

---

## 📁 檔案結構

```
tw-stock-analysis/
└── pattern_recognition/
    ├── patterns_12_masters.py       # 核心型態辨識模組
    ├── market_scanner.py            # 全市場掃描器
    ├── pattern_cli.py               # 命令行工具
    ├── test_patterns.py             # 測試腳本
    ├── PATTERN_12_MASTERS_GUIDE.md  # 完整使用指南
    └── PATTERN_SYSTEM_SUMMARY.md    # 系統總結（本文件）
```

---

## 🔧 已實現功能

### 1. 型態辨識模組 (`patterns_12_masters.py`)

#### 多頭型態（6種）

| 型態名稱 | 檢測函數 | 買點計算 | 目標價計算 | 範例報酬 |
|---------|---------|---------|-----------|---------|
| W底 | `_detect_w_bottom()` | 突破頸線 | 底到頸線等幅 | 14.8% |
| 破底翻 | `_detect_false_breakdown()` | 站回頸線 | 前高 | 20.4% |
| 破底翻W底 | `_detect_false_breakdown_w()` | 突破頸線 | W底等幅 | 29.5% |
| 下飄旗形 | `_detect_falling_flag()` | 突破上緣 | 第一波等幅 | 34% |
| 頭肩底 | `_detect_head_shoulders_bottom()` | 突破頸線 | 頭到頸線等幅 | 40.8% |
| 收斂三角形底 | `_detect_triangle_bottom()` | 突破上緣 | 三角形等高 | 139% |

#### 空頭型態（6種）

| 型態名稱 | 檢測函數 | 賣點計算 | 目標價計算 | 避免損失 |
|---------|---------|---------|-----------|---------|
| 上飄旗形 | `_detect_rising_flag()` | 跌破下緣 | 第一波等幅 | 25.4% |
| M頭 | `_detect_m_top()` | 跌破頸線 | 頭到頸線等幅 | 32% |
| 假突破 | `_detect_false_breakout()` | 跌破頸線 | 突破高度 | 23.1% |
| 頭肩頂 | `_detect_head_shoulders_top()` | 跌破頸線 | 頭到頸線等幅 | 46.2% |
| 假突破頭肩頂 | `_detect_false_breakout_hst()` | 跌破頸線 | 頭到頸線等幅 | 29% |
| 收斂三角形頂 | `_detect_triangle_top()` | 跌破下緣 | 三角形等高 | 62.9% |

#### 關鍵類別

**PatternSignal**
```python
@dataclass
class PatternSignal:
    pattern_name: str       # 型態名稱
    pattern_type: str       # bullish/bearish
    signal_type: str        # buy/sell
    confidence: float       # 信心度
    current_price: float    # 當前價
    neckline: float         # 頸線
    entry_price: float      # 進場價
    stop_loss: float        # 停損價
    target_1: float         # 目標價1
    target_2: float         # 目標價2
    potential_gain: float   # 潛在獲利%
    risk_reward: float      # 風險報酬比
```

**Pattern12Masters**
```python
class Pattern12Masters:
    def scan_all_patterns()      # 掃描所有型態
    def _detect_w_bottom()       # W底檢測
    def _detect_m_top()          # M頭檢測
    # ... 其他檢測函數
```

### 2. 市場掃描器 (`market_scanner.py`)

#### 核心類別

**MarketScanner**
```python
class MarketScanner:
    def get_all_stock_symbols()       # 取得所有股票
    def get_stock_data()              # 取得股票資料
    def scan_single_stock()           # 掃描單一股票
    def scan_market()                 # 掃描市場
    def get_top_opportunities()       # 取得最佳機會
    def generate_report()             # 生成報告
    def export_to_csv()               # 匯出CSV
    def save_to_database()            # 儲存資料庫
```

**PatternScreener**
```python
class PatternScreener:
    def screen_by_criteria()          # 條件篩選
    def get_confirmed_patterns_only() # 只取已確認
    def get_high_confidence_signals() # 高信心度
    def get_best_risk_reward()        # 最佳報酬比
```

#### 使用範例

```python
# 基本掃描
scanner = MarketScanner()
results = scanner.scan_market()

# 進階篩選
screener = PatternScreener(scanner)
filtered = screener.screen_by_criteria(
    min_potential_gain=15.0,
    min_risk_reward=3.0
)
```

### 3. 命令行工具 (`pattern_cli.py`)

#### 支援命令

```bash
# 列出所有型態
python pattern_cli.py list

# 掃描市場
python pattern_cli.py scan
python pattern_cli.py scan --buy                # 只掃描買入
python pattern_cli.py scan --pattern W底        # 指定型態
python pattern_cli.py scan --symbols 2330 2317  # 指定股票

# 顯示最佳機會
python pattern_cli.py top --n 20

# 查看特定股票
python pattern_cli.py stock 2330

# 進階篩選
python pattern_cli.py filter --min-gain 15 --min-rr 3.0
```

#### 特色

- ✅ 彩色輸出
- ✅ 表格化顯示
- ✅ 進度提示
- ✅ 錯誤處理
- ✅ 完整幫助文檔

### 4. 測試系統 (`test_patterns.py`)

#### 測試項目

```bash
# 執行所有測試
python test_patterns.py --test all

# 單項測試
python test_patterns.py --test pattern    # 型態檢測
python test_patterns.py --test scanner    # 掃描器
python test_patterns.py --test screener   # 篩選器
python test_patterns.py --test export     # 匯出功能
python test_patterns.py --test performance # 效能測試
```

#### 測試功能

- ✅ 單一型態檢測驗證
- ✅ 市場掃描器功能測試
- ✅ 篩選器功能測試
- ✅ 匯出功能測試
- ✅ 效能基準測試

---

## 🚀 快速開始

### 1. 環境需求

```bash
Python >= 3.8
MongoDB >= 4.0
pandas, numpy, pymongo
```

### 2. 安裝

```bash
pip install pandas numpy pymongo
```

### 3. 基本使用

```bash
# 掃描全市場
cd /Users/ming/Desktop/Stock/tw-stock-analysis
python pattern_recognition/pattern_cli.py scan

# 查看前20個最佳買入機會
python pattern_recognition/pattern_cli.py top --n 20

# 查看特定股票
python pattern_recognition/pattern_cli.py stock 2330
```

### 4. Python程式使用

```python
from pattern_recognition.market_scanner import MarketScanner

# 建立掃描器並執行掃描
scanner = MarketScanner()
results = scanner.scan_market(
    signal_type='buy',
    min_confidence=0.80
)

# 顯示結果
print(scanner.generate_report())

# 匯出CSV
scanner.export_to_csv('results.csv')
```

---

## 📊 技術規格

### 型態檢測算法

#### 共通參數
- **最小歷史資料**: 60天
- **檢測視窗**: 20-60天
- **價格誤差容許**: 3%
- **預設停損**: 5-7%

#### 計算公式

**W底/M頭**
```
距離 = |頸線 - 底部/頂部|
目標1 = 突破點 ± 距離
目標2 = 目標1 ± 距離
```

**旗形**
```
第一波幅度 = |前高 - 前低|
目標 = 突破點 ± 第一波幅度
```

**頭肩形**
```
距離 = |頭部 - 頸線|
目標1 = 突破點 ± 距離
目標2 = 目標1 ± 距離
```

**三角形**
```
三角高度 = |起點高 - 起點低|
目標1 = 突破點 ± 三角高度
目標2 = 目標1 ± 三角高度
```

### 信心度評分

| 型態 | 基礎信心度 | 調整因素 |
|------|-----------|---------|
| W底 | 0.85 | 量能、突破確認 |
| 破底翻 | 0.80 | 甩轎動作、拉回速度 |
| 破底翻W底 | 0.88 | W底+破底翻 |
| 下飄旗形 | 0.82 | 第一波漲幅 |
| 頭肩底 | 0.86 | 三個低點對稱性 |
| 收斂三角形底 | 0.83 | 突破位置 |
| M頭 | 0.85 | 量能、跌破確認 |
| 假突破 | 0.79 | 回落速度 |
| 頭肩頂 | 0.86 | 三個高點對稱性 |
| 假突破頭肩頂 | 0.83 | 頭肩頂+假突破 |
| 上飄旗形 | 0.81 | 第一波跌幅 |
| 收斂三角形頂 | 0.82 | 跌破位置 |

---

## 📈 實戰應用

### 1. 每日掃描策略

```python
import schedule
import time

def daily_market_scan():
    scanner = MarketScanner()
    results = scanner.scan_market(
        signal_type='buy',
        min_confidence=0.80
    )
    
    # 生成報告
    report = scanner.generate_report()
    
    # 儲存結果
    scanner.save_to_database()
    scanner.export_to_csv(f"scan_{datetime.now().strftime('%Y%m%d')}.csv")
    
    # 發送通知（可自行實現）
    # send_notification(report)

# 每天下午3點執行
schedule.every().day.at("15:00").do(daily_market_scan)

while True:
    schedule.run_pending()
    time.sleep(60)
```

### 2. 風險控管策略

```python
def create_portfolio(total_capital=1000000, max_risk_per_trade=2.0):
    scanner = MarketScanner()
    screener = PatternScreener(scanner)
    
    # 掃描高品質信號
    scanner.scan_market(signal_type='buy', min_confidence=0.85)
    signals = screener.screen_by_criteria(
        min_potential_gain=15.0,
        min_risk_reward=3.0
    )
    
    # 計算倉位
    portfolio = []
    for signal in signals[:10]:
        risk_per_share = signal['current_price'] - signal['stop_loss']
        max_loss = total_capital * (max_risk_per_trade / 100)
        position_size = max_loss / risk_per_share
        
        portfolio.append({
            'symbol': signal['symbol'],
            'shares': int(position_size / 1000) * 1000,
            'entry': signal['current_price'],
            'stop_loss': signal['stop_loss'],
            'target': signal['target_1']
        })
    
    return portfolio
```

### 3. 組合策略

```python
def multi_pattern_strategy():
    scanner = MarketScanner()
    
    # 底部型態組合
    bottom_patterns = ['W底', '破底翻', '頭肩底']
    results = scanner.scan_market(
        pattern_filter=bottom_patterns,
        signal_type='buy',
        min_confidence=0.82
    )
    
    screener = PatternScreener(scanner)
    
    # 篩選條件
    best = screener.screen_by_criteria(
        min_potential_gain=20.0,
        min_risk_reward=3.0,
        patterns=bottom_patterns
    )
    
    return best
```

---

## 🎓 技術型態說明

### 多頭型態詳解

#### 1. W底（雙底）
**特徵**: 
- 兩個低點價格接近（誤差<3%）
- 中間形成反彈頸線
- 突破頸線確認型態

**操作要點**:
- 買點：突破頸線
- 停損：跌破頸線（5-7%）
- 目標：底到頸線的等幅投影

**範例**（迎駕貢酒）:
- 頸線：15.80
- 底部：14.64
- 距離：1.16
- 目標1：16.74（+5.9%）
- 目標2：17.9（+13.3%）
- 實際獲利：14.8%

#### 2. 破底翻
**特徵**:
- 跌破支撐後快速拉回
- 包含「甩轎」動作
- 代表主力在場

**操作要點**:
- 買點：站回頸線
- 停損：頸線或前低
- 目標：前高

**範例**（中國銀行）:
- 頸線：3.43
- 前低：3.32
- 目標：4.37
- 實際獲利：20.4%

#### 3. 下飄旗形
**特徵**:
- 上漲後向下整理
- 形成旗形通道
- 多頭中繼型態

**操作要點**:
- 買點：突破上緣
- 停損：5-7%
- 目標：第一波漲幅等距

**範例**（五糧液）:
- 第一波：50.65→76.76（+26.11）
- 整理低點：64.03
- 突破：76.76
- 目標：90.14（+34%）

### 空頭型態詳解

#### 1. M頭（雙頂）
**特徵**:
- 兩個高點價格接近
- 中間回落形成頸線
- 跌破頸線確認型態

**操作要點**:
- 賣點：跌破頸線
- 停損：站回頸線（5-7%）
- 目標：頭到頸線的等幅投影

**範例**（新華保險）:
- 頭部：72.2
- 頸線：62.1
- 距離：10.1
- 目標1：53.1
- 目標2：43
- 避免損失：32%

#### 2. 頭肩頂
**特徵**:
- 左肩、頭部、右肩
- 頭部最高
- 跌破頸線確認

**操作要點**:
- 賣點：跌破頸線
- 停損：站回頸線
- 目標：頭到頸線等幅下跌

**範例**（石大勝華）:
- 頭部：38.08
- 頸線：30.60
- 距離：7.48
- 目標1：24.85
- 目標2：17.37
- 避免損失：46.2%

---

## ⚠️ 風險提示與建議

### 使用注意事項

1. **信號確認**
   - 等待型態完全確認
   - 注意量能配合
   - 考慮大盤趨勢

2. **停損設定**
   - 嚴格執行停損
   - 單筆風險控制在2-3%
   - 不要頻繁調整停損

3. **分散投資**
   - 不要單一型態過度集中
   - 建議5-10個標的
   - 控制總風險在10-15%

4. **市場環境**
   - 考慮大盤位置
   - 注意產業輪動
   - 留意重大消息

### 系統限制

- 需要至少60天歷史資料
- 某些市場環境下準確度下降
- 無法預測突發事件
- 需配合基本面分析

### 最佳實踐

1. **每日作業**
   - 每天收盤後執行掃描
   - 檢視新出現的型態
   - 追蹤現有部位

2. **週末檢討**
   - 回顧本週信號表現
   - 調整篩選條件
   - 規劃下週策略

3. **持續優化**
   - 記錄交易結果
   - 分析成功失敗案例
   - 優化參數設定

---

## 📞 技術支援

### 系統資訊
- **版本**: 1.0.0
- **建置日期**: 2026-02-13
- **最後更新**: 2026-02-13

### 文件
- 完整使用指南：`PATTERN_12_MASTERS_GUIDE.md`
- 系統總結：`PATTERN_SYSTEM_SUMMARY.md`（本文件）

### 檔案位置
```
/Users/ming/Desktop/Stock/tw-stock-analysis/pattern_recognition/
```

---

## ✅ 完成檢查清單

- [x] 12種技術型態檢測函數
- [x] 全市場掃描器
- [x] 型態篩選器
- [x] 命令行工具
- [x] 測試系統
- [x] 完整文檔
- [x] 使用範例
- [x] 風險管理功能
- [x] CSV/JSON/資料庫輸出
- [x] 效能優化

---

## 🎉 總結

「形態學12神招」系統已完整建置完成，提供：

✅ **12種專業技術型態自動識別**  
✅ **全市場並行掃描能力**  
✅ **精確的買賣點計算**  
✅ **完善的風險控管工具**  
✅ **靈活的篩選與輸出**  
✅ **易用的命令行介面**  
✅ **完整的測試與文檔**

系統已可立即投入使用，協助投資人發掘市場機會，提升交易勝率。

---

<promise>COMPLETE</promise>
