#!/usr/bin/env node
/**
 * Schema 欄位驗證腳本
 * 比對舊資料與新 Schema 的欄位差異
 */

const { MongoClient } = require('mongodb');

const OLD_URI = 'mongodb://localhost:27017/stock-data';
const NEW_URI = 'mongodb://localhost:27018/tw_stock_analysis';

async function verifySchema() {
  console.log('🔍 Schema 欄位驗證工具');
  console.log('='.repeat(50));
  console.log('');

  const oldClient = new MongoClient(OLD_URI);
  const newClient = new MongoClient(NEW_URI);

  try {
    await oldClient.connect();
    await newClient.connect();

    const oldDb = oldClient.db('stock-data');
    const newDb = newClient.db('tw_stock_analysis');

    // 驗證 tickers 集合
    console.log('📊 驗證 Tickers 集合');
    console.log('-'.repeat(50));

    const oldTicker = await oldDb.collection('tickers').findOne({ type: 'STOCK' });
    const newTicker = await newDb.collection('tickers').findOne();

    if (oldTicker) {
      console.log('\n舊資料欄位:');
      console.log(Object.keys(oldTicker).sort().join(', '));
    }

    console.log('\n新 Schema 必要欄位:');
    const requiredFields = [
      'date', 'symbol', 'name', 'type', 'exchange', 'market',
      'openPrice', 'highPrice', 'lowPrice', 'closePrice', 'close',
      'change', 'changePercent', 'volume', 'tradeVolume'
    ];
    console.log(requiredFields.join(', '));

    // 檢查欄位對應
    console.log('\n欄位對應檢查:');
    const fieldMapping = {
      'date': 'date',
      'symbol': 'symbol',
      'name': 'name',
      'type': 'type',
      'exchange': 'exchange',
      'market': 'market',
      'openPrice': 'openPrice',
      'highPrice': 'highPrice',
      'lowPrice': 'lowPrice',
      'closePrice': 'closePrice',
      'close': 'closePrice', // 相容欄位
      'change': 'change',
      'changePercent': 'changePercent',
      'volume': 'tradeVolume',
      'tradeVolume': 'tradeVolume'
    };

    for (const [newField, oldField] of Object.entries(fieldMapping)) {
      const exists = oldTicker && oldTicker.hasOwnProperty(oldField);
      const status = exists ? '✅' : '⚠️';
      console.log(`  ${status} ${newField} <- ${oldField}`);
    }

    // 統計資訊
    console.log('\n統計資訊:');
    const oldTickerCount = await oldDb.collection('tickers').countDocuments();
    const oldStockCount = await oldDb.collection('tickers').countDocuments({ type: 'STOCK' });
    const oldIndexCount = await oldDb.collection('tickers').countDocuments({ type: 'INDEX' });

    console.log(`  舊資料總筆數: ${oldTickerCount.toLocaleString()}`);
    console.log(`  - 股票: ${oldStockCount.toLocaleString()}`);
    console.log(`  - 指數: ${oldIndexCount.toLocaleString()}`);

    // 驗證 financial_reports 集合
    console.log('\n\n📊 驗證 Financial Reports 集合');
    console.log('-'.repeat(50));

    const oldFinancial = await oldDb.collection('financial_reports').findOne();
    if (oldFinancial) {
      console.log('\n舊資料結構:');
      console.log(JSON.stringify(oldFinancial, null, 2).substring(0, 500) + '...');
    }

    const financialCount = await oldDb.collection('financial_reports').countDocuments();
    console.log(`\n財報資料筆數: ${financialCount.toLocaleString()}`);

    // 驗證 technicalindicators 集合
    console.log('\n\n📊 驗證 Technical Indicators 集合');
    console.log('-'.repeat(50));

    const oldTechnical = await oldDb.collection('technicalindicators').findOne();
    if (oldTechnical) {
      console.log('\n舊資料欄位:');
      console.log(Object.keys(oldTechnical).sort().join(', '));
    }

    const technicalCount = await oldDb.collection('technicalindicators').countDocuments();
    console.log(`\n技術指標資料筆數: ${technicalCount.toLocaleString()}`);

    // 建議
    console.log('\n\n💡 遷移建議:');
    console.log('='.repeat(50));
    console.log('1. Tickers 集合:');
    console.log('   - 可直接遷移，欄位基本相容');
    console.log('   - 建議過濾 type=STOCK (排除指數)');
    console.log('   - 需確保 volume 和 tradeVolume 欄位一致');
    console.log('');
    console.log('2. Financial Reports 集合:');
    console.log('   - 結構完整，可直接遷移');
    console.log('   - 注意 reportDate 欄位格式');
    console.log('');
    console.log('3. Technical Indicators 集合:');
    console.log('   - 需檢查指標欄位是否完整');
    console.log('   - 建議重新計算最新指標');
    console.log('');

  } catch (error) {
    console.error('❌ 錯誤:', error.message);
  } finally {
    await oldClient.close();
    await newClient.close();
  }
}

verifySchema().catch(console.error);
