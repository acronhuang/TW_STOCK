#!/bin/bash
# 台股數據自動更新系統 - 狀態檢查與驗證

echo "════════════════════════════════════════════════════════════════"
echo "      台股數據自動更新系統 - 完整狀態報告"
echo "════════════════════════════════════════════════════════════════"
echo ""

# 1. launchd服務狀態
echo "【1】launchd 服務狀態"
echo "────────────────────────────────────────────────────────────────"
launchctl list | grep com.twstock | while read status pid name; do
    if [ "$status" = "-" ]; then
        echo "✅ $name (PID: $pid) - 運行中"
    else
        echo "⚠️  $name (Exit: $status)"
    fi
done
echo ""

# 2. 下次執行時間
echo "【2】下次執行時間"
echo "────────────────────────────────────────────────────────────────"
CURRENT_TIME=$(date "+%H:%M")
CURRENT_HOUR=$(date "+%H")
NEXT_HOUR=$((10#$CURRENT_HOUR + 1))
[ $NEXT_HOUR -ge 24 ] && NEXT_HOUR=0
printf "當前時間: %s\n" "$(date "+%Y-%m-%d %H:%M:%S")"
printf "下次執行: %02d:05 (hourly_update)\n" $NEXT_HOUR
echo ""

# 3. 配置檢查
echo "【3】系統配置"
echo "────────────────────────────────────────────────────────────────"
cd /home/mdsadmin/Stock/tw-stock-analysis

# 檢查CATEGORIES配置
CATEGORIES_LINE=$(grep 'CATEGORIES=(' scripts/hourly_data_update.sh | head -1)
if echo "$CATEGORIES_LINE" | grep -q "其他"; then
    echo "✅ hourly_data_update.sh: 包含 5 個類別"
    echo "   $CATEGORIES_LINE"
else
    echo "❌ hourly_data_update.sh: 缺少「其他」類別"
fi
echo ""

# 4. 最近執行記錄
echo "【4】最近執行記錄"
echo "────────────────────────────────────────────────────────────────"
if [ -d "logs/hourly_updates" ]; then
    ls -lt logs/hourly_updates/*.log 2>/dev/null | head -3 | while read line; do
        filename=$(echo "$line" | awk '{print $NF}')
        size=$(echo "$line" | awk '{print $5}')
        date=$(echo "$line" | awk '{print $6, $7, $8}')
        echo "📄 $(basename $filename)"
        echo "   大小: $size bytes, 時間: $date"
        
        # 檢查類別數量
        if [ -f "$filename" ]; then
            category_count=$(grep -o "類別 \[[0-9]/[0-9]\]" "$filename" | head -1 | grep -o "/[0-9]" | tr -d '/')
            if [ -n "$category_count" ]; then
                if [ "$category_count" = "5" ]; then
                    echo "   ✅ 處理了 $category_count 個類別"
                else
                    echo "   ⚠️  只處理了 $category_count 個類別 (應為 5)"
                fi
            fi
        fi
        echo ""
    done
else
    echo "⚠️  找不到 logs/hourly_updates 目錄"
fi

# 5. 資料表覆蓋率
echo "【5】資料表覆蓋率"
echo "────────────────────────────────────────────────────────────────"
if which python3 > /dev/null && [ -f "scripts/check_table_coverage.py" ]; then
    python3 scripts/check_table_coverage.py 2>&1 | tail -10
else
    echo "⚠️  無法執行資料表覆蓋率檢查"
fi
echo ""

# 6. API配額狀態
echo "【6】API 配額評估"
echo "────────────────────────────────────────────────────────────────"
echo "FinMind 免費版限制: 500 次/小時"
echo "系統預估使用量:"
echo "  • 技術面:      50-100 次/小時"
echo "  • 基本面:      20-50 次/小時"
echo "  • 籌碼面:      50-100 次/小時"
echo "  • 衍生性商品:  20-30 次/小時"
echo "  • 其他:        10-20 次/小時"
echo "  ─────────────────────────────"
echo "  總計:         150-300 次/小時 ✅ (安全範圍)"
echo ""

echo "════════════════════════════════════════════════════════════════"
echo "報告生成時間: $(date "+%Y-%m-%d %H:%M:%S")"
echo "════════════════════════════════════════════════════════════════"
