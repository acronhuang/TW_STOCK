# MongoDB 集合整合分析報告

**分析時間**: 2026-02-17  
**目的**: 評估 15 個 MongoDB 集合的整合可能性與必要性

---

## 📊 現況總覽

### 當前集合數: 15 個

```
資料庫: tw_stock_analysis
總記錄數: ~1,980,000+ 筆
磁碟空間: 持續增長中
```

### 集合分類

| 類別 | 集合數 | 記錄總數 | 狀態 |
|-----|-------|---------|------|
| 股票基本資料 | 3 | 5,014 | 🔴 高度重複 |
| 股價數據 | 2 | 923,898 | 🟡 部分重複 |
| 技術指標 | 1 | 36,271 | 🟢 獨立 |
| 法人與籌碼 | 2 | 510,263 | 🟢 獨立 |
| 財報數據 | 3 | 6 | 🔴 結構混亂 |
| 營收與估值 | 3 | 3,189 | 🟢 獨立 |
| 市場統計 | 1 | 8 | 🟢 獨立 |

---

## 🔍 重複性分析

### 🔴 嚴重問題：股票基本資料重複 (3個集合)

#### 1. `stocks` (2,333 筆)
```javascript
{
  _id: ObjectId,
  Code: "2330",
  symbol: "2330",
  Name: "台積電",
  name: "台積電",
  market: "上市"
}
```

#### 2. `company_basic_info` (2,336 筆)
```javascript
{
  _id: ObjectId,
  Code: "2330",
  symbol: "2330",
  Name: "台積電",
  name: "台積電",
  market: "上市"
}
```

#### 3. `tickers` (1,345 筆)
```javascript
{
  _id: ObjectId,
  symbol: "2330",
  date: Date,
  change: 5.0,
  changePercent: 1.2,
  close: 500.0,
  dealersNetBuySell: 123456,
  finiNetBuySell: 789012,
  ...
}
```

**問題分析**:
- ✅ `stocks` 和 `company_basic_info` **完全重複** (欄位相同)
- ⚠️ `tickers` 包含基本資料 + 即時行情數據
- 📊 數據量: 2,333 vs 2,336 (有 3 筆差異)

**結論**: 
- `stocks` 和 `company_basic_info` 可以合併
- `tickers` 應該拆分成「基本資料」和「即時行情」

---

### 🟡 中度問題：股價數據部分重複 (2個集合)

#### 1. `stock_price` (923,895 筆) - **主要來源**
```javascript
{
  _id: ObjectId,
  symbol: "2330",
  date: Date("2026-02-15"),
  open: 495.0,
  high: 505.0,
  low: 490.0,
  close: 500.0,
  volume: 25000000,
  source: "twse_openapi",
  updateTime: Date
}
```

#### 2. `yahoo_prices` (3 筆) - **測試/備份**
```javascript
{
  _id: ObjectId,
  stockId: "2330.TW",
  source: "yahoo",
  downloadTime: Date,
  history: [ /* 陣列格式的歷史價格 */ ]
}
```

**問題分析**:
- ✅ `stock_price` 是標準化格式 (每日一筆記錄)
- ⚠️ `yahoo_prices` 是批次下載格式 (一筆記錄包含多日)
- 📊 數據量懸殊: 923,895 vs 3 筆
- 🎯 `yahoo_prices` 似乎是測試用或備援

**結論**:
- `yahoo_prices` 可以刪除或作為備份
- 如果需要多數據源，應該統一格式後合併至 `stock_price`

---

### 🔴 嚴重問題：財報數據結構混亂 (3個集合)

#### 1. `financial_reports` (0 筆) - **空集合**
```javascript
// 空的，從未使用
```

#### 2. `finmind_financials` (3 筆)
```javascript
{
  _id: ObjectId,
  symbol: "2330",
  year: 2025,
  season: "Q1",
  accountsReceivable: 123456789,
  cash: 987654321,
  currentAssets: 555555555,
  currentLiabilities: 333333333,
  currentRatio: 1.66,
  date: Date,
  ... (31 個欄位)
}
```

