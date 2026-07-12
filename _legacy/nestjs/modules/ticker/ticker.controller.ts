import { Controller, Get, Param, Query } from '@nestjs/common';
import { ApiTags, ApiOperation, ApiResponse, ApiParam } from '@nestjs/swagger';
import { TickerService } from './ticker.service';
import { QueryTickerDto, RankingQueryDto } from './dto/query-ticker.dto';
import { Ticker } from './schemas/ticker.schema';

@ApiTags('tickers')
@Controller('tickers')
export class TickerController {
  constructor(private readonly tickerService: TickerService) {}

  // ⚠️ 具體路由必須放在動態路由 (:symbol) 前面，否則會被攔截
  @Get('ranking/top-gainers')
  @ApiOperation({ summary: '取得漲幅排行榜' })
  async getTopGainers(@Query() query: RankingQueryDto): Promise<Ticker[]> {
    return this.tickerService.getTopGainers(query.date, query.limit);
  }

  @Get('ranking/top-losers')
  @ApiOperation({ summary: '取得跌幅排行榜' })
  async getTopLosers(@Query() query: RankingQueryDto): Promise<Ticker[]> {
    return this.tickerService.getTopLosers(query.date, query.limit);
  }

  @Get('ranking/top-volume')
  @ApiOperation({ summary: '取得成交量排行榜' })
  async getTopVolume(@Query() query: RankingQueryDto): Promise<Ticker[]> {
    return this.tickerService.getTopVolume(query.date, query.limit);
  }

  @Get('date/:date')
  @ApiOperation({ summary: '取得指定日期全市場資料' })
  @ApiParam({ name: 'date', description: '日期', example: '2024-12-21' })
  async getByDate(@Param('date') date: string): Promise<Ticker[]> {
    return this.tickerService.getByDateAll(date);
  }

  @Get(':symbol/history')
  @ApiOperation({ summary: '取得單一股票歷史資料' })
  @ApiParam({ name: 'symbol', description: '股票代碼', example: '2330' })
  async getHistory(
    @Param('symbol') symbol: string,
    @Query() query: QueryTickerDto,
  ): Promise<Ticker[]> {
    return this.tickerService.getHistory(
      symbol,
      query.startDate,
      query.endDate,
      query.days,
    );
  }

  @Get(':symbol')
  @ApiOperation({ summary: '取得單一股票最新資料' })
  @ApiParam({ name: 'symbol', description: '股票代碼', example: '2330' })
  @ApiResponse({ status: 200, description: '成功取得資料' })
  async getLatest(@Param('symbol') symbol: string): Promise<Ticker> {
    return this.tickerService.getLatest(symbol);
  }
}
