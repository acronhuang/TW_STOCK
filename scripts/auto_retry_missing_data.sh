#!/bin/bash
# 自動重試下載缺失數據

cd /home/mdsadmin/Stock/tw-stock-analysis

echo "========================================================================"
echo "FinMind 缺失數據自動下載"
echo "========================================================================"
echo ""

# 載入環境變數
if [ -f .env ]; then
    export $(grep FINMIND_API_TOKEN .env | xargs)
fi

if [ -z "$FINMIND_API_TOKEN" ]; then
    echo "✗ 找不到 FINMIND_API_TOKEN"
    exit 1
fi

# 最大重試次數（24 小時，每小時重試一次）
MAX_RETRIES=24
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    RETRY_COUNT=$((RETRY_COUNT + 1))
    
    echo ""
    echo "嘗試 $RETRY_COUNT/$MAX_RETRIES"
    echo "時間: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "------------------------------------------------------------------------"
    
    # 執行下載
    python3 scripts/download_missing_data.py
    EXIT_CODE=$?
    
    if [ $EXIT_CODE -eq 0 ]; then
        echo ""
        echo "✓ 下載完成！"
        exit 0
    fi
    
    # API 限制，等待後重試
    if [ $RETRY_COUNT -lt $MAX_RETRIES ]; then
        echo ""
        echo "⏰ API 達到限制，等待 1 小時後重試..."
        echo "   下次嘗試: $(date -v+1H '+%Y-%m-%d %H:%M:%S')"
        sleep 3600
    fi
done

echo ""
echo "✗ 已達最大重試次數，請稍後手動執行"
echo "  python3 scripts/download_missing_data.py"
exit 1
