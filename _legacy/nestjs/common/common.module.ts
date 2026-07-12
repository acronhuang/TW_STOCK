import { Module, Global } from '@nestjs/common';
import { DateUtilService } from './utils/date-util.service';
import { NumberUtilService } from './utils/number-util.service';
import { CacheUtilService } from './utils/cache-util.service';

@Global()
@Module({
  providers: [DateUtilService, NumberUtilService, CacheUtilService],
  exports: [DateUtilService, NumberUtilService, CacheUtilService],
})
export class CommonModule {}
