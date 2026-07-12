#!/bin/bash
# P2 測試腳本 - 小範圍測試統一下載系統
# 僅測試 1-2 個資料表以驗證功能

set -e  # 遇到錯誤立即停止

echo "=================================="
echo "🧪 P2 統一下載系統測試"
echo "=================================="
echo ""

# 1. 檢查環境
echo "📋 步驟 1: 檢查環境"
echo "-----------------------------------"

if [ ! -f .env ]; then
    echo "❌ 錯誤: .env 檔案不存在"
    exit 1
fi

# 載入環境變數
export $(grep FINMIND_API_TOKEN .env | xargs)

if [ -z "$FINMIND_API_TOKEN" ]; then
    echo "❌ 錯誤: FINMIND_API_TOKEN 未設定"
    exit 1
fi

echo "✅ .env 載入成功"
echo "✅ API Token: ${FINMIND_API_TOKEN:0:20}..."
echo ""

# 2. 檢查 MongoDB
echo "📋 步驟 2: 檢查 MongoDB"
echo "-----------------------------------"

if ! pgrep -x mongod > /dev/null; then
    echo "❌ 錯誤: MongoDB 未運行"
    exit 1
fi

echo "✅ MongoDB 正在運行"
echo ""

# 3. 檢查 Python 套件
echo "📋 步驟 3: 檢查 Python 套件"
echo "-----------------------------------"

python3 -c "import pymongo; import requests" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "❌ 錯誤: 缺少必要套件 (pymongo, requests)"
    exit 1
fi

echo "✅ Python 套件完整"
echo ""

# 4. 測試統一下載系統（小範圍）
echo "📋 步驟 4: 測試下載（僅台股總覽 1 張表）"
echo "-----------------------------------"
echo "開始時間: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# 創建測試日誌目錄
mkdir -p logs/test

# 執行小範圍測試
python3 src/downloaders/unified_downloader.py \
    --categories 技術面 \
    --verbose 2>&1 | tee logs/test/p2_test_$(date +%Y%m%d_%H%M%S).log

TEST_EXIT_CODE=$?

echo ""
echo "結束時間: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# 5. 驗證結果
echo "📋 步驟 5: 驗證測試結果"
echo "-----------------------------------"

if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo "✅ 測試執行成功"
    
    # 檢查資料庫
    echo ""
    echo "資料庫狀態:"
    mongosh tw_stock_analysis --quiet --eval "
        print('stock_price:', db.stock_price.countDocuments());
        print('taiwan_stock_info:', db.taiwan_stock_info.countDocuments());
    "
    
    echo ""
    echo "=================================="
    echo "✅ P2 測試完成 - 統一下載系統可用"
    echo "=================================="
    exit 0
else
    echo "❌ 測試失敗 (退出碼: $TEST_EXIT_CODE)"
    echo ""
    echo "=================================="
    echo "❌ P2 測試失敗"
    echo "=================================="
    exit 1
fi
