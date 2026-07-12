import { Controller, Post, Get, Body, Param, Query, Logger } from '@nestjs/common';
import { ApiTags, ApiOperation, ApiParam, ApiQuery, ApiBody } from '@nestjs/swagger';
import { ScraperService } from './scraper.service';

/**
 * 財報爬蟲 API 控制器
 * 
 * 注意: 這些 API 會對外部網站發送請求，請謹慎使用
 * 建議使用 SchedulerModule 進行自動化排程
 */
@ApiTags('財報爬蟲 (Scraper)')
@Controller('scraper')
export class ScraperController {
  private readonly logger = new Logger(ScraperController.name);

  constructor(
    private readonly scraperService: ScraperService,
  ) {}

  /**
   * 抓取單一公司季報
   */
  @Post('financial/:symbol')
  @ApiOperation({ 
    summary: '抓取單一公司財報',
    description: '從 MOPS 公開資訊觀測站抓取指定公司的季報或年報資料' 
  })
  @ApiParam({ name: 'symbol', description: '股票代碼', example: '2330' })
  @ApiQuery({ name: 'year', description: '民國年', example: 113 })
  @ApiQuery({ name: 'season', description: '季度 (1-4)', example: 4 })
  async scrapeQuarterlyReport(
    @Param('symbol') symbol: string,
    @Query('year') year: string,
    @Query('season') season: string,
  ) {
    this.logger.log(`API: 抓取 ${symbol} ${year}Q${season} 財報`);

    const result = await this.scraperService.scrapeAndSaveQuarterlyReport(
      symbol,
      parseInt(year),
      parseInt(season),
    );

    return {
      success: true,
      message: `成功抓取 ${symbol} ${year}Q${season} 財報`,
      data: result,
    };
  }

  /**
   * 批次抓取最新財報
   */
  @Post('financial/batch/latest')
  @ApiOperation({ 
    summary: '批次抓取最新財報',
    description: '批次抓取多家公司的最新季報 (自動判斷最新期間)' 
  })
  @ApiBody({
    schema: {
      type: 'object',
      properties: {
        symbols: {
          type: 'array',
          items: { type: 'string' },
          example: ['2330', '2317', '2454', '2881', '2882'],
        },
      },
    },
  })
  async scrapeBatchLatest(@Body('symbols') symbols: string[]) {
    this.logger.log(`API: 批次抓取 ${symbols.length} 家公司最新財報`);

    const result = await this.scraperService.scrapeBatchLatest(symbols);

    return {
      success: true,
      message: `批次抓取完成: 成功 ${result.success.length}/${result.total}`,
      data: result,
    };
  }

  /**
   * 抓取歷史財報
   */
  @Post('financial/:symbol/history')
  @ApiOperation({ 
    summary: '抓取歷史財報',
    description: '抓取指定公司的歷史財報 (多個季度)' 
  })
  @ApiParam({ name: 'symbol', description: '股票代碼', example: '2330' })
  @ApiBody({
    schema: {
      type: 'object',
      properties: {
        startYear: { type: 'number', example: 110 },
        startSeason: { type: 'number', example: 1 },
        endYear: { type: 'number', example: 113 },
        endSeason: { type: 'number', example: 4 },
      },
    },
  })
  async scrapeHistory(
    @Param('symbol') symbol: string,
    @Body('startYear') startYear: number,
    @Body('startSeason') startSeason: number,
    @Body('endYear') endYear: number,
    @Body('endSeason') endSeason: number,
  ) {
    this.logger.log(
      `API: 抓取 ${symbol} 歷史財報 ${startYear}Q${startSeason} ~ ${endYear}Q${endSeason}`,
    );

    const result = await this.scraperService.scrapeHistory(
      symbol,
      startYear,
      startSeason,
      endYear,
      endSeason,
    );

    return {
      success: true,
      message: `歷史財報抓取完成: 成功 ${result.success.length}/${result.total}`,
      data: result,
    };
  }

  /**
   * 取得爬蟲狀態
   */
  @Get('status')
  @ApiOperation({ 
    summary: '取得爬蟲狀態',
    description: '查詢爬蟲系統狀態、最新期間、資料庫統計' 
  })
  async getStatus() {
    const status = await this.scraperService.getStatus();

    return {
      success: true,
      data: status,
    };
  }

  /**
   * 抓取今日所有股票交易資料 (TWSE)
   */
  @Post('stocks/daily')
  @ApiOperation({ 
    summary: '抓取今日股票交易資料',
    description: '從證交所 Open Data API 抓取今日所有股票交易資料並儲存到資料庫' 
  })
  async scrapeDailyStocks() {
    this.logger.log('API: 抓取今日股票交易資料');

    const result = await this.scraperService.scrapeAndSaveDailyStocks();

    return {
      success: true,
      message: `成功儲存 ${result.success}/${result.total} 筆股票資料`,
      data: result,
    };
  }

