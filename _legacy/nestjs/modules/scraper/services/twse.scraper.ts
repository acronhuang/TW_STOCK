import { Injectable, Logger } from '@nestjs/common';
import axios, { AxiosInstance } from 'axios';

/**
 * 台灣證券交易所 (TWSE) Open Data 爬蟲服務
 * 資料來源: https://openapi.twse.com.tw
 * 
 * 功能:
 * - 抓取每日全部股票交易資料
 * - 抓取個別股票歷史資料
 * - 抓取三大法人買賣超
 * - 資料格式為標準 JSON，無需解析 HTML
 * 
 * API 文檔: https://openapi.twse.com.tw/
 */
@Injectable()
export class TWSEScraperService {
  private readonly logger = new Logger(TWSEScraperService.name);
  private readonly axiosInstance: AxiosInstance;
  private readonly baseUrl = 'https://openapi.twse.com.tw/v1';
  
  // 爬蟲設定
  private readonly timeout: number;
  private readonly retryTimes: number;
  private readonly delay: number;

  constructor() {
    // 從環境變數讀取配置
    this.timeout = parseInt(process.env.SCRAPER_TIMEOUT || '30000');
    this.retryTimes = parseInt(process.env.SCRAPER_RETRY_TIMES || '3');
    this.delay = parseInt(process.env.SCRAPER_DELAY || '1000');

    // 建立 axios 實例
    this.axiosInstance = axios.create({
      timeout: this.timeout,
      headers: {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept': 'application/json',
      },
    });
  }

  /**
   * 抓取今日所有股票交易資料
   * API: /exchangeReport/STOCK_DAY_ALL
   * 
   * @returns 所有股票當日交易資料陣列
   */
  async fetchDailyAllStocks(): Promise<any[]> {
    this.logger.log('開始抓取今日所有股票交易資料');

    try {
      const url = `${this.baseUrl}/exchangeReport/STOCK_DAY_ALL`;
      const response = await this.retryRequest(url);
      
      const data = response.data;
      this.logger.log(`✅ 成功抓取 ${data.length} 筆股票資料`);
      
      // 轉換資料格式
      return data.map((item: any) => this.transformDailyData(item));
    } catch (error) {
      this.logger.error(`❌ 抓取失敗: ${error.message}`);
      throw error;
    }
  }

  /**
   * 抓取指定日期的所有股票資料
   * API: /exchangeReport/STOCK_DAY_ALL
   * 
   * 注意: TWSE API 只提供最新一天的資料，無法查詢歷史日期
   * 
   * @param date 日期 (YYYYMMDD 格式)
   * @returns 所有股票交易資料陣列
   */
  async fetchDailyAllStocksByDate(date: string): Promise<any[]> {
    this.logger.log(`抓取 ${date} 的所有股票交易資料`);
    
    // TWSE Open Data API 只提供最新資料，無法指定日期
    // 這裡直接調用 fetchDailyAllStocks()
    const result = await this.fetchDailyAllStocks();
    
    this.logger.warn('注意: TWSE Open Data API 只提供最新日期資料');
    return result;
  }

  /**
   * 抓取單一股票資料（從全部股票資料中篩選）
   * 
   * @param symbol 股票代碼
   * @returns 單一股票交易資料
   */
  async fetchSingleStock(symbol: string): Promise<any | null> {
    this.logger.log(`抓取股票 ${symbol} 資料`);

    try {
      const allStocks = await this.fetchDailyAllStocks();
      const stock = allStocks.find((item) => item.symbol === symbol);
      
      if (!stock) {
        this.logger.warn(`找不到股票 ${symbol}`);
        return null;
      }
      
      this.logger.log(`✅ 成功抓取 ${symbol} 資料`);
      return stock;
    } catch (error) {
      this.logger.error(`❌ 抓取 ${symbol} 失敗: ${error.message}`);
      throw error;
    }
  }

  /**
   * 抓取三大法人買賣超
   * API: /fund/T86
   * 
   * @returns 三大法人買賣超資料
   */
  async fetchInstitutionalTrading(): Promise<any[]> {
    this.logger.log('開始抓取三大法人買賣超資料');

    try {
      const url = `${this.baseUrl}/fund/T86`;
      const response = await this.retryRequest(url);
      
      const data = response.data;
      this.logger.log(`✅ 成功抓取 ${data.length} 筆三大法人資料`);
      
      return data.map((item: any) => this.transformInstitutionalData(item));
    } catch (error) {
      this.logger.error(`❌ 抓取三大法人資料失敗: ${error.message}`);
      throw error;
    }
  }

