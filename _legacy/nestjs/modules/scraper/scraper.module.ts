import { Module } from '@nestjs/common';
import { MongooseModule } from '@nestjs/mongoose';
import { ScraperController } from './scraper.controller';
import { ScraperService } from './scraper.service';
import { MOPSScraperService } from './services/mops.scraper';
import { TWSEScraperService } from './services/twse.scraper';
import { FinMindScraperService } from './services/finmind.scraper';
import { YahooScraperService } from './services/yahoo.scraper';
import { GoodinfoScraperService } from './services/goodinfo.scraper';
import { FinancialReport, FinancialReportSchema } from '../financial/schemas/financial-report.schema';
import { Ticker, TickerSchema } from '../ticker/schemas/ticker.schema';
import { CommonModule } from '../../common/common.module';

@Module({
  imports: [
    MongooseModule.forFeature([
      { name: FinancialReport.name, schema: FinancialReportSchema },
      { name: Ticker.name, schema: TickerSchema },
    ]),
    CommonModule,
  ],
  controllers: [ScraperController],
  providers: [
    ScraperService,
    MOPSScraperService,
    TWSEScraperService,
    FinMindScraperService,
    YahooScraperService,
    GoodinfoScraperService,
  ],
  exports: [
    ScraperService,
    MOPSScraperService,
    TWSEScraperService,
    FinMindScraperService,
    YahooScraperService,
    GoodinfoScraperService,
  ],
})
export class ScraperModule {}
