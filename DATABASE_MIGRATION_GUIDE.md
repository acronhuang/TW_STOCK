# 🗄️ MongoDB 資料庫搬移完整指南

## 📍 目前資料庫位置

### 基本資訊
```
主機: localhost
埠號: 27017
資料庫名稱: tw_stock_analysis
實體路徑: /opt/homebrew/var/mongodb
配置檔: /opt/homebrew/etc/mongod.conf
日誌檔: /opt/homebrew/var/log/mongodb/mongo.log
```

### 資料庫統計（目前）
```
資料大小: 135.92 MB
儲存大小: 47.13 MB
索引大小: 14.70 MB
實體佔用: 102 MB
總文件數: 748,664 筆
```

### 主要集合
| 集合名稱 | 文件數 | 大小 |
|---------|--------|------|
| stock_price | 399,100 筆 | 55.40 MB |
| institutional_investors | 302,822 筆 | 64.03 MB |
| technical_indicators | 36,271 筆 | 11.56 MB |
| company_basic_info | 2,336 筆 | 2.81 MB |

---

## 🎯 搬移場景

### 場景 1：同一台電腦，更換資料目錄
**適用情況**：
- 原本硬碟空間不足，想搬到外接硬碟
- 想改用 SSD 加快速度
- 整理檔案，統一存放位置

### 場景 2：搬到另一台電腦
**適用情況**：
- 換新電腦
- 部署到伺服器
- 備份到另一台機器

### 場景 3：搬到雲端（AWS/GCP/Azure）
**適用情況**：
- 需要遠端存取
- 多人協作
- 正式上線部署

---

## 📦 方法 1：備份與還原（推薦）

### ✅ 優點
- 最安全的方法
- 可以跨版本
- 可以選擇性還原
- 資料完整性高

### 步驟 1：備份資料庫

```bash
# 1. 建立備份目錄
mkdir -p ~/Desktop/Stock/mongodb_backup

# 2. 使用 mongodump 備份整個資料庫
mongodump --db tw_stock_analysis --out ~/Desktop/Stock/mongodb_backup

# 3. 確認備份成功
ls -lh ~/Desktop/Stock/mongodb_backup/tw_stock_analysis/

# 4. 壓縮備份（節省空間）
cd ~/Desktop/Stock
tar -czf mongodb_backup_$(date +%Y%m%d_%H%M%S).tar.gz mongodb_backup/
```

**預期輸出**：
```
2026-02-16T15:30:00.000+0800    writing tw_stock_analysis.stock_price to 
2026-02-16T15:30:10.000+0800    done dumping tw_stock_analysis.stock_price (399100 documents)
2026-02-16T15:30:10.000+0800    writing tw_stock_analysis.institutional_investors to 
...
```

### 步驟 2：還原到新位置

#### 場景 1：同一台電腦，新目錄

```bash
# 1. 停止 MongoDB
brew services stop mongodb-community@7.0

# 2. 修改配置檔，指定新的資料目錄
# 編輯 /opt/homebrew/etc/mongod.conf
# 將 dbPath 改為新路徑，例如：
#   storage:
#     dbPath: /Users/ming/Documents/mongodb_data

# 3. 建立新目錄並設定權限
mkdir -p /Users/ming/Documents/mongodb_data
chmod 755 /Users/ming/Documents/mongodb_data

# 4. 啟動 MongoDB（會在新目錄建立資料庫）
brew services start mongodb-community@7.0

# 5. 等待 MongoDB 啟動（約 5 秒）
sleep 5

# 6. 還原資料
mongorestore --db tw_stock_analysis ~/Desktop/Stock/mongodb_backup/tw_stock_analysis/

# 7. 驗證資料
mongosh --eval "
  use tw_stock_analysis
  db.stock_price.count()
  db.institutional_investors.count()
  db.technical_indicators.count()
"
```

#### 場景 2：搬到另一台電腦

**在舊電腦上**：
```bash
# 1. 備份並壓縮
cd ~/Desktop/Stock
mongodump --db tw_stock_analysis --out mongodb_backup
tar -czf mongodb_backup.tar.gz mongodb_backup/

# 2. 傳輸到新電腦（選擇一種方式）
# 方式 A：使用 USB 隨身碟複製
# 方式 B：使用 scp 傳輸
scp mongodb_backup.tar.gz username@new-computer-ip:~/

# 方式 C：上傳到雲端（Dropbox/Google Drive）後下載
```

