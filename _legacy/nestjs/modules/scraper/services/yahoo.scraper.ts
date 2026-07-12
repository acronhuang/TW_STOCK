import { Injectable, Logger } from '@nestjs/common';
import yahooFinance from 'yahoo-finance2';

// 手動定義 Yahoo Finance 回傳的資料結構介面
interface YahooQuoteSummary {
  incomeStatementHistoryQuarterly?: {
    incomeStatementHistory: any[];
  };
  balanceSheetHistoryQuarterly?: {
    balanceSheetStatements: any[];
  };
  cashflowStatementHistoryQuarterly?: {
    cashflowStatements: any[];
  };
  financialData?: any;
  defaultKeyStatistics?: any;
}

/**
 * Yahoo Finance 資料爬蟲服務
 * 
 * 資料來源: Yahoo Finance API
 * 特點: 
 * - 官方 API，穩定可靠
 * - 全球股市資料覆蓋
 * - 無 API 呼叫限制
 * 
 * 台股代碼格式: {股票代號}.TW (例如: 2330.TW)
 */
@Injectable()
export class YahooScraperService {
  private readonly logger = new Logger(YahooScraperService.name);

  /**
   * 抓取公司財務報表
   * @param symbol 股票代碼 (不含 .TW)
   * @returns 財務報表資料
   */
  async fetchFinancialStatements(symbol: string): Promise<any> {
    try {
      const yahooSymbol = `${symbol}.TW`;
      this.logger.log(`抓取 Yahoo Finance 財報: ${yahooSymbol}`);

      const quoteSummary: YahooQuoteSummary = await yahooFinance.quoteSummary(yahooSymbol, {
        modules: [
          'incomeStatementHistory',
          'incomeStatementHistoryQuarterly',
          'balanceSheetHistory',
          'balanceSheetHistoryQuarterly',
          'cashflowStatementHistory',
          'cashflowStatementHistoryQuarterly',
          'financialData',
          'defaultKeyStatistics',
        ],
      });

      return {
        symbol,
        yahooSymbol,
        incomeStatementQuarterly: quoteSummary.incomeStatementHistoryQuarterly?.incomeStatementHistory || [],
        balanceSheetQuarterly: quoteSummary.balanceSheetHistoryQuarterly?.balanceSheetStatements || [],
        cashflowQuarterly: quoteSummary.cashflowStatementHistoryQuarterly?.cashflowStatements || [],
        financialData: quoteSummary.financialData || {},
        keyStatistics: quoteSummary.defaultKeyStatistics || {},
      };
    } catch (error) {
      this.logger.error(`Yahoo Finance 抓取失敗: ${symbol}`, error.stack);
      throw new Error(`Yahoo Finance 抓取失敗: ${error.message}`);
    }
  }

  /**
   * 抓取單季財報資料
   * @param symbol 股票代碼
   * @param year 年度 (西元年)
   * @param quarter 季度 (1-4)
   * @returns 單季財報資料
   */
  async fetchQuarterlyReport(symbol: string, year: number, quarter: number): Promise<any> {
    try {
      const data = await this.fetchFinancialStatements(symbol);

      // Yahoo Finance 提供最近 4 季的季報
      const targetDate = this.getQuarterEndDate(year, quarter);

      // 從季報列表中找到對應季度
      const incomeStatement = this.findReportByDate(data.incomeStatementQuarterly, targetDate);
      const balanceSheet = this.findReportByDate(data.balanceSheetQuarterly, targetDate);
      const cashflow = this.findReportByDate(data.cashflowQuarterly, targetDate);

      if (!incomeStatement && !balanceSheet && !cashflow) {
        throw new Error(`找不到 ${year}Q${quarter} 的財報資料`);
      }

      return {
        symbol,
        year,
        quarter,
        incomeStatement: incomeStatement || {},
        balanceSheet: balanceSheet || {},
        cashflow: cashflow || {},
        reportDate: targetDate,
      };
    } catch (error) {
      this.logger.error(`Yahoo Finance 季報抓取失敗: ${symbol} ${year}Q${quarter}`, error.stack);
      throw error;
    }
  }

  /**
   * 取得季度結束日期
   * @param year 年度
   * @param quarter 季度
   * @returns 季度結束日期
   */
  private getQuarterEndDate(year: number, quarter: number): Date {
    const month = quarter * 3; // Q1=3, Q2=6, Q3=9, Q4=12
    const lastDay = new Date(year, month, 0).getDate(); // 該月最後一天
    return new Date(year, month - 1, lastDay);
  }

  /**
   * 從報表列表中找到最接近指定日期的報表
   * @param reports 報表列表
   * @param targetDate 目標日期
   * @returns 找到的報表
   */
  private findReportByDate(reports: any[], targetDate: Date): any {
    if (!reports || reports.length === 0) return null;

    // 找到日期最接近的報表
    let closestReport = null;
    let minDiff = Infinity;

    for (const report of reports) {
      if (!report.endDate) continue;

      const reportDate = new Date(report.endDate);
      const diff = Math.abs(reportDate.getTime() - targetDate.getTime());

      if (diff < minDiff) {
        minDiff = diff;
        closestReport = report;
      }
    }

    // 如果日期差距超過 45 天，視為找不到
    const maxDiffDays = 45;
    if (minDiff > maxDiffDays * 24 * 60 * 60 * 1000) {
      return null;
    }

    return closestReport;
  }

  /**
   * 檢查股票代碼是否存在
   * @param symbol 股票代碼
   * @returns 是否存在
   */
  async checkSymbolExists(symbol: string): Promise<boolean> {
    try {
      const yahooSymbol = `${symbol}.TW`;
      const quote = await yahooFinance.quote(yahooSymbol);
      return !!quote;
    } catch (error) {
      return false;
    }
  }

  /**
   * 測試連線
   * @returns 測試結果
   */
  async testConnection(): Promise<{ success: boolean; message: string }> {
    try {
      // 測試抓取台積電資料
      await this.fetchFinancialStatements('2330');
      return { success: true, message: 'Yahoo Finance 連線正常' };
    } catch (error) {
      return { success: false, message: `連線失敗: ${error.message}` };
    }
  }
}
