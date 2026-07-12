import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { MongooseModule } from '@nestjs/mongoose';
import { ScheduleModule } from '@nestjs/schedule';
import { CacheModule } from '@nestjs/cache-manager';
import type { RedisClientOptions } from 'redis';
import { redisStore } from 'cache-manager-redis-store';

// 核心模組
import { CommonModule } from './common/common.module';
import { HealthModule } from './modules/health/health.module';

// 資料模組
import { TickerModule } from './modules/ticker/ticker.module';
import { TechnicalModule } from './modules/technical/technical.module';
import { FinancialModule } from './modules/financial/financial.module';
import { RevenueModule } from './modules/revenue/revenue.module';
import { ProfitabilityModule } from './modules/profitability/profitability.module';
import { DividendModule } from './modules/dividend/dividend.module';
import { ValuationModule } from './modules/valuation/valuation.module';

// 籌碼模組
import { InstitutionalModule } from './modules/institutional/institutional.module';
import { ShareholderModule } from './modules/shareholder/shareholder.module';
import { DirectorModule } from './modules/director/director.module';

// 產業模組
import { IndustryModule } from './modules/industry/industry.module';

// 分析模組
import { VolumePriceModule } from './modules/volume-price/volume-price.module';
import { StrategyModule } from './modules/strategy/strategy.module';
import { PatternsModule } from './analysis/patterns/patterns.module';

// 資料收集模組
import { ScraperModule } from './modules/scraper/scraper.module';
import { SchedulerModule } from './modules/scheduler/scheduler.module';

// 視覺化模組
import { ViewModule } from './modules/view/view.module';

@Module({
  imports: [
    // 環境配置
    ConfigModule.forRoot({
      isGlobal: true,
      envFilePath: '.env',
    }),

    // MongoDB 連接
    MongooseModule.forRoot(
      process.env.MONGODB_URI || 'mongodb://localhost:27018/tw_stock_analysis',
      {
        connectionFactory: (connection) => {
          connection.on('connected', () => {
            console.log('✅ MongoDB 連接成功');
          });
          connection.on('error', (error) => {
            console.error('❌ MongoDB 連接錯誤:', error);
          });
          return connection;
        },
      },
    ),

    // 記憶體快取 (Redis store 與 cache-manager v5 有兼容問題，暫時使用記憶體)
    CacheModule.register({
      isGlobal: true,
      ttl: parseInt(process.env.CACHE_TTL || '300') * 1000,
    }),

    // 排程系統
    ScheduleModule.forRoot(),

    // 核心模組
    CommonModule,
    HealthModule,

    // 資料模組
    TickerModule,
    TechnicalModule,
    FinancialModule,
    RevenueModule,
    ProfitabilityModule,
    DividendModule,
    ValuationModule,

    // 籌碼模組
    InstitutionalModule,
    ShareholderModule,
    DirectorModule,

    // 產業模組
    IndustryModule,

    // 分析模組
    VolumePriceModule,
    StrategyModule,
    PatternsModule,

    // 資料收集模組
    ScraperModule,
    SchedulerModule,

    // 視覺化模組
    ViewModule,
  ],
})
export class AppModule {}
