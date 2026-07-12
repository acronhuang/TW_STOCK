import { IsOptional, IsString, IsNumber, Min, Max, IsIn } from 'class-validator';
import { Type } from 'class-transformer';
import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';

/**
 * 財報查詢 DTO
 * 支援年度、季度、報表類型等條件
 */
export class QueryFinancialDto {
  @ApiPropertyOptional({ description: '會計年度', example: 2024 })
  @IsOptional()
  @Type(() => Number)
  @IsNumber()
  @Min(2000)
  @Max(2100)
  year?: number;

  @ApiPropertyOptional({ 
    description: '會計期間', 
    example: 'Q4',
    enum: ['Q1', 'Q2', 'Q3', 'Q4', 'Annual']
  })
  @IsOptional()
  @IsString()
  @IsIn(['Q1', 'Q2', 'Q3', 'Q4', 'Annual'])
  period?: string;

  @ApiPropertyOptional({ 
    description: '報表類型', 
    example: 'quarterly',
    enum: ['quarterly', 'annual']
  })
  @IsOptional()
  @IsString()
  @IsIn(['quarterly', 'annual'])
  reportType?: 'quarterly' | 'annual';

  @ApiPropertyOptional({ description: '取得最近 N 期財報', example: 8, default: 8 })
  @IsOptional()
  @Type(() => Number)
  @IsNumber()
  @Min(1)
  @Max(40)
  limit?: number = 8;
}

/**
 * 財報趨勢查詢 DTO
 */
export class FinancialTrendDto {
  @ApiProperty({ description: '開始年度', example: 2020 })
  @Type(() => Number)
  @IsNumber()
  @Min(2000)
  @Max(2100)
  startYear: number;

  @ApiProperty({ description: '結束年度', example: 2024 })
  @Type(() => Number)
  @IsNumber()
  @Min(2000)
  @Max(2100)
  endYear: number;

  @ApiPropertyOptional({ 
    description: '報表類型', 
    example: 'annual',
    default: 'annual'
  })
  @IsOptional()
  @IsString()
  @IsIn(['quarterly', 'annual'])
  reportType?: 'quarterly' | 'annual' = 'annual';
}

/**
 * 財務比率排行查詢 DTO
 */
export class FinancialRankingDto {
  @ApiPropertyOptional({ description: '年度', example: 2024 })
  @IsOptional()
  @Type(() => Number)
  @IsNumber()
  year?: number;

  @ApiPropertyOptional({ description: '期間', example: 'Q4' })
  @IsOptional()
  @IsString()
  period?: string;

  @ApiProperty({ 
    description: '排序指標', 
    example: 'roe',
    enum: ['roe', 'roa', 'eps', 'netMargin', 'grossMargin', 'debtRatio']
  })
  @IsString()
  @IsIn(['roe', 'roa', 'eps', 'netMargin', 'grossMargin', 'debtRatio', 'operatingMargin'])
  sortBy: string;

  @ApiPropertyOptional({ description: '回傳筆數', example: 20, default: 20 })
  @IsOptional()
  @Type(() => Number)
  @IsNumber()
  @Min(1)
  @Max(100)
  limit?: number = 20;
}

/**
 * 多公司比較 DTO
 */
export class CompareCompaniesDto {
  @ApiProperty({ 
    description: '股票代碼陣列', 
    example: ['2330', '2317', '2454'],
    type: [String]
  })
  @IsString({ each: true })
  symbols: string[];

  @ApiProperty({ description: '年度', example: 2024 })
  @Type(() => Number)
  @IsNumber()
  year: number;

  @ApiPropertyOptional({ description: '期間', example: 'Q4', default: 'Annual' })
  @IsOptional()
  @IsString()
  period?: string = 'Annual';
}
