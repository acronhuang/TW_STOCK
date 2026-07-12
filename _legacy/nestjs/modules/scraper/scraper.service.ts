import { Injectable, Logger } from '@nestjs/common';
import { InjectModel } from '@nestjs/mongoose';
import { Model } from 'mongoose';
import { MOPSScraperService } from './services/mops.scraper';
import { TWSEScraperService } from './services/twse.scraper';
import { FinMindScraperService } from './services/finmind.scraper';
import { YahooScraperService } from './services/yahoo.scraper';
import { GoodinfoScraperService } from './services/goodinfo.scraper';
import { FinancialReport } from '../financial/schemas/financial-report.schema';
import { Ticker } from '../ticker/schemas/ticker.schema';

/**
 * 爬蟲服務 - 整合各資料源
 * 
 * 功能:
 * - 整合 MOPS 財報爬蟲
 * - 整合 TWSE 股價爬蟲
 * - 整合 TWSE 三大法人爬蟲
 * - 儲存資料到資料庫
 * - 批次更新功能
 * - 資料驗證
 */
@Injectable()
export class ScraperService {
  private readonly logger = new Logger(ScraperService.name);

  constructor(
    private readonly mopsScraper: MOPSScraperService,
    private readonly twseScraper: TWSEScraperService,
    private readonly finmindScraper: FinMindScraperService,
    private readonly yahooScraper: YahooScraperService,
    private readonly goodinfoScraper: GoodinfoScraperService,
    @InjectModel(FinancialReport.name)
    private readonly financialReportModel: Model<FinancialReport>,
    @InjectModel(Ticker.name)
    private readonly tickerModel: Model<Ticker>,
  ) {
    this.logger.log('爬蟲服務初始化完成 (MOPS + TWSE + FinMind + Yahoo + Goodinfo)');
  }

  /**
   * 抓取並儲存單一公司財報
   */
  async scrapeAndSaveQuarterlyReport(
    symbol: string,
    year: number,
    season: number,
  ): Promise<any> {
    this.logger.log(`開始抓取並儲存 ${symbol} ${year}Q${season} 財報`);

    try {
      // 從 MOPS 抓取資料
      const rawData = await this.mopsScraper.fetchQuarterlyReport(symbol, year, season);

      // 2. 轉換資料格式為 Schema 格式
      const reportData = this.transformToSchema(rawData);

      // 3. 儲存到資料庫 (upsert: 更新或新增)
      const result = await this.financialReportModel.findOneAndUpdate(
        {
          symbol: reportData.symbol,
          fiscalYear: reportData.fiscalYear,
          fiscalPeriod: reportData.fiscalPeriod,
        },
        reportData,
        { upsert: true, new: true },
      );

      this.logger.log(`✅ 成功儲存 ${symbol} ${year}Q${season} 財報`);
      return result;
    } catch (error) {
      this.logger.error(`❌ 抓取儲存失敗 ${symbol} ${year}Q${season}: ${error.message}`);
      throw error;
    }
  }

  /**
   * 批次抓取多家公司最新財報
   */
  async scrapeBatchLatest(symbols: string[]): Promise<any> {
    this.logger.log(`開始批次抓取 ${symbols.length} 家公司最新財報`);

    // 取得最新財報期間
    const { year, season } = this.mopsScraper.getLatestReportPeriod();
    this.logger.log(`最新財報期間: ${year}Q${season}`);

    const results = {
      success: [],
      failed: [],
      total: symbols.length,
    };

    for (const symbol of symbols) {
      try {
        const report = await this.scrapeAndSaveQuarterlyReport(symbol, year, season);
        results.success.push({
          symbol,
          fiscalYear: report.fiscalYear,
          fiscalPeriod: report.fiscalPeriod,
        });
      } catch (error) {
        results.failed.push({
          symbol,
          error: error.message,
        });
      }
    }

    this.logger.log(
      `✅ 批次抓取完成: 成功 ${results.success.length}/${results.total}`,
    );

    return results;
  }

