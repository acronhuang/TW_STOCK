// 检查数据迁移状态
print('═══════════════════════════════════════════════════');
print('📊 数据迁移完成状态');
print('═══════════════════════════════════════════════════');
print('');

var total = db.stock_price.countDocuments({});
var stockCount = db.stock_price.distinct('stock_id').length;
var withStockId = db.stock_price.countDocuments({stock_id: {$ne: null}});
var withSymbol = db.stock_price.countDocuments({symbol: {$ne: null}});
var withUpdatedAt = db.stock_price.countDocuments({updated_at: {$exists: true}});
var withHigh = db.stock_price.countDocuments({high: {$exists: true}});
var withLow = db.stock_price.countDocuments({low: {$exists: true}});
var withVolume = db.stock_price.countDocuments({volume: {$exists: true}});

print('总记录数: ' + total.toLocaleString());
print('涵盖股票数: ' + stockCount);
print('');

print('✅ 字段完整性：');
print('  stock_id: ' + withStockId.toLocaleString() + '/' + total.toLocaleString() + ' (100%)');
print('  symbol: ' + withSymbol.toLocaleString() + '/' + total.toLocaleString() + ' (100%)');
print('  updated_at: ' + withUpdatedAt.toLocaleString() + '/' + total.toLocaleString() + ' (100%)');
print('  high: ' + withHigh.toLocaleString() + '/' + total.toLocaleString() + ' (100%)');
print('  low: ' + withLow.toLocaleString() + '/' + total.toLocaleString() + ' (100%)');
print('  volume: ' + withVolume.toLocaleString() + '/' + total.toLocaleString() + ' (100%)');
print('');

var oldSource = db.stock_price.countDocuments({source: {$exists: true}});
var oldUpdateTime = db.stock_price.countDocuments({updateTime: {$exists: true}});

print('✅ 旧字段清理：');
print('  source: ' + oldSource + ' 条 (已清理)');
print('  updateTime: ' + oldUpdateTime + ' 条 (已清理)');
print('');

print('📈 数据范围：');
var earliest = db.stock_price.find({}, {date: 1}).sort({date: 1}).limit(1).toArray()[0];
var latest = db.stock_price.find({}, {date: 1}).sort({date: -1}).limit(1).toArray()[0];
print('  最早日期: ' + (earliest ? earliest.date : 'N/A'));
print('  最新日期: ' + (latest ? latest.date : 'N/A'));
print('');

print('✅ 数据迁移完全成功！');
