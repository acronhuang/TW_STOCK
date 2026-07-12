#!/bin/bash
# 驗證多支股票的 DuPont 分析計算

echo "================================================================"
echo "台股 DuPont 分析驗證測試"
echo "測試時間: $(date '+%Y-%m-%d %H:%M:%S')"
echo "================================================================"

# 測試股票清單（不同產業）
TEST_STOCKS="2330 2317 2454 1101 1216 1301"

for symbol in $TEST_STOCKS; do
    echo ""
    echo "--- 測試 $symbol ---"
    
    response=$(curl -s "http://localhost:3000/api/v1/financial/$symbol/dupont?year=2024&period=Q3")
    
    if [ $? -ne 0 ]; then
        echo "❌ API 請求失敗"
        continue
    fi
    
    # 解析 JSON
    result=$(echo "$response" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    if 'error' in d:
        print(f\"❌ 錯誤: {d.get('message', 'Unknown error')}\")
    else:
        symbol = d.get('symbol', '$symbol')
        roe = d.get('roe', 0)
        net_margin = d.get('netMargin', 0)
        asset_turnover = d.get('assetTurnover', 0)
        equity_multiplier = d.get('equityMultiplier', 0)
        industry = d.get('analysis', {}).get('industryType', '未知')
        company_name = d.get('companyName', symbol)
        
        # 驗證計算
        calculated_roe = (net_margin / 100) * asset_turnover * equity_multiplier * 100
        diff = abs(roe - calculated_roe)
        
        status = '✓' if diff < 0.1 else '❌'
        
        print(f\"{status} {symbol} {company_name}\")
        print(f\"   ROE: {roe:.2f}% (驗算: {calculated_roe:.2f}%, 差異: {diff:.4f}%)\")
        print(f\"   淨利率: {net_margin:.2f}%\")
        print(f\"   資產週轉率: {asset_turnover:.4f}\")
        print(f\"   權益乘數: {equity_multiplier:.2f}\")
        print(f\"   產業: {industry}\")
except Exception as e:
    print(f\"❌ 解析錯誤: {str(e)}\")
")
    
    echo "$result"
done

echo ""
echo "================================================================"
echo "測試完成"
echo "================================================================"