  /**
   * 抓取單一公司歷史財報 (多個季度)
   */
  async scrapeHistory(
    symbol: string,
    startYear: number,
    startSeason: number,
    endYear: number,
    endSeason: number,
  ): Promise<any> {
    this.logger.log(
      `開始抓取 ${symbol} 歷史財報: ${startYear}Q${startSeason} ~ ${endYear}Q${endSeason}`,
    );

    const results = {
      success: [],
      failed: [],
      total: 0,
    };

    // 產生期間列表
    const periods = this.generatePeriods(
      startYear,
      startSeason,
      endYear,
      endSeason,
    );
    results.total = periods.length;

    for (const { year, season } of periods) {
      try {
        const report = await this.scrapeAndSaveQuarterlyReport(symbol, year, season);
        results.success.push({
          year,
          season,
          fiscalYear: report.fiscalYear,
          fiscalPeriod: report.fiscalPeriod,
        });

        // 延遲避免過度請求
        await this.sleep(2000);
      } catch (error) {
        results.failed.push({
          year,
          season,
          error: error.message,
        });
      }
    }

    this.logger.log(
      `✅ 歷史財報抓取完成: 成功 ${results.success.length}/${results.total}`,
    );

    return results;
  }

  /**
   * 取得爬蟲狀態
   */
  async getStatus(): Promise<any> {
    const { year, season } = this.mopsScraper.getLatestReportPeriod();
    const latestPeriod = `${year + 1911}Q${season}`;

    // 統計資料庫中的財報數量
    const totalReports = await this.financialReportModel.countDocuments();
    const latestReports = await this.financialReportModel.countDocuments({
      fiscalYear: year + 1911,
      fiscalPeriod: `Q${season}`,
    });

    return {
      status: 'active',
      latestPeriod,
      database: {
        totalReports,
        latestReports,
      },
      config: {
        timeout: process.env.SCRAPER_TIMEOUT,
        retryTimes: process.env.SCRAPER_RETRY_TIMES,
        delay: process.env.SCRAPER_DELAY,
      },
      scrapers: {
        mops: {
          baseUrl: 'https://mops.twse.com.tw',
          status: 'active',
        },
        twse: this.twseScraper.getStatus(),
      },
    };
  }

  /**
   * 轉換原始資料為 Schema 格式
   */
  private transformToSchema(rawData: any): any {
    const {
      symbol,
      fiscalYear,
      fiscalPeriod,
      reportType,
      incomeStatement,
      balanceSheet,
      cashFlow,
      dataSource,  // 保留原始 dataSource
      reportDate,
      currency,
    } = rawData;

    // 計算財務比率
    const ratios: any = {};

    // ROE = 淨利 / 股東權益
    if (incomeStatement.netIncome && balanceSheet.totalEquity) {
      ratios.roe = (incomeStatement.netIncome / balanceSheet.totalEquity) * 100;
    }

    // ROA = 淨利 / 總資產
    if (incomeStatement.netIncome && balanceSheet.totalAssets) {
      ratios.roa = (incomeStatement.netIncome / balanceSheet.totalAssets) * 100;
    }

    // 流動比率
    if (balanceSheet.currentRatio) {
      ratios.currentRatio = balanceSheet.currentRatio;
    }

    // 負債比率
    if (balanceSheet.debtRatio) {
      ratios.debtRatio = balanceSheet.debtRatio;
    }

    return {
      symbol,
      fiscalYear,
      fiscalPeriod,
      reportType,
      reportDate,
      currency: currency || 'TWD',
      incomeStatement: {
        revenue: incomeStatement.revenue || 0,
        grossProfit: incomeStatement.grossProfit || 0,
        operatingIncome: incomeStatement.operatingIncome || 0,
        pretaxIncome: incomeStatement.pretaxIncome || 0,
        netIncome: incomeStatement.netIncome || 0,
        eps: incomeStatement.eps || 0,
        grossMargin: incomeStatement.grossMargin || 0,
        operatingMargin: incomeStatement.operatingMargin || 0,
        netMargin: incomeStatement.netMargin || 0,
      },
      balanceSheet: {
        currentAssets: balanceSheet.currentAssets || 0,
        totalAssets: balanceSheet.totalAssets || 0,
        currentLiabilities: balanceSheet.currentLiabilities || 0,
        totalLiabilities: balanceSheet.totalLiabilities || 0,
        totalEquity: balanceSheet.totalEquity || 0,
        shareCapital: balanceSheet.shareCapital || 0,
      },
      cashFlow: {
        operatingCashFlow: cashFlow.operatingCashFlow || 0,
        investingCashFlow: cashFlow.investingCashFlow || 0,
        financingCashFlow: cashFlow.financingCashFlow || 0,
        freeCashFlow: cashFlow.freeCashFlow || 0,
      },
      ratios,
      dataSource: dataSource || 'MOPS',  // 保留原始 dataSource，預設為 MOPS
      createdAt: new Date(),
      updatedAt: new Date(),
    };
  }

