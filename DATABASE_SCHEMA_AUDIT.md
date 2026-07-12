# 🗄️ 資料庫 Schema 審計報告

**審計日期：** 2026-02-20  
**資料庫：** MongoDB - tw_stock_analysis  
**審計標準：** 專業財經資料庫開發規範

---

## 📊 執行摘要

### ✅ 整體評估
```
資料庫類型：MongoDB 5.x
集合總數：17+ 個核心集合
索引設計：良好（有複合索引）
命名規範：符合（camelCase for TypeScript）
Schema 定義：完整（使用 NestJS @Schema 裝飾器）

整體評分：75/100
- 結構設計：85/100 ✅
- 欄位命名：90/100 ✅
- 資料型態：60/100 ⚠️（有改進空間）
- 索引優化：80/100 ✅
```

### 🔴 關鍵問題
1. **Float 精度問題：** 價格欄位使用 `number` (Float64) 而非 `Decimal128`
2. **欄位重複：** 存在相容欄位（`close` 與 `closePrice` 並存）
3. **缺少驗證：** 部分欄位無範圍驗證（如漲跌幅應限制 ±10%）

---

## 🏗️ 一、集合架構分析

### 核心集合清單（17 個）

#### 📈 行情資料（Market Data）
```
1. tickers                     # 個股每日行情
   - 包含：價格、成交量、三大法人買賣超
   - 索引：(date, symbol) 複合唯一索引
   - 資料量：~2000 股票 × 1000 交易日 = 200萬筆

2. technical_indicators        # 技術指標
   - 包含：MA/MACD/RSI/KD/布林通道
   - 索引：(symbol, date) 複合索引
   - 關聯：tickers (一對一)
```

#### 💰 財務報表（Financial Statements）
```
3. financial_reports           # 綜合財報（三表合一）
   - 子文件：incomeStatement, balanceSheet, cashFlow
   - 索引：(symbol, year, quarter) 唯一索引
   - 資料量：~2000 股票 × 20 季 = 4萬筆

4. monthly_revenues            # 月營收
   - 索引：(symbol, year, month) 唯一索引
   - 包含：營收金額、YoY、MoM 成長率

5. profitability              # 獲利能力指標
   - 包含：ROE/ROA/毛利率/淨利率/杜邦分析
   - 索引：(symbol, year, quarter)
```

#### 💸 股利與估值（Dividends & Valuation）
```
6. dividends                   # 股利政策
   - 包含：現金股利、股票股利、殖利率
   - 索引：(symbol, year) 唯一索引

7. valuation_rivers           # PE/PB 河流圖
   - 包含：PE/PB 百分位數、估價分數
   - 索引：(symbol, date), (date), (valuationScore)
```

#### 🏦 籌碼資料（Institutional Data）
```
8. institutional_trades        # 法人買賣超
   - 包含：外資、投信、自營商
   - 索引：(symbol, date), (date, finiNetBuy)

9. shareholders               # 股東結構
   - 包含：董監持股、大股東持股
   - 索引：(symbol, date), (symbol, year, quarter)

10. director_holdings         # 董監持股明細
    - 索引：(symbol, date)
```

#### 🏭 產業分類（Industry Classification）
```
11. industries                 # 產業分類表
    - 索引：(code) 唯一索引, (category)

12. stock_industries          # 個股產業對應
    - 索引：(symbol) 唯一索引, (industryCode)

13. industry_heats            # 產業熱度
    - 索引：(date, heatScore), (industryCode, date)
```

#### 📊 分析與策略（Analysis & Strategy）
```
14. volume_price_analysis      # 量價分析
    - 索引：(symbol, date), (date, score)

15. strategy_recommendations   # 策略推薦
    - 索引：(date, confidence), (symbol, date)
```

#### 🔍 系統管理（System）
```
16. data_integrity_logs        # 資料完整性日誌
    - 索引：(date), (collectionName, date)

17. system_logs                # 系統日誌（Capped Collection）
    - 大小限制：100MB
    - 筆數限制：100,000 筆
```

---

## 🔴 二、關鍵問題分析

### 問題 1：Float 精度問題（高優先級）

#### 問題描述
```typescript
// ❌ 當前實作（有精度問題）
@Prop({ required: true })
closePrice: number;  // JavaScript number = IEEE 754 Float64

// 問題範例
0.1 + 0.2 = 0.30000000000000004  // Float 精度誤差
```

