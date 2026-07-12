import { Module } from '@nestjs/common';
import { MongooseModule } from '@nestjs/mongoose';
import {
  FinancialReport,
  FinancialReportSchema,
} from './schemas/financial-report.schema';
import { FinancialService } from './financial.service';
import { FinancialController } from './financial.controller';

@Module({
  imports: [
    MongooseModule.forFeature([
      { name: FinancialReport.name, schema: FinancialReportSchema },
    ]),
  ],
  controllers: [FinancialController],
  providers: [FinancialService],
  exports: [FinancialService],
})
export class FinancialModule {}

