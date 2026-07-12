#!/bin/bash

# 批量下載股票價格數據腳本
# 使用方式: bash scripts/start_price_download.sh

cd /home/mdsadmin/Stock/tw-stock-analysis

# 設置 API Token
export FINMIND_API_TOKEN=""

# 生成日誌文件名
LOG_FILE="logs/stock_prices_download_$(date +%Y%m%d_%H%M%S).log"

echo "🚀 啟動股票價格數據下載"
echo "📂 股票列表: /tmp/stock_list_simple.txt"
echo "📅 日期範圍: 2022-01-01 ~ 2024-12-31"
echo "📝 日誌文件: $LOG_FILE"
echo ""

# 執行下載（前景運行，可使用 Ctrl+C 中斷）
python3 scripts/download_stock_prices.py \
    --stock-list /tmp/stock_list_simple.txt \
    --start-date 2022-01-01 \
    --end-date 2024-12-31 \
    2>&1 | tee "$LOG_FILE"

echo ""
echo "✅ 下載完成！"
echo "📊 查看日誌: tail -f $LOG_FILE"
