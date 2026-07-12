import { Injectable, Logger } from '@nestjs/common';
import axios, { AxiosInstance } from 'axios';

/**
 * FinMind API 爬蟲服務
 * 資料來源: https://finmind.github.io/
 * 
 * 功能:
 * - 財務報表 (TaiwanStockFinancialStatement)
 * - 月營收 (TaiwanStockMonthRevenue)
 * - 股利 (TaiwanStockDividend)
 * - 三大法人 (TaiwanStockInstitutionalInvestors)
 * - 股價 (TaiwanStockPrice) - 備援用
 * 
 * 優勢:
 * - 免費 API，無需註冊
 * - 資料完整，涵蓋台股所有資料
 * - JSON 格式，易於解析
 * - 社群維護，穩定可靠
 */
@Injectable()
export class FinMindScraperService {
  private readonly logger = new Logger(FinMindScraperService.name);
  private readonly axiosInstance: AxiosInstance;
  private readonly baseUrl = 'https://api.finmindtrade.com/api/v4/data';
  
  // API 限制配置
  private readonly timeout: number;
  private readonly retryTimes: number;
  private readonly delay: number;

  constructor() {
    this.timeout = parseInt(process.env.SCRAPER_TIMEOUT || '30000');
    this.retryTimes = parseInt(process.env.SCRAPER_RETRY_TIMES || '3');
    this.delay = parseInt(process.env.SCRAPER_DELAY || '1000');

    this.axiosInstance = axios.create({
      timeout: this.timeout,
      headers: {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept': 'application/json',
      },
    });

    this.logger.log('FinMind API 服務初始化完成');
  }

  /**
   * 抓取財務報表
   * Dataset: TaiwanStockFinancialStatements (注意有 s)
   * 
   * @param symbol 股票代碼
   * @param startDate 開始日期 (YYYY-MM-DD)
   * @returns 財務報表資料陣列
   */
  async fetchFinancialStatement(
    symbol: string,
    startDate: string = '2023-01-01',
  ): Promise<any[]> {
    this.logger.log(`抓取 ${symbol} 財務報表 (起始: ${startDate})`);

    try {
      const params = {
        dataset: 'TaiwanStockFinancialStatements',  // 正確端點名稱
        data_id: symbol,
        start_date: startDate,
      };

      const response = await this.retryRequest(params);
      const data = response.data.data || [];
      
      this.logger.log(`✅ 成功抓取 ${symbol} 財務報表 ${data.length} 筆`);
      return data;
    } catch (error) {
      this.logger.error(`❌ 抓取 ${symbol} 財務報表失敗: ${error.message}`);
      throw error;
    }
  }

  /**
   * 抓取月營收
   * Dataset: TaiwanStockMonthRevenue
   * 
   * @param symbol 股票代碼
   * @param startDate 開始日期 (YYYY-MM-DD)
   * @returns 月營收資料陣列
   */
  async fetchMonthlyRevenue(
    symbol: string,
    startDate: string = '2023-01-01',
  ): Promise<any[]> {
    this.logger.log(`抓取 ${symbol} 月營收 (起始: ${startDate})`);

    try {
      const params = {
        dataset: 'TaiwanStockMonthRevenue',
        data_id: symbol,
        start_date: startDate,
      };

      const response = await this.retryRequest(params);
      const data = response.data.data || [];
      
      this.logger.log(`✅ 成功抓取 ${symbol} 月營收 ${data.length} 筆`);
      return data;
    } catch (error) {
      this.logger.error(`❌ 抓取 ${symbol} 月營收失敗: ${error.message}`);
      throw error;
    }
  }

  /**
   * 抓取股利資料
   * Dataset: TaiwanStockDividend
   * 
   * @param symbol 股票代碼
   * @param startDate 開始日期 (YYYY-MM-DD)
   * @returns 股利資料陣列
   */
  async fetchDividend(
    symbol: string,
    startDate: string = '2020-01-01',
  ): Promise<any[]> {
    this.logger.log(`抓取 ${symbol} 股利資料 (起始: ${startDate})`);

    try {
      const params = {
        dataset: 'TaiwanStockDividend',
        data_id: symbol,
        start_date: startDate,
      };

      const response = await this.retryRequest(params);
      const data = response.data.data || [];
      
      this.logger.log(`✅ 成功抓取 ${symbol} 股利資料 ${data.length} 筆`);
      return data;
    } catch (error) {
      this.logger.error(`❌ 抓取 ${symbol} 股利資料失敗: ${error.message}`);
      throw error;
    }
  }