#### 3. `yahoo_financials` (3 筆)
```javascript
{
  _id: ObjectId,
  stockId: "2330.TW",
  source: "yahoo",
  currentPrice: 500.0,
  currentRatio: 1.5,
  debtToEquity: 0.3,
  dividendYield: 0.025,
  downloadTime: Date,
  ... (25 個欄位)
}
```

**問題分析**:
- ❌ `financial_reports` 完全未使用，應該刪除
- ⚠️ `finmind_financials` 和 `yahoo_financials` 欄位不同
- 📊 兩者都只有 3 筆測試資料
- 🎯 需要統一財報數據結構

**結論**:
- 刪除 `financial_reports`
- 設計統一的財報集合結構
- 合併 `finmind_financials` 和 `yahoo_financials`

---

## 🟢 運作良好的集合

### 1. `technical_indicators` (36,271 筆)
✅ 用途明確：技術指標計算結果  
✅ 結構清晰：symbol + date + 16 個指標  
✅ 獨立性高：不與其他集合重複  
**建議**: 保持不變

### 2. `institutional_investors` (509,012 筆)
✅ 用途明確：三大法人買賣超  
✅ 數據量大：主要數據來源  
✅ 獨立性高：專屬籌碼數據  
**建議**: 保持不變

### 3. `margin_trading` (1,251 筆)
✅ 用途明確：融資融券數據  
✅ 獨立性高：專屬籌碼數據  
**建議**: 保持不變

### 4. `monthly_revenue` (1,065 筆)
✅ 用途明確：月營收資料  
✅ 獨立性高：營運數據  
**建議**: 保持不變

### 5. `dividends` (1,056 筆)
✅ 用途明確：股利發放記錄  
✅ 獨立性高：配息數據  
**建議**: 保持不變

### 6. `pe_pb_yield` (1,068 筆)
✅ 用途明確：本益比、股價淨值比、殖利率  
✅ 獨立性高：估值指標  
**建議**: 保持不變

### 7. `market_statistics` (8 筆)
✅ 用途明確：大盤統計數據  
✅ 獨立性高：市場整體數據  
**建議**: 保持不變

---

## 🎯 整合方案

### 方案 A：激進整合 (15 → 9 個集合)

#### 刪除/合併:
1. ❌ 刪除 `financial_reports` (空集合)
2. ❌ 刪除 `yahoo_prices` (僅 3 筆測試資料)
3. 🔄 合併 `stocks` + `company_basic_info` → `stock_info` (新)
4. 🔄 拆分 `tickers` → `stock_info` (基本資料) + `real_time_quotes` (即時行情)
5. 🔄 合併 `finmind_financials` + `yahoo_financials` → `financial_statements` (新)

#### 結果:
```
✅ stock_info (新) - 統一的股票基本資料
✅ real_time_quotes (新) - 即時行情
✅ stock_price - 歷史股價 (保持)
✅ technical_indicators - 技術指標 (保持)
✅ institutional_investors - 法人買賣 (保持)
✅ margin_trading - 融資融券 (保持)
✅ financial_statements (新) - 統一財報
✅ monthly_revenue - 月營收 (保持)
✅ dividends - 股利 (保持)
✅ pe_pb_yield - 估值指標 (保持)
✅ market_statistics - 市場統計 (保持)

總計: 11 個集合
```

**優點**:
- 消除重複數據
- 結構更清晰
- 節省空間

**缺點**:
- 需要數據遷移
- 需要更新程式碼

---

### 方案 B：保守優化 (15 → 12 個集合)

#### 僅處理明顯問題:
1. ❌ 刪除 `financial_reports` (空集合)
2. ❌ 刪除 `yahoo_prices` (測試資料)
3. 🔄 合併 `stocks` + `company_basic_info` → `stocks` (保留其一)

#### 結果:
```
保留原有架構，僅刪除 3 個問題集合
總計: 12 個集合
```

