import { Prop, Schema, SchemaFactory } from '@nestjs/mongoose';
import { Document, Schema as MongooseSchema } from 'mongoose';

export type FinancialReportDocument = FinancialReport & Document;

/**
 * 損益表 (Income Statement)
 * 🔄 2026-02-20: 所有金額欄位改用 Decimal128
 */
@Schema({ _id: false })
export class IncomeStatement {
  @Prop({ default: 0, type: MongooseSchema.Types.Decimal128 })
  revenue: MongooseSchema.Types.Decimal128; // 營業收入

  @Prop({ default: 0, type: MongooseSchema.Types.Decimal128 })
  grossProfit: MongooseSchema.Types.Decimal128; // 毛利

  @Prop({ default: 0, type: MongooseSchema.Types.Decimal128 })
  operatingExpenses: MongooseSchema.Types.Decimal128; // 營業費用

  @Prop({ default: 0, type: MongooseSchema.Types.Decimal128 })
  operatingIncome: MongooseSchema.Types.Decimal128; // 營業利益

  @Prop({ default: 0, type: MongooseSchema.Types.Decimal128 })
  nonOperatingIncome: MongooseSchema.Types.Decimal128; // 營業外收支

  @Prop({ default: 0, type: MongooseSchema.Types.Decimal128 })
  pretaxIncome: MongooseSchema.Types.Decimal128; // 稅前淨利

  @Prop({ default: 0, type: MongooseSchema.Types.Decimal128 })
  incomeTax: MongooseSchema.Types.Decimal128; // 所得稅

  @Prop({ default: 0, type: MongooseSchema.Types.Decimal128 })
  netIncome: MongooseSchema.Types.Decimal128; // 稅後淨利（歸屬母公司）

  @Prop({ default: 0, type: MongooseSchema.Types.Decimal128 })
  eps: MongooseSchema.Types.Decimal128; // 每股盈餘 (EPS)

  @Prop({ default: 0, type: MongooseSchema.Types.Decimal128 })
  grossMargin: MongooseSchema.Types.Decimal128; // 毛利率 (%)

  @Prop({ default: 0, type: MongooseSchema.Types.Decimal128 })
  operatingMargin: MongooseSchema.Types.Decimal128; // 營益率 (%)

  @Prop({ default: 0, type: MongooseSchema.Types.Decimal128 })
  netMargin: MongooseSchema.Types.Decimal128; // 淨利率 (%)
}

/**
 * 資產負債表 (Balance Sheet)
 * 🔄 2026-02-20: 所有金額欄位改用 Decimal128
 */
@Schema({ _id: false })
export class BalanceSheet {
  // === 資產 ===
  @Prop({ default: 0, type: MongooseSchema.Types.Decimal128 })
  totalAssets: MongooseSchema.Types.Decimal128; // 總資產

  @Prop({ default: 0, type: MongooseSchema.Types.Decimal128 })
  currentAssets: MongooseSchema.Types.Decimal128; // 流動資產

  @Prop({ default: 0, type: MongooseSchema.Types.Decimal128 })
  cash: MongooseSchema.Types.Decimal128; // 現金及約當現金

  @Prop({ default: 0, type: MongooseSchema.Types.Decimal128 })
  accountsReceivable: MongooseSchema.Types.Decimal128; // 應收帳款

  @Prop({ default: 0, type: MongooseSchema.Types.Decimal128 })
  inventory: MongooseSchema.Types.Decimal128; // 存貨

  @Prop({ default: 0, type: MongooseSchema.Types.Decimal128 })
  fixedAssets: MongooseSchema.Types.Decimal128; // 固定資產

  @Prop({ default: 0, type: MongooseSchema.Types.Decimal128 })
  intangibleAssets: MongooseSchema.Types.Decimal128; // 無形資產

  // === 負債 ===
  @Prop({ default: 0, type: MongooseSchema.Types.Decimal128 })
  totalLiabilities: MongooseSchema.Types.Decimal128; // 總負債

  @Prop({ default: 0, type: MongooseSchema.Types.Decimal128 })
  currentLiabilities: MongooseSchema.Types.Decimal128; // 流動負債

  @Prop({ default: 0, type: MongooseSchema.Types.Decimal128 })
  shortTermDebt: MongooseSchema.Types.Decimal128; // 短期借款

  @Prop({ default: 0, type: MongooseSchema.Types.Decimal128 })
  longTermDebt: MongooseSchema.Types.Decimal128; // 長期借款

  @Prop({ default: 0, type: MongooseSchema.Types.Decimal128 })
  accountsPayable: MongooseSchema.Types.Decimal128; // 應付帳款

  // === 股東權益 ===
  @Prop({ default: 0, type: MongooseSchema.Types.Decimal128 })
  equity: MongooseSchema.Types.Decimal128; // 股東權益總計

  @Prop({ default: 0, type: MongooseSchema.Types.Decimal128 })
  shareCapital: MongooseSchema.Types.Decimal128; // 股本

  @Prop({ default: 0, type: MongooseSchema.Types.Decimal128 })
  retainedEarnings: MongooseSchema.Types.Decimal128; // 保留盈餘

  // === 比率 ===
  @Prop({ default: 0, type: MongooseSchema.Types.Decimal128 })
  currentRatio: MongooseSchema.Types.Decimal128; // 流動比率

