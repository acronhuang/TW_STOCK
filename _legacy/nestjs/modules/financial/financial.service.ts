import { Injectable, NotFoundException } from '@nestjs/common';
import { InjectModel } from '@nestjs/mongoose';
import { Model } from 'mongoose';
import {
  FinancialReport,
  FinancialReportDocument,
} from './schemas/financial-report.schema';
import { DateUtilService } from '@/common/utils/date-util.service';
import { CacheUtilService } from '@/common/utils/cache-util.service';

@Injectable()
export class FinancialService {
  constructor(
    @InjectModel(FinancialReport.name)
    private financialModel: Model<FinancialReportDocument>,
    private dateUtil: DateUtilService,
    private cacheUtil: CacheUtilService,
  ) {}

  /**
   * 取得單一公司最新財報
   */
  async getLatest(symbol: string): Promise<FinancialReport> {
    const cacheKey = `financial:${symbol}:latest`;

    return this.cacheUtil.getOrSet(
      cacheKey,
      async () => {
        const report = await this.financialModel
          .findOne({ symbol })
          .sort({ fiscalYear: -1, fiscalPeriod: -1 })
          .lean()
          .exec();

        if (!report) {
          throw new NotFoundException(`找不到 ${symbol} 的財報資料`);
        }

        return report;
      },
      300 * 1000, // 快取 5 分鐘
    );
  }

  /**
   * 取得指定年度與期間的財報
   */
  async getByPeriod(
    symbol: string,
    year: number,
    period: string,
  ): Promise<FinancialReport> {
    const cacheKey = `financial:${symbol}:${year}:${period}`;

    return this.cacheUtil.getOrSet(
      cacheKey,
      async () => {
        const report = await this.financialModel
          .findOne({ symbol, fiscalYear: year, fiscalPeriod: period })
          .lean()
          .exec();

        if (!report) {
          throw new NotFoundException(
            `找不到 ${symbol} 在 ${year} ${period} 的財報`,
          );
        }

        return report;
      },
      600 * 1000, // 快取 10 分鐘
    );
  }

  /**
   * 取得歷史財報（多期）
   * 參考 goodinfo 的財報趨勢圖
   */
  async getHistory(
    symbol: string,
    limit = 8,
    reportType?: 'quarterly' | 'annual',
  ): Promise<FinancialReport[]> {
    const query: any = { symbol };

    if (reportType) {
      query.reportType = reportType;
    }

    return this.financialModel
      .find(query)
      .sort({ fiscalYear: -1, fiscalPeriod: -1 })
      .limit(limit)
      .lean()
      .exec();
  }

  /**
   * 取得財報趨勢（指定年度範圍）
   */
  async getTrend(
    symbol: string,
    startYear: number,
    endYear: number,
    reportType: 'quarterly' | 'annual' = 'annual',
  ): Promise<FinancialReport[]> {
    const cacheKey = `financial:trend:${symbol}:${startYear}:${endYear}:${reportType}`;

    return this.cacheUtil.getOrSet(
      cacheKey,
      async () => {
        return this.financialModel
          .find({
            symbol,
            fiscalYear: { $gte: startYear, $lte: endYear },
            reportType,
          })
          .sort({ fiscalYear: 1, fiscalPeriod: 1 })
          .lean()
          .exec();
      },
      600 * 1000, // 10 分鐘
    );
  }

  /**
   * 財務比率排行
   * 參考 goodinfo 的產業財務比較
   */
  async getRanking(
    year: number,
    period: string,
    sortBy: string,
    limit = 20,
  ): Promise<FinancialReport[]> {
    const cacheKey = `financial:ranking:${year}:${period}:${sortBy}:${limit}`;

    return this.cacheUtil.getOrSet(
      cacheKey,
      async () => {
        // 根據不同指標構建排序
        const sortField = this.getSortField(sortBy);
        const sortOrder: any = {};
        sortOrder[sortField] = -1; // 降序

        return this.financialModel
          .find({
            fiscalYear: year,
            fiscalPeriod: period,
            [sortField]: { $exists: true, $ne: 0 },
          })
          .sort(sortOrder)
          .limit(limit)
          .lean()
          .exec();
      },
      300 * 1000, // 5 分鐘
    );
  }

