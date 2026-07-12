#!/bin/bash

# MongoDB 自動備份腳本
# 用法: ./backup_mongodb.sh
# 可選參數: --keep-days N (保留 N 天的備份，默認 30 天)

set -e

# 解析參數
KEEP_DAYS=30
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --keep-days) KEEP_DAYS="$2"; shift ;;
        *) echo "未知參數: $1"; exit 1 ;;
    esac
    shift
done

BACKUP_DIR="$HOME/Stock/mongodb_backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="tw_stock_analysis_$TIMESTAMP"
BACKUP_PATH="$BACKUP_DIR/$BACKUP_NAME"

echo "=========================================="
echo "📦 MongoDB 資料庫備份"
echo "=========================================="
echo "時間: $(date '+%Y-%m-%d %H:%M:%S')"
echo "保留天數: $KEEP_DAYS 天"
echo ""

# 建立備份目錄
mkdir -p "$BACKUP_DIR"
echo "✓ 備份目錄: $BACKUP_DIR"

# 檢查 MongoDB 是否運行
if ! pgrep -x "mongod" > /dev/null; then
    echo "❌ MongoDB 未運行，請先啟動 MongoDB"
    echo "   brew services start mongodb-community"
    exit 1
fi

echo "✓ MongoDB 運行中"
echo ""

# 執行備份
echo "開始備份資料庫..."
if mongodump --db tw_stock_analysis --out "$BACKUP_PATH" --quiet; then
    echo "✓ 資料庫備份完成"
else
    echo "❌ 備份失敗"
    exit 1
fi

# 壓縮備份
echo ""
echo "壓縮備份檔案..."
cd "$BACKUP_DIR"
if tar -czf "$BACKUP_NAME.tar.gz" "$BACKUP_NAME"; then
    # 刪除未壓縮的備份
    rm -rf "$BACKUP_NAME"
    echo "✓ 壓縮完成"
else
    echo "❌ 壓縮失敗"
    exit 1
fi

# 計算大小
SIZE=$(du -h "$BACKUP_NAME.tar.gz" | cut -f1)

echo ""
echo "=========================================="
echo "✅ 備份完成！"
echo "=========================================="
echo "檔案: $BACKUP_DIR/$BACKUP_NAME.tar.gz"
echo "大小: $SIZE"
echo ""

# 列出所有備份
echo "📋 現有備份檔案:"
ls -lht "$BACKUP_DIR"/*.tar.gz 2>/dev/null | head -10 | awk '{print "  " $9 " (" $5 ", " $6 " " $7 ")"}' || echo "  (無備份檔案)"

# 清理舊備份（保留指定天數）
echo ""
echo "清理 $KEEP_DAYS 天前的舊備份..."
DELETED=$(find "$BACKUP_DIR" -name "tw_stock_analysis_*.tar.gz" -mtime +$KEEP_DAYS 2>/dev/null | wc -l | tr -d ' ')
find "$BACKUP_DIR" -name "tw_stock_analysis_*.tar.gz" -mtime +$KEEP_DAYS -delete 2>/dev/null || true
echo "✓ 已刪除 $DELETED 個舊備份"

echo ""
echo "=========================================="
echo "備份資訊已記錄到: $BACKUP_DIR/backup_log.txt"

# 記錄備份日誌
{
    echo "=========================================="
    echo "備份時間: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "檔案名稱: $BACKUP_NAME.tar.gz"
    echo "檔案大小: $SIZE"
    
    # 取得資料庫統計
    STATS=$(mongosh tw_stock_analysis --quiet --eval "
        const stats = db.stats()
        const stock_count = db.stock_price.countDocuments()
        const inst_count = db.institutional_investors.countDocuments()
        print('資料大小: ' + (stats.dataSize / 1024 / 1024).toFixed(2) + ' MB')
        print('股價記錄: ' + stock_count)
        print('三大法人: ' + inst_count)
    " 2>/dev/null || echo "無法取得資料庫統計")
    
    echo "$STATS"
    echo "$STATS"
    echo ""
} >> "$BACKUP_DIR/backup_log.txt"

echo "=========================================="
