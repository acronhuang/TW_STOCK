import { IsString, IsNumber, IsOptional, IsDateString } from 'class-validator';
import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import { Type } from 'class-transformer';

export class QueryTickerDto {
  @ApiProperty({ description: '股票代碼', example: '2330' })
  @IsString()
  symbol: string;

  @ApiPropertyOptional({ description: '查詢日期 (YYYY-MM-DD)', example: '2024-12-21' })
  @IsOptional()
  @IsDateString()
  date?: string;

  @ApiPropertyOptional({ description: '起始日期', example: '2024-01-01' })
  @IsOptional()
  @IsDateString()
  startDate?: string;

  @ApiPropertyOptional({ description: '結束日期', example: '2024-12-31' })
  @IsOptional()
  @IsDateString()
  endDate?: string;

  @ApiPropertyOptional({ description: '查詢天數', example: 60, default: 60 })
  @IsOptional()
  @Type(() => Number)
  @IsNumber()
  days?: number;
}

export class RankingQueryDto {
  @ApiPropertyOptional({ description: '查詢日期', example: '2024-12-21' })
  @IsOptional()
  @IsDateString()
  date?: string;

  @ApiPropertyOptional({ description: '回傳筆數', example: 20, default: 20 })
  @IsOptional()
  @Type(() => Number)
  @IsNumber()
  limit?: number;

  @ApiPropertyOptional({ description: '排序欄位', example: 'changePercent' })
  @IsOptional()
  @IsString()
  sortBy?: string;
}
