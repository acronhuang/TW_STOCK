# 📚 台股智能分析系統 - 完整文件

> **版本**: 2.0  
> **更新日期**: 2026-02-17  
> **狀態**: ✅ 生產就緒

---

## 📖 目錄

1. [系統概述](#系統概述)
2. [核心功能](#核心功能)
3. [資料下載系統](#資料下載系統)
4. [技術指標計算](#技術指標計算)
5. [形態識別系統](#形態識別系統)
6. [資料庫管理](#資料庫管理)
7. [快速開始](#快速開始)
8. [常見問題](#常見問題)

---

## 🎯 系統概述

台股智能分析系統是一個企業級的股票分析平台，整合了：

### 核心技術棧
- **後端**: NestJS 10.0 + TypeScript 5.1
- **資料庫**: MongoDB 7.0 + Redis 7.0
- **分析引擎**: Python 3.14
- **數據源**: FinMind API

### 主要特色
✅ **完整資料下載** - 2,333 檔台股完整歷史數據  
✅ **技術指標分析** - MA(5/10/20/60/120/240/1200)、RSI、MACD、KD、BB  
✅ **形態識別** - 12 種經典買賣形態自動識別  
✅ **多時間週期** - 支援日/週/月/季/半年/年/5年線分析  
✅ **自動化監控** - 背景持續更新，即時監控  

---

## 🚀 核心功能

### 1. 資料下載系統

#### 背景完整下載
```bash
# 啟動背景下載（2,333 檔股票）
nohup /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 \
  scripts/background_full_download.py > full_download.log 2>&1 &

# 檢查下載進度
python3 scripts/check_download_status.py

# 或使用快速監控
./monitor_download.sh
```

#### 下載內容
- **股價數據**: 完整 OHLCV 歷史數據
- **法人數據**: 三大法人買賣超
- **財務報表**: 損益表、資產負債表、現金流量表
- **公司資訊**: 產業分類、股本、市值

#### FinMind API 說明
- **API Token**: 已配置
- **速率限制**: 600 calls/hour
- **數據範圍**: 2007-01-01 至今
- **更新頻率**: 每日盤後更新

> 📖 詳見: [FinMind 數據說明](#finmind-數據說明)

---

### 2. 技術指標計算

#### 計算全部指標
```bash
# 計算單一股票的所有指標
python3 scripts/calculate_all_indicators.py --symbol 2330

# 批次計算（所有有數據的股票）
python3 scripts/calculate_all_indicators.py --all
```

#### 支援的指標

**趨勢指標**:
- MA5, MA10, MA20 (短期均線)
- MA60, MA120 (中期均線)
- MA240, MA1200 (長期均線/5年線)

**動能指標**:
- RSI (14) - 相對強弱指標
- MACD - 指數平滑異同移動平均線
- KD - 隨機指標

**波動指標**:
- BB (布林通道) - 20日標準差
- ATR - 真實波動幅度

**多空指標**:
- 牛熊指標 (Bull/Bear Indicators)
- 河流圖 (River Charts)

#### 計算特定指標
```bash
# 僅計算技術指標
python3 scripts/calculate_technical_indicators.py --symbol 2330

# 僅計算多空指標
python3 scripts/calculate_bull_bear_indicators.py --symbol 2330

# 僅計算河流圖
python3 scripts/calculate_river_charts.py --symbol 2330
```

---

### 3. 形態識別系統

#### 12 種經典形態

**買入形態** (6種):
1. 📈 突破整理 (Breakout)
2. 📈 黃金交叉 (Golden Cross)
3. 📈 W底 (Double Bottom)
4. 📈 頭肩底 (Head & Shoulders Bottom)
5. 📈 上升三角 (Ascending Triangle)
6. 📈 V型反轉 (V-shaped Reversal)

**賣出形態** (6種):
1. 📉 跌破支撐 (Breakdown)
2. 📉 死亡交叉 (Death Cross)
3. 📉 M頭 (Double Top)
4. 📉 頭肩頂 (Head & Shoulders Top)
5. 📉 下降三角 (Descending Triangle)
6. 📉 倒V反轉 (Inverted V Reversal)

#### 使用 Pattern CLI

```bash
# 列出所有形態
python3 pattern_recognition/pattern_cli.py list

# 掃描買入訊號
python3 pattern_recognition/pattern_cli.py scan --buy --min-confidence 0.8

# 掃描賣出訊號
python3 pattern_recognition/pattern_cli.py scan --sell --min-confidence 0.8

# 分析特定股票
python3 pattern_recognition/pattern_cli.py stock 2330

# 快速掃描
python3 pattern_recognition/quick_scan.py --top 50
```

#### 市場掃描器
```bash
# 掃描整個市場
python3 pattern_recognition/market_scanner.py --min-confidence 0.85

# 只掃描高信心度形態
python3 pattern_recognition/market_scanner.py --min-confidence 0.9 --top 20
```

---

### 4. 資料庫管理

#### MongoDB 配置
- **主機**: localhost:27017
- **資料庫**: tw_stock_analysis
- **位置**: `/opt/homebrew/var/mongodb`
- **配置檔**: `/opt/homebrew/etc/mongod.conf`

#### 備份與還原

```bash
# 自動備份（壓縮）
./backup_mongodb.sh

# 還原資料庫
./restore_mongodb.sh /path/to/backup.tar.gz
```

備份位置: `~/Desktop/Stock/mongodb_backups/`

#### 資料庫遷移

**方法 1: mongodump + 壓縮** (推薦)
```bash
# 1. 在舊機器備份
./backup_mongodb.sh

# 2. 複製到新機器
scp mongodb_backup_*.tar.gz user@newserver:~/

# 3. 在新機器還原
./restore_mongodb.sh ~/mongodb_backup_*.tar.gz
```

**方法 2: 直接複製數據檔**
```bash
# 1. 停止 MongoDB
brew services stop mongodb-community

# 2. 複製整個資料目錄
rsync -av /opt/homebrew/var/mongodb/ user@newserver:/path/to/mongodb/

# 3. 在新機器啟動
brew services start mongodb-community
```

> 📖 完整遷移指南請參考獨立文件: `DATABASE_MIGRATION_GUIDE.md`

---

## ⚡ 快速開始

### 1. 安裝依賴

```bash
# Python 依賴
pip3 install pymongo pandas numpy requests ta

# Node.js 依賴（如需使用 Web API）
npm install
```

### 2. 啟動背景下載

```bash
# 啟動背景下載程序
nohup python3 scripts/background_full_download.py > download.log 2>&1 &

# 記下 PID
echo $! > download.pid
```

### 3. 監控進度

```bash
# 即時監控
./monitor_download.sh

# 或使用 Python 腳本
python3 scripts/check_download_status.py
```

### 4. 計算指標

```bash
# 等待下載完成後，計算技術指標
python3 scripts/calculate_all_indicators.py --all
```

### 5. 掃描形態

```bash
# 掃描買入訊號
python3 pattern_recognition/pattern_cli.py scan --buy --min-confidence 0.85
```

---

## 📊 FinMind 數據說明

### FinMind API 提供的原始數據

✅ **有提供**:
- 股價 OHLCV (開高低收量)
- 三大法人買賣超
- 財務報表 (損益表、資產負債表、現金流量表)
- 公司基本資料

❌ **不提供** (需本地計算):
- 技術指標 (MA、RSI、MACD、KD、BB)
- 形態識別結果
- 多空分析
- 河流圖

### 為何需要本地計算？

FinMind 只提供**原始市場數據**，所有技術分析指標都需要在本地計算：

```
原始數據 (FinMind)  →  技術指標計算  →  形態識別  →  投資決策
    ↓                      ↓                ↓
 股價OHLCV          MA/RSI/MACD        買賣訊號
 法人數據              KD/BB           風險評估
 財務報表            多空指標          選股策略
```

### 數據更新流程

1. **下載階段** - `background_full_download.py`
   - 從 FinMind 下載原始數據
   - 儲存到 MongoDB
   - 預計 4-6 天完成 2,333 檔

2. **計算階段** - `calculate_all_indicators.py`
   - 讀取原始股價
   - 計算所有技術指標
   - 更新到資料庫

3. **分析階段** - `pattern_cli.py`
   - 識別形態
   - 生成買賣訊號
   - 評估信心度

> 📖 完整說明: `FINMIND_DATA_EXPLANATION.md`

---

## 🔧 系統維護

### 監控下載進度

```bash
# 方法 1: Shell 腳本（推薦）
./monitor_download.sh

# 方法 2: Python 腳本
python3 scripts/check_download_status.py

# 方法 3: 直接查看日誌
tail -f full_download_20260216.log
```

### 重啟下載程序

```bash
# 停止現有程序
kill $(cat download.pid)

# 重新啟動
./restart_download.sh
```

### 資料庫備份

```bash
# 手動備份
./backup_mongodb.sh

# 設定自動備份（crontab）
0 2 * * * /Users/ming/Desktop/Stock/tw-stock-analysis/backup_mongodb.sh
```

---

## ❓ 常見問題

### Q1: 下載狀態顯示 0% 但實際在運行？

**A**: 這是狀態追蹤的已知問題。請使用 `check_download_status.py` 查看實際進度：

```bash
python3 scripts/check_download_status.py
```

實際進度從日誌檔案讀取，比狀態檔案更準確。

---

### Q2: 為什麼需要計算指標，FinMind 沒有提供嗎？

**A**: FinMind 只提供原始市場數據（股價、成交量、法人數據），不提供技術指標。所有 MA 線、RSI、MACD 等都需要本地計算。

詳見: `FINMIND_DATA_EXPLANATION.md`

---

### Q3: 背景下載需要多久？

**A**: 
- **總股票數**: 2,333 檔
- **預估時間**: 4-6 天
- **API 限制**: 600 calls/hour
- **目前進度**: 可用 `check_download_status.py` 查詢

---

### Q4: 如何遷移到另一台電腦？

**A**: 使用備份還原功能：

```bash
# 舊機器
./backup_mongodb.sh

# 新機器
./restore_mongodb.sh backup.tar.gz
```

完整指南: `DATABASE_MIGRATION_GUIDE.md`

---

### Q5: 記憶體不足怎麼辦？

**A**: 
1. 減少並行處理數量
2. 分批計算指標（不要用 `--all`）
3. 關閉不必要的應用程式
4. 考慮升級記憶體

---

### Q6: 形態識別信心度如何解讀？

**A**:
- **0.9+**: 極高信心，強烈訊號
- **0.8-0.9**: 高信心，可考慮行動
- **0.7-0.8**: 中等信心，謹慎觀察
- **<0.7**: 低信心，僅供參考

---

## 📁 檔案結構

```
tw-stock-analysis/
├── scripts/                          # Python 核心腳本
│   ├── background_full_download.py   # 背景下載主程式
│   ├── check_download_status.py      # 進度檢查
│   ├── calculate_all_indicators.py   # 指標計算（整合）
│   ├── calculate_technical_indicators.py  # 技術指標
│   ├── calculate_bull_bear_indicators.py  # 多空指標
│   └── calculate_river_charts.py     # 河流圖
├── pattern_recognition/              # 形態識別系統
│   ├── pattern_cli.py                # CLI 工具
│   ├── patterns_12_masters.py        # 12 種形態
│   ├── market_scanner.py             # 市場掃描器
│   └── quick_scan.py                 # 快速掃描
├── backup_mongodb.sh                 # 資料庫備份
├── restore_mongodb.sh                # 資料庫還原
├── monitor_download.sh               # 監控腳本
├── restart_download.sh               # 重啟下載
├── download_status.json              # 下載狀態記錄
├── DOCUMENTATION.md                  # 📖 本文件（整合文件）
├── DATABASE_MIGRATION_GUIDE.md       # 資料庫遷移指南
└── README.md                         # 專案說明
```

---

## 🎯 核心檔案說明

### Python 腳本 (6個核心)

| 檔案 | 功能 | 用途 |
|------|------|------|
| `background_full_download.py` | 背景完整下載 | 下載 2,333 檔股票數據 |
| `check_download_status.py` | 狀態檢查 | 即時查看下載進度 |
| `calculate_all_indicators.py` | 整合指標計算 | 一次計算所有指標 |
| `calculate_technical_indicators.py` | 技術指標 | MA/RSI/MACD/KD/BB |
| `calculate_bull_bear_indicators.py` | 多空指標 | 多空力道分析 |
| `calculate_river_charts.py` | 河流圖 | 視覺化多空趨勢 |

### 形態識別 (4個核心)

| 檔案 | 功能 | 用途 |
|------|------|------|
| `pattern_cli.py` | CLI 工具 | 命令列介面 |
| `patterns_12_masters.py` | 12 種形態 | 形態識別核心 |
| `market_scanner.py` | 市場掃描 | 全市場掃描 |
| `quick_scan.py` | 快速掃描 | TOP 50 快速分析 |

---

## 🚦 系統狀態

### 當前狀態 (2026-02-17)

✅ **資料下載**: 進行中 (14.1%, 330/2333)  
✅ **背景程序**: PID 78087 (運行 19+ 小時)  
✅ **資料庫**: MongoDB 正常 (15 集合, 507K+ 記錄)  
✅ **形態識別**: 可用  
✅ **技術指標**: 準備就緒  

---

## 📞 支援與聯絡

### 文件
- 📖 完整文件: `DOCUMENTATION.md` (本文件)
- 🗄️ 資料庫遷移: `DATABASE_MIGRATION_GUIDE.md`
- 📊 FinMind 說明: `FINMIND_DATA_EXPLANATION.md`
- 📈 下載狀態: `DOWNLOAD_STATUS_REPORT.md`

### 日誌檔案
- 下載日誌: `full_download_20260216.log`
- 系統日誌: `logs/` 目錄

---

## 🎉 版本歷史

### v2.0 (2026-02-17)
- ✅ 完成專案清理
- ✅ 精簡至 6 個核心 Python 腳本
- ✅ 刪除 82+ 個重複/舊版檔案
- ✅ 整併文件系統
- ✅ 全面功能測試通過

### v1.0 (2026-02-16)
- ✅ 建立背景下載系統
- ✅ 整合 FinMind API
- ✅ 實作 12 種形態識別
- ✅ 建立資料庫架構

---

## 📜 授權

本專案為私有專案，僅供內部使用。

---

**文件維護**: 2026-02-17  
**系統版本**: 2.0  
**狀態**: ✅ 生產就緒