  /**
   * 多公司比較
   * 參考 goodinfo 的同業比較功能
   */
  async compareCompanies(
    symbols: string[],
    year: number,
    period: string,
  ): Promise<FinancialReport[]> {
    return this.financialModel
      .find({
        symbol: { $in: symbols },
        fiscalYear: year,
        fiscalPeriod: period,
      })
      .sort({ symbol: 1 })
      .lean()
      .exec();
  }

  /**
   * 取得 EPS 趨勢（最近 N 期）
   */
  async getEPSTrend(symbol: string, limit = 8): Promise<any[]> {
    const reports = await this.getHistory(symbol, limit, 'quarterly');

    return reports.map((report) => ({
      year: report.fiscalYear,
      period: report.fiscalPeriod,
      eps: report.incomeStatement?.eps || 0,
      revenue: report.incomeStatement?.revenue || 0,
      netIncome: report.incomeStatement?.netIncome || 0,
    }));
  }

  /**
   * 取得 ROE 趨勢（最近 N 期）
   */
  async getROETrend(symbol: string, limit = 8): Promise<any[]> {
    const reports = await this.getHistory(symbol, limit);

    return reports.map((report) => ({
      year: report.fiscalYear,
      period: report.fiscalPeriod,
      roe: report.ratios?.roe || 0,
      roa: report.ratios?.roa || 0,
      netMargin: report.incomeStatement?.netMargin || 0,
    }));
  }

  /**
   * 計算財務健康分數（參考 goodinfo 評分邏輯）
   */
  async getFinancialScore(symbol: string): Promise<any> {
    const latest = await this.getLatest(symbol);

    const scores = {
      profitability: this.scoreProfitability(latest),
      growth: this.scoreGrowth(latest),
      safety: this.scoreSafety(latest),
      cashFlow: this.scoreCashFlow(latest),
    };

    const totalScore =
      (scores.profitability +
        scores.growth +
        scores.safety +
        scores.cashFlow) /
      4;

    return {
      symbol,
      totalScore: Math.round(totalScore),
      details: scores,
      rating: this.getRating(totalScore),
      fiscalYear: latest.fiscalYear,
      fiscalPeriod: latest.fiscalPeriod,
    };
  }

  /**
   * 獲利能力評分
   */
  private scoreProfitability(report: FinancialReport): number {
    let score = 0;
    const { roe = 0, roa = 0 } = report.ratios || {};
    const { netMargin = 0, operatingMargin = 0 } =
      report.incomeStatement || {};

    if (roe > 15) score += 25;
    else if (roe > 10) score += 20;
    else if (roe > 5) score += 10;

    if (roa > 8) score += 25;
    else if (roa > 5) score += 20;
    else if (roa > 3) score += 10;

    if (netMargin > 15) score += 25;
    else if (netMargin > 10) score += 20;
    else if (netMargin > 5) score += 10;

    if (operatingMargin > 15) score += 25;
    else if (operatingMargin > 10) score += 20;
    else if (operatingMargin > 5) score += 10;

    return Math.min(score, 100);
  }

  /**
   * 成長性評分
   */
  private scoreGrowth(report: FinancialReport): number {
    let score = 0;
    const { yoyRevenue = 0, yoyNetIncome = 0 } = report;

    if (yoyRevenue > 20) score += 50;
    else if (yoyRevenue > 10) score += 40;
    else if (yoyRevenue > 5) score += 25;
    else if (yoyRevenue > 0) score += 10;

    if (yoyNetIncome > 20) score += 50;
    else if (yoyNetIncome > 10) score += 40;
    else if (yoyNetIncome > 5) score += 25;
    else if (yoyNetIncome > 0) score += 10;

    return Math.min(score, 100);
  }

  /**
   * 安全性評分
   */
  private scoreSafety(report: FinancialReport): number {
    let score = 0;
    const { currentRatio = 0, debtRatio = 0 } = report.balanceSheet || {};

    if (currentRatio > 200) score += 50;
    else if (currentRatio > 150) score += 40;
    else if (currentRatio > 100) score += 25;

    if (debtRatio < 30) score += 50;
    else if (debtRatio < 50) score += 40;
    else if (debtRatio < 70) score += 20;

    return Math.min(score, 100);
  }

