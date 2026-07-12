// 計算下載預估完成時間（使用最近 1 小時的速度）
const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000);
const recentStocks = db.financial_statements.distinct('symbol', {updateTime: {$gte: oneHourAgo}});
const recentCount = recentStocks.length;

const totalCount = db.financial_statements.distinct('symbol').length;
const total = 1947; // 固定總數
const remaining = total - totalCount;

if (recentCount > 0) {
    const stocksPerHour = recentCount;
    const hoursRemaining = remaining / stocksPerHour;
    
    print('=== 下載速度分析（最近 1 小時）===');
    print('已完成: ' + totalCount + ' / ' + total + ' 股票 (' + (totalCount/total*100).toFixed(1) + '%)');
    print('下載速度: ' + stocksPerHour + ' 股票/小時');
    print('剩餘: ' + remaining + ' 股票');
    print('預估完成: ' + hoursRemaining.toFixed(1) + ' 小時');
    
    const now = new Date();
    const finishTime = new Date(now.getTime() + hoursRemaining * 60 * 60 * 1000);
    print('預計完成時間: ' + finishTime.toLocaleString('zh-TW', {hour12: false, timeZone: 'Asia/Taipei'}));
} else {
    print('最近 1 小時無新下載，可能程式已暫停或剛啟動');
}
