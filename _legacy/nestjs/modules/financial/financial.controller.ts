import { Controller, Get, Param, Query } from '@nestjs/common';
import { ApiTags, ApiOperation, ApiResponse, ApiParam } from '@nestjs/swagger';
import { FinancialService } from './financial.service';
import {
  QueryFinancialDto,
  FinancialTrendDto,
  FinancialRankingDto,
  CompareCompaniesDto,
} from './dto/query-financial.dto';
import { FinancialReport } from './schemas/financial-report.schema';

@ApiTags('financial-reports')
@Controller('financial')
export class FinancialController {
  constructor(private readonly financialService: FinancialService) {}

  /**
   * 取得單一公司最新財報
   * 參考 goodinfo 個股財報頁面
   */
  @Get(':symbol')
  @ApiOperation({ summary: '取得單一公司最新財報' })
  @ApiParam({ name: 'symbol', description: '股票代碼', example: '2330' })
  @ApiResponse({ status: 200, description: '成功取得財報' })
  async getLatest(@Param('symbol') symbol: string): Promise<FinancialReport> {
    return this.financialService.getLatest(symbol);
  }

  /**
   * 取得歷史財報（多期）
   */
  @Get(':symbol/history')
  @ApiOperation({ summary: '取得歷史財報（多期）' })
  @ApiParam({ name: 'symbol', description: '股票代碼', example: '2330' })
  async getHistory(
    @Param('symbol') symbol: string,
    @Query() query: QueryFinancialDto,
  ): Promise<FinancialReport[]> {
    return this.financialService.getHistory(
      symbol,
      query.limit,
      query.reportType,
    );
  }

  /**
   * 取得財報趨勢（指定年度範圍）
   * 用於繪製財報趨勢圖
   */
  @Get(':symbol/trend')
  @ApiOperation({ summary: '取得財報趨勢（指定年度範圍）' })
  @ApiParam({ name: 'symbol', description: '股票代碼', example: '2330' })
  async getTrend(
    @Param('symbol') symbol: string,
    @Query() query: FinancialTrendDto,
  ): Promise<FinancialReport[]> {
    return this.financialService.getTrend(
      symbol,
      query.startYear,
      query.endYear,
      query.reportType,
    );
  }

  /**
   * 取得 EPS 趨勢
   */
  @Get(':symbol/eps-trend')
  @ApiOperation({ summary: '取得 EPS 趨勢' })
  @ApiParam({ name: 'symbol', description: '股票代碼', example: '2330' })
  async getEPSTrend(
    @Param('symbol') symbol: string,
    @Query('limit') limit?: number,
  ): Promise<any[]> {
    return this.financialService.getEPSTrend(symbol, limit || 8);
  }

  /**
   * 取得 ROE 趨勢
   */
  @Get(':symbol/roe-trend')
  @ApiOperation({ summary: '取得 ROE 趨勢' })
  @ApiParam({ name: 'symbol', description: '股票代碼', example: '2330' })
  async getROETrend(
    @Param('symbol') symbol: string,
    @Query('limit') limit?: number,
  ): Promise<any[]> {
    return this.financialService.getROETrend(symbol, limit || 8);
  }

  /**
   * 取得財務健康評分
   * 參考 goodinfo 評分機制
   */
  @Get(':symbol/score')
  @ApiOperation({ summary: '取得財務健康評分' })
  @ApiParam({ name: 'symbol', description: '股票代碼', example: '2330' })
  async getFinancialScore(@Param('symbol') symbol: string): Promise<any> {
    return this.financialService.getFinancialScore(symbol);
  }

  /**
   * 取得指定年度與期間的財報
   */
  @Get(':symbol/:year/:period')
  @ApiOperation({ summary: '取得指定年度與期間的財報' })
  @ApiParam({ name: 'symbol', description: '股票代碼', example: '2330' })
  @ApiParam({ name: 'year', description: '會計年度', example: 2024 })
  @ApiParam({ name: 'period', description: '會計期間', example: 'Q4' })
  async getByPeriod(
    @Param('symbol') symbol: string,
    @Param('year') year: number,
    @Param('period') period: string,
  ): Promise<FinancialReport> {
    return this.financialService.getByPeriod(symbol, Number(year), period);
  }

  /**
   * 財務比率排行
   * 參考 goodinfo 產業比較功能
   */
  @Get('ranking/:sortBy')
  @ApiOperation({ summary: '財務比率排行' })
  @ApiParam({
    name: 'sortBy',
    description: '排序指標',
    example: 'roe',
    enum: [
      'roe',
      'roa',
      'eps',
      'netMargin',
      'grossMargin',
      'operatingMargin',
      'debtRatio',
    ],
  })
  async getRanking(
    @Param('sortBy') sortBy: string,
    @Query() query: FinancialRankingDto,
  ): Promise<FinancialReport[]> {
    const year = query.year || new Date().getFullYear();
    const period = query.period || 'Annual';

    return this.financialService.getRanking(
      year,
      period,
      sortBy,
      query.limit,
    );
  }

  /**
   * 多公司比較
   * 參考 goodinfo 同業比較
   */
  @Get('compare/companies')
  @ApiOperation({ summary: '多公司財報比較' })
  async compareCompanies(
    @Query() query: CompareCompaniesDto,
  ): Promise<FinancialReport[]> {
    return this.financialService.compareCompanies(
      query.symbols,
      query.year,
      query.period,
    );
  }

  /**
   * 杜邦分析 - ROE 拆解
   * 
   * 三步驟拆解：ROE = 淨利率 × 資產週轉率 × 權益乘數
   * - 淨利率：獲利能力指標
   * - 資產週轉率：經營效率指標
   * - 權益乘數：財務槓桿指標
   * 
   * 參考 goodinfo 杜邦分析頁面
   */
  @Get(':symbol/dupont')
  @ApiOperation({ 
    summary: '杜邦分析 - ROE 拆解',
    description: '分析 ROE 組成：淨利率、資產週轉率、權益乘數。提供優勢/劣勢/建議'
  })
  @ApiParam({ name: 'symbol', description: '股票代碼', example: '2330' })
  @ApiResponse({ 
    status: 200, 
    description: '成功取得杜邦分析結果',
    schema: {
      example: {
        symbol: '2330',
        companyName: '台積電',
        fiscalYear: 2023,
        fiscalPeriod: 'Q4',
        roe: 25.6,
        netMargin: 38.2,
        assetTurnover: 0.55,
        equityMultiplier: 1.22,
        threeStepDecomposition: {
          profitability: 38.2,
          efficiency: 0.55,
          leverage: 1.22
        },
        fiveStepDecomposition: {
          grossMargin: 54.3,
          operatingMargin: 42.1,
          netMargin: 38.2,
          assetTurnover: 0.55,
          equityMultiplier: 1.22
        },
        analysis: {
          strengths: ['淨利率優異 (>20%)，獲利能力強'],
          weaknesses: [],
          recommendations: []
        }
      }
    }
  })
  async getDuPontAnalysis(
    @Param('symbol') symbol: string,
    @Query('year') year?: number,
    @Query('period') period?: string,
  ): Promise<any> {
    return this.financialService.calculateDuPont(symbol, year, period);
  }
}
