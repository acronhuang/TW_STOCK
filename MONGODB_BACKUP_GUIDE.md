# MongoDB 備份系統完整指南

**更新時間**: 2026-02-22  
**系統狀態**: ✅ 已安裝並正常運行  

---

## 📦 系統概覽

### 備份策略
- **自動備份**: 每週日凌晨 1:00 自動執行
- **備份位置**: `~/Desktop/Stock/mongodb_backups/`
- **保留策略**: 自動清理 30 天前的舊備份
- **備份格式**: tar.gz 壓縮檔案
- **預計大小**: 180-200 MB/個

### 備份內容
- **資料庫**: tw_stock_analysis
- **包含集合**: 所有集合（stock_price, institutional_investors, dividend_results 等）
- **索引**: 自動備份所有索引定義

---

## 🚀 快速開始

### 立即執行備份
```bash
cd /Users/ming/Desktop/Stock/tw-stock-analysis
./backup_mongodb.sh
```

### 查看現有備份
```bash
ls -lht ~/Desktop/Stock/mongodb_backups/*.tar.gz | head -10
```

### 還原備份
```bash
cd /Users/ming/Desktop/Stock/tw-stock-analysis
./restore_mongodb.sh ~/Desktop/Stock/mongodb_backups/tw_stock_analysis_YYYYMMDD_HHMMSS.tar.gz
```

---

## ⚙️ 自動備份系統

### launchd 服務配置

**服務名稱**: `com.twstock.weekly_mongodb_backup`

**執行時間**: 
- 每週日凌晨 1:00
- 在 outstanding_shares 更新（02:00）之前
- 在 log_cleanup（03:00）之前

**配置文件**: `~/Library/LaunchAgents/com.twstock.weekly_mongodb_backup.plist`

### 服務管理命令

#### 查看服務狀態
```bash
launchctl list | grep mongodb_backup
```

**正常輸出**: 
```
-    0    com.twstock.weekly_mongodb_backup
```

#### 手動啟動/停止服務
```bash
# 停止服務
launchctl unload ~/Library/LaunchAgents/com.twstock.weekly_mongodb_backup.plist

# 啟動服務
launchctl load ~/Library/LaunchAgents/com.twstock.weekly_mongodb_backup.plist

# 重新加載服務
launchctl unload ~/Library/LaunchAgents/com.twstock.weekly_mongodb_backup.plist
launchctl load ~/Library/LaunchAgents/com.twstock.weekly_mongodb_backup.plist
```

#### 查看執行日誌
```bash
# 查看最新日誌
tail -50 logs/mongodb_backup.log

# 實時監控日誌
tail -f logs/mongodb_backup.log

# 查看錯誤日誌
tail -50 logs/mongodb_backup_error.log
```

---

## 📋 備份腳本詳解

### backup_mongodb.sh

**功能**: 自動備份 MongoDB 資料庫並壓縮

**參數**:
```bash
./backup_mongodb.sh                    # 使用默認保留期（30天）
./backup_mongodb.sh --keep-days 60     # 保留 60 天
./backup_mongodb.sh --keep-days 7      # 保留 7 天
```

**執行流程**:
1. ✅ 檢查 MongoDB 是否運行
2. 📦 執行 mongodump 備份
3. 🗜️ 壓縮為 tar.gz 格式
4. 📊 記錄資料庫統計
5. 🧹 清理舊備份（超過保留天數）
6. 📝 寫入備份日誌

**備份檔案命名**: `tw_stock_analysis_YYYYMMDD_HHMMSS.tar.gz`

**範例**: `tw_stock_analysis_20260222_221724.tar.gz`

### restore_mongodb.sh

**功能**: 從備份檔案還原資料庫

**用法**:
```bash
# 查看可用備份
./restore_mongodb.sh

# 還原指定備份
./restore_mongodb.sh ~/Desktop/Stock/mongodb_backups/tw_stock_analysis_20260222_221724.tar.gz
```

**執行流程**:
1. ✅ 檢查備份檔案是否存在
2. 📂 解壓縮備份檔案
3. ⚠️ 提示確認（會覆蓋現有資料）
4. 🔄 執行 mongorestore 還原
5. ✅ 驗證還原結果
6. 🧹 清理臨時文件

**⚠️ 重要警告**: 還原會覆蓋現有資料庫，請謹慎操作！

---

## 🗂️ 備份管理

### 備份目錄結構
```
~/Desktop/Stock/mongodb_backups/
├── tw_stock_analysis_20260222_221724.tar.gz  (184M)
├── tw_stock_analysis_20260215_010000.tar.gz  (178M)
├── tw_stock_analysis_20260208_010000.tar.gz  (175M)
└── backup_log.txt                            (備份記錄)
```

