import { Injectable, Logger } from '@nestjs/common';
import { InjectConnection } from '@nestjs/mongoose';
import { Connection } from 'mongoose';
import { TechnicalPatternsService } from './technical-patterns.service';

/**
 * 型態掃描器服務 - 批量掃描股票型態
 */
@Injectable()
export class PatternScannerService {
  private readonly logger = new Logger(PatternScannerService.name);

  constructor(
    @InjectConnection() private readonly connection: Connection,
    private readonly patternsService: TechnicalPatternsService,
  ) {}

  /**
   * 掃描單一股票的所有型態
   */
  async scanStock(symbol: string, days: number = 120): Promise<any> {
    try {
      this.logger.log(`掃描股票 ${symbol} 的技術型態...`);

      // 從 MongoDB 獲取歷史價格數據
      const priceData = await this.getPriceData(symbol, days);
      
      if (!priceData || priceData.length < 20) {
        return {
          symbol,
          error: '數據不足，無法進行型態分析',
          dataPoints: priceData?.length || 0,
        };
      }

      const prices = priceData.map(d => d.close);
      const dates = priceData.map(d => d.date);

      // 掃描所有型態
      const scanResult = this.patternsService.scanAllPatterns(prices, dates);

      // 整理檢測到的型態
      const detectedPatterns = this.extractDetectedPatterns(scanResult.patterns);

      return {
        symbol,
        currentPrice: prices[prices.length - 1],
        scanDate: new Date().toISOString(),
        dataPoints: prices.length,
        dateRange: {
          start: dates[0],
          end: dates[dates.length - 1],
        },
        detectedPatterns,
        allPatterns: scanResult.patterns,
        summary: {
          totalDetected: detectedPatterns.length,
          bullishSignals: detectedPatterns.filter(p => p.type === 'bullish').length,
          bearishSignals: detectedPatterns.filter(p => p.type === 'bearish').length,
        },
      };
    } catch (error) {
      this.logger.error(`掃描股票 ${symbol} 時發生錯誤: ${error.message}`);
      return {
        symbol,
        error: error.message,
      };
    }
  }

  /**
   * 批量掃描多支股票
   */
  async scanMultipleStocks(symbols: string[], days: number = 120): Promise<any[]> {
    this.logger.log(`開始批量掃描 ${symbols.length} 支股票...`);
    
    const results = [];
    
    for (const symbol of symbols) {
      const result = await this.scanStock(symbol, days);
      results.push(result);
      
      // 避免過於頻繁的數據庫查詢
      await this.sleep(100);
    }
    
    return results;
  }

  /**
   * 掃描所有股票並返回有信號的股票
   */
  async scanAllStocksWithSignals(days: number = 120): Promise<any> {
    try {
      this.logger.log('開始掃描所有股票的技術型態...');

      // 獲取所有股票代碼
      const symbols = await this.getAllStockSymbols();
      
      this.logger.log(`共找到 ${symbols.length} 支股票`);

      const results = [];
      const withSignals = [];
      let processed = 0;

      for (const symbol of symbols) {
        try {
          const result = await this.scanStock(symbol, days);
          results.push(result);

          if (result.detectedPatterns && result.detectedPatterns.length > 0) {
            withSignals.push(result);
            this.logger.log(`${symbol}: 檢測到 ${result.detectedPatterns.length} 個型態`);
          }

          processed++;
          if (processed % 50 === 0) {
            this.logger.log(`進度: ${processed}/${symbols.length}`);
          }

          // 避免過於頻繁的數據庫查詢
          await this.sleep(50);
        } catch (error) {
          this.logger.error(`處理 ${symbol} 時發生錯誤: ${error.message}`);
        }
      }

      // 按信號類型分類
      const bullishStocks = withSignals.filter(s => 
        s.summary.bullishSignals > s.summary.bearishSignals
      );
      
      const bearishStocks = withSignals.filter(s => 
        s.summary.bearishSignals > s.summary.bullishSignals
      );

      return {
        scanDate: new Date().toISOString(),
        totalScanned: symbols.length,
        withSignals: withSignals.length,
        summary: {
          bullishStocks: bullishStocks.length,
          bearishStocks: bearishStocks.length,
          totalSignals: withSignals.reduce((sum, s) => sum + s.detectedPatterns.length, 0),
        },
        bullishStocks: bullishStocks.sort((a, b) => 
          b.summary.bullishSignals - a.summary.bullishSignals
        ).slice(0, 50), // 前50名多頭信號
        bearishStocks: bearishStocks.sort((a, b) => 
          b.summary.bearishSignals - a.summary.bearishSignals
        ).slice(0, 50), // 前50名空頭信號
      };
    } catch (error) {
      this.logger.error(`批量掃描時發生錯誤: ${error.message}`);
      throw error;
    }
  }

