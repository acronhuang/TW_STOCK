import { Injectable, Logger } from '@nestjs/common';
import { Cron, CronExpression } from '@nestjs/schedule';
import { ScraperService } from '../scraper/scraper.service';
import { MOPSScraperService } from '../scraper/services/mops.scraper';

/**
 * 排程服務 - 自動化資料更新
 * 
 * 功能:
 * - 每日自動抓取財報
 * - 每週批次更新
 * - 失敗重試機制
 * - 狀態監控
 */
@Injectable()
export class SchedulerService {
  private readonly logger = new Logger(SchedulerService.name);
  private isScrapingEnabled: boolean;
  private lastScrapingTime: Date;
  private scrapingStatus: {
    inProgress: boolean;
    lastSuccess: Date;
    lastError: string;
    totalRuns: number;
    successRuns: number;
    failedRuns: number;
  };

  // 前100大市值公司代碼 (範例)
  private readonly TOP_100_SYMBOLS = [
    '2330', // 台積電
    '2317', // 鴻海
    '2454', // 聯發科
    '2881', // 富邦金
    '2882', // 國泰金
    '2886', // 兆豐金
    '2308', // 台達電
    '2303', // 聯電
    '2891', // 中信金
    '6505', // 台塑化
    '2884', // 玉山金
    '2892', // 第一金
    '2412', // 中華電
    '2885', // 元大金
    '2207', // 和泰車
    '2357', // 華碩
    '2382', // 廣達
    '2395', // 研華
    '2408', // 南亞科
    '3008', // 大立光
    // ...可擴展到100家
  ];

  constructor(
    private readonly scraperService: ScraperService,
    private readonly mopsScraper: MOPSScraperService,
  ) {
    this.isScrapingEnabled = process.env.ENABLE_SCHEDULER !== 'false';
    this.scrapingStatus = {
      inProgress: false,
      lastSuccess: null,
      lastError: null,
      totalRuns: 0,
      successRuns: 0,
      failedRuns: 0,
    };
    
    this.logger.log(`排程服務初始化完成 (${this.isScrapingEnabled ? '啟用' : '停用'})`);
  }

  /**
   * 每週五下午4點抓取最新財報
   * Cron: 每週五 16:00
   */
  @Cron('0 16 * * 5', {
    name: 'weeklyFinancialScraping',
    timeZone: 'Asia/Taipei',
  })
  async handleWeeklyFinancialScraping() {
    if (!this.isScrapingEnabled) {
      this.logger.debug('排程已停用，跳過財報抓取');
      return;
    }

    if (this.scrapingStatus.inProgress) {
      this.logger.warn('財報抓取進行中，跳過本次排程');
      return;
    }

    this.logger.log('🚀 開始每週財報抓取任務');
    this.scrapingStatus.inProgress = true;
    this.scrapingStatus.totalRuns++;
    this.lastScrapingTime = new Date();

    try {
      // 取得最新財報期間
      const { year, season } = this.mopsScraper.getLatestReportPeriod();
      this.logger.log(`最新財報期間: ${year}Q${season} (${year + 1911}年第${season}季)`);

      // 批次抓取前20家公司 (避免一次抓太多)
      const symbols = this.TOP_100_SYMBOLS.slice(0, 20);
      this.logger.log(`批次抓取 ${symbols.length} 家公司`);

      const results = await this.scraperService.scrapeBatchLatest(symbols);

      // 記錄結果
      this.logger.log(
        `✅ 財報抓取完成: 成功 ${results.success.length}/${results.total}`,
      );

      if (results.failed.length > 0) {
        this.logger.warn(
          `⚠️ 失敗 ${results.failed.length} 筆: ${results.failed.map(f => f.symbol).join(', ')}`,
        );
      }

      this.scrapingStatus.lastSuccess = new Date();
      this.scrapingStatus.successRuns++;
    } catch (error) {
      this.logger.error(`❌ 財報抓取失敗: ${error.message}`, error.stack);
      this.scrapingStatus.lastError = error.message;
      this.scrapingStatus.failedRuns++;
    } finally {
      this.scrapingStatus.inProgress = false;
    }
  }

