import { Injectable, Logger } from '@nestjs/common';
import axios, { AxiosInstance } from 'axios';
import * as cheerio from 'cheerio';
import { DateUtilService } from '../../../common/utils/date-util.service';

/**
 * 公開資訊觀測站 (MOPS) 爬蟲服務
 * 資料來源: https://mops.twse.com.tw
 * 
 * 功能:
 * - 抓取季報財務報表 (損益表、資產負債表、現金流量表)
 * - 抓取年報財務報表
 * - 支援單一公司或批次抓取
 * - 錯誤重試機制
 */
@Injectable()
export class MOPSScraperService {
  private readonly logger = new Logger(MOPSScraperService.name);
  private readonly axiosInstance: AxiosInstance;
  private readonly baseUrl = 'https://mops.twse.com.tw';
  
  // 爬蟲設定
  private readonly timeout: number;
  private readonly retryTimes: number;
  private readonly delay: number;

  constructor(private readonly dateUtil: DateUtilService) {
    // 從環境變數讀取配置
    this.timeout = parseInt(process.env.SCRAPER_TIMEOUT || '30000');
    this.retryTimes = parseInt(process.env.SCRAPER_RETRY_TIMES || '3');
    this.delay = parseInt(process.env.SCRAPER_DELAY || '1000');

    // 建立 axios 實例
    this.axiosInstance = axios.create({
      timeout: this.timeout,
      headers: {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
      },
    });
  }

  /**
   * 抓取單一公司季報
   * @param symbol 股票代碼
   * @param year 民國年
   * @param season 季度 (1-4)
   */
  async fetchQuarterlyReport(
    symbol: string,
    year: number,
    season: number,
  ): Promise<any> {
    this.logger.log(`開始抓取 ${symbol} ${year}Q${season} 財報`);

    try {
      // 1. 抓取損益表
      const incomeStatement = await this.fetchIncomeStatement(symbol, year, season);
      await this.sleep(this.delay);

      // 2. 抓取資產負債表
      const balanceSheet = await this.fetchBalanceSheet(symbol, year, season);
      await this.sleep(this.delay);

      // 3. 抓取現金流量表
      const cashFlow = await this.fetchCashFlowStatement(symbol, year, season);

      this.logger.log(`✅ 成功抓取 ${symbol} ${year}Q${season} 財報`);

      return {
        symbol,
        fiscalYear: year + 1911, // 轉換為西元年
        fiscalPeriod: `Q${season}`,
        reportType: 'quarterly',
        incomeStatement,
        balanceSheet,
        cashFlow,
        scrapedAt: new Date(),
      };
    } catch (error) {
      this.logger.error(`❌ 抓取失敗 ${symbol} ${year}Q${season}: ${error.message}`);
      throw error;
    }
  }

  /**
   * 抓取損益表
   * API: https://mops.twse.com.tw/mops/web/ajax_t163sb04
   */
  private async fetchIncomeStatement(
    symbol: string,
    year: number,
    season: number,
  ): Promise<any> {
    const url = `${this.baseUrl}/mops/web/ajax_t163sb04`;
    const params = {
      encodeURIComponent: '1',
      step: '1',
      firstin: '1',
      off: '1',
      co_id: symbol,
      year: year.toString(),
      season: season.toString(),
    };

    let lastError: Error;
    for (let attempt = 1; attempt <= this.retryTimes; attempt++) {
      try {
        const response = await this.axiosInstance.post(url, new URLSearchParams(params));
        const $ = cheerio.load(response.data);
        
        return this.parseIncomeStatement($, symbol);
      } catch (error) {
        lastError = error;
        this.logger.warn(`損益表抓取失敗 (嘗試 ${attempt}/${this.retryTimes}): ${error.message}`);
        if (attempt < this.retryTimes) {
          await this.sleep(this.delay * attempt);
        }
      }
    }

    throw lastError;
  }