  /**
   * 現金流評分
   */
  private scoreCashFlow(report: FinancialReport): number {
    let score = 0;
    const { operatingCashFlow = 0, freeCashFlow = 0 } =
      report.cashFlow || {};
    const { netIncome = 0 } = report.incomeStatement || {};

    // 營業現金流 > 淨利
    if (operatingCashFlow > netIncome && netIncome > 0) {
      score += 50;
    } else if (operatingCashFlow > 0) {
      score += 25;
    }

    // 自由現金流為正
    if (freeCashFlow > 0) {
      score += 50;
    }

    return Math.min(score, 100);
  }

  /**
   * 取得評級
   */
  private getRating(score: number): string {
    if (score >= 90) return 'A+';
    if (score >= 80) return 'A';
    if (score >= 70) return 'B+';
    if (score >= 60) return 'B';
    if (score >= 50) return 'C+';
    if (score >= 40) return 'C';
    return 'D';
  }

  /**
   * 取得排序欄位
   */
  private getSortField(sortBy: string): string {
    const fieldMap: Record<string, string> = {
      roe: 'ratios.roe',
      roa: 'ratios.roa',
      eps: 'incomeStatement.eps',
      netMargin: 'incomeStatement.netMargin',
      grossMargin: 'incomeStatement.grossMargin',
      operatingMargin: 'incomeStatement.operatingMargin',
      debtRatio: 'balanceSheet.debtRatio',
    };

    return fieldMap[sortBy] || 'ratios.roe';
  }

  /**
   * 新增或更新財報
   */
  async upsert(reportData: Partial<FinancialReport>): Promise<FinancialReport> {
    const { symbol, fiscalYear, fiscalPeriod } = reportData;

    return this.financialModel
      .findOneAndUpdate(
        { symbol, fiscalYear, fiscalPeriod },
        { $set: reportData },
        { upsert: true, new: true },
      )
      .lean()
      .exec();
  }

  /**
   * 批次新增或更新
   */
  async bulkUpsert(reportsData: Partial<FinancialReport>[]): Promise<number> {
    const operations = reportsData.map((data) => ({
      updateOne: {
        filter: {
          symbol: data.symbol,
          fiscalYear: data.fiscalYear,
          fiscalPeriod: data.fiscalPeriod,
        },
        update: { $set: data },
        upsert: true,
      },
    }));

    const result = await this.financialModel.bulkWrite(operations);
    return result.upsertedCount + result.modifiedCount;
  }