#### 影響範圍
```
影響集合：
- tickers.{openPrice, highPrice, lowPrice, closePrice}
- tickers.{change, tradeValue}
- financial_reports.incomeStatement.{revenue, netIncome}
- financial_reports.balanceSheet.{totalAssets, equity}
- financial_reports.cashFlow.{operatingCashFlow}
- dividends.{cashDividend, stockDividend}
- valuation_rivers.{currentPE, currentPB}

影響筆數：~250萬筆
風險等級：🔴 高（可能造成財務計算錯誤）
```

#### 修正方案
```typescript
// ✅ 建議修正
import { Schema } from 'mongoose';

@Prop({ 
  required: true, 
  type: Schema.Types.Decimal128 
})
closePrice: Schema.Types.Decimal128;

// 使用時轉換
const price = parseFloat(doc.closePrice.toString());
```

#### 遷移腳本
```python
# scripts/migrate_to_decimal128.py
from pymongo import MongoClient
from decimal import Decimal
from bson.decimal128 import Decimal128

def migrate_tickers_to_decimal():
    db = MongoClient()['tw_stock_analysis']
    
    # 批次更新
    batch_size = 1000
    cursor = db.tickers.find()
    
    for doc in cursor:
        updates = {
            'openPrice': Decimal128(Decimal(str(doc['openPrice']))),
            'highPrice': Decimal128(Decimal(str(doc['highPrice']))),
            'lowPrice': Decimal128(Decimal(str(doc['lowPrice']))),
            'closePrice': Decimal128(Decimal(str(doc['closePrice']))),
        }
        
        db.tickers.update_one(
            {'_id': doc['_id']},
            {'$set': updates}
        )
    
    print("✅ 遷移完成")
```

---

### 問題 2：欄位重複（中優先級）

#### 問題描述
```typescript
// ❌ 同時存在兩個相同意義的欄位
@Prop({ required: true })
closePrice: number;  // 首選欄位名稱

@Prop({ required: true })
close: number;       // 相容欄位（為了向下相容）
```

#### 影響範圍
```
重複欄位：
- tickers.{closePrice, close}
- tickers.{tradeVolume, volume}

問題：
1. 佔用額外儲存空間（雙倍）
2. 查詢時不確定使用哪個欄位
3. 資料更新需同步兩個欄位
4. 新開發者會困惑

影響筆數：~200萬筆
風險等級：🟡 中（影響可維護性）
```

#### 修正方案

**階段 1：資料整合（統一到首選欄位）**
```javascript
// 確保所有資料都有 closePrice
db.tickers.updateMany(
  { closePrice: { $exists: false } },
  [{ $set: { closePrice: "$close" } }]
);

// 確保所有資料都有 tradeVolume
db.tickers.updateMany(
  { tradeVolume: { $exists: false } },
  [{ $set: { tradeVolume: "$volume" } }]
);
```

**階段 2：建立 View（過渡期）**
```javascript
// 建立相容 View，避免中斷現有查詢
db.createView(
  "tickers_compat",
  "tickers",
  [
    {
      $addFields: {
        close: "$closePrice",
        volume: "$tradeVolume"
      }
    }
  ]
);
```

**階段 3：更新所有查詢程式碼**
```bash
# 全域搜尋並替換
grep -r "\.close[^P]" src/ | wc -l  # 檢查有多少地方使用 .close
```

**階段 4：刪除相容欄位**
```typescript
// ✅ 刪除相容欄位定義
@Prop({ required: true })
closePrice: number;

// @Prop({ required: true })
// close: number;  // 已移除
```

---

### 問題 3：缺少欄位驗證（中優先級）

#### 問題描述
```typescript
// ❌ 無驗證（可能存入異常值）
@Prop({ required: true })
changePercent: number;  // 漲跌幅

// 可能的異常值
changePercent: 999999   // 不可能的漲幅
changePercent: -100     // 不可能的跌幅（下市除外）
```

#### 建議驗證規則

