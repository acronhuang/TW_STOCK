# 形態學12神招 - 全市場掃描器使用指南

## 📋 目錄

1. [系統概述](#系統概述)
2. [12種技術型態說明](#12種技術型態說明)
3. [安裝與設定](#安裝與設定)
4. [使用方法](#使用方法)
5. [API參考](#api參考)
6. [實戰範例](#實戰範例)

---

## 系統概述

「形態學12神招」是根據專業技術分析報告建立的標準化型態識別系統，能夠自動掃描全市場股票，識別12種經典技術型態，並提供精確的買賣信號。

### 核心功能

- ✅ 自動識別12種經典技術型態
- ✅ 精確計算進場點、停損點、目標價
- ✅ 風險報酬比分析
- ✅ 全市場並行掃描
- ✅ 多維度篩選條件
- ✅ 支援CSV/JSON/資料庫輸出

---

## 12種技術型態說明

### 🟢 多頭型態（6種）

#### 1. W底（雙底）
- **特徵**: 兩個低點形成W型，突破頸線確認
- **信號**: 多頭買進
- **計算**: 距離 = 頸線 - 底部，目標 = 突破點 + 距離
- **範例**: 頸線15.80，底部14.64，目標16.74、17.9
- **最大獲利**: 14.8%

#### 2. 破底翻
- **特徵**: 跌破支撐後快速拉回（甩轎動作）
- **信號**: 難得的多頭買進訊號
- **操作**: 站回頸線後買進，頸線為停損
- **範例**: 站回3.43後買進，目標4.37
- **最大獲利**: 20.4%

#### 3. 破底翻（W底）
- **特徵**: W底的第二隻腳破底後拉回
- **信號**: 更安全的底部佈局
- **操作**: 等待時間越長，獲利空間越大
- **範例**: 突破16.12，目標18.38、20.64
- **最大獲利**: 29.5%

#### 4. 下飄旗形
- **特徵**: 上漲後向下整理形成旗形
- **信號**: 多頭波段中繼型態
- **計算**: 第一波漲幅 = 前高 - 前低，目標 = 突破點 + 漲幅
- **範例**: 第一波漲26.11，突破76.76，目標90.14
- **最大獲利**: 34%

#### 5. 頭肩底
- **特徵**: 左肩、頭部、右肩，頭部最低
- **信號**: 行情由弱轉強
- **計算**: 距離 = 頸線 - 頭部，目標 = 突破點 + 距離
- **範例**: 突破22.48，目標27.07、31.66
- **最大獲利**: 40.8%

#### 6. 收斂三角形底
- **特徵**: 高點降低、低點升高形成三角形
- **信號**: 需在1/2到3/4處突破
- **計算**: 目標 = 突破點 + 三角形高度
- **範例**: 突破3.15，目標5.35、7.55
- **最大獲利**: 139%

### 🔴 空頭型態（6種）

#### 7. 上飄旗形
- **特徵**: 下跌後向上整理形成旗形
- **信號**: 空頭波段中繼型態
- **計算**: 第一波跌幅 = 前高 - 前低，目標 = 跌破點 - 跌幅
- **範例**: 第一波跌7.46，跌破19.73，目標14.72
- **最大避免損失**: 25.4%

#### 8. M頭（雙頂）
- **特徵**: 兩個高點形成M型，跌破頸線確認
- **信號**: 空單進場
- **計算**: 距離 = 頭部 - 頸線，目標 = 跌破點 - 距離
- **範例**: 跌破63.2，目標53.1、43
- **最大避免損失**: 32%

#### 9. 假突破
- **特徵**: 突破整理區後又跌回（騙線）
- **信號**: 高檔震盪出貨信號
- **操作**: 跌破頸線確認後進場
- **範例**: 跌破16.24確認，目標10.91
- **最大避免損失**: 23.1%

#### 10. 頭肩頂
- **特徵**: 左肩、頭部、右肩，頭部最高
- **信號**: 行情由強轉弱
- **計算**: 距離 = 頭部 - 頸線，目標 = 跌破點 - 距離
- **範例**: 跌破32.33，目標24.85、17.37
- **最大避免損失**: 46.2%

#### 11. 假突破（頭肩頂）
- **特徵**: 頭肩頂假突破結構
- **信號**: 更早判斷高檔轉弱
- **操作**: 跌破頸線前即可佈空
- **範例**: 跌破50.15確認，目標35.58
- **最大避免損失**: 29%

#### 12. 收斂三角形頂
- **特徵**: 高點降低、低點升高形成三角形
- **信號**: 需在1/2到3/4處跌破
- **計算**: 目標 = 跌破點 - 三角形高度
- **範例**: 跌破16.5，目標6.11
- **最大避免損失**: 62.9%

---

## 安裝與設定

### 1. 系統需求

```bash
Python >= 3.8
MongoDB >= 4.0
```

### 2. 安裝依賴

```bash
pip install pandas numpy pymongo
```

### 3. 資料庫設定

確保MongoDB運行並包含以下集合：
- `stock_info`: 股票基本資訊
- `daily_price`: 每日價格資料
- `pattern_signals`: 型態信號（自動建立）

---

## 使用方法

### 命令行使用

#### 1. 掃描全市場

```bash
# 掃描所有股票的所有型態
python market_scanner.py

# 只掃描買入信號
python market_scanner.py --signal-type buy

# 只掃描賣出信號
python market_scanner.py --signal-type sell

# 設定最低信心度
python market_scanner.py --min-confidence 0.85
```

#### 2. 指定型態掃描

```bash
# 只掃描W底型態
python market_scanner.py --pattern W底

# 只掃描頭肩底型態
python market_scanner.py --pattern 頭肩底

# 只掃描M頭型態
python market_scanner.py --pattern M頭
```

#### 3. 指定股票掃描

```bash
# 掃描特定股票
python market_scanner.py --symbols 2330 2317 2454

# 掃描特定股票的買入信號
python market_scanner.py --symbols 2330 2317 --signal-type buy
```

#### 4. 輸出格式

```bash
# 文字格式（預設）
python market_scanner.py --output text

# JSON格式
python market_scanner.py --output json

# CSV格式
python market_scanner.py --output csv

# 儲存到資料庫
python market_scanner.py --save-db
```

#### 5. 顯示前N個機會

```bash
# 顯示前10個最佳機會
python market_scanner.py --top 10

# 顯示前50個最佳機會
python market_scanner.py --top 50
```

### Python程式使用

#### 基本使用

```python
from pattern_recognition.market_scanner import MarketScanner

# 建立掃描器
scanner = MarketScanner()

# 掃描全市場
results = scanner.scan_market()

# 生成報告
report = scanner.generate_report()
print(report)
```

#### 進階使用

```python
from pattern_recognition.market_scanner import MarketScanner, PatternScreener

# 建立掃描器
scanner = MarketScanner()

# 掃描特定型態
results = scanner.scan_market(
    pattern_filter=['W底', '破底翻', '頭肩底'],
    signal_type='buy',
    min_confidence=0.80
)

# 建立篩選器
screener = PatternScreener(scanner)

# 篩選高品質信號
high_quality = screener.screen_by_criteria(
    min_potential_gain=15.0,  # 最少15%獲利
    min_risk_reward=3.0,      # 風險報酬比3:1以上
    max_formation_days=40     # 形成時間不超過40天
)

print(f"找到 {len(high_quality)} 個高品質信號")

# 取得最佳風險報酬比
best_rr = screener.get_best_risk_reward(10)
for signal in best_rr:
    print(f"{signal['symbol']}: {signal['pattern_name']}, "
          f"報酬比 {signal['risk_reward']:.2f}:1")
```

---

## API參考

### MarketScanner類

#### 初始化
```python
scanner = MarketScanner(
    mongo_uri='mongodb://localhost:27017/',
    db_name='tw_stock_data'
)
```

#### 主要方法

**scan_market()**
```python
results = scanner.scan_market(
    symbols=None,              # 股票列表（None=全部）
    pattern_filter=None,       # 型態篩選
    signal_type=None,          # 'buy'/'sell'/None
    min_confidence=0.75,       # 最低信心度
    max_workers=10             # 並行執行緒數
)
```

**get_top_opportunities()**
```python
top_20 = scanner.get_top_opportunities(
    n=20,                      # 取得數量
    signal_type='buy'          # 信號類型
)
```

**generate_report()**
```python
report = scanner.generate_report(
    output_format='text'       # 'text'/'json'/'html'
)
```

**export_to_csv()**
```python
scanner.export_to_csv('results.csv')
```

**save_to_database()**
```python
scanner.save_to_database()
```

### PatternScreener類

#### 初始化
```python
screener = PatternScreener(scanner)
```

#### 主要方法

**screen_by_criteria()**
```python
filtered = screener.screen_by_criteria(
    min_potential_gain=10.0,   # 最小潛在獲利%
    min_risk_reward=2.0,       # 最小風險報酬比
    max_formation_days=60,     # 最大形成天數
    patterns=None              # 指定型態列表
)
```

**get_confirmed_patterns_only()**
```python
confirmed = screener.get_confirmed_patterns_only()
```

**get_high_confidence_signals()**
```python
high_conf = screener.get_high_confidence_signals(min_confidence=0.85)
```

**get_best_risk_reward()**
```python
best_rr = screener.get_best_risk_reward(n=10)
```

---

## 實戰範例

### 範例1：尋找最佳W底機會

```python
from pattern_recognition.market_scanner import MarketScanner, PatternScreener

# 建立掃描器
scanner = MarketScanner()

# 只掃描W底型態的買入信號
results = scanner.scan_market(
    pattern_filter=['W底'],
    signal_type='buy',
    min_confidence=0.80
)

print(f"找到 {len(results)} 個W底型態")

# 取得前10個最佳機會
top_10 = scanner.get_top_opportunities(10, 'buy')

for i, signal in enumerate(top_10, 1):
    print(f"\n{i}. {signal['symbol']} - W底型態")
    print(f"   當前價: {signal['current_price']:.2f}")
    print(f"   頸線: {signal['neckline']:.2f}")
    print(f"   目標1: {signal['target_1']:.2f}")
    print(f"   目標2: {signal['target_2']:.2f}")
    print(f"   停損: {signal['stop_loss']:.2f}")
    print(f"   潛在獲利: {signal['potential_gain']:.2f}%")
    print(f"   風險報酬比: {signal['risk_reward']:.2f}:1")
```

### 範例2：尋找破底翻機會

```python
# 掃描破底翻型態
results = scanner.scan_market(
    pattern_filter=['破底翻', '破底翻W底'],
    signal_type='buy',
    min_confidence=0.75
)

# 篩選高品質信號
screener = PatternScreener(scanner)
high_quality = screener.screen_by_criteria(
    min_potential_gain=15.0,
    min_risk_reward=2.5,
    patterns=['破底翻', '破底翻W底']
)

print(f"找到 {len(high_quality)} 個高品質破底翻信號")

# 匯出為CSV
scanner.export_to_csv('破底翻_機會.csv')
```

### 範例3：每日自動掃描

```python
import schedule
import time
from datetime import datetime

def daily_scan():
    """每日掃描任務"""
    print(f"\n{'='*60}")
    print(f"開始每日掃描: {datetime.now()}")
    print(f"{'='*60}")
    
    scanner = MarketScanner()
    
    # 掃描買入信號
    buy_results = scanner.scan_market(
        signal_type='buy',
        min_confidence=0.80
    )
    
    # 生成報告
    report = scanner.generate_report()
    print(report)
    
    # 儲存到資料庫
    scanner.save_to_database()
    
    # 匯出CSV
    filename = f"scan_{datetime.now().strftime('%Y%m%d')}.csv"
    scanner.export_to_csv(filename)
    
    print(f"\n掃描完成，結果已儲存至 {filename}")

# 設定每天下午3點執行
schedule.every().day.at("15:00").do(daily_scan)

# 立即執行一次
daily_scan()

# 持續運行
while True:
    schedule.run_pending()
    time.sleep(60)
```

### 範例4：組合策略掃描

```python
def find_best_opportunities():
    """尋找最佳投資機會"""
    scanner = MarketScanner()
    
    # 掃描多頭型態
    bullish_patterns = ['W底', '破底翻', '破底翻W底', '下飄旗形', '頭肩底', '收斂三角形底']
    
    results = scanner.scan_market(
        pattern_filter=bullish_patterns,
        signal_type='buy',
        min_confidence=0.80
    )
    
    screener = PatternScreener(scanner)
    
    # 篩選條件
    best = screener.screen_by_criteria(
        min_potential_gain=20.0,    # 最少20%獲利空間
        min_risk_reward=3.0,        # 風險報酬比3:1以上
        max_formation_days=45       # 形成時間不超過45天
    )
    
    # 只要已確認的型態
    confirmed = [s for s in best if s['status'] == 'confirmed']
    
    # 按風險報酬比排序
    confirmed.sort(key=lambda x: x['risk_reward'], reverse=True)
    
    print(f"\n找到 {len(confirmed)} 個最佳投資機會：")
    print("="*80)
    
    for i, signal in enumerate(confirmed[:10], 1):
        print(f"\n{i}. {signal['symbol']} - {signal['pattern_name']}")
        print(f"   當前價: {signal['current_price']:.2f}")
        print(f"   目標價: {signal['target_1']:.2f} ({signal['potential_gain']:.1f}%)")
        print(f"   停損價: {signal['stop_loss']:.2f}")
        print(f"   風險報酬比: {signal['risk_reward']:.2f}:1")
        print(f"   信心度: {signal['confidence']*100:.1f}%")
    
    return confirmed

# 執行
best_opportunities = find_best_opportunities()
```

### 範例5：風險控管策略

```python
def risk_managed_portfolio(max_risk_per_trade=2.0, total_capital=1000000):
    """
    風險控管投資組合
    
    參數:
        max_risk_per_trade: 每筆交易最大風險%
        total_capital: 總資本
    """
    scanner = MarketScanner()
    screener = PatternScreener(scanner)
    
    # 掃描高信心度信號
    scanner.scan_market(signal_type='buy', min_confidence=0.85)
    high_conf = screener.get_high_confidence_signals(0.85)
    
    # 只要確認的型態
    confirmed = [s for s in high_conf if s['status'] == 'confirmed']
    
    # 計算每筆交易的倉位
    portfolio = []
    
    for signal in confirmed[:10]:  # 最多10個標的
        # 計算風險
        risk_per_share = signal['current_price'] - signal['stop_loss']
        risk_percent = (risk_per_share / signal['current_price']) * 100
        
        # 計算倉位（風險不超過max_risk_per_trade%）
        max_loss = total_capital * (max_risk_per_trade / 100)
        position_size = max_loss / risk_per_share
        position_value = position_size * signal['current_price']
        
        portfolio.append({
            'symbol': signal['symbol'],
            'pattern': signal['pattern_name'],
            'entry_price': signal['current_price'],
            'stop_loss': signal['stop_loss'],
            'target': signal['target_1'],
            'shares': int(position_size / 1000) * 1000,  # 整千股
            'position_value': position_value,
            'max_loss': max_loss,
            'potential_gain': signal['potential_gain'],
            'risk_reward': signal['risk_reward']
        })
    
    # 顯示投資組合
    print("\n風險控管投資組合")
    print("="*80)
    print(f"總資本: {total_capital:,.0f}")
    print(f"單筆最大風險: {max_risk_per_trade}%")
    print("\n")
    
    total_position = 0
    for i, pos in enumerate(portfolio, 1):
        print(f"{i}. {pos['symbol']} - {pos['pattern']}")
        print(f"   進場價: {pos['entry_price']:.2f}")
        print(f"   停損價: {pos['stop_loss']:.2f}")
        print(f"   目標價: {pos['target']:.2f}")
        print(f"   股數: {pos['shares']:,} 股")
        print(f"   倉位金額: {pos['position_value']:,.0f}")
        print(f"   最大虧損: {pos['max_loss']:,.0f} ({max_risk_per_trade}%)")
        print(f"   潛在獲利: {pos['potential_gain']:.1f}%")
        print(f"   風險報酬比: {pos['risk_reward']:.2f}:1")
        print()
        
        total_position += pos['position_value']
    
    print(f"總投入資金: {total_position:,.0f} ({total_position/total_capital*100:.1f}%)")
    print(f"預留現金: {total_capital-total_position:,.0f} ({(total_capital-total_position)/total_capital*100:.1f}%)")
    
    return portfolio

# 執行
portfolio = risk_managed_portfolio(max_risk_per_trade=2.0, total_capital=1000000)
```

---

## 注意事項

### 使用建議

1. **信號確認**: 建議等待型態完全確認後再進場
2. **停損設定**: 嚴格執行停損，保護資本
3. **分散投資**: 不要把所有資金集中在單一型態
4. **量能配合**: 注意成交量是否配合型態突破
5. **市場環境**: 考慮大盤趨勢和市場氣氛

### 風險提示

- 技術型態僅供參考，不保證100%準確
- 過去表現不代表未來結果
- 請配合基本面分析
- 建議設定適當的停損
- 控制單筆交易風險在總資本的2-3%以內

### 系統限制

- 需要至少60天的歷史資料
- 某些型態可能產生誤判
- 極端市場環境下效果可能下降
- 需定期更新資料以保持準確性

---

## 技術支援

如有問題或建議，請聯繫技術團隊。

**版本**: 1.0.0  
**更新日期**: 2026-02-13  
**作者**: 技術分析系統團隊

---

<promise>COMPLETE</promise>