  /**
   * 抓取資產負債表
   * API: https://mops.twse.com.tw/mops/web/ajax_t163sb05
   */
  private async fetchBalanceSheet(
    symbol: string,
    year: number,
    season: number,
  ): Promise<any> {
    const url = `${this.baseUrl}/mops/web/ajax_t163sb05`;
    const params = {
      encodeURIComponent: '1',
      step: '1',
      firstin: '1',
      off: '1',
      co_id: symbol,
      year: year.toString(),
      season: season.toString(),
    };

    let lastError: Error;
    for (let attempt = 1; attempt <= this.retryTimes; attempt++) {
      try {
        const response = await this.axiosInstance.post(url, new URLSearchParams(params));
        const $ = cheerio.load(response.data);
        
        return this.parseBalanceSheet($, symbol);
      } catch (error) {
        lastError = error;
        this.logger.warn(`資產負債表抓取失敗 (嘗試 ${attempt}/${this.retryTimes}): ${error.message}`);
        if (attempt < this.retryTimes) {
          await this.sleep(this.delay * attempt);
        }
      }
    }

    throw lastError;
  }

  /**
   * 抓取現金流量表
   * API: https://mops.twse.com.tw/mops/web/ajax_t163sb20
   */
  private async fetchCashFlowStatement(
    symbol: string,
    year: number,
    season: number,
  ): Promise<any> {
    const url = `${this.baseUrl}/mops/web/ajax_t163sb20`;
    const params = {
      encodeURIComponent: '1',
      step: '1',
      firstin: '1',
      off: '1',
      co_id: symbol,
      year: year.toString(),
      season: season.toString(),
    };

    let lastError: Error;
    for (let attempt = 1; attempt <= this.retryTimes; attempt++) {
      try {
        const response = await this.axiosInstance.post(url, new URLSearchParams(params));
        const $ = cheerio.load(response.data);
        
        return this.parseCashFlowStatement($, symbol);
      } catch (error) {
        lastError = error;
        this.logger.warn(`現金流量表抓取失敗 (嘗試 ${attempt}/${this.retryTimes}): ${error.message}`);
        if (attempt < this.retryTimes) {
          await this.sleep(this.delay * attempt);
        }
      }
    }

    throw lastError;
  }

  /**
   * 解析損益表 HTML
   */
  private parseIncomeStatement($: cheerio.CheerioAPI, symbol: string): any {
    const data: any = {};

    // MOPS 表格結構: <table class="hasBorder">
    // 尋找包含「營業收入」的表格
    $('table.hasBorder').each((_, table) => {
      const rows = $(table).find('tr');
      
      rows.each((_, row) => {
        const cells = $(row).find('td');
        if (cells.length < 2) return;

        const label = $(cells[0]).text().trim();
        const value = $(cells[1]).text().trim();

        // 解析關鍵欄位
        if (label.includes('營業收入')) {
          data.revenue = this.parseNumber(value);
        } else if (label.includes('營業毛利（毛損）')) {
          data.grossProfit = this.parseNumber(value);
        } else if (label.includes('營業利益（損失）')) {
          data.operatingIncome = this.parseNumber(value);
        } else if (label.includes('稅前淨利（淨損）')) {
          data.pretaxIncome = this.parseNumber(value);
        } else if (label.includes('本期淨利（淨損）')) {
          data.netIncome = this.parseNumber(value);
        } else if (label.includes('基本每股盈餘')) {
          data.eps = this.parseNumber(value);
        }
      });
    });

    // 計算毛利率和淨利率
    if (data.revenue && data.grossProfit) {
      data.grossMargin = (data.grossProfit / data.revenue) * 100;
    }
    if (data.revenue && data.netIncome) {
      data.netMargin = (data.netIncome / data.revenue) * 100;
    }

    return data;
  }

  /**
   * 解析資產負債表 HTML
   */
  private parseBalanceSheet($: cheerio.CheerioAPI, symbol: string): any {
    const data: any = {};

    $('table.hasBorder').each((_, table) => {
      const rows = $(table).find('tr');
      
      rows.each((_, row) => {
        const cells = $(row).find('td');
        if (cells.length < 2) return;

        const label = $(cells[0]).text().trim();
        const value = $(cells[1]).text().trim();

        // 解析關鍵欄位
        if (label.includes('流動資產')) {
          data.currentAssets = this.parseNumber(value);
        } else if (label.includes('資產總額') || label.includes('資產總計')) {
          data.totalAssets = this.parseNumber(value);
        } else if (label.includes('流動負債')) {
          data.currentLiabilities = this.parseNumber(value);
        } else if (label.includes('負債總額') || label.includes('負債總計')) {
          data.totalLiabilities = this.parseNumber(value);
        } else if (label.includes('權益總額') || label.includes('權益總計')) {
          data.totalEquity = this.parseNumber(value);
        } else if (label.includes('股本')) {
          data.shareCapital = this.parseNumber(value);
        }
      });
    });

    // 計算財務比率
    if (data.currentAssets && data.currentLiabilities) {
      data.currentRatio = (data.currentAssets / data.currentLiabilities) * 100;
    }
    if (data.totalLiabilities && data.totalAssets) {
      data.debtRatio = (data.totalLiabilities / data.totalAssets) * 100;
    }

    return data;
  }

