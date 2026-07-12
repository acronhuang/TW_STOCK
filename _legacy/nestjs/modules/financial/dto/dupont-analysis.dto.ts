import { ApiProperty } from '@nestjs/swagger';

/**
 * 杜邦分析結果 DTO
 * 
 * ROE 拆解公式：
 * ROE = 淨利率 × 總資產週轉率 × 權益乘數
 * ROE = (淨利/營收) × (營收/總資產) × (總資產/股東權益)
 */
export class DuPontAnalysisDto {
  @ApiProperty({ description: '股票代碼', example: '2330' })
  symbol: string;

  @ApiProperty({ description: '公司名稱', example: '台積電' })
  companyName?: string;

  @ApiProperty({ description: '會計年度', example: 2024 })
  fiscalYear: number;

  @ApiProperty({ description: '會計期間', example: 'Q4' })
  fiscalPeriod: string;

  @ApiProperty({ description: '股東權益報酬率 ROE (%)', example: 23.45 })
  roe: number;

  @ApiProperty({ description: '淨利率 = 淨利 / 營收 (%)', example: 36.57 })
  netMargin: number;

  @ApiProperty({ description: '總資產週轉率 = 營收 / 總資產 (次)', example: 0.64 })
  assetTurnover: number;

  @ApiProperty({ description: '權益乘數 = 總資產 / 股東權益 (倍)', example: 1.51 })
  equityMultiplier: number;

  @ApiProperty({ 
    description: '三步驟拆解',
    type: 'object',
    example: {
      profitability: 36.57,
      efficiency: 0.64,
      leverage: 1.51,
    }
  })
  threeStepDecomposition: {
    profitability: number;  // 獲利能力（淨利率）
    efficiency: number;     // 經營效率（資產週轉率）
    leverage: number;       // 財務槓桿（權益乘數）
  };

  @ApiProperty({ 
    description: '五步驟拆解（進階）',
    type: 'object',
    example: {
      grossMargin: 54.32,
      operatingMargin: 42.15,
      netMargin: 36.57,
      assetTurnover: 0.64,
      equityMultiplier: 1.51,
    }
  })
  fiveStepDecomposition?: {
    grossMargin: number;        // 毛利率
    operatingMargin: number;    // 營業利益率
    netMargin: number;          // 淨利率
    assetTurnover: number;      // 資產週轉率
    equityMultiplier: number;   // 權益乘數
  };

  @ApiProperty({ 
    description: '計算所需的財務數據',
    type: 'object'
  })
  financialData: {
    revenue: number;          // 營業收入
    grossProfit: number;      // 毛利
    operatingIncome: number;  // 營業利益
    netIncome: number;        // 稅後淨利
    totalAssets: number;      // 總資產
    equity: number;           // 股東權益
  };

  @ApiProperty({ 
    description: '分析與建議',
    type: 'object'
  })
  analysis?: {
    strengths: string[];      // 優勢
    weaknesses: string[];     // 劣勢
    recommendations: string[]; // 建議
  };

  @ApiProperty({ description: '資料來源', example: 'MOPS' })
  dataSource?: string;

  @ApiProperty({ description: '計算時間' })
  calculatedAt: Date;
}
