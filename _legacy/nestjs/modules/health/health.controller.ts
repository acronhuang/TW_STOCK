import { Controller, Get } from '@nestjs/common';
import { ApiTags, ApiOperation } from '@nestjs/swagger';
import { HealthService } from './health.service';

@ApiTags('system')
@Controller('health')
export class HealthController {
  constructor(private readonly healthService: HealthService) {}

  @Get()
  @ApiOperation({ summary: '健康檢查' })
  async check() {
    return this.healthService.check();
  }

  @Get('database')
  @ApiOperation({ summary: '資料庫狀態檢查' })
  async checkDatabase() {
    return this.healthService.checkDatabase();
  }

  @Get('cache')
  @ApiOperation({ summary: '快取狀態檢查' })
  async checkCache() {
    return this.healthService.checkCache();
  }
}
