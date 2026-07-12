import { Module } from '@nestjs/common';
import { ViewController } from './view.controller';
import { FinancialModule } from '../financial/financial.module';
import { TickerModule } from '../ticker/ticker.module';

@Module({
  imports: [FinancialModule, TickerModule],
  controllers: [ViewController],
})
export class ViewModule {}