  /**
   * 抓取三大法人買賣超
   * Dataset: TaiwanStockInstitutionalInvestorsBuySell (正確端點)
   * 
   * @param symbol 股票代碼
   * @param startDate 開始日期 (YYYY-MM-DD)
   * @returns 三大法人資料陣列
   */
  async fetchInstitutionalInvestors(
    symbol: string,
    startDate: string,
  ): Promise<any[]> {
    this.logger.log(`抓取 ${symbol} 三大法人 (起始: ${startDate})`);

    try {
      const params = {
        dataset: 'TaiwanStockInstitutionalInvestorsBuySell',  // 正確端點
        data_id: symbol,
        start_date: startDate,
      };

      const response = await this.retryRequest(params);
      const data = response.data.data || [];
      
      this.logger.log(`✅ 成功抓取 ${symbol} 三大法人 ${data.length} 筆`);
      return data;
    } catch (error) {
      this.logger.error(`❌ 抓取 ${symbol} 三大法人失敗: ${error.message}`);
      throw error;
    }
  }

  /**
   * 抓取股價資料 (備援用)
   * Dataset: TaiwanStockPrice
   * 
   * @param symbol 股票代碼
   * @param startDate 開始日期 (YYYY-MM-DD)
   * @returns 股價資料陣列
   */
  async fetchStockPrice(
    symbol: string,
    startDate: string,
  ): Promise<any[]> {
    this.logger.log(`抓取 ${symbol} 股價 (起始: ${startDate})`);

    try {
      const params = {
        dataset: 'TaiwanStockPrice',
        data_id: symbol,
        start_date: startDate,
      };

      const response = await this.retryRequest(params);
      const data = response.data.data || [];
      
      this.logger.log(`✅ 成功抓取 ${symbol} 股價 ${data.length} 筆`);
      return data;
    } catch (error) {
      this.logger.error(`❌ 抓取 ${symbol} 股價失敗: ${error.message}`);
      throw error;
    }
  }

  /**
   * 批次抓取多檔股票財報
   * 
   * @param symbols 股票代碼陣列
   * @param startDate 開始日期
   * @returns 所有股票財報資料
   */
  async batchFetchFinancialStatements(
    symbols: string[],
    startDate: string = '2023-01-01',
  ): Promise<Map<string, any[]>> {
    this.logger.log(`批次抓取 ${symbols.length} 檔股票財報`);

    const results = new Map<string, any[]>();
    
    for (const symbol of symbols) {
      try {
        const data = await this.fetchFinancialStatement(symbol, startDate);
        results.set(symbol, data);
        
        // 延遲避免 API 限流
        await this.sleep(this.delay);
      } catch (error) {
        this.logger.warn(`跳過 ${symbol}: ${error.message}`);
        results.set(symbol, []);
      }
    }

    this.logger.log(`✅ 批次抓取完成: 成功 ${results.size}/${symbols.length}`);
    return results;
  }

  /**
   * 批次抓取月營收
   */
  async batchFetchMonthlyRevenues(
    symbols: string[],
    startDate: string = '2024-01-01',
  ): Promise<Map<string, any[]>> {
    this.logger.log(`批次抓取 ${symbols.length} 檔股票月營收`);

    const results = new Map<string, any[]>();
    
    for (const symbol of symbols) {
      try {
        const data = await this.fetchMonthlyRevenue(symbol, startDate);
        results.set(symbol, data);
        await this.sleep(this.delay);
      } catch (error) {
        this.logger.warn(`跳過 ${symbol}: ${error.message}`);
        results.set(symbol, []);
      }
    }

    this.logger.log(`✅ 批次抓取完成: 成功 ${results.size}/${symbols.length}`);
    return results;
  }

  /**
   * 重試請求機制
   */
  private async retryRequest(params: any): Promise<any> {
    let lastError: Error;
    
    for (let attempt = 1; attempt <= this.retryTimes; attempt++) {
      try {
        const response = await this.axiosInstance.get(this.baseUrl, { params });
        
        // 檢查回應狀態
        if (response.data.status !== 200) {
          throw new Error(`API 錯誤: ${response.data.msg || 'Unknown error'}`);
        }
        
        return response;
      } catch (error) {
        lastError = error;
        this.logger.warn(`請求失敗 (嘗試 ${attempt}/${this.retryTimes}): ${error.message}`);
        
        if (attempt < this.retryTimes) {
          await this.sleep(this.delay * attempt);
        }
      }
    }
    
    throw lastError;
  }

  /**
   * 延遲函數
   */
  private sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  /**
   * 轉換財報資料為標準格式
   * 
   * FinMind 回傳格式:
   * {
   *   date: "2024-11-14",
   *   stock_id: "2330",
   *   type: "綜合損益表",
   *   value: 868531628
   * }
   */
  transformFinancialData(rawData: any[]): any {
    const result = {
      incomeStatement: {},
      balanceSheet: {},
      cashFlow: {},
    };

    // 按類型分組
    const grouped = rawData.reduce((acc, item) => {
      const type = item.type || '';
      if (!acc[type]) acc[type] = [];
      acc[type].push(item);
      return acc;
    }, {});

    // TODO: 實作詳細的資料轉換邏輯
    // 這需要根據 FinMind 的實際欄位名稱進行對應

    return result;
  }
}
