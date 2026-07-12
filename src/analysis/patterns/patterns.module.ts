import { Module } from '@nestjs/common';
import { MongooseModule } from '@nestjs/mongoose';
import { TechnicalPatternsService } from './technical-patterns.service';
import { PatternScannerService } from './pattern-scanner.service';
import { PatternsController } from './patterns.controller';

/**
 * 技術型態分析模組
 */
@Module({
  imports: [MongooseModule.forFeature([])],
  controllers: [PatternsController],
  providers: [TechnicalPatternsService, PatternScannerService],
  exports: [TechnicalPatternsService, PatternScannerService],
})
export class PatternsModule {}