  /**
   * 抓取三大法人買賣超 (TWSE)
   */
  @Post('institutional/daily')
  @ApiOperation({ 
    summary: '抓取三大法人買賣超',
    description: '從證交所 Open Data API 抓取三大法人買賣超資料並更新到資料庫' 
  })
  async scrapeInstitutionalTrading() {
    this.logger.log('API: 抓取三大法人買賣超');

    const result = await this.scraperService.scrapeAndSaveInstitutionalTrading();

    return {
      success: true,
      message: `成功更新 ${result.success}/${result.total} 筆三大法人資料`,
      data: result,
    };
  }

  /**
   * 批次補齊財報 - 多家公司 (FinMind)
   * 注意: 此路由必須放在 /:symbol 路由之前，避免 batch 被當作 symbol 參數
   */
  @Post('finmind/backfill/batch')
  @ApiOperation({ 
    summary: '批次財報補齊 (FinMind)',
    description: '從 FinMind 批次補齊多家公司財報資料 (三大報表)。資料來源: FinMind API，包含損益表、資產負債表、現金流量表完整資訊。' 
  })
  @ApiBody({
    description: '股票代碼列表與開始日期',
    schema: {
      type: 'object',
      properties: {
        symbols: {
          type: 'array',
          items: { type: 'string' },
          example: ['2330', '2317', '2454'],
          description: '股票代碼陣列，建議每批不超過 50 家公司',
        },
        startDate: {
          type: 'string',
          example: '2024-01-01',
          description: '開始日期 (格式: YYYY-MM-DD)',
        },
      },
    },
  })
  async backfillBatch(
    @Body() body: { symbols: string[]; startDate?: string },
  ) {
    const { symbols, startDate } = body;
    const start = startDate || '2024-01-01';

    this.logger.log(`API: 批次財報補齊 ${symbols.length} 家公司 (FinMind, 起始: ${start})`);

    const result = await this.scraperService.batchBackfillFinancialReports(
      symbols,
      start,
    );

    return {
      success: result.failed === 0,
      message: `處理完成: 成功 ${result.success}/${result.total}，失敗 ${result.failed}`,
      ...result,
    };
  }

  /**
   * 批次補齊財報 - 單一公司 (FinMind)
   */
  @Post('finmind/backfill/:symbol')
  @ApiOperation({ 
    summary: '單一公司財報補齊 (FinMind)',
    description: '從 FinMind 補齊指定公司財報資料 (三大報表: 損益表、資產負債表、現金流量表)' 
  })
  @ApiParam({ name: 'symbol', description: '股票代碼', example: '2330' })
  @ApiQuery({ name: 'startDate', description: '開始日期', example: '2024-01-01', required: false })
  async backfillSingleCompany(
    @Param('symbol') symbol: string,
    @Query('startDate') startDate?: string,
  ) {
    this.logger.log(`API: 財報補齊 ${symbol} (起始: ${startDate || '2024-01-01'})`);

    try {
      const reports = await this.scraperService.scrapeFromFinMind(
        symbol,
        startDate || '2024-01-01',
      );

      return {
        success: true,
        message: `✅ ${symbol} 財報補齊完成，共 ${reports.length} 筆`,
        symbol,
        count: reports.length,
      };
    } catch (error) {
      this.logger.error(`❌ ${symbol} 失敗: ${error.message}`);
      return {
        success: false,
        message: `❌ ${symbol} 失敗: ${error.message}`,
        symbol,
      };
    }
  }

  // ========== Yahoo Finance 端點 ==========

  /**
   * Yahoo Finance 批次補齊歷史資料
   */
  @Post('yahoo/backfill/batch')
  @ApiOperation({
    summary: 'Yahoo Finance 批次補齊歷史財報',
    description: '使用 Yahoo Finance API 批次補齊多家公司的歷史財報資料',
  })
  @ApiBody({
    schema: {
      type: 'object',
      properties: {
        symbols: {
          type: 'array',
          items: { type: 'string' },
          example: ['2330', '2317', '2454'],
        },
        startYear: {
          type: 'number',
          example: 2023,
          description: '開始年度 (西元年)',
        },
        endYear: {
          type: 'number',
          example: 2024,
          description: '結束年度 (西元年)',
        },
      },
    },
  })
  async yahooBackfillBatch(
    @Body('symbols') symbols: string[],
    @Body('startYear') startYear: number,
    @Body('endYear') endYear: number,
  ) {
    this.logger.log(
      `API: Yahoo Finance 批次補齊 ${symbols.length} 家公司, ${startYear}-${endYear}`,
    );

    const result = await this.scraperService.batchBackfillFromYahoo(
      symbols,
      startYear,
      endYear,
    );

    return {
      success: result.success,
      message: `處理完成: 成功 ${result.success}/${result.total}，失敗 ${result.failed}`,
      failed: result.failed,
      total: result.total,
      errors: result.errors,
    };
  }