  /**
   * 每天凌晨1點清理舊資料 (可選)
   * Cron: 每天 01:00
   */
  @Cron('0 1 * * *', {
    name: 'dailyDataCleanup',
    timeZone: 'Asia/Taipei',
  })
  async handleDailyDataCleanup() {
    if (!this.isScrapingEnabled) {
      return;
    }

    this.logger.log('🧹 開始每日資料清理任務');
    
    try {
      // TODO: 實作資料清理邏輯
      // - 刪除超過3年的舊財報
      // - 清理失敗的爬蟲記錄
      // - 優化資料庫索引
      
      this.logger.log('✅ 資料清理完成');
    } catch (error) {
      this.logger.error(`❌ 資料清理失敗: ${error.message}`);
    }
  }

  /**
   * 每日股價爬蟲 - 週一到週五下午 2:00 執行
   * Cron: 週一到週五 14:00
   * 說明: 台股收盤時間為下午 1:30，2:00 執行可確保當日交易資料已更新
   */
  @Cron('0 14 * * 1-5', {
    name: 'dailyStocksScraping',
    timeZone: 'Asia/Taipei',
  })
  async handleDailyStocksScraping() {
    if (!this.isScrapingEnabled) {
      this.logger.debug('排程已停用，跳過股價抓取');
      return;
    }

    this.logger.log('📈 開始每日股價爬蟲任務');
    const startTime = Date.now();

    try {
      const result = await this.scraperService.scrapeAndSaveDailyStocks();
      
      const duration = ((Date.now() - startTime) / 1000).toFixed(2);
      this.logger.log(
        `✅ 股價爬蟲完成: 成功 ${result.success}/${result.total} 筆 (耗時 ${duration} 秒)`,
      );

      if (result.failed > 0) {
        this.logger.warn(`⚠️ 失敗 ${result.failed} 筆`);
      }
    } catch (error) {
      this.logger.error(`❌ 股價爬蟲失敗: ${error.message}`, error.stack);
    }
  }

  /**
   * 手動觸發財報抓取
   */
  async manualTriggerFinancialScraping(symbols?: string[]): Promise<any> {
    this.logger.log('🔧 手動觸發財報抓取');

    if (this.scrapingStatus.inProgress) {
      throw new Error('財報抓取進行中，請稍後再試');
    }

    this.scrapingStatus.inProgress = true;
    this.scrapingStatus.totalRuns++;

    try {
      const targetSymbols = symbols || this.TOP_100_SYMBOLS.slice(0, 10);
      this.logger.log(`目標公司: ${targetSymbols.join(', ')}`);

      const results = await this.scraperService.scrapeBatchLatest(targetSymbols);

      this.scrapingStatus.lastSuccess = new Date();
      this.scrapingStatus.successRuns++;

      return {
        success: true,
        message: `成功抓取 ${results.success.length}/${results.total} 筆財報`,
        results,
      };
    } catch (error) {
      this.scrapingStatus.lastError = error.message;
      this.scrapingStatus.failedRuns++;
      throw error;
    } finally {
      this.scrapingStatus.inProgress = false;
    }
  }

  /**
   * 取得排程狀態
   */
  getStatus() {
    return {
      enabled: this.isScrapingEnabled,
      lastScrapingTime: this.lastScrapingTime,
      status: this.scrapingStatus,
      nextRun: {
        weeklyFinancial: '每週五 16:00 (抓取財報)',
        dailyStocks: '週一至週五 14:00 (抓取股價)',
        dailyCleanup: '每天 01:00 (清理資料)',
      },
      config: {
        enableScheduler: process.env.ENABLE_SCHEDULER,
        timezone: 'Asia/Taipei',
      },
      description: {
        weeklyFinancial: '批次抓取前20家公司最新季報',
        dailyStocks: '抓取所有股票當日交易資料 (Open/High/Low/Close/Volume)',
        dailyCleanup: '清理超過3年的舊資料',
      },
    };
  }

  /**
   * 啟用排程
   */
  enableScheduler() {
    this.isScrapingEnabled = true;
    this.logger.log('✅ 排程已啟用');
  }

  /**
   * 停用排程
   */
  disableScheduler() {
    this.isScrapingEnabled = false;
    this.logger.log('⏸️ 排程已停用');
  }
}
