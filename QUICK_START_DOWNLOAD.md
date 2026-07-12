# 🚀 快速開始指南

## ⚡ 3 步驟立即使用

### 1️⃣ 安裝依賴（首次執行）
```bash
pip3 install requests pymongo
```

### 2️⃣ 確認 MongoDB 運行
```bash
brew services list | grep mongodb
# 如果未運行：
brew services start mongodb-community
```

### 3️⃣ 執行下載
```bash
cd /Users/ming/Desktop/Stock/tw-stock-analysis
python3 scripts/main_download.py
```

---

## 📋 常用命令

### 下載所有資料（首次）
```bash
python3 scripts/main_download.py
```

### 每日更新（自動跳過已存在）
```bash
python3 scripts/main_download.py
```

### 只下載特定類別
```bash
# 技術面
python3 scripts/main_download.py --categories 技術面

# 籌碼面 + 基本面
python3 scripts/main_download.py --categories 籌碼面 基本面
```

### 強制重新下載
```bash
python3 scripts/main_download.py --force
```

### 查看詳細日誌
```bash
python3 scripts/main_download.py --log-level DEBUG
```

---

## 📊 查看結果

### 檢查日誌
```bash
# 查看最新日誌
ls -lt logs/download_*.log | head -1

# 即時監看
tail -f logs/download_*.log
```

### 檢查資料字典
```bash
cat docs/data_dictionary.md
```

### 查詢 MongoDB
```bash
# 進入 MongoDB Shell
mongosh tw_stock_analysis

# 查看所有集合
show collections

# 查詢資料
db.stock_price.findOne()
db.stock_price.countDocuments({stock_id: "2330"})
```

---

## ⏰ 設定自動排程

### 每天下午 3:30 自動下載（收盤後）
```bash
# 編輯 crontab
crontab -e

# 加入以下行
30 15 * * 1-5 cd /Users/ming/Desktop/Stock/tw-stock-analysis && python3 scripts/main_download.py >> logs/cron.log 2>&1
```

---

## 🐛 故障排除

### 問題：找不到 API Token
```bash
# 解決方案：檢查 .env 檔案
cat .env | grep FINMIND_API_TOKEN

# 應該看到：
FINMIND_API_TOKEN=
```

### 問題：MongoDB 連線失敗
```bash
# 解決方案：啟動 MongoDB
brew services start mongodb-community
```

### 問題：權限錯誤
```bash
# 解決方案：賦予執行權限
chmod +x scripts/main_download.py
```

---

## 📚 進階功能

### 測試系統
```bash
python3 scripts/test_download_system.py
```

### 查看幫助
```bash
python3 scripts/main_download.py --help
```

### 指定 MongoDB URI
```bash
python3 scripts/main_download.py --mongo mongodb://localhost:27017/
```

---

## 📖 完整文件

1. **使用手冊**: [DOWNLOAD_SYSTEM_README.md](DOWNLOAD_SYSTEM_README.md)
2. **完成報告**: [DOWNLOAD_SYSTEM_COMPLETION_REPORT.md](DOWNLOAD_SYSTEM_COMPLETION_REPORT.md)
3. **資料字典**: `docs/data_dictionary.md`（自動生成）
4. **執行日誌**: `logs/download_*.log`（自動生成）

---

## ✅ 系統特色

- ✅ **全自動執行**：無需人工干預
- ✅ **智能跳過**：避免重複下載
- ✅ **自動重試**：網路錯誤自動重試
- ✅ **完整日誌**：所有操作記錄
- ✅ **金融精度**：Decimal128 數值系統
- ✅ **43 個資料表**：涵蓋技術面、籌碼面、基本面

---

**需要協助？** 查看完整文件或檢查日誌檔案。
