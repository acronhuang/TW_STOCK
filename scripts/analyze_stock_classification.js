// 分析现有股票代码分布和分类
print('检查现有股票代码分布:');
print('='.repeat(60));

// 获取所有股票代码
var allSymbols = db.stock_price.distinct('stock_id');
print('总股票数:', allSymbols.length);
print('');

// 分析股票代码特征
var normalStocks = [];
var etfs = [];
var warrants = [];
var special = [];
var other = [];

allSymbols.forEach(function(symbol) {
  if (!symbol) return;
  
  // ETF: 00 开头，4位数字
  if (/^00\d{2}$/.test(symbol)) {
    etfs.push(symbol);
  }
  // ETF: 00 开头，6位数字或带字母
  else if (/^00\d{3}/.test(symbol)) {
    etfs.push(symbol);
  }
  // 权证: 6位数字以0开头且以T结尾
  else if (/^\d{5}T$/.test(symbol)) {
    warrants.push(symbol);
  }
  // 特殊代码: 含字母（非权证）
  else if (/[A-Z]/.test(symbol) && !symbol.endsWith('T')) {
    special.push(symbol);
  }
  // 正常股票: 4位数字, 1-9开头
  else if (/^[1-9]\d{3}$/.test(symbol)) {
    normalStocks.push(symbol);
  }
  // 其他
  else {
    other.push(symbol);
  }
});

print('📊 股票分类统计:');
print('  正常股票 (4位数字, 1-9开头):', normalStocks.length);
print('  ETF (00开头):', etfs.length);
print('  权证 (5位数+T):', warrants.length);
print('  特殊代码 (含字母):', special.length);
print('  其他:', other.length);
print('');

print('📝 样本:');
print('  正常股票:', normalStocks.slice(0, 10).join(', '));
print('  ETF:', etfs.slice(0, 10).join(', '));
if (warrants.length > 0) {
  print('  权证:', warrants.slice(0, 5).join(', '));
}
if (special.length > 0) {
  print('  特殊代码:', special.slice(0, 5).join(', '));
}
if (other.length > 0) {
  print('  其他:', other.slice(0, 5).join(', '));
}

print('');
print('='.repeat(60));

// 检查 taiwan_stock_info 是否有 security_type 字段
print('\n检查 taiwan_stock_info 集合的 security_type 字段:');
var sampleInfo = db.taiwan_stock_info.findOne({});
if (sampleInfo) {
  print('样本记录字段:', Object.keys(sampleInfo).filter(k => k !== '_id').join(', '));
  print('');
  if ('security_type' in sampleInfo) {
    print('✅ security_type 字段存在');
    var types = db.taiwan_stock_info.aggregate([
      {$group: {_id: '$security_type', count: {$sum: 1}}},
      {$sort: {count: -1}}
    ]).toArray();
    print('证券类型分布:');
    types.forEach(function(t) {
      print('  ' + (t._id || 'null') + ':', t.count);
    });
  } else {
    print('❌ security_type 字段不存在');
  }
} else {
  print('⚠️  taiwan_stock_info 集合为空');
}
