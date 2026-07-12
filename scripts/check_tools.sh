#!/bin/bash
# 快速驗證所有工具是否存在

echo "================================================================================"
echo "🔍 驗證 P0/P1/P2 工具完整性"
echo "================================================================================"
echo ""

# 切換到專案根目錄
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo "📁 專案根目錄: $PROJECT_ROOT"
echo ""

# 檢查工具列表
TOOLS=(
    "src/migrations/p0_force_decimal_migration.py"
    "src/utils/quick_type_check.py"
    "src/utils/date_cleaner.py"
    "src/calculators/adj_close_calculator_atomic.py"
    "src/downloaders/stock_split_downloader.py"
    "src/calculators/market_metrics_calculator.py"
)

MISSING=0

for tool in "${TOOLS[@]}"; do
    if [ -f "$tool" ]; then
        echo "✅ $tool"
    else
        echo "❌ $tool (缺失)"
        MISSING=$((MISSING + 1))
    fi
done

echo ""
echo "================================================================================"

if [ $MISSING -eq 0 ]; then
    echo "✅ 所有工具完整！"
    echo ""
    echo "可以執行："
    echo "  ./scripts/execute_all_improvements_auto.sh  # 自動執行（推薦）"
    echo "  ./scripts/execute_all_improvements.sh       # 交互式執行"
else
    echo "❌ 有 $MISSING 個工具缺失"
    exit 1
fi

echo "================================================================================"
echo ""
