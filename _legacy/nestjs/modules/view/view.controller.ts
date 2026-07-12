import { Controller, Get, Param, Render, Query } from '@nestjs/common';
import { FinancialService } from '../financial/financial.service';
import { TickerService } from '../ticker/ticker.service';

/**
 * 前端視覺化頁面 Controller
 * 
 * 提供財報與股價的視覺化展示頁面：
 * 1. 財報表格（損益表、資產負債表、現金流量表）
 * 2. 杜邦分析瀑布圖
 * 3. EPS/ROE 趨勢圖
 * 4. 股價 K 線圖
 * 
 * 參考設計：goodinfo.tw
 */
@Controller('view')
export class ViewController {
  constructor(
    private readonly financialService: FinancialService,
    private readonly tickerService: TickerService,
  ) {}

  /**
   * 首頁 - 股票查詢頁面
   */
  @Get()
  @Render('index')
  async index() {
    return {
      title: '台股智能分析系統',
      description: '提供完整的台股財報分析、技術分析、杜邦分析等功能',
    };
  }

  /**
   * 財報分析頁面
   * 顯示完整的財報三表、財務比率、杜邦分析
   * 
   * @param symbol 股票代碼
   * @param year 會計年度（可選）
   * @param period 會計期間（可選）
   */
  @Get('financial/:symbol')
  @Render('financial-report')
  async financialReport(
    @Param('symbol') symbol: string,
    @Query('year') year?: number,
    @Query('period') period?: string,
  ) {
    try {
      // 取得財報資料
      const report = year && period
        ? await this.financialService.getByPeriod(symbol, year, period)
        : await this.financialService.getLatest(symbol);

      // 取得杜邦分析
      const dupontAnalysis = await this.financialService.calculateDuPont(
        symbol,
        year,
        period,
      );

      // 取得 EPS 趨勢
      const epsTrend = await this.financialService.getEPSTrend(symbol, 8);

      // 取得 ROE 趨勢
      const roeTrend = await this.financialService.getROETrend(symbol, 8);

      return {
        symbol,
        report,
        dupontAnalysis,
        epsTrend,
        roeTrend,
        title: `${report.companyName} (${symbol}) - 財報分析`,
      };
    } catch (error) {
      return {
        error: error.message || '無法取得財報資料',
        symbol,
        title: `${symbol} - 財報分析`,
      };
    }
  }

  /**
   * 股價走勢頁面
   * 顯示 K 線圖、成交量、技術指標
   * 
   * @param symbol 股票代碼
   * @param days 顯示天數（預設 90 天）
   */
  @Get('chart/:symbol')
  @Render('stock-chart')
  async stockChart(
    @Param('symbol') symbol: string,
    @Query('days') days?: number,
  ) {
    try {
      const limit = days || 90;

      // 取得歷史股價（使用 days 參數）
      const history = await this.tickerService.getHistory(
        symbol,
        undefined,
        undefined,
        limit,
      );

      // 取得最新股價
      const latest = await this.tickerService.getLatest(symbol);

      return {
        symbol,
        companyName: latest?.name || symbol,
        latest,
        history,
        days: limit,
        title: `${latest?.name || symbol} (${symbol}) - 股價走勢`,
      };
    } catch (error) {
      return {
        error: error.message || '無法取得股價資料',
        symbol,
        title: `${symbol} - 股價走勢`,
      };
    }
  }

  /**
   * 杜邦分析頁面
   * 專注於 ROE 拆解分析與瀑布圖
   * 
   * @param symbol 股票代碼
   */
  @Get('dupont/:symbol')
  @Render('dupont-analysis')
  async dupontAnalysis(@Param('symbol') symbol: string) {
    try {
      // 取得杜邦分析
      const analysis = await this.financialService.calculateDuPont(symbol);

      // 取得近 8 季 ROE 趨勢（用於比較）
      const roeTrend = await this.financialService.getROETrend(symbol, 8);

      return {
        symbol,
        companyName: analysis.companyName,
        analysis,
        roeTrend,
        title: `${analysis.companyName} (${symbol}) - 杜邦分析`,
      };
    } catch (error) {
      return {
        error: error.message || '無法取得杜邦分析資料',
        symbol,
        title: `${symbol} - 杜邦分析`,
      };
    }
  }

  /**
   * 綜合儀表板
   * 一頁顯示所有重要資訊
   * 
   * @param symbol 股票代碼
   */
  @Get('dashboard/:symbol')
  @Render('dashboard')
  async dashboard(@Param('symbol') symbol: string) {
    try {
      // 並行取得所有資料
      const [
        latestReport,
        latestStock,
        dupontAnalysis,
        epsTrend,
        roeTrend,
        stockHistory,
      ] = await Promise.all([
        this.financialService.getLatest(symbol),
        this.tickerService.getLatest(symbol),
        this.financialService.calculateDuPont(symbol),
        this.financialService.getEPSTrend(symbol, 8),
        this.financialService.getROETrend(symbol, 8),
        this.tickerService.getHistory(symbol, undefined, undefined, 60),
      ]);

      return {
        symbol,
        companyName: latestReport.companyName,
        latestReport,
        latestStock,
        dupontAnalysis,
        epsTrend,
        roeTrend,
        stockHistory,
        title: `${latestReport.companyName} (${symbol}) - 綜合儀表板`,
      };
    } catch (error) {
      return {
        error: error.message || '無法取得資料',
        symbol,
        title: `${symbol} - 綜合儀表板`,
      };
    }
  }
}
