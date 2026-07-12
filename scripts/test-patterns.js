#!/usr/bin/env node
/**
 * 技術型態掃描測試腳本
 * 用於測試12種技術型態的識別功能
 */

const axios = require('axios');

const BASE_URL = 'http://localhost:3000';

// 測試數據
const TEST_SYMBOLS = ['2330', '2317', '2454', '2412', '2308'];

async function testPatternScanner() {
  console.log('========================================');
  console.log('技術型態掃描器測試');
  console.log('========================================\n');

  try {
    // 1. 健康檢查
    console.log('1. 健康檢查...');
    const health = await axios.get(`${BASE_URL}/api/patterns/health`);
    console.log('✓ 服務正常運行');
    console.log(`  支援型態數: ${health.data.patterns}`);
    console.log('');

    // 2. 獲取型態類型列表
    console.log('2. 獲取支援的型態類型...');
    const types = await axios.get(`${BASE_URL}/api/patterns/types`);
    console.log(`✓ 共支援 ${types.data.summary.total} 種型態`);
    console.log(`  多頭型態: ${types.data.summary.bullish}`);
    console.log(`  空頭型態: ${types.data.summary.bearish}`);
    console.log('');

    // 3. 掃描單一股票
    console.log('3. 掃描單一股票 (2330)...');
    const singleScan = await axios.get(`${BASE_URL}/api/patterns/scan/2330?days=120`);
    console.log('✓ 掃描完成');
    console.log(`  當前價格: ${singleScan.data.currentPrice}`);
    console.log(`  檢測到型態: ${singleScan.data.summary.totalDetected}`);
    console.log(`  多頭信號: ${singleScan.data.summary.bullishSignals}`);
    console.log(`  空頭信號: ${singleScan.data.summary.bearishSignals}`);
    
    if (singleScan.data.detectedPatterns.length > 0) {
      console.log('  檢測到的型態:');
      singleScan.data.detectedPatterns.forEach(p => {
        console.log(`    - ${p.pattern} (${p.type === 'bullish' ? '多頭' : '空頭'})`);
      });
    }
    console.log('');

    // 4. 批量掃描
    console.log(`4. 批量掃描 (${TEST_SYMBOLS.join(', ')})...`);
    const multipleScan = await axios.get(
      `${BASE_URL}/api/patterns/scan-multiple?symbols=${TEST_SYMBOLS.join(',')}&days=120`
    );
    console.log('✓ 批量掃描完成');
    console.log(`  掃描股票數: ${multipleScan.data.length}`);
    
    const withSignals = multipleScan.data.filter(s => s.summary && s.summary.totalDetected > 0);
    console.log(`  有信號股票: ${withSignals.length}`);
    
    withSignals.forEach(stock => {
      console.log(`    ${stock.symbol}: ${stock.summary.totalDetected} 個型態`);
    });
    console.log('');

    // 5. 生成報告
    console.log('5. 生成技術型態報告 (2330)...');
    const report = await axios.get(`${BASE_URL}/api/patterns/report/2330`);
    console.log('✓ 報告生成完成');
    console.log(report.data.report);

    // 6. 搜尋特定型態
    console.log('6. 搜尋 W底 型態的股票...');
    const patternSearch = await axios.get(
      `${BASE_URL}/api/patterns/find-by-pattern?pattern=W底&limit=5`
    );
    console.log(`✓ 找到 ${patternSearch.data.length} 支符合條件的股票`);
    patternSearch.data.forEach(stock => {
      console.log(`  - ${stock.symbol}: ${stock.currentPrice}`);
    });
    console.log('');

    console.log('========================================');
    console.log('所有測試完成！');
    console.log('========================================');

  } catch (error) {
    console.error('測試失敗:', error.message);
    if (error.response) {
      console.error('錯誤詳情:', error.response.data);
    }
  }
}

// 執行測試
testPatternScanner();
