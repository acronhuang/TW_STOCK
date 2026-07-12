// 檢查所有集合的時間字段
print('檢查所有集合的時間字段:');
print('='.repeat(60));

var collections = [
  'stock_price',
  'financial_reports', 
  'financial_statements',
  'dividends',
  'stock_factors',
  'taiwan_stock_per',
  'stock_split',
  'outstanding_shares'
];

collections.forEach(function(collName) {
  if (db.getCollectionNames().includes(collName)) {
    var sample = db[collName].findOne();
    if (sample) {
      var hasUpdateTime = 'updateTime' in sample;
      var hasUpdatedAt = 'updated_at' in sample;
      var hasSource = 'source' in sample;
      
      print('\n📁 ' + collName + ':');
      print('  記錄數:', db[collName].countDocuments({}));
      print('  updateTime:', hasUpdateTime ? '❌ 存在 (需修改)' : '✅ 不存在');
      print('  updated_at:', hasUpdatedAt ? '✅ 存在' : '❌ 不存在 (需添加)');
      print('  source:', hasSource ? '❌ 存在 (可能需刪除)' : '✅ 不存在');
    }
  } else {
    print('\n📭 ' + collName + ': 集合不存在');
  }
});

print('\n' + '='.repeat(60));
print('完成檢查');
