#!/bin/bash

# 重新啟動下載程式

echo "正在檢查現有程式..."

# 檢查是否有執行中的程式
PID=$(ps aux | grep '[b]ackground_full_download.py' | awk '{print $2}')

if [ -n "$PID" ]; then
    echo "發現執行中的程式 (PID: $PID)"
    read -p "是否要停止並重新啟動? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "正在停止程式..."
        kill $PID
        sleep 2
    else
        echo "取消操作"
        exit 0
    fi
fi

echo "正在啟動背景下載程式..."
cd /home/mdsadmin/Stock/tw-stock-analysis

nohup python3 scripts/background_full_download.py > logs/background_download.log 2>&1 &

NEW_PID=$!
echo "✅ 程式已啟動 (PID: $NEW_PID)"
echo ""
echo "查看狀態: ./monitor_download.sh"
echo "即時日誌: tail -f logs/full_download_*.log"
