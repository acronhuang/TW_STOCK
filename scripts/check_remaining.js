// 檢查剩餘未下載的股票
const all = db.stock_price.distinct('symbol').filter(function(s) { 
    return s.length === 4 && s.charAt(0) !== '0'; 
}).sort();

const downloaded = db.financial_statements.distinct('symbol');
const remaining = all.filter(function(s) { 
    return !downloaded.includes(s); 
});

print('剩餘未下載: ' + remaining.length + ' 支');
if (remaining.length > 0) {
    print('範圍: ' + remaining[0] + ' - ' + remaining[remaining.length - 1]);
    print('');
    print('前 20 支: ' + remaining.slice(0, 20).join(', '));
}