  /**
   * 解析現金流量表 HTML
   */
  private parseCashFlowStatement($: cheerio.CheerioAPI, symbol: string): any {
    const data: any = {};

    $('table.hasBorder').each((_, table) => {
      const rows = $(table).find('tr');
      
      rows.each((_, row) => {
        const cells = $(row).find('td');
        if (cells.length < 2) return;

        const label = $(cells[0]).text().trim();
        const value = $(cells[1]).text().trim();

        // 解析關鍵欄位
        if (label.includes('營業活動之淨現金流入（流出）')) {
          data.operatingCashFlow = this.parseNumber(value);
        } else if (label.includes('投資活動之淨現金流入（流出）')) {
          data.investingCashFlow = this.parseNumber(value);
        } else if (label.includes('籌資活動之淨現金流入（流出）')) {
          data.financingCashFlow = this.parseNumber(value);
        }
      });
    });

    // 計算自由現金流
    if (data.operatingCashFlow && data.investingCashFlow) {
      data.freeCashFlow = data.operatingCashFlow + data.investingCashFlow;
    }

    return data;
  }

  /**
   * 批次抓取多家公司
   * @param symbols 股票代碼陣列
   * @param year 民國年
   * @param season 季度
   */
  async fetchBatch(
    symbols: string[],
    year: number,
    season: number,
  ): Promise<any[]> {
    this.logger.log(`開始批次抓取 ${symbols.length} 家公司 ${year}Q${season} 財報`);

    const results = [];
    for (const symbol of symbols) {
      try {
        const data = await this.fetchQuarterlyReport(symbol, year, season);
        results.push(data);
        
        // 延遲避免被封鎖
        await this.sleep(this.delay);
      } catch (error) {
        this.logger.error(`批次抓取失敗 ${symbol}: ${error.message}`);
        results.push({
          symbol,
          error: error.message,
          success: false,
        });
      }
    }

    this.logger.log(`✅ 批次抓取完成: 成功 ${results.filter(r => !r.error).length}/${symbols.length}`);
    return results;
  }

  /**
   * 解析數字 (處理千分位逗號和負號)
   */
  private parseNumber(value: string): number {
    if (!value) return 0;
    
    // 移除千分位逗號
    let cleaned = value.replace(/,/g, '');
    
    // 處理括號表示負數 (會計格式)
    if (cleaned.includes('(') || cleaned.includes(')')) {
      cleaned = '-' + cleaned.replace(/[()]/g, '');
    }
    
    const num = parseFloat(cleaned);
    return isNaN(num) ? 0 : num;
  }

  /**
   * 延遲執行
   */
  private sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  /**
   * 取得最新財報期間
   * 根據當前日期推算最新應公布的財報期間
   */
  getLatestReportPeriod(): { year: number; season: number } {
    const now = new Date();
    const currentYear = now.getFullYear();
    const currentMonth = now.getMonth() + 1;

    // 財報公布時間:
    // Q1 (1-3月): 5月中公布
    // Q2 (4-6月): 8月中公布
    // Q3 (7-9月): 11月中公布
    // Q4 (10-12月): 隔年3月底公布

    let year = currentYear - 1911; // 轉民國年
    let season: number;

    if (currentMonth >= 11) {
      season = 3;
    } else if (currentMonth >= 8) {
      season = 2;
    } else if (currentMonth >= 5) {
      season = 1;
    } else if (currentMonth >= 3) {
      year--;
      season = 4;
    } else {
      year--;
      season = 3;
    }

    return { year, season };
  }
}
