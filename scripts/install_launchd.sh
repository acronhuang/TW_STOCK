#!/bin/bash
#
# launchd 服務安裝腳本
# 用途：安裝台股數據自動更新服務（替代 crontab）
#

set -e

# 顏色定義
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo "========================================"
echo "🚀 launchd 服務安裝程序"
echo "========================================"
echo ""

# 獲取當前目錄
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LAUNCHAGENTS_DIR="$HOME/Library/LaunchAgents"

# 確保 LaunchAgents 目錄存在
mkdir -p "$LAUNCHAGENTS_DIR"

# 服務列表
SERVICES=(
    "com.twstock.hourly_update"
    "com.twstock.weekly_outstanding_shares"
    "com.twstock.weekly_log_cleanup"
)

echo -e "${YELLOW}步驟 1: 複製 plist 文件到 LaunchAgents 目錄${NC}"
echo ""

for service in "${SERVICES[@]}"; do
    plist_file="${service}.plist"
    
    if [ -f "$PROJECT_ROOT/$plist_file" ]; then
        echo "  📄 複製: $plist_file"
        cp "$PROJECT_ROOT/$plist_file" "$LAUNCHAGENTS_DIR/"
        chmod 644 "$LAUNCHAGENTS_DIR/$plist_file"
    else
        echo -e "  ${RED}❌ 找不到: $plist_file${NC}"
        exit 1
    fi
done

echo ""
echo -e "${GREEN}✅ 文件複製完成${NC}"
echo ""

echo -e "${YELLOW}步驟 2: 加載 launchd 服務${NC}"
echo ""

for service in "${SERVICES[@]}"; do
    plist_path="$LAUNCHAGENTS_DIR/${service}.plist"
    
    # 先卸載（如果已存在）
    launchctl unload "$plist_path" 2>/dev/null || true
    
    # 加載服務
    if launchctl load "$plist_path"; then
        echo -e "  ${GREEN}✅ 已加載: $service${NC}"
    else
        echo -e "  ${RED}❌ 加載失敗: $service${NC}"
    fi
done

echo ""
echo -e "${GREEN}✅ launchd 服務安裝完成！${NC}"
echo ""

echo "========================================"
echo "📊 服務狀態檢查"
echo "========================================"
echo ""

for service in "${SERVICES[@]}"; do
    if launchctl list | grep -q "$service"; then
        echo -e "  ${GREEN}✅ $service - 運行中${NC}"
    else
        echo -e "  ${YELLOW}⚠️  $service - 未運行${NC}"
    fi
done

echo ""
echo "========================================"
echo "📝 後續步驟"
echo "========================================"
echo ""
echo "1. 檢查服務狀態："
echo "   launchctl list | grep twstock"
echo ""
echo "2. 查看日誌："
echo "   tail -f $SCRIPT_DIR/logs/launchd_hourly_stdout.log"
echo ""
echo "3. 停用服務（如需要）："
echo "   launchctl unload ~/Library/LaunchAgents/com.twstock.hourly_update.plist"
echo ""
echo "4. 重新加載服務："
echo "   launchctl load ~/Library/LaunchAgents/com.twstock.hourly_update.plist"
echo ""
echo "5. 停用舊的 crontab（可選）："
echo "   crontab -r"
echo ""
echo -e "${GREEN}✅ 安裝完成！下次執行時間：每小時 XX:05${NC}"
echo ""