  /**
   * 杜邦分析 - ROE 拆解
   * 
   * 三步驟拆解：
   * ROE = 淨利率 × 總資產週轉率 × 權益乘數
   * ROE = (淨利/營收) × (營收/總資產) × (總資產/股東權益)
   * 
   * 分析重點：
   * 1. 淨利率：獲利能力，越高越好
   * 2. 資產週轉率：經營效率，越高越好
   * 3. 權益乘數：財務槓桿，過高有風險
   * 
   * @param symbol 股票代碼
   * @param year 會計年度（可選，默認最新）
   * @param period 會計期間（可選，默認最新）
   */
  async calculateDuPont(
    symbol: string,
    year?: number,
    period?: string,
  ): Promise<any> {
    // 1. 取得財報資料
    let report: any;
    if (year && period) {
      report = await this.getByPeriod(symbol, year, period);
    } else {
      report = await this.getLatest(symbol);
    }

    // 2. 提取財務數據
    const {
      incomeStatement,
      balanceSheet,
      ratios,
    } = report;

    const revenue = incomeStatement?.revenue || 0;
    const grossProfit = incomeStatement?.grossProfit || 0;
    const operatingIncome = incomeStatement?.operatingIncome || 0;
    const netIncome = incomeStatement?.netIncome || 0;
    const totalAssets = balanceSheet?.totalAssets || 0;
    const equity = balanceSheet?.equity || 0;

    // 檢查必要數據
    if (!revenue || !netIncome || !totalAssets || !equity) {
      throw new NotFoundException(
        `${symbol} 的財報數據不完整，無法進行杜邦分析`,
      );
    }

    // 3. 計算三大指標
    const netMargin = (netIncome / revenue) * 100; // 淨利率 (%)
    
    // 判斷是否為季報，如果是則年化營收和週轉率
    const isQuarterly = report.fiscalPeriod && report.fiscalPeriod.startsWith('Q');
    const annualizationFactor = isQuarterly ? 4 : 1;
    
    // 資產週轉率使用年化營收
    const annualizedRevenue = revenue * annualizationFactor;
    const assetTurnover = annualizedRevenue / totalAssets; // 資產週轉率 (次)
    const equityMultiplier = totalAssets / equity; // 權益乘數 (倍)

    // 4. 計算 ROE（年化）
    // ROE = 淨利率 × 資產週轉率 × 權益乘數
    const calculatedROE = (netMargin / 100) * assetTurnover * equityMultiplier * 100;
    
    // 使用計算的 ROE（年化後的正確值），不使用資料庫中未年化的 ratios.roe
    const reportedROE = calculatedROE;

    // 5. 五步驟拆解（進階）
    const grossMargin = incomeStatement?.grossMargin || (grossProfit / revenue) * 100;
    const operatingMargin = incomeStatement?.operatingMargin || (operatingIncome / revenue) * 100;

    // 6. 分析與建議
    const analysis = this.analyzeDuPont({
      netMargin,
      assetTurnover,
      equityMultiplier,
      grossMargin,
      operatingMargin,
    });

    // 7. 組裝結果
    return {
      symbol,
      companyName: report.companyName,
      fiscalYear: report.fiscalYear,
      fiscalPeriod: report.fiscalPeriod,
      roe: reportedROE,
      netMargin: this.roundTo2(netMargin),
      assetTurnover: this.roundTo2(assetTurnover),
      equityMultiplier: this.roundTo2(equityMultiplier),
      threeStepDecomposition: {
        profitability: this.roundTo2(netMargin),
        efficiency: this.roundTo2(assetTurnover),
        leverage: this.roundTo2(equityMultiplier),
      },
      fiveStepDecomposition: {
        grossMargin: this.roundTo2(grossMargin),
        operatingMargin: this.roundTo2(operatingMargin),
        netMargin: this.roundTo2(netMargin),
        assetTurnover: this.roundTo2(assetTurnover),
        equityMultiplier: this.roundTo2(equityMultiplier),
      },
      financialData: {
        revenue,
        grossProfit,
        operatingIncome,
        netIncome,
        totalAssets,
        equity,
      },
      analysis,
      dataSource: report.dataSource,
      calculatedAt: new Date(),
    };
  }

  /**
   * 分析杜邦指標並提供建議
   */
  private analyzeDuPont(indicators: {
    netMargin: number;
    assetTurnover: number;
    equityMultiplier: number;
    grossMargin: number;
    operatingMargin: number;
  }): any {
    const strengths: string[] = [];
    const weaknesses: string[] = [];
    const recommendations: string[] = [];

    // 判斷產業類型（基於淨利率和資產週轉率特徵）
    const industryType = this.detectIndustryType(indicators);

    // 分析淨利率
    if (indicators.netMargin > 20) {
      strengths.push('淨利率優異 (>20%)，獲利能力強');
    } else if (indicators.netMargin > 10) {
      strengths.push('淨利率良好 (10-20%)');
    } else if (indicators.netMargin > 5) {
      weaknesses.push('淨利率偏低 (5-10%)，需提升獲利能力');
      recommendations.push('建議：控制成本、提高產品附加價值、優化產品組合');
    } else {
      weaknesses.push('淨利率過低 (<5%)，獲利能力不佳');
      recommendations.push('建議：檢視成本結構、提高毛利率、改善經營效率');
    }

    // 分析資產週轉率（依產業調整標準）
    this.analyzeAssetTurnover(
      indicators.assetTurnover,
      industryType,
      strengths,
      weaknesses,
      recommendations,
    );

    // 分析權益乘數（財務槓桿）
    if (indicators.equityMultiplier < 1.5) {
      strengths.push('權益乘數低 (<1.5)，財務風險低，財務結構穩健');
    } else if (indicators.equityMultiplier < 2.5) {
      strengths.push('權益乘數適中 (1.5-2.5)，財務槓桿運用得當');
    } else if (indicators.equityMultiplier < 3.5) {
      weaknesses.push('權益乘數偏高 (2.5-3.5)，財務槓桿較高，需注意負債風險');
      recommendations.push('建議：控制負債比例、提升自有資本、注意利息負擔');
    } else {
      weaknesses.push('權益乘數過高 (>3.5)，財務槓桿過度，財務風險高');
      recommendations.push('建議：降低負債、增資或保留盈餘、改善財務結構');
    }

    // 分析毛利率與營業利益率的差距
    const marginDiff = indicators.grossMargin - indicators.operatingMargin;
    if (marginDiff > 20) {
      weaknesses.push(`營業費用率過高 (${this.roundTo2(marginDiff)}%)，費用控制不佳`);
      recommendations.push('建議：檢視營業費用結構、控制管銷費用、提升營運效率');
    }

    return {
      strengths,
      weaknesses,
      recommendations,
      industryType, // 回傳產業類型供參考
    };
  }