### 自動清理規則

**保留策略**: 保留最近 30 天的備份

**清理時機**: 每次執行備份時自動清理

**手動清理**:
```bash
# 清理 30 天前的備份
find ~/Desktop/Stock/mongodb_backups/ -name "tw_stock_analysis_*.tar.gz" -mtime +30 -delete

# 清理 7 天前的備份（更激進）
find ~/Desktop/Stock/mongodb_backups/ -name "tw_stock_analysis_*.tar.gz" -mtime +7 -delete
```

### 備份日誌

**日誌位置**: `~/Desktop/Stock/mongodb_backups/backup_log.txt`

**內容範例**:
```
==========================================
備份時間: 2026-02-22 22:17:24
檔案名稱: tw_stock_analysis_20260222_221724.tar.gz
檔案大小: 184M
資料大小: 1250.45 MB
股價記錄: 5120000
三大法人: 730000
==========================================
```

---

## 🔍 驗證與監控

### 驗證備份完整性

```bash
# 1. 檢查備份檔案是否存在
ls -lh ~/Desktop/Stock/mongodb_backups/tw_stock_analysis_*.tar.gz

# 2. 檢查最新備份
ls -lt ~/Desktop/Stock/mongodb_backups/*.tar.gz | head -1

# 3. 查看備份內容（不解壓）
tar -tzf ~/Desktop/Stock/mongodb_backups/tw_stock_analysis_20260222_221724.tar.gz | head -20

# 4. 驗證壓縮檔完整性
gzip -t ~/Desktop/Stock/mongodb_backups/tw_stock_analysis_20260222_221724.tar.gz
```

### 監控自動備份

**檢查清單**:
- ✅ 每週一上午檢查是否有週日 01:00 的新備份
- ✅ 檢查備份檔案大小是否正常（180-200 MB）
- ✅ 查看 `logs/mongodb_backup.log` 是否有錯誤
- ✅ 驗證舊備份是否正常清理

**監控命令**:
```bash
# 查看最近 3 個備份及時間
ls -lht ~/Desktop/Stock/mongodb_backups/*.tar.gz | head -3

# 查看最新備份日誌
tail -30 logs/mongodb_backup.log

# 檢查備份數量
ls ~/Desktop/Stock/mongodb_backups/*.tar.gz | wc -l
```

---

## 🛠️ 故障排除

### 問題 1: 備份失敗 - MongoDB 未運行

**錯誤訊息**:
```
❌ MongoDB 未運行，請先啟動 MongoDB
```

**解決方案**:
```bash
# 啟動 MongoDB
brew services start mongodb-community

# 查看服務狀態
brew services list | grep mongodb

# 驗證 MongoDB 連接
mongosh --eval "db.adminCommand('ping')"
```

### 問題 2: 磁碟空間不足

**錯誤訊息**:
```
❌ 備份失敗
Error: ENOSPC: no space left on device
```

**解決方案**:
```bash
# 1. 檢查磁碟空間
df -h ~/Desktop

# 2. 清理舊備份
./backup_mongodb.sh --keep-days 7

# 3. 手動刪除特定備份
rm ~/Desktop/Stock/mongodb_backups/tw_stock_analysis_20260101_*.tar.gz
```

### 問題 3: launchd 服務未執行

**症狀**: 週日 01:00 未自動備份

**診斷步驟**:
```bash
# 1. 檢查服務是否加載
launchctl list | grep mongodb_backup

# 2. 檢查 plist 文件是否存在
ls ~/Library/LaunchAgents/com.twstock.weekly_mongodb_backup.plist

# 3. 查看錯誤日誌
cat logs/mongodb_backup_error.log

# 4. 手動測試備份腳本
./backup_mongodb.sh
```

**修復方案**:
```bash
# 重新安裝服務
./scripts/install_backup_service.sh
```

### 問題 4: 還原後資料不完整

**診斷**:
```bash
# 1. 檢查備份檔案完整性
tar -tzf ~/Desktop/Stock/mongodb_backups/tw_stock_analysis_YYYYMMDD_HHMMSS.tar.gz

# 2. 手動還原並檢查錯誤
mongorestore --db tw_stock_analysis --drop /path/to/backup/tw_stock_analysis

# 3. 驗證集合記錄數
mongosh tw_stock_analysis --eval "
  db.getCollectionNames().forEach(function(col) {
    print(col + ': ' + db[col].countDocuments())
  })
"
```

---

## 📊 當前系統狀態

### launchd 服務 (2026-02-22)

```bash
$ launchctl list | grep com.twstock
-    0    com.twstock.weekly_mongodb_backup      # ✅ 每週日 01:00 備份
-    0    com.twstock.hourly_update              # ✅ 每小時 XX:05 更新
-    0    com.twstock.weekly_outstanding_shares  # ✅ 每週日 02:00 更新股本
-    0    com.twstock.weekly_log_cleanup         # ✅ 每週日 03:00 清理日誌
```