  /**
   * 產生財報期間列表
   */
  private generatePeriods(
    startYear: number,
    startSeason: number,
    endYear: number,
    endSeason: number,
  ): Array<{ year: number; season: number }> {
    const periods = [];
    let currentYear = startYear;
    let currentSeason = startSeason;

    while (
      currentYear < endYear ||
      (currentYear === endYear && currentSeason <= endSeason)
    ) {
      periods.push({ year: currentYear, season: currentSeason });

      currentSeason++;
      if (currentSeason > 4) {
        currentSeason = 1;
        currentYear++;
      }
    }

    return periods;
  }

  /**
   * 抓取並儲存今日所有股票交易資料 (TWSE)
   */
  async scrapeAndSaveDailyStocks(): Promise<any> {
    this.logger.log('開始抓取今日所有股票交易資料 (TWSE)');

    try {
      // 1. 從 TWSE 抓取資料
      const stocks = await this.twseScraper.fetchDailyAllStocks();
      
      if (!stocks || stocks.length === 0) {
        this.logger.warn('未抓取到任何股票資料');
        return { success: 0, failed: 0, total: 0 };
      }

      // 2. 批次儲存到資料庫
      const results = {
        success: 0,
        failed: 0,
        total: stocks.length,
        errors: [],
      };

      for (const stock of stocks) {
        try {
          await this.tickerModel.findOneAndUpdate(
            {
              symbol: stock.symbol,
              date: stock.date,
            },
            stock,
            { upsert: true, new: true },
          );
          results.success++;
        } catch (error) {
          results.failed++;
          results.errors.push({
            symbol: stock.symbol,
            error: error.message,
          });
        }
      }

      this.logger.log(
        `✅ 儲存完成: 成功 ${results.success}/${results.total}，失敗 ${results.failed}`,
      );

      return results;
    } catch (error) {
      this.logger.error(`❌ 抓取今日股票資料失敗: ${error.message}`);
      throw error;
    }
  }

  /**
   * 抓取並更新三大法人買賣超資料 (TWSE)
   */
  async scrapeAndSaveInstitutionalTrading(): Promise<any> {
    this.logger.log('開始抓取三大法人買賣超資料 (TWSE)');

    try {
      // 1. 從 TWSE 抓取資料
      const institutions = await this.twseScraper.fetchInstitutionalTrading();
      
      if (!institutions || institutions.length === 0) {
        this.logger.warn('未抓取到三大法人資料');
        return { success: 0, failed: 0, total: 0 };
      }

      // 2. 更新 ticker 的三大法人欄位
      const results = {
        success: 0,
        failed: 0,
        total: institutions.length,
        errors: [],
      };

      for (const inst of institutions) {
        try {
          // 找到最新一筆 ticker 資料並更新三大法人欄位
          const latestTicker = await this.tickerModel
            .findOne({ symbol: inst.symbol })
            .sort({ date: -1 })
            .exec();

          if (latestTicker) {
            await this.tickerModel.updateOne(
              { _id: latestTicker._id },
              {
                $set: {
                  'institutional.foreign.netBuySell': inst.foreign.buySell,
                  'institutional.trust.netBuySell': inst.trust.buySell,
                  'institutional.dealer.netBuySell': inst.dealer.buySell,
                  'institutional.total.netBuySell': inst.total.buySell,
                },
              },
            );
            results.success++;
          } else {
            results.failed++;
            results.errors.push({
              symbol: inst.symbol,
              error: '找不到對應的 ticker 資料',
            });
          }
        } catch (error) {
          results.failed++;
          results.errors.push({
            symbol: inst.symbol,
            error: error.message,
          });
        }
      }

      this.logger.log(
        `✅ 更新完成: 成功 ${results.success}/${results.total}，失敗 ${results.failed}`,
      );

      return results;
    } catch (error) {
      this.logger.error(`❌ 抓取三大法人資料失敗: ${error.message}`);
      throw error;
    }
  }

