#!/bin/bash

# MongoDB 備份系統安裝腳本
# 安裝每週自動備份服務

set -e

PROJECT_DIR="/home/mdsadmin/Stock/tw-stock-analysis"
PLIST_FILE="com.twstock.weekly_mongodb_backup.plist"
LAUNCHAGENTS_DIR="$HOME/Library/LaunchAgents"

echo "========================================"
echo "📦 MongoDB 每週備份系統安裝"
echo "========================================"
echo ""

# 1. 檢查備份腳本
echo "1️⃣  檢查備份腳本..."
if [ ! -f "$PROJECT_DIR/backup_mongodb.sh" ]; then
    echo "❌ 找不到備份腳本: backup_mongodb.sh"
    exit 1
fi

# 確保備份腳本可執行
chmod +x "$PROJECT_DIR/backup_mongodb.sh"
echo "✅ 備份腳本就緒"
echo ""

# 2. 檢查 plist 文件
echo "2️⃣  檢查 plist 配置..."
if [ ! -f "$PROJECT_DIR/$PLIST_FILE" ]; then
    echo "❌ 找不到配置文件: $PLIST_FILE"
    exit 1
fi
echo "✅ 配置文件就緒"
echo ""

# 3. 複製 plist 到 LaunchAgents
echo "3️⃣  安裝 launchd 服務..."
cp "$PROJECT_DIR/$PLIST_FILE" "$LAUNCHAGENTS_DIR/"
echo "✅ 配置文件已複製到 $LAUNCHAGENTS_DIR"
echo ""

# 4. 卸載舊服務（如果存在）
echo "4️⃣  卸載舊服務..."
launchctl unload "$LAUNCHAGENTS_DIR/$PLIST_FILE" 2>/dev/null || echo "   (舊服務不存在，跳過)"
echo ""

# 5. 加載新服務
echo "5️⃣  加載新服務..."
if launchctl load "$LAUNCHAGENTS_DIR/$PLIST_FILE"; then
    echo "✅ 服務加載成功"
else
    echo "❌ 服務加載失敗"
    exit 1
fi
echo ""

# 6. 驗證服務狀態
echo "6️⃣  驗證服務狀態..."
if launchctl list | grep -q "com.twstock.weekly_mongodb_backup"; then
    echo "✅ 服務運行中"
    launchctl list | grep "com.twstock.weekly_mongodb_backup"
else
    echo "⚠️  服務未在列表中（可能是正常的，因為尚未到執行時間）"
fi
echo ""

# 7. 創建日誌目錄
echo "7️⃣  創建日誌目錄..."
mkdir -p "$PROJECT_DIR/logs"
echo "✅ 日誌目錄就緒"
echo ""

echo "========================================"
echo "✅ MongoDB 每週備份系統安裝完成！"
echo "========================================"
echo ""
echo "📋 系統資訊："
echo "   • 執行時間: 每週日凌晨 1:00"
echo "   • 備份位置: ~/Stock/mongodb_backups/"
echo "   • 保留天數: 30 天"
echo "   • 日誌文件: logs/mongodb_backup.log"
echo ""
echo "🔍 驗證命令："
echo "   # 查看服務狀態"
echo "   launchctl list | grep mongodb_backup"
echo ""
echo "   # 查看日誌"
echo "   tail -f logs/mongodb_backup.log"
echo ""
echo "   # 手動執行備份測試"
echo "   ./backup_mongodb.sh"
echo ""
echo "   # 查看現有備份"
echo "   ls -lht ~/Stock/mongodb_backups/*.tar.gz | head -5"
echo ""
echo "⚠️  重要提醒："
echo "   • 建議現在執行一次手動備份測試"
echo "   • 定期檢查備份檔案是否正常生成"
echo "   • 備份會自動清理 30 天前的舊檔案"
echo ""