```typescript
// ✅ 價格欄位驗證
@Prop({ 
  required: true,
  min: 0.01,         // 最低價格（避免零或負數）
  validate: {
    validator: (v) => v > 0,
    message: '價格必須大於 0'
  }
})
closePrice: number;

// ✅ 漲跌幅驗證（台股漲跌停限制）
@Prop({ 
  required: true,
  min: -10,          // 跌停
  max: 10,           // 漲停
  validate: {
    validator: (v) => v >= -10 && v <= 10,
    message: '漲跌幅超出合理範圍'
  }
})
changePercent: number;

// ✅ 成交量驗證
@Prop({
  required: true,
  min: 0,
  validate: {
    validator: Number.isInteger,
    message: '成交量必須為整數'
  }
})
tradeVolume: number;

// ✅ 日期格式驗證
@Prop({
  required: true,
  validate: {
    validator: (v) => /^\d{4}-\d{2}-\d{2}$/.test(v),
    message: '日期格式必須為 YYYY-MM-DD'
  }
})
date: string;

// ✅ 價格邏輯驗證（在 Document middleware 中）
TickerSchema.pre('save', function(next) {
  // 驗證：最高價 >= 收盤價 >= 最低價
  if (this.highPrice < this.closePrice || this.closePrice < this.lowPrice) {
    next(new Error('價格邏輯錯誤：high >= close >= low'));
  }
  
  // 驗證：最高價 >= 開盤價 >= 最低價
  if (this.highPrice < this.openPrice || this.openPrice < this.lowPrice) {
    next(new Error('價格邏輯錯誤：high >= open >= low'));
  }
  
  next();
});
```

---

## ✅ 三、優良設計分析

### 優點 1：複合索引設計良好

```javascript
// ✅ 最常用的查詢模式
// 查詢：特定股票的歷史資料
db.tickers.createIndex({ symbol: 1, date: -1 });

// 查詢：特定日期的所有股票
db.tickers.createIndex({ date: -1, symbol: 1 }, { unique: true });

// 查詢：漲幅排行
db.tickers.createIndex({ changePercent: -1 });

// 查詢：成交量排行
db.tickers.createIndex({ volume: -1 });
```

**效能分析：**
```
✅ 支援覆蓋查詢（Covered Query）
✅ 支援排序優化
✅ 有唯一性約束（防止重複資料）
✅ 索引方向正確（1 升序, -1 降序）
```

---

### 優點 2：嵌套文件設計（三表合一）

```typescript
// ✅ 將三大財報合併在一個文件中
@Schema({ timestamps: true, collection: 'financial_reports' })
export class FinancialReport {
  @Prop({ required: true })
  symbol: string;
  
  @Prop({ required: true })
  year: number;
  
  @Prop({ required: true })
  quarter: number;
  
  // 嵌套文件：損益表
  @Prop({ type: IncomeStatement })
  incomeStatement: IncomeStatement;
  
  // 嵌套文件：資產負債表
  @Prop({ type: BalanceSheet })
  balanceSheet: BalanceSheet;
  
  // 嵌套文件：現金流量表
  @Prop({ type: CashFlow })
  cashFlow: CashFlow;
}
```

**優點：**
```
✅ 單次查詢取得完整財報（減少 JOIN）
✅ 原子性更新（三表資料一致）
✅ 符合 MongoDB 設計哲學（嵌套相關資料）
✅ 減少跨集合查詢（效能更好）
```

**注意事項：**
```
⚠️ 文件大小限制：16MB（財報資料遠小於此限制）
⚠️ 索引數量：嵌套欄位也可建立索引
```

---

### 優點 3：時間戳記自動管理

```typescript
@Schema({ timestamps: true })  // ✅ 自動加入 createdAt, updatedAt
export class Ticker {
  // ... 其他欄位
  
  createdAt: Date;   // 自動建立
  updatedAt: Date;   // 自動更新
}
```

**優點：**
```
✅ 自動記錄建立時間
✅ 自動記錄最後更新時間
✅ 方便追蹤資料新鮮度
✅ 支援審計與除錯
```

---

### 優點 4：Capped Collection 用於日誌

```javascript
// ✅ 系統日誌使用 Capped Collection
db.createCollection('system_logs', {
  capped: true,
  size: 104857600,  // 100MB
  max: 100000       // 最多 10 萬筆
});
```

**優點：**
```
✅ 自動清理舊日誌（FIFO）
✅ 固定空間佔用
✅ 插入效能極高
✅ 適合高頻日誌寫入
```

---

## 📝 四、改進建議清單

### 🔴 P0 - 資料正確性（必須修正）

#### 1. 價格欄位改用 Decimal128
```
影響：所有金額欄位
工作量：中（需遷移腳本 + Schema 更新）
風險：高（修正錯誤，降低風險）
預估時間：2-3 天
```