  /**
   * Yahoo Finance 單一公司補齊
   */
  @Post('yahoo/backfill/:symbol')
  @ApiOperation({
    summary: 'Yahoo Finance 單一公司補齊',
    description: '使用 Yahoo Finance API 補齊單一公司的財報資料',
  })
  @ApiParam({ name: 'symbol', description: '股票代碼', example: '2330' })
  @ApiQuery({ name: 'year', description: '年度 (西元年)', example: 2024 })
  @ApiQuery({ name: 'quarter', description: '季度 (1-4)', example: 3 })
  async yahooBackfillSingle(
    @Param('symbol') symbol: string,
    @Query('year') year: number,
    @Query('quarter') quarter: number,
  ) {
    this.logger.log(`API: Yahoo Finance 補齊 ${symbol} ${year}Q${quarter}`);

    try {
      const result = await this.scraperService.scrapeFromYahoo(
        symbol,
        parseInt(year.toString()),
        parseInt(quarter.toString()),
      );

      return {
        success: true,
        message: `✅ ${symbol} ${year}Q${quarter} Yahoo 補齊完成`,
        data: result,
      };
    } catch (error) {
      return {
        success: false,
        message: `❌ Yahoo 補齊失敗: ${error.message}`,
        symbol,
      };
    }
  }

  // ========== Goodinfo 端點 ==========

  /**
   * Goodinfo 批次補齊歷史資料
   */
  @Post('goodinfo/backfill/batch')
  @ApiOperation({
    summary: 'Goodinfo 批次補齊歷史財報',
    description: '使用 Goodinfo 網頁爬蟲批次補齊多家公司的歷史財報資料',
  })
  @ApiBody({
    schema: {
      type: 'object',
      properties: {
        symbols: {
          type: 'array',
          items: { type: 'string' },
          example: ['2330', '2317', '2454'],
        },
        startYear: {
          type: 'number',
          example: 112,
          description: '開始年度 (民國年)',
        },
        endYear: {
          type: 'number',
          example: 113,
          description: '結束年度 (民國年)',
        },
      },
    },
  })
  async goodinfoBackfillBatch(
    @Body('symbols') symbols: string[],
    @Body('startYear') startYear: number,
    @Body('endYear') endYear: number,
  ) {
    this.logger.log(
      `API: Goodinfo 批次補齊 ${symbols.length} 家公司, ${startYear}-${endYear} (民國年)`,
    );

    const result = await this.scraperService.batchBackfillFromGoodinfo(
      symbols,
      startYear,
      endYear,
    );

    return {
      success: result.success,
      message: `處理完成: 成功 ${result.success}/${result.total}，失敗 ${result.failed}`,
      failed: result.failed,
      total: result.total,
      errors: result.errors,
    };
  }

  /**
   * Goodinfo 單一公司補齊
   */
  @Post('goodinfo/backfill/:symbol')
  @ApiOperation({
    summary: 'Goodinfo 單一公司補齊',
    description: '使用 Goodinfo 網頁爬蟲補齊單一公司的財報資料',
  })
  @ApiParam({ name: 'symbol', description: '股票代碼', example: '2330' })
  @ApiQuery({ name: 'year', description: '年度 (民國年)', example: 113 })
  @ApiQuery({ name: 'quarter', description: '季度 (1-4)', example: 3 })
  async goodinfoBackfillSingle(
    @Param('symbol') symbol: string,
    @Query('year') year: number,
    @Query('quarter') quarter: number,
  ) {
    this.logger.log(`API: Goodinfo 補齊 ${symbol} ${year}Q${quarter} (民國年)`);

    try {
      const result = await this.scraperService.scrapeFromGoodinfo(
        symbol,
        parseInt(year.toString()),
        parseInt(quarter.toString()),
      );

      return {
        success: true,
        message: `✅ ${symbol} ${year}Q${quarter} Goodinfo 補齊完成`,
        data: result,
      };
    } catch (error) {
      return {
        success: false,
        message: `❌ Goodinfo 補齊失敗: ${error.message}`,
        symbol,
      };
    }
  }

}


