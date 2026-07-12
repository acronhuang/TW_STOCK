# 📥 台股資料全自動下載系統

## ✨ 特色

### 1. 全自動執行
- ✅ 無需人工干預，完全自動化
- ✅ 智能跳過已存在資料
- ✅ 自動重試機制（指數退避）
- ✅ 速率限制保護（600 requests/hour）

### 2. 完整日誌記錄
- ✅ 所有操作記錄於 `logs/download_YYYYMMDD_HHMMSS.log`
- ✅ 同時輸出到終端和檔案
- ✅ 分級日誌（DEBUG/INFO/WARNING/ERROR）

### 3. 狀態追蹤
- ✅ 檢查資料是否已存在
- ✅ 避免重複下載
- ✅ 記錄新增/更新/跳過數量

### 4. 自動文件同步
- ✅ 自動更新 `docs/data_dictionary.md`
- ✅ 標註已完成的資料表
- ✅ 包含完整欄位說明

## 📊 支援的資料表（43 個）

### 技術面（9 個）
- 台股總覽
- 台灣股價資料表
- 個股 PER、PBR
- 台股加權指數
- 台股交易日
- 台灣類股股價表
- 每 5 秒委託成交統計
- 當日沖銷交易標的
- 加權、櫃買報酬指數

### 籌碼面（9 個）
- 個股融資融劵表
- 整體市場融資融劵表
- 個股三大法人買賣表
- 整體三大市場法人買賣表
- 外資持股表
- 借券成交明細
- 暫停融券賣出表
- 信用額度總量管制餘額表
- 證券商資訊表

### 基本面（10 個）
- 綜合損益表
- 資產負債表
- 現金流量表
- 股利政策表
- 除權除息結果表
- 月營收表
- 減資恢復買賣參考價格
- 台股下市資料表
- 台股分割後參考價
- 台灣股票變更面額恢復買賣參考價格

### 衍生性金融商品（6 個）
- 期貨日成交資訊
- 選擇權日成交資訊
- 期貨三大法人買賣
- 選擇權三大法人買賣
- 期貨各券商每日交易
- 選擇權各券商每日交易

### 其他（4 個）
- 黃金價格表
- 原油資料表
- 外幣對台幣資料表
- 央行利率資料表
- 台股相關新聞

## 🚀 快速開始

### 1. 環境需求
```bash
# Python 3.8+
python3 --version

# 安裝依賴
pip3 install requests pymongo
```

### 2. 設定 API Token
在 `.env` 檔案中設定：
```bash
FINMIND_API_TOKEN=your_token_here
```

或使用環境變數：
```bash
export FINMIND_API_TOKEN=your_token_here
```

### 3. 執行下載

#### 下載所有資料表
```bash
cd /Users/ming/Desktop/Stock/tw-stock-analysis
python3 scripts/main_download.py
```

#### 下載指定類別
```bash
# 只下載技術面資料
python3 scripts/main_download.py --categories 技術面

# 下載多個類別
python3 scripts/main_download.py --categories 技術面 籌碼面 基本面
```

#### 強制重新下載（不跳過已存在資料）
```bash
python3 scripts/main_download.py --force
```

#### 指定 MongoDB 連線
```bash
python3 scripts/main_download.py --mongo mongodb://localhost:27017/
```

#### 調整日誌等級
```bash
python3 scripts/main_download.py --log-level DEBUG
```

## 📋 使用範例

### 範例 1: 首次完整下載
```bash
# 下載所有 43 個資料表
python3 scripts/main_download.py

# 預期結果：
# - 下載所有資料表
# - 建立索引
# - 生成資料字典
# - 耗時約 10-30 分鐘
```

### 範例 2: 每日更新
```bash
# 只下載有更新的資料（跳過已存在）
python3 scripts/main_download.py

# 預期結果：
# - 自動跳過已有最新資料的表
# - 只下載有更新的資料
# - 耗時約 5-15 分鐘
```

### 範例 3: 針對性下載
```bash
# 只更新技術面和籌碼面資料
python3 scripts/main_download.py --categories 技術面 籌碼面

# 預期結果：
# - 只處理指定類別
# - 節省 API 配額
# - 耗時約 5-10 分鐘
```

## 📊 輸出結果

