# 🗄️ MongoDB 資料庫管理快速參考

## 📍 目前資料庫位置

```
實體路徑: /opt/homebrew/var/mongodb
配置檔: /opt/homebrew/etc/mongod.conf
目前大小: 102 MB
預估最終: 1-2 GB（完整下載後）
```

---

## 🚀 快速操作

### 1. 立即備份（推薦先做！）

```bash
cd ~/Desktop/Stock/tw-stock-analysis
./backup_mongodb.sh
```

**輸出**：
- 備份檔案：`~/Desktop/Stock/mongodb_backups/tw_stock_analysis_YYYYMMDD_HHMMSS.tar.gz`
- 自動保留最近 7 天備份
- 記錄到 `backup_log.txt`

---

### 2. 還原備份

```bash
# 查看可用備份
./restore_mongodb.sh

# 還原特定備份
./restore_mongodb.sh ~/Desktop/Stock/mongodb_backups/tw_stock_analysis_20260216_153000.tar.gz
```

**注意**：還原會覆蓋現有資料，執行前會要求確認

---

### 3. 查看資料庫狀態

```bash
# 快速檢查
mongosh --eval "
  use tw_stock_analysis
  print('股價:', db.stock_price.count())
  print('法人:', db.institutional_investors.count())
  print('指標:', db.technical_indicators.count())
"

# 詳細統計
mongosh --eval "
  use tw_stock_analysis
  db.stats()
"
```

---

## 📦 完整搬移流程

### 場景 A：搬到同一台電腦的新位置

```bash
# 1. 備份資料
./backup_mongodb.sh

# 2. 停止 MongoDB
brew services stop mongodb-community@7.0

# 3. 修改配置檔
sudo nano /opt/homebrew/etc/mongod.conf
# 修改 dbPath 為新路徑，例如：
#   storage:
#     dbPath: /Users/ming/Documents/mongodb_data

# 4. 建立新目錄
mkdir -p /Users/ming/Documents/mongodb_data
chmod 755 /Users/ming/Documents/mongodb_data

# 5. 啟動 MongoDB
brew services start mongodb-community@7.0
sleep 5

# 6. 還原資料
./restore_mongodb.sh ~/Desktop/Stock/mongodb_backups/tw_stock_analysis_最新備份.tar.gz

# 7. 驗證
mongosh --eval "use tw_stock_analysis; db.stock_price.count()"
```

---

### 場景 B：搬到另一台電腦

**在舊電腦上**：
```bash
# 1. 備份
cd ~/Desktop/Stock/tw-stock-analysis
./backup_mongodb.sh

# 2. 複製備份檔到 USB 或上傳雲端
# 檔案在: ~/Desktop/Stock/mongodb_backups/
```

**在新電腦上**：
```bash
# 1. 安裝 MongoDB
brew install mongodb-community@7.0

# 2. 啟動 MongoDB
brew services start mongodb-community@7.0

# 3. 複製專案和備份檔
# 將整個 tw-stock-analysis 目錄複製過來

# 4. 還原資料
cd ~/Desktop/Stock/tw-stock-analysis
./restore_mongodb.sh <備份檔案路徑>

# 5. 測試
./monitor_download.sh
```

---

### 場景 C：使用 Docker（最簡單）

```bash
# 1. 確保 docker-compose.yml 中有 MongoDB 設定
# 2. 啟動
cd ~/Desktop/Stock/tw-stock-analysis
docker-compose up -d mongodb

# 3. 還原資料（如有備份）
./restore_mongodb.sh <備份檔案>

# 搬移時只需複製整個專案目錄
# 資料在 ./mongodb_data/
```

---

## 🔍 常用指令

### 查看資料庫位置
```bash
ps aux | grep mongod | grep -v grep | grep -o -- '--config [^ ]*'
cat /opt/homebrew/etc/mongod.conf | grep dbPath
```

### 查看資料庫大小
```bash
du -sh /opt/homebrew/var/mongodb
```