**優點**:
- 變動最小
- 風險最低
- 快速執行

**缺點**:
- 仍有部分重複
- `tickers` 混合問題未解決

---

### 方案 C：完整重構 (15 → 8 個集合)

#### 按數據類型完全重構:
1. 📦 `stocks` - 股票主表 (Code, Name, Market, Industry, etc.)
2. 📦 `prices` - 統一價格數據 (歷史 + 即時)
3. 📦 `indicators` - 所有技術指標
4. 📦 `institutions` - 法人 + 融資融券 (合併)
5. 📦 `financials` - 統一財報數據
6. 📦 `operations` - 月營收 + 股利 + 估值 (合併)
7. 📦 `market` - 市場統計
8. 📦 `meta` - 元數據 (數據來源、更新時間等)

**優點**:
- 最佳化結構
- 最少集合數
- 查詢效率最高

**缺點**:
- 大規模重構
- 需要完全重寫程式
- 風險最高

---

## 💡 建議方案

### 推薦：**方案 A (激進整合)** + **分階段執行**

#### 第一階段：立即執行 (低風險)
```bash
# 1. 刪除空集合
db.financial_reports.drop()

# 2. 刪除測試資料
db.yahoo_prices.drop()

# 3. 刪除重複集合 (保留 stocks，刪除 company_basic_info)
db.company_basic_info.drop()
```

**結果**: 15 → 12 個集合  
**時間**: < 5 分鐘  
**風險**: 無

---

#### 第二階段：整合財報 (中風險)
```javascript
// 1. 創建統一財報集合
db.createCollection('financial_statements')

// 2. 遷移 finmind 數據
db.finmind_financials.find().forEach(doc => {
  db.financial_statements.insertOne({
    symbol: doc.symbol,
    year: doc.year,
    season: doc.season,
    source: 'finmind',
    data: doc,
    updateTime: new Date()
  })
})

// 3. 遷移 yahoo 數據
db.yahoo_financials.find().forEach(doc => {
  db.financial_statements.insertOne({
    symbol: doc.stockId.replace('.TW', ''),
    source: 'yahoo',
    data: doc,
    updateTime: new Date()
  })
})

// 4. 驗證後刪除舊集合
db.finmind_financials.drop()
db.yahoo_financials.drop()
```

**結果**: 12 → 10 個集合  
**時間**: 10-15 分鐘  
**風險**: 低 (財報數據僅 6 筆)

---

#### 第三階段：優化 tickers (中風險)
```javascript
// 1. 拆分 tickers 成兩個集合

// 基本資料部分 → 合併到 stocks
db.tickers.find().forEach(doc => {
  db.stocks.updateOne(
    { symbol: doc.symbol },
    { 
      $setOnInsert: {
        symbol: doc.symbol,
        // ... 其他基本資料
      }
    },
    { upsert: true }
  )
})

// 2. 即時行情部分 → 創建新集合
db.createCollection('real_time_quotes')

db.tickers.find().forEach(doc => {
  db.real_time_quotes.insertOne({
    symbol: doc.symbol,
    date: doc.date,
    close: doc.close,
    change: doc.change,
    changePercent: doc.changePercent,
    dealersNetBuySell: doc.dealersNetBuySell,
    finiNetBuySell: doc.finiNetBuySell,
    updateTime: doc.createdAt
  })
})

// 3. 驗證後刪除 tickers
db.tickers.drop()
```

**結果**: 10 → 10 個集合 (tickers 拆分)  
**時間**: 15-20 分鐘  
**風險**: 中 (1,345 筆數據)

---

#### 最終結構 (10 個集合)

```
✅ 股票基本資料 (1個)
   └─ stocks

✅ 價格數據 (2個)
   ├─ stock_price (歷史)
   └─ real_time_quotes (即時)

✅ 技術分析 (1個)
   └─ technical_indicators

✅ 籌碼數據 (2個)
   ├─ institutional_investors
   └─ margin_trading

✅ 財務數據 (4個)
   ├─ financial_statements
   ├─ monthly_revenue
   ├─ dividends
   └─ pe_pb_yield

✅ 市場數據 (1個)
   └─ market_statistics
```