  /**
   * 延遲執行
   */
  private sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  /**
   * 從 FinMind 抓取並儲存單一公司財報
   * 支援三大報表: 損益表、資產負債表、現金流量表
   */
  async scrapeFromFinMind(symbol: string, startDate: string = '2024-01-01'): Promise<any> {
    this.logger.log(`從 FinMind 抓取 ${symbol} 財報 (起始: ${startDate})`);

    try {
      // 1. 並行抓取三大報表
      const [incomeData, balanceData, cashflowData] = await Promise.all([
        this.finmindScraper.fetchFinancialStatement(symbol, startDate),
        this.fetchBalanceSheetFromFinMind(symbol, startDate),
        this.fetchCashFlowFromFinMind(symbol, startDate),
      ]);

      if (incomeData.length === 0) {
        throw new Error('無財報資料');
      }

      // 2. 按日期分組資料
      const groupedData = this.groupFinMindDataByDate(incomeData, balanceData, cashflowData);

      // 3. 轉換並儲存每個季度
      const savedReports = [];
      for (const [date, data] of groupedData) {
        try {
          const rawData = this.convertFinMindToRawFormat(symbol, date, data);
          const reportData = this.transformToSchema(rawData);
          
          const result = await this.financialReportModel.findOneAndUpdate(
            {
              symbol: reportData.symbol,
              fiscalYear: reportData.fiscalYear,
              fiscalPeriod: reportData.fiscalPeriod,
            },
            reportData,
            { upsert: true, new: true },
          );
          
          savedReports.push(result);
        } catch (error) {
          this.logger.warn(`${symbol} ${date} 轉換失敗: ${error.message}`);
        }
      }

      this.logger.log(`✅ ${symbol} 成功儲存 ${savedReports.length} 筆財報`);
      return savedReports;
    } catch (error) {
      this.logger.error(`❌ ${symbol} FinMind 抓取失敗: ${error.message}`);
      throw error;
    }
  }

  /**
   * 批次補齊多家公司財報 (從 FinMind)
   */
  async batchBackfillFinancialReports(
    symbols: string[],
    startDate: string = '2024-01-01',
  ): Promise<any> {
    this.logger.log(`開始批次補齊 ${symbols.length} 家公司財報 (FinMind)`);

    const results = {
      success: 0,
      failed: 0,
      total: symbols.length,
      errors: [],
    };

    for (const symbol of symbols) {
      try {
        await this.scrapeFromFinMind(symbol, startDate);
        results.success++;
        this.logger.log(`✅ ${symbol} 完成 (${results.success}/${results.total})`);
      } catch (error) {
        results.failed++;
        results.errors.push({
          symbol,
          error: error.message,
        });
        this.logger.error(`❌ ${symbol} 失敗: ${error.message}`);
      }

      // 延遲避免 API 限流
      await this.sleep(1000);
    }

    this.logger.log(
      `✅ 批次補齊完成: 成功 ${results.success}/${results.total}，失敗 ${results.failed}`,
    );

    return results;
  }

  /**
   * 從 FinMind 抓取資產負債表
   */
  private async fetchBalanceSheetFromFinMind(symbol: string, startDate: string): Promise<any[]> {
    try {
      const response = await this.finmindScraper['retryRequest']({
        dataset: 'TaiwanStockBalanceSheet',
        data_id: symbol,
        start_date: startDate,
      });
      return response.data.data || [];
    } catch (error) {
      this.logger.warn(`${symbol} 資產負債表抓取失敗: ${error.message}`);
      return [];
    }
  }

  /**
   * 從 FinMind 抓取現金流量表
   */
  private async fetchCashFlowFromFinMind(symbol: string, startDate: string): Promise<any[]> {
    try {
      const response = await this.finmindScraper['retryRequest']({
        dataset: 'TaiwanStockCashFlowsStatement',
        data_id: symbol,
        start_date: startDate,
      });
      return response.data.data || [];
    } catch (error) {
      this.logger.warn(`${symbol} 現金流量表抓取失敗: ${error.message}`);
      return [];
    }
  }