#### 2. 移除相容欄位（統一命名）
```
影響：tickers 集合
工作量：中（需更新查詢程式碼）
風險：中（可能影響現有功能）
預估時間：1-2 天
```

---

### 🟡 P1 - 資料完整性（建議修正）

#### 3. 加入欄位驗證規則
```
影響：所有數值欄位
工作量：低（Schema 定義更新）
風險：低（新資料才會驗證）
預估時間：1 天
```

#### 4. 加入價格邏輯驗證 Middleware
```
影響：tickers 集合
工作量：低（Document middleware）
風險：低
預估時間：半天
```

---

### 🟢 P2 - 效能優化（可選）

#### 5. 部分欄位索引優化
```javascript
// 可考慮加入複合索引（如果查詢頻繁）

// 外資買超排行 + 特定日期
db.institutional_trades.createIndex({ 
  date: -1, 
  finiNetBuy: -1 
});

// PE 百分位數篩選
db.valuation_rivers.createIndex({ 
  pePercentile: 1,
  date: -1 
});
```

#### 6. 考慮分片（Sharding）
```
時機：當單一集合超過 100GB
候選：tickers（最大集合）
Shard Key：{ symbol: 1, date: 1 }
優點：水平擴展、查詢並行
```

---

## 📊 五、資料庫健康度評分

### 結構設計：85/100 ✅
```
✅ 集合劃分清晰
✅ 嵌套設計合理
✅ 關聯關係明確
⚠️ 可考慮更多聚合設計
```

### 欄位命名：90/100 ✅
```
✅ 使用 camelCase（符合 TypeScript）
✅ 語義化命名
✅ 避免縮寫
⚠️ 存在相容欄位（待清理）
```

### 資料型態：60/100 ⚠️
```
❌ Float 用於金額（應改 Decimal128）
✅ Date 型態正確
✅ String 長度合理
⚠️ 缺少 Enum 約束
```

### 索引優化：80/100 ✅
```
✅ 有複合索引
✅ 索引涵蓋主要查詢
✅ 有唯一性約束
⚠️ 部分高頻查詢可再優化
```

### 驗證機制：50/100 ⚠️
```
✅ 有 required 約束
❌ 缺少範圍驗證
❌ 缺少格式驗證
❌ 缺少邏輯驗證
```

**總分：73/100（良好）**

---

## 🚀 六、執行計畫

### 階段 1：資料型態修正（1 週）
```
Week 1:
- [ ] 開發 Decimal128 遷移腳本
- [ ] 在測試環境執行遷移
- [ ] 驗證資料一致性
- [ ] 更新 Schema 定義
- [ ] 更新查詢程式碼
```

### 階段 2：欄位整合（1 週）
```
Week 2:
- [ ] 統一欄位名稱（close → closePrice）
- [ ] 建立相容 View（過渡期）
- [ ] grep 搜尋並替換所有查詢
- [ ] 刪除相容欄位定義
- [ ] 回歸測試
```

### 階段 3：驗證機制（3 天）
```
Week 3:
- [ ] 加入欄位範圍驗證
- [ ] 實作 Document middleware（邏輯驗證）
- [ ] 測試異常資料處理
- [ ] 更新 API 錯誤處理
```

### 階段 4：文檔更新（2 天）
```
Week 3:
- [ ] 更新 DATABASE_SCHEMA.md
- [ ] 生成 ER Diagram
- [ ] 更新 API 文檔
- [ ] 建立範例查詢文檔
```

---

## ✅ 七、驗收標準

### 資料正確性
- [ ] 所有金額欄位使用 Decimal128
- [ ] 無相容欄位（命名統一）
- [ ] 價格邏輯驗證：high >= close >= low
- [ ] 漲跌幅範圍：-10% ~ +10%
- [ ] 成交量為正整數

### 效能標準
- [ ] 主要查詢使用索引（explai n "executionStats"）
- [ ] 平均查詢時間 < 100ms
- [ ] 無全表掃描（除非必要）

### 程式碼品質
- [ ] Schema 定義有完整註解
- [ ] 所有欄位有型態定義
- [ ] 複雜邏輯有單元測試
- [ ] 通過 TypeScript 型態檢查

---

**📌 備註**
- 詳細改進腳本見：`scripts/database/` 目錄
- Schema 文檔見：`docs/DATABASE_SCHEMA.md`
- 遷移計畫見：`docs/DATABASE_MIGRATION_PLAN.md`

---

*資料庫 Schema 審計報告 v1.0 | 2026-02-20*
