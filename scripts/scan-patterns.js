#!/usr/bin/env node
/**
 * 技術型態掃描命令行工具
 * 使用方法:
 *   node scan-patterns.js scan 2330           # 掃描單一股票
 *   node scan-patterns.js scan 2330,2317      # 掃描多支股票
 *   node scan-patterns.js find W底            # 搜尋特定型態
 *   node scan-patterns.js report 2330         # 生成報告
 *   node scan-patterns.js bullish             # 多頭股票列表
 *   node scan-patterns.js bearish             # 空頭股票列表
 */

const axios = require('axios');
const fs = require('fs').promises;

const BASE_URL = process.env.API_URL || 'http://localhost:3000';
const COMMAND = process.argv[2];
const ARGS = process.argv.slice(3);

// 顏色輸出
const colors = {
  reset: '\x1b[0m',
  bright: '\x1b[1m',
  red: '\x1b[31m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  magenta: '\x1b[35m',
  cyan: '\x1b[36m',
};

function colorize(text, color) {
  return `${colors[color]}${text}${colors.reset}`;
}

function printHeader(text) {
  console.log('\n' + colorize('='.repeat(60), 'cyan'));
  console.log(colorize(text, 'bright'));
  console.log(colorize('='.repeat(60), 'cyan') + '\n');
}

function printSuccess(text) {
  console.log(colorize('✓ ' + text, 'green'));
}

function printError(text) {
  console.log(colorize('✗ ' + text, 'red'));
}

function printWarning(text) {
  console.log(colorize('⚠ ' + text, 'yellow'));
}

function printInfo(text) {
  console.log(colorize('ℹ ' + text, 'blue'));
}

// 掃描單一或多支股票
async function scanStocks(symbolsStr) {
  const symbols = symbolsStr.split(',').map(s => s.trim());
  
  printHeader(`掃描股票: ${symbols.join(', ')}`);

  try {
    let result;
    if (symbols.length === 1) {
      // 單一股票
      const response = await axios.get(`${BASE_URL}/api/patterns/scan/${symbols[0]}`);
      result = [response.data];
    } else {
      // 多支股票
      const response = await axios.get(
        `${BASE_URL}/api/patterns/scan-multiple?symbols=${symbolsStr}`
      );
      result = response.data;
    }

    for (const stock of result) {
      if (stock.error) {
        printError(`${stock.symbol}: ${stock.error}`);
        continue;
      }

      console.log(colorize(`\n【${stock.symbol}】`, 'bright'));
      console.log(`當前價格: ${colorize(stock.currentPrice.toFixed(2), 'yellow')}`);
      console.log(`數據點數: ${stock.dataPoints}`);
      console.log(`檢測型態: ${stock.summary.totalDetected}`);
      console.log(`多頭信號: ${colorize(stock.summary.bullishSignals, 'green')}`);
      console.log(`空頭信號: ${colorize(stock.summary.bearishSignals, 'red')}`);

      if (stock.detectedPatterns.length > 0) {
        console.log('\n檢測到的型態:');
        for (const pattern of stock.detectedPatterns) {
          const typeColor = pattern.type === 'bullish' ? 'green' : 'red';
          const typeText = pattern.type === 'bullish' ? '多頭' : '空頭';
          console.log(`  ${colorize('●', typeColor)} ${pattern.pattern} (${typeText})`);
          console.log(`    ${pattern.signal}`);
          
          if (pattern.target || pattern.target1) {
            const target = pattern.target || pattern.target1;
            console.log(`    目標價: ${colorize(target.toFixed(2), 'yellow')}`);
          }
          
          if (pattern.buyPoint) {
            console.log(`    買點: ${colorize(pattern.buyPoint.toFixed(2), 'green')}`);
          }
          
          if (pattern.stopLoss) {
            console.log(`    停損: ${colorize(pattern.stopLoss.toFixed(2), 'red')}`);
          }
        }
      } else {
        printInfo('未檢測到明確的技術型態');
      }
    }

    printSuccess(`\n掃描完成！共處理 ${result.length} 支股票`);
  } catch (error) {
    printError(`掃描失敗: ${error.message}`);
    process.exit(1);
  }
}

// 搜尋特定型態
async function findPattern(patternName, limit = 10) {
  printHeader(`搜尋型態: ${patternName}`);

  try {
    const response = await axios.get(
      `${BASE_URL}/api/patterns/find-by-pattern?pattern=${encodeURIComponent(patternName)}&limit=${limit}`
    );
    
    const results = response.data;

    if (results.length === 0) {
      printWarning('未找到符合條件的股票');
      return;
    }

    console.log(`找到 ${colorize(results.length, 'green')} 支符合條件的股票:\n`);

    for (const stock of results) {
      const patterns = stock.detectedPatterns.filter(p => 
        p.pattern.includes(patternName) || p.pattern === patternName
      );
      
      console.log(colorize(`${stock.symbol}`, 'bright') + ` - 價格: ${stock.currentPrice.toFixed(2)}`);
      for (const pattern of patterns) {
        console.log(`  ${pattern.pattern}: ${pattern.signal}`);
        if (pattern.description) {
          console.log(`  ${pattern.description.substring(0, 80)}...`);
        }
      }
      console.log('');
    }

    printSuccess(`搜尋完成！`);
  } catch (error) {
    printError(`搜尋失敗: ${error.message}`);
    process.exit(1);
  }
}

// 生成報告
async function generateReport(symbol) {
  printHeader(`生成報告: ${symbol}`);

  try {
    const response = await axios.get(`${BASE_URL}/api/patterns/report/${symbol}`);
    console.log(response.data.report);
    
    // 選擇性儲存到檔案
    const filename = `pattern_report_${symbol}_${Date.now()}.txt`;
    await fs.writeFile(filename, response.data.report);
    printSuccess(`報告已儲存至: ${filename}`);
  } catch (error) {
    printError(`生成報告失敗: ${error.message}`);
    process.exit(1);
  }
}

// 列出多頭股票
async function listBullish(limit = 20) {
  printHeader('多頭型態股票列表');

  try {
    const response = await axios.get(`${BASE_URL}/api/patterns/bullish`);
    const stocks = response.data.stocks.slice(0, limit);

    console.log(`掃描日期: ${new Date(response.data.scanDate).toLocaleString('zh-TW')}`);
    console.log(`總掃描數: ${response.data.totalScanned}`);
    console.log(`多頭股票: ${colorize(response.data.bullishCount, 'green')}\n`);

    console.log(colorize('排名  股票  價格    多頭信號  空頭信號  型態數', 'bright'));
    console.log('─'.repeat(60));

    stocks.forEach((stock, idx) => {
      const rank = `${idx + 1}`.padEnd(4);
      const symbol = stock.symbol.padEnd(6);
      const price = stock.currentPrice.toFixed(2).padEnd(8);
      const bullish = colorize(stock.summary.bullishSignals.toString().padEnd(10), 'green');
      const bearish = stock.summary.bearishSignals.toString().padEnd(10);
      const total = stock.summary.totalDetected;
      
      console.log(`${rank}  ${symbol}  ${price}  ${bullish}  ${bearish}  ${total}`);
    });

    printSuccess(`\n列表完成！`);
  } catch (error) {
    printError(`獲取列表失敗: ${error.message}`);
    process.exit(1);
  }
}

// 列出空頭股票
async function listBearish(limit = 20) {
  printHeader('空頭型態股票列表');

  try {
    const response = await axios.get(`${BASE_URL}/api/patterns/bearish`);
    const stocks = response.data.stocks.slice(0, limit);

    console.log(`掃描日期: ${new Date(response.data.scanDate).toLocaleString('zh-TW')}`);
    console.log(`總掃描數: ${response.data.totalScanned}`);
    console.log(`空頭股票: ${colorize(response.data.bearishCount, 'red')}\n`);

    console.log(colorize('排名  股票  價格    多頭信號  空頭信號  型態數', 'bright'));
    console.log('─'.repeat(60));

    stocks.forEach((stock, idx) => {
      const rank = `${idx + 1}`.padEnd(4);
      const symbol = stock.symbol.padEnd(6);
      const price = stock.currentPrice.toFixed(2).padEnd(8);
      const bullish = stock.summary.bullishSignals.toString().padEnd(10);
      const bearish = colorize(stock.summary.bearishSignals.toString().padEnd(10), 'red');
      const total = stock.summary.totalDetected;
      
      console.log(`${rank}  ${symbol}  ${price}  ${bullish}  ${bearish}  ${total}`);
    });

    printSuccess(`\n列表完成！`);
  } catch (error) {
    printError(`獲取列表失敗: ${error.message}`);
    process.exit(1);
  }
}

// 顯示說明
function showHelp() {
  console.log(`
${colorize('技術型態掃描工具', 'bright')}

${colorize('使用方法:', 'cyan')}
  node scan-patterns.js <command> [arguments]

${colorize('命令列表:', 'cyan')}
  ${colorize('scan <symbols>', 'green')}      掃描股票 (支援單一或多支，逗號分隔)
    範例: node scan-patterns.js scan 2330
    範例: node scan-patterns.js scan 2330,2317,2454

  ${colorize('find <pattern>', 'green')}      搜尋特定型態的股票
    範例: node scan-patterns.js find W底
    範例: node scan-patterns.js find 頭肩頂

  ${colorize('report <symbol>', 'green')}     生成股票的技術型態報告
    範例: node scan-patterns.js report 2330

  ${colorize('bullish', 'green')}             列出多頭型態股票
    範例: node scan-patterns.js bullish

  ${colorize('bearish', 'green')}             列出空頭型態股票
    範例: node scan-patterns.js bearish

  ${colorize('help', 'green')}                顯示此說明

${colorize('支援的型態:', 'cyan')}
  ${colorize('多頭:', 'green')} W底、破底翻、破底翻(W底)、下飄旗形、頭肩底、收斂三角形(底部)
  ${colorize('空頭:', 'red')} M頭、假突破、上飄旗形、頭肩頂、假突破(頭肩頂)、收斂三角形(頭部)

${colorize('環境變數:', 'cyan')}
  API_URL               API 服務位址 (預設: http://localhost:3000)

${colorize('範例:', 'cyan')}
  # 掃描台積電
  node scan-patterns.js scan 2330

  # 批量掃描
  node scan-patterns.js scan 2330,2317,2454

  # 搜尋W底型態
  node scan-patterns.js find W底

  # 生成報告
  node scan-patterns.js report 2330

  # 查看多頭股票
  node scan-patterns.js bullish
`);
}

// 主程式
async function main() {
  if (!COMMAND || COMMAND === 'help') {
    showHelp();
    return;
  }

  try {
    // 檢查服務狀態
    await axios.get(`${BASE_URL}/api/patterns/health`);
  } catch (error) {
    printError(`無法連接到 API 服務 (${BASE_URL})`);
    printInfo('請確認服務已啟動: npm run start');
    process.exit(1);
  }

  switch (COMMAND) {
    case 'scan':
      if (!ARGS[0]) {
        printError('請指定股票代碼');
        printInfo('範例: node scan-patterns.js scan 2330');
        process.exit(1);
      }
      await scanStocks(ARGS[0]);
      break;

    case 'find':
      if (!ARGS[0]) {
        printError('請指定型態名稱');
        printInfo('範例: node scan-patterns.js find W底');
        process.exit(1);
      }
      await findPattern(ARGS[0], ARGS[1] ? parseInt(ARGS[1]) : 10);
      break;

    case 'report':
      if (!ARGS[0]) {
        printError('請指定股票代碼');
        printInfo('範例: node scan-patterns.js report 2330');
        process.exit(1);
      }
      await generateReport(ARGS[0]);
      break;

    case 'bullish':
      await listBullish(ARGS[0] ? parseInt(ARGS[0]) : 20);
      break;

    case 'bearish':
      await listBearish(ARGS[0] ? parseInt(ARGS[0]) : 20);
      break;

    default:
      printError(`未知的命令: ${COMMAND}`);
      printInfo('使用 "node scan-patterns.js help" 查看說明');
      process.exit(1);
  }
}

// 執行
main().catch(error => {
  printError(`執行錯誤: ${error.message}`);
  process.exit(1);
});