---

## 📊 效益評估

### 空間節省
```
刪除前: 15 個集合
刪除後: 10 個集合
節省: 5 個集合 (33.3%)

重複記錄:
  - stocks + company_basic_info: ~2,333 筆
  - yahoo_prices: 3 筆 (含大量歷史數據)
  
預計節省空間: ~20-30 MB
```

### 維護效益
- ✅ 減少混淆 (哪個是主表?)
- ✅ 提升查詢效率 (少掃描 5 個集合)
- ✅ 簡化程式碼 (統一接口)
- ✅ 降低錯誤率 (單一數據源)

### 風險評估
- 🟢 第一階段: 無風險 (刪除空集合)
- 🟡 第二階段: 低風險 (財報僅 6 筆)
- 🟡 第三階段: 中風險 (需更新查詢代碼)

---

## 🛠️ 執行腳本

### 自動化整合腳本
創建 `scripts/consolidate_collections.py`:

```python
#!/usr/bin/env python3
"""
MongoDB 集合整合腳本
執行方式: python3 scripts/consolidate_collections.py --phase 1
"""

import pymongo
from datetime import datetime
import argparse

def phase_1_delete_empty(db):
    """第一階段：刪除空集合和測試數據"""
    print("=" * 80)
    print("第一階段：刪除無用集合")
    print("=" * 80)
    
    # 1. 刪除空集合
    if 'financial_reports' in db.list_collection_names():
        count = db.financial_reports.count_documents({})
        if count == 0:
            db.financial_reports.drop()
            print("✅ 已刪除空集合: financial_reports")
        else:
            print(f"⚠️  financial_reports 有 {count} 筆數據，跳過")
    
    # 2. 刪除測試數據
    if 'yahoo_prices' in db.list_collection_names():
        count = db.yahoo_prices.count_documents({})
        print(f"⚠️  yahoo_prices 有 {count} 筆數據")
        
        confirm = input("是否刪除 yahoo_prices? (yes/no): ")
        if confirm.lower() == 'yes':
            db.yahoo_prices.drop()
            print("✅ 已刪除: yahoo_prices")
        else:
            print("⏭️  跳過 yahoo_prices")
    
    # 3. 檢查並刪除重複集合
    stocks_count = db.stocks.count_documents({})
    company_count = db.company_basic_info.count_documents({})
    
    print(f"\n📊 stocks: {stocks_count} 筆")
    print(f"📊 company_basic_info: {company_count} 筆")
    
    if abs(stocks_count - company_count) <= 10:
        confirm = input("\n兩個集合數量接近，是否刪除 company_basic_info? (yes/no): ")
        if confirm.lower() == 'yes':
            db.company_basic_info.drop()
            print("✅ 已刪除重複集合: company_basic_info")
        else:
            print("⏭️  保留 company_basic_info")
    
    print("\n✅ 第一階段完成")

def phase_2_merge_financials(db):
    """第二階段：整合財報數據"""
    print("=" * 80)
    print("第二階段：整合財報數據")
    print("=" * 80)
    
    # 創建新集合
    if 'financial_statements' not in db.list_collection_names():
        db.create_collection('financial_statements')
        print("✅ 創建新集合: financial_statements")
    
    # 遷移 finmind 數據
    finmind_count = 0
    for doc in db.finmind_financials.find():
        db.financial_statements.insert_one({
            'symbol': doc.get('symbol'),
            'year': doc.get('year'),
            'season': doc.get('season'),
            'source': 'finmind',
            'data': doc,
            'updateTime': datetime.now()
        })
        finmind_count += 1
    print(f"✅ 遷移 finmind 數據: {finmind_count} 筆")
    
    # 遷移 yahoo 數據
    yahoo_count = 0
    for doc in db.yahoo_financials.find():
        stock_id = doc.get('stockId', '').replace('.TW', '')
        db.financial_statements.insert_one({
            'symbol': stock_id,
            'source': 'yahoo',
            'data': doc,
            'updateTime': datetime.now()
        })
        yahoo_count += 1
    print(f"✅ 遷移 yahoo 數據: {yahoo_count} 筆")
    
    # 驗證
    total = db.financial_statements.count_documents({})
    print(f"\n📊 financial_statements 總數: {total} 筆")
    
    if total == finmind_count + yahoo_count:
        confirm = input("\n數據驗證通過，是否刪除舊集合? (yes/no): ")
        if confirm.lower() == 'yes':
            db.finmind_financials.drop()
            db.yahoo_financials.drop()
            print("✅ 已刪除舊集合")
        else:
            print("⏭️  保留舊集合供驗證")
    else:
        print("❌ 數據驗證失敗，保留舊集合")
    
    print("\n✅ 第二階段完成")

def main():
    parser = argparse.ArgumentParser(description='MongoDB 集合整合工具')
    parser.add_argument('--phase', type=int, choices=[1, 2], required=True,
                       help='執行階段: 1=刪除無用集合, 2=整合財報')
    
    args = parser.parse_args()
    
    # 連接資料庫
    client = pymongo.MongoClient('mongodb://localhost:27017/')
    db = client['tw_stock_analysis']
    
    print(f"\n連接資料庫: tw_stock_analysis")
    print(f"當前集合數: {len(db.list_collection_names())}")
    print()
    
    if args.phase == 1:
        phase_1_delete_empty(db)
    elif args.phase == 2:
        phase_2_merge_financials(db)
    
    print(f"\n最終集合數: {len(db.list_collection_names())}")
    
    client.close()

if __name__ == '__main__':
    main()
```

