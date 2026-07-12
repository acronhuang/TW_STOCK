#!/bin/bash
#
# 資料庫改進 - 一鍵驗證腳本
# 用於快速檢查所有改進是否正確應用
#

set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔍 資料庫改進驗證工具"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 進入專案目錄
cd "$(dirname "$0")"

# 顏色定義
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 檢查 MongoDB 是否運行
echo -e "${BLUE}[1/5] 檢查 MongoDB 連線...${NC}"
if mongosh tw_stock_analysis --quiet --eval "db.stats()" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ MongoDB 連線正常${NC}"
else
    echo -e "${RED}✗ MongoDB 連線失敗！請確保 MongoDB 正在運行${NC}"
    echo "  提示: brew services start mongodb-community"
    exit 1
fi
echo ""

# P0 驗證
echo -e "${BLUE}[2/5] P0: Decimal128 精度驗證${NC}"
DECIMAL_RESULT=$(mongosh tw_stock_analysis --quiet --eval "
var div = db.dividend_detail.findOne();
var result = 'FAIL';
if (div && div.cash_earnings_distribution) {
    var type = div.cash_earnings_distribution.constructor.name;
    if (type === 'Decimal128') {
        result = 'PASS';
    }
}
print(result);
" | tail -1)

if [ "$DECIMAL_RESULT" == "PASS" ]; then
    echo -e "${GREEN}✓ dividend_detail 欄位已轉換為 Decimal128${NC}"
else
    echo -e "${YELLOW}⚠ dividend_detail 欄位尚未轉換（或無資料）${NC}"
    echo "  執行: python3 src/migrations/p0_decimal_migration.py --execute"
fi
echo ""

# P1-A 驗證
echo -e "${BLUE}[3/5] P1-A: 命名規範驗證${NC}"
NAMING_RESULT=$(mongosh tw_stock_analysis --quiet --eval "
var price = db.stock_price.findOne();
var hasClose = price && price.close ? 'Y' : 'N';
var hasVolume = price && price.volume ? 'Y' : 'N';
var noOldFields = price && !price.closePrice ? 'Y' : 'N';
print(hasClose + '|' + hasVolume + '|' + noOldFields);
" | tail -1)

IFS='|' read -r HAS_CLOSE HAS_VOLUME NO_OLD <<< "$NAMING_RESULT"

if [ "$HAS_CLOSE" == "Y" ] && [ "$HAS_VOLUME" == "Y" ]; then
    echo -e "${GREEN}✓ stock_price 欄位命名已規範化${NC}"
    echo -e "  - close 欄位: ${GREEN}✓${NC}"
    echo -e "  - volume 欄位: ${GREEN}✓${NC}"
    if [ "$NO_OLD" == "Y" ]; then
        echo -e "  - 舊欄位已清除: ${GREEN}✓${NC}"
    else
        echo -e "  - 舊欄位殘留: ${YELLOW}⚠${NC}"
    fi
else
    echo -e "${YELLOW}⚠ stock_price 欄位尚未規範化（或使用舊命名）${NC}"
    echo "  執行: python3 src/migrations/p1_naming_migration.py --execute"
fi
echo ""

# P1-B 驗證
echo -e "${BLUE}[4/5] P1-B: 調整後收盤價驗證${NC}"
ADJ_CLOSE_STATS=$(mongosh tw_stock_analysis --quiet --eval "
var withAdj = db.stock_price.countDocuments({adj_close: {\$exists: true}});
var total = db.stock_price.countDocuments({});
var coverage = total > 0 ? (withAdj / total * 100).toFixed(2) : 0;
print(withAdj + '|' + total + '|' + coverage);
" | tail -1)

IFS='|' read -r WITH_ADJ TOTAL_PRICE COVERAGE <<< "$ADJ_CLOSE_STATS"

echo "  有 adj_close: $(printf "%'d" "$WITH_ADJ") / $(printf "%'d" "$TOTAL_PRICE") 筆 ($COVERAGE%)"

if (( $(echo "$COVERAGE > 95" | bc -l) )); then
    echo -e "${GREEN}✓ 調整後收盤價覆蓋率優秀 (>95%)${NC}"
elif (( $(echo "$COVERAGE > 0" | bc -l) )); then
    echo -e "${YELLOW}⚠ 調整後收盤價覆蓋率: $COVERAGE%${NC}"
    echo "  執行: python3 src/calculators/adj_close_calculator.py --all --execute"
else
    echo -e "${YELLOW}⚠ 尚未計算調整後收盤價${NC}"
    echo "  執行: python3 src/calculators/adj_close_calculator.py --all --execute"
fi
echo ""

# P2 驗證
echo -e "${BLUE}[5/5] P2: 關鍵欄位補齊驗證${NC}"
P2_RESULT=$(mongosh tw_stock_analysis --quiet --eval "
var info = db.taiwan_stock_info.findOne({security_type: {\$exists: true}});
var hasType = info && info.security_type ? 'Y' : 'N';
var hasIndustry = info && info.industry_l1 ? 'Y' : 'N';
var delistedCount = db.taiwan_stock_info.countDocuments({is_delisted: true});
print(hasType + '|' + hasIndustry + '|' + delistedCount);
" | tail -1)

IFS='|' read -r HAS_TYPE HAS_INDUSTRY DELISTED_COUNT <<< "$P2_RESULT"

if [ "$HAS_TYPE" == "Y" ]; then
    echo -e "${GREEN}✓ security_type 欄位已新增${NC}"
else
    echo -e "${YELLOW}⚠ security_type 欄位尚未新增${NC}"
    echo "  執行: python3 src/migrations/p2_field_enrichment.py --task add-security-type --execute"
fi

if [ "$HAS_INDUSTRY" == "Y" ]; then
    echo -e "${GREEN}✓ industry_l1/l2 多級分類已新增${NC}"
else
    echo -e "${YELLOW}⚠ industry_l1/l2 尚未新增${NC}"
    echo "  執行: python3 src/migrations/p2_field_enrichment.py --task split-industry --execute"
fi

echo "  下市標記數量: $DELISTED_COUNT"
if [ "$DELISTED_COUNT" -gt 0 ]; then
    echo -e "${GREEN}✓ 已標記下市股票${NC}"
else
    echo -e "${YELLOW}⚠ 尚未標記下市股票${NC}"
    echo "  執行: python3 src/migrations/p2_field_enrichment.py --task mark-delisted --execute"
fi
echo ""

# 總結
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${BLUE}📊 驗證總結${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 計算通過的項目
PASS_COUNT=0

[ "$DECIMAL_RESULT" == "PASS" ] && ((PASS_COUNT++))
[ "$HAS_CLOSE" == "Y" ] && [ "$HAS_VOLUME" == "Y" ] && ((PASS_COUNT++))
(( $(echo "$COVERAGE > 95" | bc -l) )) && ((PASS_COUNT++))
[ "$HAS_TYPE" == "Y" ] && ((PASS_COUNT++))
[ "$HAS_INDUSTRY" == "Y" ] && ((PASS_COUNT++))

TOTAL_CHECKS=5

echo "通過項目: $PASS_COUNT / $TOTAL_CHECKS"
echo ""

if [ "$PASS_COUNT" -eq "$TOTAL_CHECKS" ]; then
    echo -e "${GREEN}🎉 所有改進已成功應用！資料庫已達到專業標準。${NC}"
    echo ""
    echo "您現在可以："
    echo "  • 使用 adj_close 進行回測分析"
    echo "  • 依據 security_type 區分股票類型"
    echo "  • 使用多級行業分類進行同業比較"
    echo "  • 享受 Decimal128 的精確計算"
else
    echo -e "${YELLOW}⚠ 還有 $((TOTAL_CHECKS - PASS_COUNT)) 個項目需要處理${NC}"
    echo ""
    echo "請參考 DATABASE_IMPROVEMENT_EXECUTION_GUIDE.md 完成剩餘改進"
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
