#!/bin/bash
# 檢查批次下載進度

echo "=== 批次下載進度檢查 ==="
echo ""

# 檢查程式是否在執行
if ps aux | grep -v grep | grep batch_download_all_financials > /dev/null; then
    echo "✓ 下載程式正在執行中"
    PID=$(ps aux | grep -v grep | grep batch_download_all_financials | awk '{print $2}')
    echo "  PID: $PID"
    echo ""
else
    echo "✗ 下載程式未執行"
    echo ""
fi

# 統計資料庫中的股票數量
echo "--- 資料庫統計 ---"
mongosh --quiet tw_stock_analysis --eval "
    const fsCount = db.financial_statements.distinct('symbol').length;
    const total = db.stock_price.distinct('symbol').filter(s => s.length === 4 && !s.startsWith('0')).length;
    
    print('financial_statements: ' + fsCount + ' / ' + total + ' 股票');
    print('完成度: ' + (fsCount / total * 100).toFixed(1) + '%');
"

echo ""
echo "--- 最近下載的 10 支股票 ---"
mongosh --quiet tw_stock_analysis --eval "
    db.financial_statements.aggregate([
        { \$group: { 
            _id: '\$symbol', 
            count: { \$sum: 1 }, 
            updateTime: { \$max: '\$updateTime' },
            companyName: { \$first: '\$companyName' }
        }},
        { \$sort: { updateTime: -1 } },
        { \$limit: 10 }
    ]).forEach(doc => {
        const time = doc.updateTime ? doc.updateTime.toISOString().substr(11, 8) : 'N/A';
        print(doc._id + ' ' + (doc.companyName || '') + ': ' + doc.count + ' 季，更新: ' + time);
    });
"

echo ""
echo "使用方式: watch -n 30 ./scripts/check_download_progress.sh"
