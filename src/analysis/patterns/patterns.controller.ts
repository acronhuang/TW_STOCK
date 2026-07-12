import { Controller, Get, Query, Param, Logger } from '@nestjs/common';
import { PatternScannerService } from './pattern-scanner.service';
import { TechnicalPatternsService } from './technical-patterns.service';

/**
 * 技術型態分析 API 控制器
 */
@Controller('api/patterns')
export class PatternsController {
  private readonly logger = new Logger(PatternsController.name);

  constructor(
    private readonly scannerService: PatternScannerService,
    private readonly patternsService: TechnicalPatternsService,
  ) {}

  /**
   * GET /api/patterns/scan/:symbol
   * 掃描單一股票的所有技術型態
   */
  @Get('scan/:symbol')
  async scanStock(
    @Param('symbol') symbol: string,
    @Query('days') days?: string,
  ) {
    const daysNum = days ? parseInt(days) : 120;
    this.logger.log(`API: 掃描股票 ${symbol} 的技術型態 (${daysNum}天)`);
    
    return await this.scannerService.scanStock(symbol, daysNum);
  }

  /**
   * GET /api/patterns/scan-multiple
   * 批量掃描多支股票
   * 參數: symbols=2330,2317,2454 (逗號分隔)
   */
  @Get('scan-multiple')
  async scanMultiple(
    @Query('symbols') symbols: string,
    @Query('days') days?: string,
  ) {
    const symbolArray = symbols.split(',').map(s => s.trim()).filter(s => s);
    const daysNum = days ? parseInt(days) : 120;
    
    this.logger.log(`API: 批量掃描 ${symbolArray.length} 支股票`);
    
    return await this.scannerService.scanMultipleStocks(symbolArray, daysNum);
  }

  /**
   * GET /api/patterns/scan-all
   * 掃描所有股票並返回有信號的股票
   */
  @Get('scan-all')
  async scanAll(@Query('days') days?: string) {
    const daysNum = days ? parseInt(days) : 120;
    this.logger.log(`API: 掃描所有股票的技術型態`);
    
    return await this.scannerService.scanAllStocksWithSignals(daysNum);
  }

  /**
   * GET /api/patterns/find-by-pattern
   * 依型態類型搜尋股票
   * 參數: pattern=W底&limit=20
   */
  @Get('find-by-pattern')
  async findByPattern(
    @Query('pattern') pattern: string,
    @Query('days') days?: string,
    @Query('limit') limit?: string,
  ) {
    const daysNum = days ? parseInt(days) : 120;
    const limitNum = limit ? parseInt(limit) : 20;
    
    this.logger.log(`API: 搜尋 ${pattern} 型態的股票`);
    
    return await this.scannerService.findStocksByPattern(pattern, daysNum, limitNum);
  }

  /**
   * GET /api/patterns/report/:symbol
   * 生成股票的技術型態報告（純文字格式）
   */
  @Get('report/:symbol')
  async getReport(@Param('symbol') symbol: string) {
    this.logger.log(`API: 生成股票 ${symbol} 的型態報告`);
    
    const report = await this.scannerService.generatePatternReport(symbol);
    
    return {
      symbol,
      report,
      timestamp: new Date().toISOString(),
    };
  }