  /**
   * 偵測產業類型
   */
  private detectIndustryType(indicators: {
    netMargin: number;
    assetTurnover: number;
    grossMargin: number;
  }): string {
    // 半導體製造業特徵：高毛利率(>40%)、低週轉率(<0.6)、高淨利率(>15%)
    if (
      indicators.grossMargin > 40 &&
      indicators.assetTurnover < 0.6 &&
      indicators.netMargin > 15
    ) {
      return '半導體製造';
    }

    // 傳統製造業特徵：中等毛利率(15-40%)、中等週轉率(0.5-1.5)
    if (
      indicators.grossMargin >= 15 &&
      indicators.grossMargin <= 40 &&
      indicators.assetTurnover >= 0.5 &&
      indicators.assetTurnover <= 1.5
    ) {
      return '傳統製造';
    }

    // 零售業特徵：低毛利率(<30%)、高週轉率(>1.5)
    if (indicators.grossMargin < 30 && indicators.assetTurnover > 1.5) {
      return '零售服務';
    }

    // 資本密集產業：低週轉率(<0.5)、中高毛利率(>25%)
    if (indicators.assetTurnover < 0.5 && indicators.grossMargin > 25) {
      return '資本密集';
    }

    return '一般產業';
  }

  /**
   * 分析資產週轉率（依產業別調整標準）
   */
  private analyzeAssetTurnover(
    assetTurnover: number,
    industryType: string,
    strengths: string[],
    weaknesses: string[],
    recommendations: string[],
  ): void {
    // 依產業設定不同的標準
    let thresholds = {
      excellent: 1.5,
      good: 0.8,
      fair: 0.5,
      industryName: '一般產業',
    };

    switch (industryType) {
      case '半導體製造':
        thresholds = {
          excellent: 0.6,
          good: 0.4,
          fair: 0.3,
          industryName: '半導體製造業',
        };
        break;
      case '資本密集':
        thresholds = {
          excellent: 0.8,
          good: 0.5,
          fair: 0.3,
          industryName: '資本密集產業',
        };
        break;
      case '傳統製造':
        thresholds = {
          excellent: 1.5,
          good: 1.0,
          fair: 0.6,
          industryName: '傳統製造業',
        };
        break;
      case '零售服務':
        thresholds = {
          excellent: 3.0,
          good: 2.0,
          fair: 1.5,
          industryName: '零售服務業',
        };
        break;
    }

    // 進行評估
    if (assetTurnover > thresholds.excellent) {
      strengths.push(
        `資產週轉率優異 (>${thresholds.excellent})，資產運用效率高（${thresholds.industryName}標準）`,
      );
    } else if (assetTurnover > thresholds.good) {
      strengths.push(
        `資產週轉率良好 (${thresholds.good}-${thresholds.excellent})，符合${thresholds.industryName}常態`,
      );
    } else if (assetTurnover > thresholds.fair) {
      weaknesses.push(
        `資產週轉率偏低 (${thresholds.fair}-${thresholds.good})，資產運用效率待提升（${thresholds.industryName}）`,
      );
      recommendations.push(
        `建議：${industryType === '半導體製造' || industryType === '資本密集' 
          ? '優化產能利用率、提升先進製程比例、擴大高附加價值產品' 
          : '加速存貨週轉、提高應收帳款回收效率、優化資產配置'}`,
      );
    } else {
      weaknesses.push(
        `資產週轉率過低 (<${thresholds.fair})，低於${thresholds.industryName}常態`,
      );
      recommendations.push(
        `建議：${industryType === '半導體製造' || industryType === '資本密集' 
          ? '檢視產能利用率、評估設備效能、考慮處分老舊產線' 
          : '處分閒置資產、提升營運效率、加強資產管理'}`,
      );
    }
  }

  /**
   * 四捨五入到小數點後2位
   */
  private roundTo2(num: number): number {
    return Math.round(num * 100) / 100;
  }
}