**在新電腦上**：
```bash
# 1. 安裝 MongoDB（如果未安裝）
brew install mongodb-community@7.0

# 2. 啟動 MongoDB
brew services start mongodb-community@7.0

# 3. 解壓縮備份
cd ~
tar -xzf mongodb_backup.tar.gz

# 4. 還原資料
mongorestore --db tw_stock_analysis mongodb_backup/tw_stock_analysis/

# 5. 驗證
mongosh --eval "use tw_stock_analysis; db.stock_price.count()"
```

---

## 📁 方法 2：直接複製資料目錄

### ⚠️ 注意事項
- 必須完全停止 MongoDB
- 必須是相同版本的 MongoDB
- 較快但風險較高

### 步驟

```bash
# 1. 停止 MongoDB
brew services stop mongodb-community@7.0

# 2. 等待程序完全停止
sleep 5
ps aux | grep mongod  # 確認沒有 mongod 程序

# 3. 複製整個資料目錄
# 場景 1：複製到新位置
sudo cp -R /opt/homebrew/var/mongodb /Users/ming/Documents/mongodb_data

# 場景 2：複製到外接硬碟
sudo cp -R /opt/homebrew/var/mongodb /Volumes/ExternalDrive/mongodb_data

# 場景 3：打包傳輸
cd /opt/homebrew/var
tar -czf ~/Desktop/mongodb_data.tar.gz mongodb/

# 4. 設定權限
sudo chown -R ming:admin /Users/ming/Documents/mongodb_data

# 5. 修改配置檔
sudo nano /opt/homebrew/etc/mongod.conf
# 修改 dbPath 為新路徑

# 6. 啟動 MongoDB
brew services start mongodb-community@7.0

# 7. 驗證
mongosh --eval "show dbs"
```

---

## ☁️ 方法 3：搬移到 MongoDB Atlas（雲端）

### 優點
- 免費方案 512MB
- 自動備份
- 全球存取
- 專業維護

### 步驟

#### 1. 註冊 MongoDB Atlas
1. 前往 https://www.mongodb.com/cloud/atlas/register
2. 註冊免費帳號
3. 建立 Free Cluster（M0）

#### 2. 取得連線字串
```
mongodb+srv://username:password@cluster0.xxxxx.mongodb.net/tw_stock_analysis
```

#### 3. 使用 mongodump 和 mongorestore

```bash
# 1. 從本地備份
mongodump --db tw_stock_analysis --out ~/Desktop/mongodb_backup

# 2. 還原到 Atlas
mongorestore \
  --uri "mongodb+srv://username:password@cluster0.xxxxx.mongodb.net" \
  --db tw_stock_analysis \
  ~/Desktop/mongodb_backup/tw_stock_analysis/
```

#### 4. 修改應用程式連線字串

**修改 Python 腳本**：
```python
# 舊的（本地）
client = MongoClient('mongodb://localhost:27017/')

# 新的（Atlas）
client = MongoClient('mongodb+srv://username:password@cluster0.xxxxx.mongodb.net/')
```

**建立環境變數**：
```bash
# 在 ~/.zshrc 或 ~/.bash_profile 加入
export MONGODB_URI="mongodb+srv://username:password@cluster0.xxxxx.mongodb.net/"

# 在 Python 中使用
import os
from pymongo import MongoClient

MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
client = MongoClient(MONGODB_URI)
```

---

## 🔄 方法 4：使用 Docker（容器化）

### 優點
- 環境隔離
- 易於遷移
- 版本控制
- 可重現性高

### 步驟

#### 1. 建立 Docker Compose 配置

```yaml
# docker-compose.yml（已存在，需修改）
version: '3.8'

services:
  mongodb:
    image: mongo:7.0
    container_name: tw_stock_mongodb
    restart: always
    ports:
      - "27017:27017"
    volumes:
      # 資料持久化到本地目錄
      - ./mongodb_data:/data/db
      # 備份目錄
      - ./mongodb_backup:/backup
    environment:
      MONGO_INITDB_DATABASE: tw_stock_analysis
      # 可選：設定帳號密碼
      # MONGO_INITDB_ROOT_USERNAME: admin
      # MONGO_INITDB_ROOT_PASSWORD: password123
```

#### 2. 啟動 Docker MongoDB

