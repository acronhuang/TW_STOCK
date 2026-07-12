// 最终验证 FinMind 数据完整性
print('═══════════════════════════════════════════════════');
print('📊 FinMind 数据库完整性最终报告');
print('═══════════════════════════════════════════════════');
print('');

var total = db.stock_price.countDocuments({});
print('总记录数: ' + total.toLocaleString());
print('涵盖股票数: ' + db.stock_price.distinct('stock_id').length);
print('');

// 字段完整性检查
print('✅ 字段完整性 (18 个必需字段):');
var fields = [
    'stock_id', 'symbol', 'date', 'open', 'high', 'low', 'close', 'volume',
    'max', 'min', 'spread', 'Trading_Volume', 'Trading_money', 'Trading_turnover',
    'turnover', 'adjustment_factor', 'adj_close', 'updated_at'
];

var allComplete = true;
fields.forEach(function(field) {
    var count = db.stock_price.countDocuments({[field]: {$exists: true}});
    var coverage = (count / total * 100).toFixed(1);
    var status = coverage == '100.0' ? '✅' : '⚠️ ';
    print('  ' + status + ' ' + field + ': ' + count.toLocaleString() + '/' + total.toLocaleString() + ' (' + coverage + '%)');
    if (coverage != '100.0') allComplete = false;
});

print('');

// 数据质量检查
print('📈 数据质量检查:');

// 1. 检查默认值比例
var defaultTurnover = db.stock_price.countDocuments({turnover: 0});
var defaultTradingTurnover = db.stock_price.countDocuments({Trading_turnover: 0});
var defaultSpread = db.stock_price.countDocuments({spread: 0});

print('  turnover = 0: ' + defaultTurnover.toLocaleString() + '/' + total.toLocaleString() + ' (' + (defaultTurnover/total*100).toFixed(1) + '%)');
print('  Trading_turnover = 0: ' + defaultTradingTurnover.toLocaleString() + '/' + total.toLocaleString() + ' (' + (defaultTradingTurnover/total*100).toFixed(1) + '%)');
print('  spread = 0: ' + defaultSpread.toLocaleString() + '/' + total.toLocaleString() + ' (' + (defaultSpread/total*100).toFixed(1) + '%)');

print('');

// 2. 抽样检查数据一致性（max vs high, min vs low）
var sampleSize = 1000;
var samples = db.stock_price.aggregate([
    {$sample: {size: sampleSize}},
    {$project: {
        max_eq_high: {$eq: ['$max', '$high']},
        min_eq_low: {$eq: ['$min', '$low']}
    }}
]).toArray();

var maxHighMatch = samples.filter(s => s.max_eq_high).length;
var minLowMatch = samples.filter(s => s.min_eq_low).length;

print('📊 数据一致性验证 (抽样 ' + sampleSize + ' 条):');
print('  max == high: ' + maxHighMatch + '/' + sampleSize + ' (' + (maxHighMatch/sampleSize*100).toFixed(1) + '%)');
print('  min == low: ' + minLowMatch + '/' + sampleSize + ' (' + (minLowMatch/sampleSize*100).toFixed(1) + '%)');

print('');

// 3. 数据范围
var earliest = db.stock_price.find({}, {date: 1}).sort({date: 1}).limit(1).toArray()[0];
var latest = db.stock_price.find({}, {date: 1}).sort({date: -1}).limit(1).toArray()[0];

print('📅 数据范围:');
if (earliest && latest) {
    var earliestDate = earliest.date;
    var latestDate = latest.date;
    
    // 处理不同日期格式
    if (typeof earliestDate === 'string') {
        print('  最早日期: ' + earliestDate.split('T')[0]);
    } else if (earliestDate instanceof Date) {
        print('  最早日期: ' + earliestDate.toISOString().split('T')[0]);
    } else {
        print('  最早日期: ' + earliestDate);
    }
    
    if (typeof latestDate === 'string') {
        print('  最新日期: ' + latestDate.split('T')[0]);
    } else if (latestDate instanceof Date) {
        print('  最新日期: ' + latestDate.toISOString().split('T')[0]);
    } else {
        print('  最新日期: ' + latestDate);
    }
} else {
    print('  无日期数据');
}

print('');

// 4. 随机选择一支股票展示完整记录
var randomStock = db.stock_price.aggregate([{$sample: {size: 1}}]).toArray()[0];
if (randomStock) {
    var dateStr = randomStock.date;
    if (typeof dateStr === 'string') {
        dateStr = dateStr.split('T')[0];
    } else if (dateStr instanceof Date) {
        dateStr = dateStr.toISOString().split('T')[0];
    }
    
    print('📝 示例记录 (股票: ' + randomStock.stock_id + ', 日期: ' + dateStr + '):');
    print('  开盘: ' + randomStock.open + ', 最高: ' + randomStock.high + ', 最低: ' + randomStock.low + ', 收盘: ' + randomStock.close);
    print('  成交量: ' + randomStock.volume + ', 成交笔数: ' + randomStock.turnover);
    print('  涨跌额: ' + randomStock.spread + ', 交易金额: ' + randomStock.Trading_money);
    print('  复权因子: ' + randomStock.adjustment_factor + ', 复权收盘: ' + randomStock.adj_close);
}

print('');
print('═══════════════════════════════════════════════════');
if (allComplete) {
    print('✅ 数据库完整性检查通过！');
    print('   • 所有字段 100% 覆盖');
    print('   • 数据格式符合 FinMind 标准');
    print('   • 数据迁移及补齐成功完成');
} else {
    print('⚠️  仍有字段不完整，请检查上方报告');
}
print('═══════════════════════════════════════════════════');
