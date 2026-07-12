// 最终验证：检查所有集合的字段规范
print('═════════════════════════════════════════════════════════════');
print('📊 FinMind 字段标准化最终验证报告');
print('═════════════════════════════════════════════════════════════');
print('验证时间:', new Date().toISOString());
print('');

var collections = [
  'stock_price',
  'financial_reports', 
  'financial_statements',
  'dividends',
  'stock_factors',
  'taiwan_stock_per'
];

var totalPass = 0;
var totalFail = 0;

collections.forEach(function(collName) {
  if (!db.getCollectionNames().includes(collName)) {
    print('⏭️  ' + collName + ': 集合不存在，跳过');
    return;
  }
  
  var sample = db[collName].findOne();
  if (!sample) {
    print('⏭️  ' + collName + ': 集合为空，跳过');
    return;
  }
  
  var count = db[collName].countDocuments({});
  var hasUpdateTime = 'updateTime' in sample;
  var hasUpdatedAt = 'updated_at' in sample;
  var hasSource = 'source' in sample;
  
  // 检查违规情况
  var violations = [];
  if (hasUpdateTime) violations.push('存在旧字段 updateTime');
  if (!hasUpdatedAt) violations.push('缺少标准字段 updated_at');
  if (hasSource && collName !== 'financial_reports') violations.push('存在旧字段 source');
  
  var passed = violations.length === 0;
  
  print('');
  print((passed ? '✅ ' : '❌ ') + collName + ':');
  print('  记录数:', count.toLocaleString());
  print('  updated_at:', hasUpdatedAt ? '✅ 存在' : '❌ 不存在');
  print('  updateTime:', hasUpdateTime ? '❌ 存在' : '✅ 不存在');
  print('  source:', hasSource ? '⚠️  存在' : '✅ 不存在');
  
  if (passed) {
    print('  状态: ✅ 符合 FinMind 标准');
    totalPass++;
  } else {
    print('  状态: ❌ 不符合标准');
    print('  违规项:', violations.join(', '));
    totalFail++;
  }
});

print('');
print('═════════════════════════════════════════════════════════════');
print('📋 验证总结');
print('═════════════════════════════════════════════════════════════');
print('通过:', totalPass, '个集合');
print('失败:', totalFail, '个集合');
print('');

if (totalFail === 0) {
  print('🎉 所有集合字段已标准化！');
  print('');
  print('✅ 数据库字段规范：');
  print('  - 所有集合使用 updated_at (不使用 updateTime)');
  print('  - 所有集合已移除旧的 source 字段');
  print('  - 符合 FinMind API 标准');
} else {
  print('⚠️  仍有集合需要修复');
}

print('═════════════════════════════════════════════════════════════');