  /**
   * 重試請求（錯誤處理）
   */
  private async retryRequest(url: string): Promise<any> {
    let lastError: Error;
    
    for (let attempt = 1; attempt <= this.retryTimes; attempt++) {
      try {
        const response = await this.axiosInstance.get(url);
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
   * 轉換每日股價資料格式
   * 
   * TWSE 原始格式:
   * {
   *   "Date": "1141219",          // 民國年月日
   *   "Code": "2330",             // 股票代碼
   *   "Name": "台積電",           // 股票名稱
   *   "TradeVolume": "81027467",  // 成交股數
   *   "TradeValue": "5067295440", // 成交金額
   *   "OpeningPrice": "62.40",    // 開盤價
   *   "HighestPrice": "62.75",    // 最高價
   *   "LowestPrice": "62.35",     // 最低價
   *   "ClosingPrice": "62.50",    // 收盤價
   *   "Change": "0.6000",         // 漲跌
   *   "Transaction": "41675"      // 成交筆數
   * }
   * 
   * 轉換為統一格式
   */
  private transformDailyData(raw: any): any {
    // 轉換民國年為西元年
    const rocDate = raw.Date; // 1141219
    const year = parseInt(rocDate.substring(0, 3)) + 1911;
    const month = rocDate.substring(3, 5);
    const day = rocDate.substring(5, 7);
    const date = new Date(`${year}-${month}-${day}`);

    // 轉換數值
    const parseNumber = (str: string): number => {
      if (!str || str === '' || str === '--') return 0;
      return parseFloat(str.replace(/,/g, ''));
    };

    return {
      symbol: raw.Code,
      name: raw.Name,
      date: date,
      open: parseNumber(raw.OpeningPrice),
      high: parseNumber(raw.HighestPrice),
      low: parseNumber(raw.LowestPrice),
      close: parseNumber(raw.ClosingPrice),
      volume: parseNumber(raw.TradeVolume),
      turnover: parseNumber(raw.TradeValue),
      change: parseNumber(raw.Change),
      changePercent: 0, // 需要計算
      transactions: parseNumber(raw.Transaction),
      
      // 原始資料保留
      rawDate: raw.Date,
      
      // 資料來源標記
      dataSource: 'TWSE_OpenData',
      scrapedAt: new Date(),
    };
  }

  /**
   * 轉換三大法人資料格式
   * 
   * TWSE 原始格式:
   * {
   *   "Code": "2330",
   *   "Name": "台積電",
   *   "ForeignInvestmentBuySell": "12345",  // 外資買賣超
   *   "InvestmentTrustBuySell": "678",      // 投信買賣超
   *   "DealersBuySell": "90",               // 自營商買賣超
   *   "TotalBuySell": "13113"               // 三大法人合計
   * }
   */
  private transformInstitutionalData(raw: any): any {
    const parseNumber = (str: string): number => {
      if (!str || str === '' || str === '--') return 0;
      return parseFloat(str.replace(/,/g, ''));
    };

    return {
      symbol: raw.Code,
      name: raw.Name,
      foreign: {
        buySell: parseNumber(raw.ForeignInvestmentBuySell || '0'),
      },
      trust: {
        buySell: parseNumber(raw.InvestmentTrustBuySell || '0'),
      },
      dealer: {
        buySell: parseNumber(raw.DealersBuySell || '0'),
      },
      total: {
        buySell: parseNumber(raw.TotalBuySell || '0'),
      },
      dataSource: 'TWSE_OpenData',
      scrapedAt: new Date(),
    };
  }

  /**
   * 延遲執行
   */
  private sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  /**
   * 取得服務狀態
   */
  getStatus(): any {
    return {
      service: 'TWSE Open Data Scraper',
      baseUrl: this.baseUrl,
      timeout: this.timeout,
      retryTimes: this.retryTimes,
      delay: this.delay,
      apiEndpoints: {
        dailyAll: `${this.baseUrl}/exchangeReport/STOCK_DAY_ALL`,
        institutional: `${this.baseUrl}/fund/T86`,
      },
    };
  }
}
