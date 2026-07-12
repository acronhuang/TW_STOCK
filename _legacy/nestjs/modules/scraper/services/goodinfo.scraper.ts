import { Injectable, Logger } from '@nestjs/common';
import axios from 'axios';
import * as cheerio from 'cheerio';

/**
 * Goodinfo 資料爬蟲服務
 * 
 * 資料來源: https://goodinfo.tw
 * 特點:
 * - 完整的台股財報資料
 * - 多年歷史資料
 * - 使用 Session Cookie 維持連線
 * 
 * 注意: Goodinfo 使用 ASP.NET ViewState，需要先訪問首頁取得 Cookie
 */
@Injectable()
export class GoodinfoScraperService {
  private readonly logger = new Logger(GoodinfoScraperService.name);
  private readonly baseUrl = 'https://goodinfo.tw/tw';
  private sessionCookies: string = '';

  private readonly headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Referer': 'https://goodinfo.tw/tw/index.asp',
  };

  /**
   * 初始化 Session (取得 Cookie)
   */
  private async initSession(): Promise<void> {
    if (this.sessionCookies) return;

    try {
      this.logger.log('初始化 Goodinfo Session...');
      const response = await axios.get(`${this.baseUrl}/index.asp`, {
        headers: this.headers,
        timeout: 10000,
      });

      // 取得 Set-Cookie
      const cookies = response.headers['set-cookie'];
      if (cookies) {
        this.sessionCookies = cookies.map(c => c.split(';')[0]).join('; ');
        this.logger.log('✅ Goodinfo Session 初始化完成');
      }
    } catch (error) {
      this.logger.warn(`Goodinfo Session 初始化失敗: ${error.message}`);
    }
  }

  /**
   * 抓取公司財務報表
   * @param symbol 股票代碼
   * @returns 財務報表資料
   */
  async fetchFinancialStatements(symbol: string): Promise<any> {
    try {
      this.logger.log(`抓取 Goodinfo 財報: ${symbol}`);

      // 初始化 Session
      await this.initSession();

      // Goodinfo 綜合損益表頁面 (包含多季度資料)
      const url = `${this.baseUrl}/StockFinDetail.asp?STOCK_ID=${symbol}`;

      const requestHeaders = {
        ...this.headers,
        ...(this.sessionCookies && { 'Cookie': this.sessionCookies }),
      };

      // 第一次請求 - 可能會遇到 meta refresh
      let response = await axios.get(url, {
        headers: requestHeaders,
        timeout: 15000,
        maxRedirects: 0, // 禁止自動重定向
        validateStatus: (status) => status < 400, // 接受 3xx 狀態碼
      });

      let html = response.data;

      // 檢查是否有 meta refresh
      if (html.includes('META_REFRESH')) {
        this.logger.log(`${symbol}: 檢測到 meta refresh，進行第二次請求...`);
        
        // 等待 1 秒後再次請求
        await this.delay(1000);
        
        // 第二次請求 - 帶上 META_REFRESH 參數
        const urlWithRefresh = `${url}&META_REFRESH=`;
        response = await axios.get(urlWithRefresh, {
          headers: requestHeaders,
          timeout: 15000,
        });
        
        html = response.data;
      }

      // 更新 Cookie
      const newCookies = response.headers['set-cookie'];
      if (newCookies) {
        this.sessionCookies = newCookies.map(c => c.split(';')[0]).join('; ');
      }

      // 解析財報表格
      const financialData = this.parseFinancialTable(html, symbol);

      return {
        symbol,
        source: 'Goodinfo',
        url,
        data: financialData,
        fetchTime: new Date(),
      };
    } catch (error) {
      this.logger.error(`Goodinfo 抓取失敗: ${symbol}`, error.stack);
      throw new Error(`Goodinfo 抓取失敗: ${error.message}`);
    }
  }

  /**
   * 解析財報表格
   * @param html HTML 字串
   * @param symbol 股票代碼
   * @returns 解析後的財報資料
   */
  private parseFinancialTable(html: string, symbol: string): any {
    const $ = cheerio.load(html);
    const result = {};

    try {
      // Goodinfo 的財報頁面包含多個表格
      // 嘗試找到包含季度資料的表格
      
      // 方法1: 找 id="txtFinDetailData" 的表格
      let $table = $('#txtFinDetailData');
      
      // 方法2: 找 class 包含 "solid" 的表格
      if ($table.length === 0) {
        $table = $('table[class*="solid"]').first();
      }
      
      // 方法3: 找所有大表格
      if ($table.length === 0) {
        $table = $('table').filter((i, el) => {
          return $(el).find('tr').length > 5; // 至少5行的表格
        }).first();
      }

      if ($table.length === 0) {
        this.logger.warn(`${symbol}: 找不到財報表格`);
        return result;
      }

      // 取得表頭 (季度/年度)
      const headers: string[] = [];
      $table.find('tr').first().find('th, td').each((i, cell) => {
        const text = $(cell).text().trim();
        // 尋找包含年度和季度的標題，例如: "113/1Q", "112/4Q"
        if (text && (text.includes('Q') || text.includes('年') || text.includes('/'))) {
          headers.push(text);
        }
      });

      if (headers.length === 0) {
        this.logger.warn(`${symbol}: 找不到季度標題`);
        return result;
      }

      this.logger.log(`${symbol}: 找到 ${headers.length} 個季度: ${headers.slice(0, 5).join(', ')}`);

      // 解析資料列
      $table.find('tr').each((rowIndex, row) => {
        if (rowIndex === 0) return; // 跳過表頭

        const $row = $(row);
        const cells = $row.find('td');
        if (cells.length === 0) return;

        const itemName = $(cells[0]).text().trim();
        if (!itemName) return;

        // 取得每季/年的數值
        cells.each((cellIndex, cell) => {
          if (cellIndex === 0) return; // 跳過項目名稱欄

          const headerIndex = cellIndex - 1;
          if (headerIndex >= headers.length) return;

          const period = headers[headerIndex];
          const value = $(cell).text().trim();

          if (!result[period]) {
            result[period] = {};
          }

          // 轉換數值
          const numValue = this.parseNumber(value);
          result[period][itemName] = numValue;
        });
      });

      return result;
    } catch (error) {
      this.logger.error(`解析財報表格失敗: ${symbol}`, error.stack);
      return result;
    }
  }

  /**
   * 解析數值字串
   * @param value 數值字串
   * @returns 數值
   */
  private parseNumber(value: string): number | string | null {
    if (!value || value === '-' || value === 'N/A' || value === '') {
      return null;
    }

    // 移除逗號、空格、千分位
    const cleaned = value.replace(/,/g, '').replace(/\s/g, '');

    // 檢查是否為數值
    const num = parseFloat(cleaned);
    if (isNaN(num)) {
      return value; // 保留原始字串
    }

    return num;
  }

  /**
   * 抓取單季財報資料
   * @param symbol 股票代碼
   * @param year 年度 (民國年)
   * @param quarter 季度 (1-4)
   * @returns 單季財報資料
   */
  async fetchQuarterlyReport(symbol: string, year: number, quarter: number): Promise<any> {
    try {
      const data = await this.fetchFinancialStatements(symbol);

      // 從抓取的資料中找出指定季度
      // Goodinfo 可能使用格式: "113Q1", "113/1Q", "113年第1季" 等
      const possibleKeys = [
        `${year}Q${quarter}`,
        `${year}/${quarter}Q`,
        `${year}年Q${quarter}`,
        `${year}年第${quarter}季`,
      ];

      let quarterData = null;
      for (const key of possibleKeys) {
        if (data.data[key]) {
          quarterData = data.data[key];
          break;
        }
      }

      // 如果找不到精確匹配，嘗試模糊匹配
      if (!quarterData) {
        for (const [key, value] of Object.entries(data.data)) {
          if (key.includes(`${year}`) && key.includes(`${quarter}`)) {
            quarterData = value;
            this.logger.log(`使用模糊匹配找到季度資料: ${key}`);
            break;
          }
        }
      }

      if (!quarterData) {
        const availableKeys = Object.keys(data.data).slice(0, 5).join(', ');
        throw new Error(
          `找不到 ${year}Q${quarter} 的財報資料。可用的季度: ${availableKeys}...`
        );
      }

      return {
        symbol,
        year,
        quarter,
        ...quarterData,
        reportDate: new Date(year + 1911, quarter * 3 - 1, 1), // 轉換為西元年
      };
    } catch (error) {
      this.logger.error(`Goodinfo 季報抓取失敗: ${symbol} ${year}Q${quarter}`, error.stack);
      throw error;
    }
  }

  /**
   * 測試連線
   * @returns 測試結果
   */
  async testConnection(): Promise<{ success: boolean; message: string }> {
    try {
      // 測試抓取台積電資料
      const data = await this.fetchFinancialStatements('2330');
      
      const quarterCount = Object.keys(data.data).length;
      if (quarterCount > 0) {
        const quarters = Object.keys(data.data).slice(0, 5).join(', ');
        return { 
          success: true, 
          message: `Goodinfo 連線正常，抓取到 ${quarterCount} 個季度資料。範例: ${quarters}` 
        };
      } else {
        return { 
          success: false, 
          message: 'Goodinfo 回應正常但無資料，可能需要處理驗證碼' 
        };
      }
    } catch (error) {
      return { 
        success: false, 
        message: `連線失敗: ${error.message}` 
      };
    }
  }

  /**
   * 延遲執行 (避免被 ban)
   * @param ms 延遲毫秒數
   */
  async delay(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }
}