  /**
   * 依型態類型篩選股票
   */
  async findStocksByPattern(
    patternType: string, 
    days: number = 120,
    limit: number = 20
  ): Promise<any[]> {
    this.logger.log(`搜尋符合 ${patternType} 型態的股票...`);

    const symbols = await this.getAllStockSymbols();
    const matches = [];

    for (const symbol of symbols) {
      const result = await this.scanStock(symbol, days);
      
      if (result.detectedPatterns) {
        const hasPattern = result.detectedPatterns.some(p => 
          p.pattern.includes(patternType) || p.pattern === patternType
        );
        
        if (hasPattern) {
          matches.push(result);
          
          if (matches.length >= limit) {
            break;
          }
        }
      }

      await this.sleep(50);
    }

    return matches;
  }

  /**
   * 從 MongoDB 獲取價格數據
   */
  private async getPriceData(symbol: string, days: number): Promise<any[]> {
    try {
      const collection = this.connection.collection('stock_prices');
      
      const endDate = new Date();
      const startDate = new Date();
      startDate.setDate(startDate.getDate() - days);

      const data = await collection
        .find({
          symbol,
          date: {
            $gte: startDate.toISOString().split('T')[0],
            $lte: endDate.toISOString().split('T')[0],
          },
        })
        .sort({ date: 1 })
        .toArray();

      return data.map(d => ({
        date: d.date,
        open: d.open,
        high: d.high,
        low: d.low,
        close: d.close,
        volume: d.volume,
      }));
    } catch (error) {
      this.logger.error(`獲取 ${symbol} 價格數據時發生錯誤: ${error.message}`);
      return [];
    }
  }

  /**
   * 獲取所有股票代碼
   */
  private async getAllStockSymbols(): Promise<string[]> {
    try {
      const collection = this.connection.collection('stock_prices');
      const symbols = await collection.distinct('symbol');
      return symbols.filter(s => s && s.length === 4); // 台股代碼為4碼
    } catch (error) {
      this.logger.error(`獲取股票代碼列表時發生錯誤: ${error.message}`);
      return [];
    }
  }

  /**
   * 從掃描結果中提取已檢測到的型態
   */
  private extractDetectedPatterns(patterns: any): any[] {
    const detected = [];

    for (const [key, value] of Object.entries(patterns)) {
      if (value && typeof value === 'object' && value['detected'] === true) {
        detected.push({
          key,
          ...value,
        });
      }
    }

    return detected;
  }

  /**
   * 睡眠函數
   */
  private sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  /**
   * 生成型態報告
   */
  async generatePatternReport(symbol: string): Promise<string> {
    const result = await this.scanStock(symbol);
    
    if (result.error) {
      return `股票 ${symbol} 掃描失敗: ${result.error}`;
    }

    let report = `\n========================================\n`;
    report += `技術型態分析報告\n`;
    report += `========================================\n`;
    report += `股票代碼: ${symbol}\n`;
    report += `當前價格: ${result.currentPrice.toFixed(2)}\n`;
    report += `分析日期: ${new Date().toLocaleDateString('zh-TW')}\n`;
    report += `數據範圍: ${result.dateRange.start} ~ ${result.dateRange.end}\n`;
    report += `數據點數: ${result.dataPoints}\n`;
    report += `========================================\n\n`;

    if (result.detectedPatterns.length === 0) {
      report += `未檢測到明確的技術型態信號。\n`;
    } else {
      report += `檢測到 ${result.detectedPatterns.length} 個技術型態:\n\n`;

      for (const pattern of result.detectedPatterns) {
        report += `【${pattern.pattern}】\n`;
        report += `  類型: ${pattern.type === 'bullish' ? '多頭' : '空頭'}\n`;
        report += `  信號: ${pattern.signal}\n`;
        report += `  說明: ${pattern.description}\n`;
        
        if (pattern.target || pattern.target1) {
          report += `  目標價: ${pattern.target?.toFixed(2) || pattern.target1?.toFixed(2)}\n`;
        }
        
        if (pattern.buyPoint) {
          report += `  買點: ${pattern.buyPoint.toFixed(2)}\n`;
        }
        
        if (pattern.sellPoint) {
          report += `  賣點: ${pattern.sellPoint.toFixed(2)}\n`;
        }
        
        if (pattern.stopLoss) {
          report += `  停損: ${pattern.stopLoss.toFixed(2)}\n`;
        }
        
        report += `\n`;
      }
    }

    report += `========================================\n`;
    report += `多頭信號: ${result.summary.bullishSignals} 個\n`;
    report += `空頭信號: ${result.summary.bearishSignals} 個\n`;
    report += `========================================\n`;

    return report;
  }
}