  /**
   * 按日期分組 FinMind 資料
   */
  private groupFinMindDataByDate(
    incomeData: any[],
    balanceData: any[],
    cashflowData: any[],
  ): Map<string, any> {
    const grouped = new Map<string, any>();

    // 處理損益表
    for (const item of incomeData) {
      if (!grouped.has(item.date)) {
        grouped.set(item.date, {
          income: [],
          balance: [],
          cashflow: [],
        });
      }
      grouped.get(item.date).income.push(item);
    }

    // 處理資產負債表
    for (const item of balanceData) {
      if (grouped.has(item.date)) {
        grouped.get(item.date).balance.push(item);
      }
    }

    // 處理現金流量表
    for (const item of cashflowData) {
      if (grouped.has(item.date)) {
        grouped.get(item.date).cashflow.push(item);
      }
    }

    return grouped;
  }

  /**
   * 將 FinMind 格式轉換為 rawData 格式 (供 transformToSchema 使用)
   */
  private convertFinMindToRawFormat(symbol: string, date: string, data: any): any {
    const { income, balance, cashflow } = data;

    // 解析日期取得年度與季度
    const dateObj = new Date(date);
    const year = dateObj.getFullYear();
    const month = dateObj.getMonth() + 1;
    const period = this.getQuarterFromMonth(month);

    // 轉換為 Map 方便查詢
    const incomeMap = this.arrayToMap(income);
    const balanceMap = this.arrayToMap(balance);
    const cashflowMap = this.arrayToMap(cashflow);

    return {
      symbol,
      fiscalYear: year,
      fiscalPeriod: period,
      reportType: 'quarterly',
      incomeStatement: {
        revenue: this.getFinMindValue(incomeMap, 'Revenue') / 1000,
        grossProfit: this.getFinMindValue(incomeMap, 'GrossProfit') / 1000,
        operatingExpenses: this.getFinMindValue(incomeMap, 'OperatingExpenses') / 1000,
        operatingIncome: this.getFinMindValue(incomeMap, 'OperatingIncome') / 1000,
        pretaxIncome: this.getFinMindValue(incomeMap, 'PreTaxIncome') / 1000,
        incomeTax: this.getFinMindValue(incomeMap, 'TAX') / 1000,
        netIncome: this.getFinMindValue(incomeMap, 'IncomeAfterTaxes') / 1000,
        eps: this.getFinMindValue(incomeMap, 'EPS'),
        grossMargin: 0, // 稍後計算
        operatingMargin: 0, // 稍後計算
        netMargin: 0, // 稍後計算
      },
      balanceSheet: {
        currentAssets: this.getFinMindValue(balanceMap, 'TotalCurrentAssets') / 1000,
        totalAssets: this.getFinMindValue(balanceMap, 'TotalAssets') / 1000,
        currentLiabilities: this.getFinMindValue(balanceMap, 'TotalCurrentLiabilities') / 1000,
        totalLiabilities: this.getFinMindValue(balanceMap, 'TotalLiabilities') / 1000,
        totalEquity: this.getFinMindValue(balanceMap, 'EquityAttributableToOwnersOfParent') / 1000,
        shareCapital: this.getFinMindValue(balanceMap, 'OrdinaryShare') / 1000,
        cash: this.getFinMindValue(balanceMap, 'CashAndCashEquivalents') / 1000,
        accountsReceivable: this.getFinMindValue(balanceMap, 'AccountsReceivableNet') / 1000,
        inventory: this.getFinMindValue(balanceMap, 'Inventories') / 1000,
        fixedAssets: this.getFinMindValue(balanceMap, 'PropertyPlantAndEquipment') / 1000,
        shortTermDebt: this.getFinMindValue(balanceMap, 'ShortTermLoans') / 1000,
        longTermDebt: this.getFinMindValue(balanceMap, 'LongTermLoans') / 1000,
        currentRatio: 0, // 稍後計算
        debtRatio: 0, // 稍後計算
      },
      cashFlow: {
        operatingCashFlow: this.getFinMindValue(cashflowMap, 'CashProvidedByOperatingActivit') / 1000,
        investingCashFlow: this.getFinMindValue(cashflowMap, 'CashProvidedByInvestingActivitie') / 1000,
        financingCashFlow: this.getFinMindValue(cashflowMap, 'CashFlowsProvidedByFinancingActivi') / 1000,
        freeCashFlow: 0, // 稍後計算
      },
      dataSource: 'FinMind',
      reportDate: date,
      currency: 'TWD',
    };
  }