### 執行時間表

| 時間 | 任務 | 服務 |
|------|------|------|
| 週日 01:00 | **MongoDB 備份** | weekly_mongodb_backup |
| 週日 02:00 | 流通股數更新 | weekly_outstanding_shares |
| 週日 03:00 | 日誌清理 | weekly_log_cleanup |
| 每小時 XX:05 | 資料更新 | hourly_update |

### 最新備份狀態

```bash
$ ls -lh ~/Desktop/Stock/mongodb_backups/*.tar.gz | head -1
-rw-r--r--  1 ming  staff   184M Feb 22 22:17 tw_stock_analysis_20260222_221724.tar.gz
```

**狀態**: ✅ 備份正常，大小 184 MB

---

## 🔐 安全建議

### 1. 異地備份

**建議**: 定期複製備份到其他位置

```bash
# 複製到外接硬碟
cp ~/Desktop/Stock/mongodb_backups/*.tar.gz /Volumes/BackupDisk/tw-stock/

# 複製到 NAS
rsync -avz ~/Desktop/Stock/mongodb_backups/ user@nas:/backups/tw-stock/

# 上傳到雲端（需配置 rclone）
rclone copy ~/Desktop/Stock/mongodb_backups/ remote:tw-stock-backups/
```

### 2. 定期測試還原

**建議**: 每月測試一次備份還原

```bash
# 1. 記錄當前資料庫狀態
mongosh tw_stock_analysis --eval "db.stock_price.countDocuments()"

# 2. 還原測試備份到測試資料庫
mongorestore --db tw_stock_test --drop /path/to/backup/

# 3. 驗證資料完整性
mongosh tw_stock_test --eval "db.stock_price.countDocuments()"

# 4. 刪除測試資料庫
mongosh --eval "db.getSiblingDB('tw_stock_test').dropDatabase()"
```

### 3. 監控備份大小

**異常判斷**: 
- 備份大小與上週相比變化超過 ±20% → 需檢查
- 備份大小小於 100 MB → 可能備份失敗

```bash
# 檢查最近 4 週備份大小趨勢
ls -lh ~/Desktop/Stock/mongodb_backups/*.tar.gz | tail -4 | awk '{print $5, $9}'
```

---

## 📚 附錄

### A. 完整檔案清單

```
tw-stock-analysis/
├── backup_mongodb.sh                           # 備份腳本
├── restore_mongodb.sh                          # 還原腳本
├── com.twstock.weekly_mongodb_backup.plist     # launchd 配置
├── scripts/
│   └── install_backup_service.sh               # 安裝腳本
└── logs/
    ├── mongodb_backup.log                      # 備份日誌
    └── mongodb_backup_error.log                # 錯誤日誌
```

### B. 相關文檔

- [LAUNCHD_SETUP_GUIDE.md](LAUNCHD_SETUP_GUIDE.md) - launchd 服務設置指南
- [PROJECT_GUIDE.md](PROJECT_GUIDE.md) - 專案開發規範
- [QUICK_START.md](QUICK_START.md) - 快速開始指南

### C. MongoDB 命令參考

**mongodump 參數**:
```bash
mongodump \
  --db tw_stock_analysis \          # 指定資料庫
  --out /path/to/backup \           # 輸出目錄
  --gzip \                          # 壓縮（可選）
  --quiet                           # 靜默模式
```

**mongorestore 參數**:
```bash
mongorestore \
  --db tw_stock_analysis \          # 目標資料庫
  --drop \                          # 先刪除現有資料
  --gzip \                          # 如果備份已壓縮
  /path/to/backup/tw_stock_analysis # 備份目錄
```

---

## ✅ 檢查清單

### 初次安裝
- [ ] 執行 `./scripts/install_backup_service.sh`
- [ ] 驗證 launchd 服務已加載
- [ ] 執行一次手動備份測試
- [ ] 檢查備份檔案是否生成
- [ ] 測試還原功能（可選）

### 每週檢查
- [ ] 檢查週日 01:00 是否有新備份
- [ ] 驗證備份檔案大小正常
- [ ] 查看備份日誌無錯誤
- [ ] 確認舊備份已自動清理

### 每月檢查
- [ ] 測試一次備份還原
- [ ] 檢查磁碟空間充足（至少 5 GB 可用）
- [ ] 複製備份到異地存儲
- [ ] 審查備份保留策略是否合適

---

**文檔版本**: 1.0  
**最後更新**: 2026-02-22  
**維護者**: Ming  
**系統狀態**: ✅ 已安裝並運行