```bash
# 1. 停止現有的 MongoDB
brew services stop mongodb-community@7.0

# 2. 確保 Docker Desktop 正在運行

# 3. 啟動容器
cd ~/Desktop/Stock/tw-stock-analysis
docker-compose up -d mongodb

# 4. 檢查容器狀態
docker ps | grep mongodb

# 5. 還原資料到 Docker MongoDB
mongorestore --db tw_stock_analysis ~/Desktop/Stock/mongodb_backup/tw_stock_analysis/
```

#### 3. 搬移 Docker 資料

```bash
# 資料存在 ./mongodb_data 目錄，可直接複製整個專案
# 在新電腦上：
git clone <your-repo>
cd tw-stock-analysis
docker-compose up -d
```

---

## 📋 完整搬移檢查清單

### 搬移前
- [ ] 確認目前資料庫大小（至少需要 200MB 空間）
- [ ] 檢查 MongoDB 版本：`mongod --version`
- [ ] 備份資料：`mongodump --db tw_stock_analysis --out backup/`
- [ ] 壓縮備份：`tar -czf backup.tar.gz backup/`
- [ ] 驗證備份完整性
- [ ] 記錄目前連線設定

### 搬移中
- [ ] 停止所有使用資料庫的程式
- [ ] 停止 MongoDB：`brew services stop mongodb-community@7.0`
- [ ] 確認程序已停止：`ps aux | grep mongod`
- [ ] 執行搬移操作（選擇上述方法之一）
- [ ] 修改配置檔（如有需要）

### 搬移後
- [ ] 啟動 MongoDB
- [ ] 驗證資料完整性：
  ```bash
  mongosh --eval "
    use tw_stock_analysis
    print('stock_price:', db.stock_price.count())
    print('institutional_investors:', db.institutional_investors.count())
    print('technical_indicators:', db.technical_indicators.count())
  "
  ```
- [ ] 測試查詢功能
- [ ] 更新應用程式連線字串（如有需要）
- [ ] 測試背景下載程式
- [ ] 測試形態分析功能
- [ ] 刪除舊資料（確認新位置運作正常後）

---

## 🛠️ 實用腳本

### 一鍵備份腳本

建立 `backup_mongodb.sh`：
```bash
#!/bin/bash

BACKUP_DIR="$HOME/Desktop/Stock/mongodb_backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_PATH="$BACKUP_DIR/backup_$TIMESTAMP"

echo "開始備份 MongoDB..."

# 建立備份目錄
mkdir -p "$BACKUP_DIR"

# 執行備份
mongodump --db tw_stock_analysis --out "$BACKUP_PATH"

# 壓縮
cd "$BACKUP_DIR"
tar -czf "backup_$TIMESTAMP.tar.gz" "backup_$TIMESTAMP"
rm -rf "backup_$TIMESTAMP"

# 計算大小
SIZE=$(du -h "backup_$TIMESTAMP.tar.gz" | cut -f1)

echo "✅ 備份完成！"
echo "檔案: $BACKUP_DIR/backup_$TIMESTAMP.tar.gz"
echo "大小: $SIZE"

# 保留最近 7 天的備份
find "$BACKUP_DIR" -name "backup_*.tar.gz" -mtime +7 -delete
echo "已清理 7 天前的舊備份"
```

### 一鍵還原腳本

建立 `restore_mongodb.sh`：
```bash
#!/bin/bash

if [ -z "$1" ]; then
    echo "用法: ./restore_mongodb.sh <備份檔案.tar.gz>"
    exit 1
fi

BACKUP_FILE="$1"
TEMP_DIR="/tmp/mongodb_restore_$$"

echo "準備還原: $BACKUP_FILE"

# 解壓縮
mkdir -p "$TEMP_DIR"
tar -xzf "$BACKUP_FILE" -C "$TEMP_DIR"

# 找到備份目錄
BACKUP_DIR=$(find "$TEMP_DIR" -name "tw_stock_analysis" -type d | head -1)

if [ -z "$BACKUP_DIR" ]; then
    echo "❌ 找不到 tw_stock_analysis 目錄"
    exit 1
fi

# 還原
echo "開始還原..."
mongorestore --db tw_stock_analysis "$BACKUP_DIR"

# 清理
rm -rf "$TEMP_DIR"

echo "✅ 還原完成！"

# 驗證
echo "驗證資料..."
mongosh --eval "
  use tw_stock_analysis
  print('stock_price:', db.stock_price.count())
  print('institutional_investors:', db.institutional_investors.count())
  print('technical_indicators:', db.technical_indicators.count())
"
```

