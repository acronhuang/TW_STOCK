import { Module } from '@nestjs/common';
import { MongooseModule } from '@nestjs/mongoose';
import { Ticker, TickerSchema } from './schemas/ticker.schema';
import { TickerService } from './ticker.service';
import { TickerController } from './ticker.controller';

@Module({
  imports: [
    MongooseModule.forFeature([{ name: Ticker.name, schema: TickerSchema }]),
  ],
  controllers: [TickerController],
  providers: [TickerService],
  exports: [TickerService],
})
export class TickerModule {}