  /**
   * GET /api/patterns/types
   * 獲取所有支援的型態類型列表
   */
  @Get('types')
  getPatternTypes() {
    return {
      patterns: [
        {
          id: 1,
          name: 'W底 (雙底)',
          type: 'bullish',
          signal: '多頭買進信號',
          description: '當突破頸線位置後，確立W底型態。計算公式：底部至頸線距離 = 突破後的等幅距離。',
          example: '迎駕貢酒：頸線15.80，雙底14.64，最大獲利約14.8%',
        },
        {
          id: 2,
          name: '破底翻',
          type: 'bullish',
          signal: '多頭買進信號',
          description: '築底過程中跌破支撐後翻升站回頸線。含「甩轎」動作，表示主力在場。',
          example: '中國銀行：買點3.43，目標價4.37，最大獲利約20.4%',
        },
        {
          id: 3,
          name: '破底翻 (W底)',
          type: 'bullish',
          signal: '多頭買進信號',
          description: 'W底第二隻腳破底後拉回，更安全的底部布局。',
          example: '視覺中國：買點16.12，最大獲利約29.5%',
        },
        {
          id: 4,
          name: '下飄旗形',
          type: 'bullish',
          signal: '多頭中繼信號',
          description: '上漲途中的向下整理，突破上緣頸線為再度攻擊信號。',
          example: '五糧液：突破76.76後看漲幅滿足90.14，最大獲利約34%',
        },
        {
          id: 5,
          name: '上飄旗形',
          type: 'bearish',
          signal: '空頭中繼信號',
          description: '下跌途中的向上整理，跌破下緣頸線為空頭再度攻擊。',
          example: '東港股份：跌破19.73後看跌幅滿足14.72，避免損失約25.4%',
        },
        {
          id: 6,
          name: 'M頭 (雙頂)',
          type: 'bearish',
          signal: '空單進場信號',
          description: 'W底的反向。跌破頸線後不能再站回。',
          example: '新華保險：跌破63.2後看第一波段53.1，避免損失約32%',
        },
        {
          id: 7,
          name: '假突破',
          type: 'bearish',
          signal: '空單進場信號',
          description: '股價突破整理區後又跌回頸線之下，屬主力高檔出貨騙線。',
          example: '晶盛機電：跌破16.24確認假突破，避免損失約23.1%',
        },
        {
          id: 8,
          name: '頭肩頂',
          type: 'bearish',
          signal: '空單進場信號',
          description: '行情由強轉弱。頭部與頸線距離等於跌破後的等幅跌幅。',
          example: '石大勝華：跌破32.33後看跌幅滿足17.37，避免損失約46.2%',
        },
        {
          id: 9,
          name: '假突破 (頭肩頂)',
          type: 'bearish',
          signal: '空單進場信號',
          description: '利用假突破結構，更早判斷高檔轉弱。',
          example: '紫光國微：跌破50.15確認，避免損失約29%',
        },
        {
          id: 10,
          name: '頭肩底',
          type: 'bullish',
          signal: '多頭買進信號',
          description: '底部盤整行情由弱轉強。低點到頸線距離 = 突破後的距離。',
          example: '亞翔集成：突破22.48看滿足點27.07與31.66，最大獲利約40.8%',
        },
        {
          id: 11,
          name: '收斂三角形 (頭部)',
          type: 'bearish',
          signal: '空單進場信號',
          description: '需在三角形1/2至3/4處跌破才有效。',
          example: '二三四五：跌破16.5後看跌幅滿足6.11，避免損失約62.9%',
        },
        {
          id: 12,
          name: '收斂三角形 (底部)',
          type: 'bullish',
          signal: '多頭買進信號',
          description: '三角形底部為頭部的反向結構。',
          example: '工商銀行：突破3.15後看滿足點5.35與7.55，最大獲利約139%',
        },
      ],
      summary: {
        total: 12,
        bullish: 6,
        bearish: 6,
      },
    };
  }

  /**
   * GET /api/patterns/bullish
   * 獲取所有多頭型態股票
   */
  @Get('bullish')
  async getBullishStocks(@Query('days') days?: string) {
    const daysNum = days ? parseInt(days) : 120;
    const result = await this.scannerService.scanAllStocksWithSignals(daysNum);
    
    return {
      scanDate: result.scanDate,
      totalScanned: result.totalScanned,
      bullishCount: result.summary.bullishStocks,
      stocks: result.bullishStocks,
    };
  }

  /**
   * GET /api/patterns/bearish
   * 獲取所有空頭型態股票
   */
  @Get('bearish')
  async getBearishStocks(@Query('days') days?: string) {
    const daysNum = days ? parseInt(days) : 120;
    const result = await this.scannerService.scanAllStocksWithSignals(daysNum);
    
    return {
      scanDate: result.scanDate,
      totalScanned: result.totalScanned,
      bearishCount: result.summary.bearishStocks,
      stocks: result.bearishStocks,
    };
  }

  /**
   * GET /api/patterns/health
   * 健康檢查
   */
  @Get('health')
  healthCheck() {
    return {
      status: 'ok',
      service: 'Technical Patterns Analysis',
      timestamp: new Date().toISOString(),
      patterns: 12,
    };
  }
}
