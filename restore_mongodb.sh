#!/bin/bash

# MongoDB 資料庫還原腳本
# 用法: ./restore_mongodb.sh <備份檔案.tar.gz>

set -e

if [ -z "$1" ]; then
    echo "=========================================="
    echo "📥 MongoDB 資料庫還原"
    echo "=========================================="
    echo ""
    echo "用法: ./restore_mongodb.sh <備份檔案.tar.gz>"
    echo ""
    echo "可用的備份檔案:"
    BACKUP_DIR="$HOME/Stock/mongodb_backups"
    if [ -d "$BACKUP_DIR" ]; then
        ls -lht "$BACKUP_DIR"/*.tar.gz 2>/dev/null | head -10 | awk '{print "  " $9 " (" $5 ", " $6 " " $7 ")"}'
    else
        echo "  (找不到備份目錄)"
    fi
    echo ""
    exit 1
fi

BACKUP_FILE="$1"
TEMP_DIR="/tmp/mongodb_restore_$$"

echo "=========================================="
echo "📥 MongoDB 資料庫還原"
echo "=========================================="
echo "備份檔案: $BACKUP_FILE"
echo "時間: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# 檢查檔案是否存在
if [ ! -f "$BACKUP_FILE" ]; then
    echo "❌ 找不到備份檔案: $BACKUP_FILE"
    exit 1
fi

# 檢查 MongoDB 是否運行
if ! pgrep -x "mongod" > /dev/null; then
    echo "❌ MongoDB 未運行，請先啟動 MongoDB"
    echo "   brew services start mongodb-community@7.0"
    exit 1
fi

echo "✓ MongoDB 運行中"
echo ""

# 警告
echo "⚠️  警告：還原將會覆蓋現有資料！"
echo ""
read -p "確定要繼續嗎？(yes/no): " -r
echo ""
if [[ ! $REPLY =~ ^[Yy]es$ ]]; then
    echo "已取消還原"
    exit 0
fi

# 建立臨時目錄
mkdir -p "$TEMP_DIR"
echo "✓ 建立臨時目錄: $TEMP_DIR"

# 解壓縮
echo ""
echo "解壓縮備份檔案..."
if tar -xzf "$BACKUP_FILE" -C "$TEMP_DIR"; then
    echo "✓ 解壓縮完成"
else
    echo "❌ 解壓縮失敗"
    rm -rf "$TEMP_DIR"
    exit 1
fi

# 找到備份目錄
BACKUP_DIR=$(find "$TEMP_DIR" -name "tw_stock_analysis" -type d | head -1)

if [ -z "$BACKUP_DIR" ]; then
    echo "❌ 找不到 tw_stock_analysis 目錄"
    rm -rf "$TEMP_DIR"
    exit 1
fi

echo "✓ 找到備份資料: $BACKUP_DIR"

# 顯示即將還原的資料統計
echo ""
echo "備份內容統計:"
for collection_file in "$BACKUP_DIR"/*.bson; do
    if [ -f "$collection_file" ]; then
        collection_name=$(basename "$collection_file" .bson)
        file_size=$(du -h "$collection_file" | cut -f1)
        echo "  $collection_name: $file_size"
    fi
done

echo ""
echo "開始還原資料庫..."

# 還原（drop 選項會先刪除現有集合）
if mongorestore --db tw_stock_analysis --drop "$BACKUP_DIR" --quiet; then
    echo "✓ 資料庫還原完成"
else
    echo "❌ 還原失敗"
    rm -rf "$TEMP_DIR"
    exit 1
fi

# 清理臨時目錄
rm -rf "$TEMP_DIR"
echo "✓ 清理臨時檔案"

echo ""
echo "=========================================="
echo "驗證還原資料..."
echo "=========================================="

# 驗證資料
STATS=$(mongosh --quiet --eval "
    use tw_stock_analysis
    const stock_count = db.stock_price.count()
    const inst_count = db.institutional_investors.count()
    const ind_count = db.technical_indicators.count()
    const company_count = db.company_basic_info.count()
    print('股價記錄:', stock_count)
    print('三大法人:', inst_count)
    print('技術指標:', ind_count)
    print('公司資料:', company_count)
" 2>/dev/null)

echo "$STATS"

echo ""
echo "=========================================="
echo "✅ 還原完成！"
echo "=========================================="
echo ""

# 記錄還原日誌
RESTORE_LOG="$HOME/Stock/mongodb_backups/restore_log.txt"
{
    echo "=========================================="
    echo "還原時間: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "來源檔案: $BACKUP_FILE"
    echo "$STATS"
    echo ""
} >> "$RESTORE_LOG"