### 查看集合列表
```bash
mongosh --eval "use tw_stock_analysis; show collections"
```

### 查看索引
```bash
mongosh --eval "use tw_stock_analysis; db.stock_price.getIndexes()"
```

### 清理資料（謹慎使用！）
```bash
# 清空特定集合
mongosh --eval "use tw_stock_analysis; db.technical_indicators.deleteMany({})"

# 重建索引
mongosh --eval "use tw_stock_analysis; db.stock_price.reIndex()"
```

---

## ⚠️ 注意事項

### 搬移前必做
1. ✅ **先備份**：`./backup_mongodb.sh`
2. ✅ **停止背景程式**：`kill <PID>`（如果正在下載）
3. ✅ **確認空間**：至少需要 3-5 GB

### 搬移時
1. ✅ **完全停止 MongoDB**：`brew services stop mongodb-community@7.0`
2. ✅ **等待程序結束**：`ps aux | grep mongod` 應該沒有結果
3. ✅ **不要在運行時複製資料檔**

### 搬移後
1. ✅ **驗證資料**：檢查文件數是否正確
2. ✅ **測試查詢**：確保功能正常
3. ✅ **更新連線字串**：如果改變了主機或埠號
4. ✅ **重啟背景程式**：如果之前有停止

---

## 📊 推薦方案（針對您）

### 🎯 最佳方案：保持現狀 + 定期備份

**原因**：
- ✅ 目前位置 `/opt/homebrew/var/mongodb` 是標準位置
- ✅ 資料量不大（102 MB → 1-2 GB）
- ✅ 個人使用，不需要遠端存取
- ✅ 本機速度最快

**操作**：
```bash
# 1. 設定每日自動備份（crontab）
crontab -e

# 加入以下行（每天凌晨 3 點備份）
0 3 * * * cd /Users/ming/Desktop/Stock/tw-stock-analysis && ./backup_mongodb.sh

# 2. 或手動定期備份
# 每週執行一次
./backup_mongodb.sh
```

**優點**：
- 無需搬移，零風險
- 定期備份，資料安全
- 速度最快（本機 SSD）
- 維護簡單

---

### 🔄 備選方案：如果需要搬移

**情況 1：硬碟空間不足**
→ 搬到外接硬碟或另一個分區

**情況 2：換新電腦**
→ 使用 `backup_mongodb.sh` + `restore_mongodb.sh`

**情況 3：需要遠端存取**
→ 考慮 MongoDB Atlas（雲端）

**情況 4：正式部署**
→ 使用 Docker + docker-compose

---

## 🎓 學習資源

### MongoDB 指令參考
- 官方文件：https://www.mongodb.com/docs/manual/
- mongodump：https://www.mongodb.com/docs/database-tools/mongodump/
- mongorestore：https://www.mongodb.com/docs/database-tools/mongorestore/

### 相關檔案
- 詳細指南：`DATABASE_MIGRATION_GUIDE.md`
- 備份腳本：`backup_mongodb.sh`
- 還原腳本：`restore_mongodb.sh`
- 監控腳本：`monitor_download.sh`

---

## ✅ 執行檢查清單

### 定期維護（每週）
- [ ] 執行備份：`./backup_mongodb.sh`
- [ ] 檢查備份檔案是否正常
- [ ] 檢查資料庫大小：`du -sh /opt/homebrew/var/mongodb`
- [ ] 清理舊日誌（如需要）

### 搬移前（如需要）
- [ ] 完整備份
- [ ] 記錄連線設定
- [ ] 停止所有相關程式
- [ ] 確認目標位置有足夠空間

### 搬移後
- [ ] 驗證資料完整性
- [ ] 測試所有功能
- [ ] 更新應用程式設定
- [ ] 測試備份流程

---

**建議**：先執行 `./backup_mongodb.sh` 備份一次，確保資料安全！

**文件更新**: 2026-02-16 15:30:00  
**目前狀態**: 資料庫運作正常，背景下載進行中
