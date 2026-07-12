// 台股資料完整性檢查
print('=== 台股資料完整性檢查 ===\n');

// 1. 股價資料
const allSymbols = db.stock_price.distinct('symbol');
const stockSymbols = allSymbols.filter(function(s) { return s.length === 4 && s.charAt(0) !== '0'; });
const etfSymbols = allSymbols.filter(function(s) { return s.length === 4 && s.charAt(0) === '0'; });
const otherSymbols = allSymbols.filter(function(s) { return s.length !== 4; });

print('【股價資料 (stock_price)】');
print('  總計: ' + allSymbols.length + ' 支');
print('  一般股票 (1xxx-9xxx): ' + stockSymbols.length + ' 支');
print('  ETF (0xxx): ' + etfSymbols.length + ' 支');
print('  其他: ' + otherSymbols.length + ' 支');
print('  ETF 範例: ' + etfSymbols.slice(0, 10).join(', '));

// 2. 財報資料
const financialStocks = db.financial_statements.distinct('symbol');
print('\n【財報資料 (financial_statements)】');
print('  已下載: ' + financialStocks.length + ' 支');
print('  目標: ' + stockSymbols.length + ' 支（一般股票，不含 ETF）');
print('  完成度: ' + (financialStocks.length / stockSymbols.length * 100).toFixed(1) + '%');

// 3. 檢查是否有 ETF 被誤下載財報
const etfWithFinancials = financialStocks.filter(function(s) { return s.charAt(0) === '0'; });
if (etfWithFinancials.length > 0) {
    print('\n⚠️  警告: 發現 ' + etfWithFinancials.length + ' 支 ETF 有財報資料（應該忽略）');
    print('  ETF 清單: ' + etfWithFinancials.join(', '));
}

// 4. 公司基本資料
const companiesCount = db.stocks.countDocuments();
const companiesWithStock = db.stocks.distinct('symbol');
print('\n【公司基本資料 (stocks)】');
print('  總計: ' + companiesCount + ' 筆');
print('  有股票代碼: ' + companiesWithStock.length + ' 筆');

// 5. 待下載清單
const remaining = stockSymbols.filter(function(s) { 
    return financialStocks.indexOf(s) === -1; 
});
print('\n【待下載財報】');
print('  剩餘: ' + remaining.length + ' 支股票');
if (remaining.length > 0 && remaining.length <= 20) {
    print('  清單: ' + remaining.join(', '));
} else if (remaining.length > 0) {
    print('  前 20 支: ' + remaining.slice(0, 20).join(', '));
}

// 6. 資料品質檢查
print('\n【資料品質檢查】');

// 檢查股價資料完整性
const priceDataCheck = db.stock_price.aggregate([
    { $group: { _id: '$symbol', count: { $sum: 1 }, latest: { $max: '$date' } } },
    { $match: { count: { $lt: 10 } } }
]).toArray();

if (priceDataCheck.length > 0) {
    print('⚠️  發現 ' + priceDataCheck.length + ' 支股票的股價資料少於 10 筆');
}

// 檢查財報資料完整性
const financialQualityCheck = db.financial_statements.aggregate([
    { $group: { _id: '$symbol', quarters: { $sum: 1 } } },
    { $match: { quarters: { $lt: 5 } } }
]).toArray();

if (financialQualityCheck.length > 0) {
    print('⚠️  發現 ' + financialQualityCheck.length + ' 支股票的財報資料少於 5 季（可能是新上市）');
    print('  範例: ' + financialQualityCheck.slice(0, 5).map(function(d) { 
        return d._id + '(' + d.quarters + '季)'; 
    }).join(', '));
}

print('\n【總結】');
print('✓ 股價資料: ' + allSymbols.length + ' 支（含股票 + ETF）');
print('✓ ETF 股價: ' + etfSymbols.length + ' 支');
print('○ 財報進度: ' + financialStocks.length + '/' + stockSymbols.length + ' (' + 
      (financialStocks.length / stockSymbols.length * 100).toFixed(1) + '%)');