  /**
   * FinMind 陣列轉 Map
   */
  private arrayToMap(data: any[]): Map<string, number> {
    const map = new Map<string, number>();
    for (const item of data) {
      if (item.type && item.value !== null) {
        map.set(item.type, item.value);
      }
    }
    return map;
  }

  /**
   * 從 FinMind Map 取值
   */
  private getFinMindValue(map: Map<string, number>, key: string): number {
    return map.get(key) || 0;
  }

  /**
   * 根據月份判斷季度
   */
  private getQuarterFromMonth(month: number): string {
    if (month >= 1 && month <= 3) return 'Q1';
    if (month >= 4 && month <= 6) return 'Q2';
    if (month >= 7 && month <= 9) return 'Q3';
    return 'Q4';
  }

  /**
   * 延遲執行 (避免被 ban)
   */
  private delay(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  // ========== Yahoo Finance 資料源整合 ==========

  /**
   * 從 Yahoo Finance 抓取並儲存財報
   * @param symbol 股票代碼
   * @param year 年度 (西元年)
   * @param quarter 季度 (1-4)
   * @returns 儲存結果
   */
  async scrapeFromYahoo(symbol: string, year: number, quarter: number): Promise<any> {
    this.logger.log(`從 Yahoo Finance 抓取 ${symbol} ${year}Q${quarter}`);

    try {
      const yahooData = await this.yahooScraper.fetchQuarterlyReport(symbol, year, quarter);
      const converted = this.convertYahooToRawFormat(yahooData);
      const reportData = this.transformToSchema(converted);

      // 檢查是否已存在
      const existing = await this.financialReportModel.findOne({
        symbol,
        fiscalYear: year,
        fiscalPeriod: `Q${quarter}`,
        dataSource: 'Yahoo',
      });

      if (existing) {
        this.logger.log(`${symbol} ${year}Q${quarter} Yahoo 資料已存在，跳過`);
        return existing;
      }

      const saved = await this.financialReportModel.create(reportData);
      this.logger.log(`✅ ${symbol} ${year}Q${quarter} Yahoo 資料已儲存`);
      return saved;
    } catch (error) {
      this.logger.error(`Yahoo 資料儲存失敗: ${symbol} ${year}Q${quarter}`, error.stack);
      throw error;
    }
  }

  /**
   * 批次從 Yahoo Finance 補齊歷史資料
   * @param symbols 股票代碼列表
   * @param startYear 開始年度
   * @param endYear 結束年度
   * @returns 處理結果
   */
  async batchBackfillFromYahoo(
    symbols: string[],
    startYear: number,
    endYear: number,
  ): Promise<any> {
    this.logger.log(`Yahoo 批次補齊: ${symbols.length} 家公司, ${startYear}-${endYear}`);

    const results = {
      success: 0,
      failed: 0,
      total: 0,
      errors: [],
    };

    for (const symbol of symbols) {
      for (let year = startYear; year <= endYear; year++) {
        for (let quarter = 1; quarter <= 4; quarter++) {
          results.total++;

          try {
            await this.scrapeFromYahoo(symbol, year, quarter);
            results.success++;
            this.logger.log(`✅ ${symbol} ${year}Q${quarter} (${results.success}/${results.total})`);
          } catch (error) {
            results.failed++;
            results.errors.push({
              symbol,
              year,
              quarter,
              error: error.message,
            });
            this.logger.warn(`❌ ${symbol} ${year}Q${quarter}: ${error.message}`);
          }

          // 延遲避免被 ban (Yahoo 需要較短延遲)
          await this.delay(500);
        }
      }
    }

    this.logger.log(
      `Yahoo 批次補齊完成: 成功 ${results.success}/${results.total}，失敗 ${results.failed}`,
    );

    return results;
  }

  /**
   * 將 Yahoo Finance 格式轉換為 rawData 格式
   */
  private convertYahooToRawFormat(yahooData: any): any {
    const { symbol, year, quarter, incomeStatement, balanceSheet, cashflow, reportDate } = yahooData;

    return {
      symbol,
      fiscalYear: year,
      fiscalPeriod: `Q${quarter}`,
      reportType: 'quarterly',
      dataSource: 'Yahoo',
      reportDate,
      currency: 'TWD',
      incomeStatement: {
        revenue: incomeStatement.totalRevenue / 1000 || 0, // Yahoo 是元，轉千元
        operatingRevenue: incomeStatement.operatingRevenue / 1000 || 0,
        operatingCosts: incomeStatement.costOfRevenue / 1000 || 0,
        grossProfit: incomeStatement.grossProfit / 1000 || 0,
        operatingExpenses: incomeStatement.operatingExpense / 1000 || 0,
        operatingIncome: incomeStatement.operatingIncome / 1000 || 0,
        nonOperatingIncome: incomeStatement.otherIncomeExpense / 1000 || 0,
        pretaxIncome: incomeStatement.incomeBeforeTax / 1000 || 0,
        incomeTax: incomeStatement.incomeTaxExpense / 1000 || 0,
        netIncome: incomeStatement.netIncome / 1000 || 0,
        eps: incomeStatement.basicEPS || 0,
      },
      balanceSheet: {
        totalAssets: balanceSheet.totalAssets / 1000 || 0,
        currentAssets: balanceSheet.currentAssets / 1000 || 0,
        cash: balanceSheet.cash / 1000 || 0,
        accountsReceivable: balanceSheet.accountsReceivable / 1000 || 0,
        inventory: balanceSheet.inventory / 1000 || 0,
        nonCurrentAssets: balanceSheet.totalNonCurrentAssets / 1000 || 0,
        fixedAssets: balanceSheet.propertyPlantEquipment / 1000 || 0,
        totalLiabilities: balanceSheet.totalLiab / 1000 || 0,
        currentLiabilities: balanceSheet.currentLiabilities / 1000 || 0,
        shortTermDebt: balanceSheet.shortTermDebt / 1000 || 0,
        accountsPayable: balanceSheet.accountsPayable / 1000 || 0,
        nonCurrentLiabilities: balanceSheet.totalNonCurrentLiabilities / 1000 || 0,
        longTermDebt: balanceSheet.longTermDebt / 1000 || 0,
        totalEquity: balanceSheet.totalStockholderEquity / 1000 || 0,
        capitalStock: balanceSheet.commonStock / 1000 || 0,
        retainedEarnings: balanceSheet.retainedEarnings / 1000 || 0,
      },
      cashFlow: {
        operatingCashFlow: cashflow.totalCashFromOperatingActivities / 1000 || 0,
        investingCashFlow: cashflow.totalCashflowsFromInvestingActivities / 1000 || 0,
        financingCashFlow: cashflow.totalCashFromFinancingActivities / 1000 || 0,
        netCashFlow: cashflow.changeInCash / 1000 || 0,
        freeCashFlow: cashflow.freeCashFlow / 1000 || 0,
      },
    };
  }

  // ========== Goodinfo 資料源整合 ==========

  /**
   * 從 Goodinfo 抓取並儲存財報
   * @param symbol 股票代碼
   * @param year 年度 (民國年)
   * @param quarter 季度 (1-4)
   * @returns 儲存結果
   */
  async scrapeFromGoodinfo(symbol: string, year: number, quarter: number): Promise<any> {
    this.logger.log(`從 Goodinfo 抓取 ${symbol} ${year}Q${quarter}`);

    try {
      const goodinfoData = await this.goodinfoScraper.fetchQuarterlyReport(symbol, year, quarter);
      const converted = this.convertGoodinfoToRawFormat(goodinfoData);
      const reportData = this.transformToSchema(converted);

      // 檢查是否已存在
      const existing = await this.financialReportModel.findOne({
        symbol,
        fiscalYear: year + 1911, // 民國年轉西元年
        fiscalPeriod: `Q${quarter}`,
        dataSource: 'Goodinfo',
      });

      if (existing) {
        this.logger.log(`${symbol} ${year}Q${quarter} Goodinfo 資料已存在，跳過`);
        return existing;
      }

      const saved = await this.financialReportModel.create(reportData);
      this.logger.log(`✅ ${symbol} ${year}Q${quarter} Goodinfo 資料已儲存`);
      return saved;
    } catch (error) {
      this.logger.error(`Goodinfo 資料儲存失敗: ${symbol} ${year}Q${quarter}`, error.stack);
      throw error;
    }
  }

  /**
   * 批次從 Goodinfo 補齊歷史資料
   * @param symbols 股票代碼列表
   * @param startYear 開始年度 (民國年)
   * @param endYear 結束年度 (民國年)
   * @returns 處理結果
   */
  async batchBackfillFromGoodinfo(
    symbols: string[],
    startYear: number,
    endYear: number,
  ): Promise<any> {
    this.logger.log(`Goodinfo 批次補齊: ${symbols.length} 家公司, ${startYear}-${endYear}`);

    const results = {
      success: 0,
      failed: 0,
      total: 0,
      errors: [],
    };

    for (const symbol of symbols) {
      for (let year = startYear; year <= endYear; year++) {
        for (let quarter = 1; quarter <= 4; quarter++) {
          results.total++;

          try {
            await this.scrapeFromGoodinfo(symbol, year, quarter);
            results.success++;
            this.logger.log(`✅ ${symbol} ${year}Q${quarter} (${results.success}/${results.total})`);
          } catch (error) {
            results.failed++;
            results.errors.push({
              symbol,
              year,
              quarter,
              error: error.message,
            });
            this.logger.warn(`❌ ${symbol} ${year}Q${quarter}: ${error.message}`);
          }

          // Goodinfo 需要較長延遲避免被 ban
          await this.delay(3000);
        }
      }
    }

    this.logger.log(
      `Goodinfo 批次補齊完成: 成功 ${results.success}/${results.total}，失敗 ${results.failed}`,
    );

    return results;
  }

  /**
   * 將 Goodinfo 格式轉換為 rawData 格式
   */
  private convertGoodinfoToRawFormat(goodinfoData: any): any {
    const { symbol, year, quarter, reportDate } = goodinfoData;

    // Goodinfo 欄位名稱與 rawData 的映射
    const data = goodinfoData;

    return {
      symbol,
      fiscalYear: year + 1911, // 民國年轉西元年
      fiscalPeriod: `Q${quarter}`,
      reportType: 'quarterly',
      dataSource: 'Goodinfo',
      reportDate,
      currency: 'TWD',
      incomeStatement: {
        revenue: data['營業收入'] || 0,
        operatingCosts: data['營業成本'] || 0,
        grossProfit: data['營業毛利'] || 0,
        operatingExpenses: data['營業費用'] || 0,
        operatingIncome: data['營業利益'] || 0,
        nonOperatingIncome: data['業外損益'] || 0,
        pretaxIncome: data['稅前淨利'] || 0,
        incomeTax: data['所得稅'] || 0,
        netIncome: data['本期淨利'] || 0,
        eps: data['每股盈餘'] || 0,
      },
      balanceSheet: {
        totalAssets: data['資產總計'] || 0,
        currentAssets: data['流動資產'] || 0,
        cash: data['現金及約當現金'] || 0,
        accountsReceivable: data['應收帳款'] || 0,
        inventory: data['存貨'] || 0,
        nonCurrentAssets: data['非流動資產'] || 0,
        fixedAssets: data['不動產、廠房及設備'] || 0,
        totalLiabilities: data['負債總計'] || 0,
        currentLiabilities: data['流動負債'] || 0,
        nonCurrentLiabilities: data['非流動負債'] || 0,
        totalEquity: data['權益總計'] || 0,
        capitalStock: data['股本'] || 0,
        retainedEarnings: data['保留盈餘'] || 0,
      },
      cashFlow: {
        operatingCashFlow: data['營業活動之現金流量'] || 0,
        investingCashFlow: data['投資活動之現金流量'] || 0,
        financingCashFlow: data['融資活動之現金流量'] || 0,
        netCashFlow: data['本期現金增減'] || 0,
        freeCashFlow: data['自由現金流量'] || 0,
      },
    };
  }
}