使用方式：
```bash
# 備份
chmod +x backup_mongodb.sh
./backup_mongodb.sh

# 還原
chmod +x restore_mongodb.sh
./restore_mongodb.sh ~/Desktop/Stock/mongodb_backups/backup_20260216_153000.tar.gz
```

---

## 🔍 常見問題

### Q1: 搬移後程式找不到資料庫？
**A**: 檢查連線字串是否正確：
```python
# 檢查所有 Python 腳本中的 MongoClient
grep -r "MongoClient" scripts/
grep -r "localhost:27017" scripts/
```

### Q2: 資料大小會成長多少？
**A**: 
- 目前：102 MB（399K 筆股價）
- 完整下載後：約 1-2 GB（2333 股 × 10 年 × 2 資料集）
- 建議預留：3-5 GB 空間

### Q3: 可以同時使用本地和雲端嗎？
**A**: 可以！建立雙資料庫配置：
```python
class DatabaseManager:
    def __init__(self):
        self.local = MongoClient('mongodb://localhost:27017/')
        self.cloud = MongoClient('mongodb+srv://...')
    
    def sync_to_cloud(self):
        # 同步本地資料到雲端
        pass
```

### Q4: 搬移會影響背景下載嗎？
**A**: 
- 如果只是備份：不影響
- 如果更換資料目錄：需重新啟動背景程式
- 如果搬到其他電腦：需在新電腦上執行

### Q5: 如何設定自動備份？
**A**: 使用 cron：
```bash
# 編輯 crontab
crontab -e

# 每天凌晨 3 點備份
0 3 * * * /Users/ming/Desktop/Stock/tw-stock-analysis/backup_mongodb.sh
```

---

## 📊 建議方案

### 針對您的情況

**目前狀態**：
- 資料量：102 MB（小）
- 成長速度：背景下載中，預計 1-2 GB
- 使用場景：本機開發 + 分析

**建議方案**：

#### 方案 A：保持現狀 + 定期備份（推薦）
```bash
# 每天自動備份
./backup_mongodb.sh

# 資料存在：/opt/homebrew/var/mongodb
# 備份存在：~/Desktop/Stock/mongodb_backups
```
**優點**：簡單、穩定、速度快  
**適合**：個人使用、資料不超過 10GB

#### 方案 B：搬到專案目錄（整理檔案）
```bash
# 搬到 ~/Desktop/Stock/tw-stock-analysis/mongodb_data
# 好處：專案檔案集中，易於管理
```
**優點**：檔案整齊、易於備份整個專案  
**適合**：需要頻繁備份或版本控制

#### 方案 C：使用 Docker（專業部署）
```bash
# 使用 docker-compose.yml
# 資料在 ./mongodb_data
```
**優點**：易於遷移、環境隔離  
**適合**：準備上線或多環境開發

---

## 🎯 快速操作指令

### 立即備份（安全第一）
```bash
cd ~/Desktop/Stock/tw-stock-analysis
mkdir -p mongodb_backup
mongodump --db tw_stock_analysis --out mongodb_backup
tar -czf mongodb_backup_$(date +%Y%m%d).tar.gz mongodb_backup/
echo "✅ 備份完成: mongodb_backup_$(date +%Y%m%d).tar.gz"
```

### 查看目前位置
```bash
ps aux | grep mongod | grep -v grep | grep -o -- '--config [^ ]*'
cat /opt/homebrew/etc/mongod.conf | grep dbPath
du -sh /opt/homebrew/var/mongodb
```

### 驗證資料完整性
```bash
mongosh --eval "
  use tw_stock_analysis
  print('資料庫大小:', (db.stats().dataSize / 1024 / 1024).toFixed(2), 'MB')
  print('stock_price:', db.stock_price.count())
  print('institutional_investors:', db.institutional_investors.count())
  print('technical_indicators:', db.technical_indicators.count())
  print('公司資料:', db.company_basic_info.count())
"
```

---

**文件產生時間**: 2026-02-16 15:25:00  
**資料庫版本**: MongoDB 7.0.30  
**目前資料量**: 102 MB (748,664 筆文件)  
**預估最終**: 1-2 GB (完整下載後)