---

## 📋 執行檢查清單

### 執行前準備
- [ ] 備份 MongoDB 資料庫
  ```bash
  mongodump --db tw_stock_analysis --out /backup/$(date +%Y%m%d)
  ```
- [ ] 確認有足夠磁碟空間
- [ ] 停止正在運行的數據下載程序
- [ ] 記錄當前集合數量和大小

### 第一階段執行
- [ ] 執行 `python3 scripts/consolidate_collections.py --phase 1`
- [ ] 驗證集合數量 (15 → 12)
- [ ] 測試基本查詢功能
- [ ] 確認 stocks 集合完整

### 第二階段執行
- [ ] 執行 `python3 scripts/consolidate_collections.py --phase 2`
- [ ] 驗證 financial_statements 數據完整性
- [ ] 測試財報查詢功能
- [ ] 確認集合數量 (12 → 10)

### 執行後驗證
- [ ] 檢查所有 API 端點
- [ ] 執行測試套件
- [ ] 監控錯誤日誌
- [ ] 更新文檔

---

## 🎯 結論

### 為何有這麼多集合？

**歷史原因**:
1. 📥 多數據源並行 (FinMind, Yahoo, TWSE)
2. 🔧 開發過程中的實驗集合
3. 📦 不同功能模組各自建立集合
4. 🔄 缺乏統一的數據架構設計

### 有機會整合嗎？

**答案：✅ 可以且應該整合**

**整合效益**:
- 減少 33% 集合數量 (15 → 10)
- 消除數據重複
- 提升查詢效率
- 簡化維護成本

**建議時程**:
- 📅 第一階段: 立即執行 (今天)
- 📅 第二階段: 1 週內完成
- 📅 第三階段: 2 週內完成

**風險控制**:
- 🔒 分階段執行
- 💾 每階段前備份
- ✅ 每階段後驗證
- 📝 詳細記錄變更

---

## 📞 後續行動

1. **立即執行**: 刪除無用集合 (無風險)
2. **一週內**: 整合財報數據 (低風險)
3. **兩週內**: 優化 tickers 結構 (中風險)
4. **持續優化**: 監控查詢效能，持續改進

---

**報告結束**

下一步: 執行 `python3 scripts/consolidate_collections.py --phase 1` 開始整合

<promise>COMPLETE</promise>