### 1. 日誌檔案
```
logs/download_20260220_143025.log
```

### 2. 資料字典
```
docs/data_dictionary.md
```

### 3. MongoDB 集合
所有資料儲存在 `tw_stock_analysis` 資料庫中：
```javascript
// 查看所有集合
use tw_stock_analysis
show collections

// 查詢資料
db.stock_price.findOne()
db.institutional_investors_detail.find({stock_id: "2330"}).limit(10)
```

## 🔧 進階配置

### 自動化排程

#### 使用 cron（macOS/Linux）
```bash
# 編輯 crontab
crontab -e

# 每天下午 3:30 執行（收盤後）
30 15 * * 1-5 cd /Users/ming/Desktop/Stock/tw-stock-analysis && python3 scripts/main_download.py >> logs/cron.log 2>&1
```

#### 使用 launchd（macOS 推薦）
創建 `~/Library/LaunchAgents/com.stock.download.plist`：
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.stock.download</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/python3</string>
        <string>/Users/ming/Desktop/Stock/tw-stock-analysis/scripts/main_download.py</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>15</integer>
        <key>Minute</key>
        <integer>30</integer>
        <key>Weekday</key>
        <integer>1-5</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/Users/ming/Desktop/Stock/tw-stock-analysis/logs/launchd.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/ming/Desktop/Stock/tw-stock-analysis/logs/launchd_error.log</string>
</dict>
</plist>
```

載入排程：
```bash
launchctl load ~/Library/LaunchAgents/com.stock.download.plist
```

## 🐛 故障排除

### 問題 1: ModuleNotFoundError
```bash
# 解決方案：安裝依賴
pip3 install requests pymongo
```

### 問題 2: 找不到 API Token
```bash
# 解決方案：設定環境變數
export FINMIND_API_TOKEN=your_token_here

# 或編輯 .env 檔案
nano .env
```

### 問題 3: MongoDB 連線失敗
```bash
# 檢查 MongoDB 是否運行
brew services list | grep mongodb

# 啟動 MongoDB
brew services start mongodb-community
```

### 問題 4: API 配額用盡
```bash
# 等待一小時後重試
# 或檢查 API 使用狀態
python3 -c "from src.downloaders.finmind_client import FinMindClient; import os; client = FinMindClient(os.environ['FINMIND_API_TOKEN']); print(client.get_api_usage())"
```

## 📚 模組架構

```
src/downloaders/
├── __init__.py                 # 模組入口
├── finmind_client.py           # FinMind API 客戶端
│   ├── fetch_data()            # API 請求（帶重試）
│   ├── _convert_to_decimal128() # 數值轉換
│   └── get_api_usage()         # 使用統計
├── table_config.py             # 資料表配置
│   └── DATA_TABLES             # 43 個表的完整定義
└── download_coordinator.py     # 下載協調器
    ├── download_all()          # 下載所有表
    ├── download_table()        # 下載單一表
    └── _save_data()            # 儲存到 MongoDB

scripts/
└── main_download.py            # 主入口程式
```

## 🔐 安全性

- ✅ API Token 存於 `.env` 檔案（不納入版本控制）
- ✅ 環境變數優先於檔案配置
- ✅ 速率限制保護避免封鎖
- ✅ 所有敏感資訊記錄會自動遮罩

## 📈 效能優化

- ✅ 智能跳過已存在資料（節省 50-80% 時間）
- ✅ 批次處理（每批 50-100 檔股票）
- ✅ 索引自動建立（加速查詢）
- ✅ 指數退避重試（避免過度請求）
- ✅ Decimal128 精確數值（金融級精度）

## 📞 支援

遇到問題？
1. 查看日誌檔案：`logs/download_*.log`
2. 檢查資料字典：`docs/data_dictionary.md`
3. 參考完整報告：`PHASE1_COMPLETION_REPORT.md`

## 📝 更新歷史

### v2.0.0 (2026-02-20)
- ✅ 全面重構為模組化架構
- ✅ 移除所有手動確認邏輯
- ✅ 加入自動重試機制
- ✅ 完整日誌記錄
- ✅ 智能狀態追蹤
- ✅ 自動文件同步
- ✅ Decimal128 數值轉換

### v1.0.0 (2026-02-16)
- 初始版本（已刪除）