  @Prop({ default: 0, type: MongooseSchema.Types.Decimal128 })
  quickRatio: MongooseSchema.Types.Decimal128; // 速動比率

  @Prop({ default: 0, type: MongooseSchema.Types.Decimal128 })
  debtRatio: MongooseSchema.Types.Decimal128; // 負債比率 (%)
}

/**
 * 現金流量表 (Cash Flow Statement)
 * 🔄 2026-02-20: 所有金額欄位改用 Decimal128
 */
@Schema({ _id: false })
export class CashFlow {
  @Prop({ default: 0, type: MongooseSchema.Types.Decimal128 })
  operatingCashFlow: MongooseSchema.Types.Decimal128; // 營業活動現金流量

  @Prop({ default: 0, type: MongooseSchema.Types.Decimal128 })
  investingCashFlow: MongooseSchema.Types.Decimal128; // 投資活動現金流量

  @Prop({ default: 0, type: MongooseSchema.Types.Decimal128 })
  financingCashFlow: MongooseSchema.Types.Decimal128; // 融資活動現金流量

  @Prop({ default: 0, type: MongooseSchema.Types.Decimal128 })
  freeCashFlow: MongooseSchema.Types.Decimal128; // 自由現金流量

  @Prop({ default: 0, type: MongooseSchema.Types.Decimal128 })
  netCashFlow: MongooseSchema.Types.Decimal128; // 現金流量淨增（減）

  @Prop({ default: 0, type: MongooseSchema.Types.Decimal128 })
  capitalExpenditure: MongooseSchema.Types.Decimal128; // 資本支出

  @Prop({ default: 0, type: MongooseSchema.Types.Decimal128 })
  dividendPaid: MongooseSchema.Types.Decimal128; // 支付股利
}

/**
 * 財務比率 (Financial Ratios)
 * 參考 goodinfo 財務分析頁面
 */
@Schema({ _id: false })
export class FinancialRatios {
  // === 獲利能力 ===
  @Prop({ default: 0 })
  roe: number; // 股東權益報酬率 (%)

  @Prop({ default: 0 })
  roa: number; // 資產報酬率 (%)

  @Prop({ default: 0 })
  roic: number; // 投資資本報酬率 (%)

  // === 經營能力 ===
  @Prop({ default: 0 })
  assetTurnover: number; // 總資產週轉率

  @Prop({ default: 0 })
  inventoryTurnover: number; // 存貨週轉率

  @Prop({ default: 0 })
  receivableTurnover: number; // 應收帳款週轉率

  @Prop({ default: 0 })
  inventoryDays: number; // 平均銷貨天數

  @Prop({ default: 0 })
  receivableDays: number; // 平均收款天數

  // === 償債能力 ===
  @Prop({ default: 0 })
  interestCoverage: number; // 利息保障倍數

  @Prop({ default: 0 })
  debtToEquity: number; // 負債對權益比

  // === 每股指標 ===
  @Prop({ default: 0 })
  bookValuePerShare: number; // 每股淨值

  @Prop({ default: 0 })
  cashFlowPerShare: number; // 每股現金流量

  @Prop({ default: 0 })
  freeCashFlowPerShare: number; // 每股自由現金流量
}

/**
 * 財務報表主 Schema
 * 參考 goodinfo 財報結構設計
 */
@Schema({ timestamps: true, collection: 'financial_reports' })
export class FinancialReport {
  @Prop({ required: true, index: true })
  symbol: string; // 股票代碼

  @Prop()
  companyName: string; // 公司名稱

  @Prop({ required: true })
  fiscalYear: number; // 會計年度

  @Prop({ required: true })
  fiscalPeriod: string; // 會計期間 (Q1, Q2, Q3, Q4, Annual)

  @Prop({ type: String, enum: ['quarterly', 'annual'] })
  reportType: string; // 報表類型

  @Prop({ required: true })
  reportDate: string; // 報告日期 (YYYY-MM-DD)

  @Prop()
  currency: string; // 幣別 (TWD, USD...)

  @Prop()
  dataSource: string; // 資料來源 (TWSE, TPEx, MOPS...)

  // === 三大報表 ===
  @Prop({ type: IncomeStatement })
  incomeStatement: IncomeStatement; // 損益表

  @Prop({ type: BalanceSheet })
  balanceSheet: BalanceSheet; // 資產負債表

  @Prop({ type: CashFlow })
  cashFlow: CashFlow; // 現金流量表

  // === 財務比率 ===
  @Prop({ type: FinancialRatios })
  ratios: FinancialRatios; // 財務比率分析

  // === 同期比較 ===
  @Prop()
  yoyRevenue: number; // 營收年增率 (%)

  @Prop()
  yoyNetIncome: number; // 淨利年增率 (%)

  @Prop()
  qoqRevenue: number; // 營收季增率 (%)

  @Prop()
  qoqNetIncome: number; // 淨利季增率 (%)

  // === 元數據 ===
  createdAt: Date;
  updatedAt: Date;
}

export const FinancialReportSchema = SchemaFactory.createForClass(FinancialReport);

// 複合索引
FinancialReportSchema.index({ symbol: 1, fiscalYear: -1, fiscalPeriod: -1 }, { unique: true });
FinancialReportSchema.index({ fiscalYear: -1, fiscalPeriod: -1 });
FinancialReportSchema.index({ reportDate: -1 });
