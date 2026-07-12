import { Controller, Post, Get, Body, Logger } from '@nestjs/common';
import { ApiTags, ApiOperation, ApiBody } from '@nestjs/swagger';
import { SchedulerService } from './scheduler.service';

/**
 * 排程管理 API 控制器
 * 
 * 功能:
 * - 手動觸發排程任務
 * - 查看排程狀態
 * - 啟用/停用排程
 */
@ApiTags('排程管理 (Scheduler)')
@Controller('scheduler')
export class SchedulerController {
  private readonly logger = new Logger(SchedulerController.name);

  constructor(private readonly schedulerService: SchedulerService) {}

  /**
   * 取得排程狀態
   */
  @Get('status')
  @ApiOperation({
    summary: '取得排程狀態',
    description: '查詢排程系統狀態、上次執行時間、成功/失敗統計',
  })
  async getStatus() {
    const status = this.schedulerService.getStatus();

    return {
      success: true,
      data: status,
    };
  }

  /**
   * 手動觸發財報抓取
   */
  @Post('trigger/financial')
  @ApiOperation({
    summary: '手動觸發財報抓取',
    description: '立即執行財報抓取任務（不等待排程時間）',
  })
  @ApiBody({
    schema: {
      type: 'object',
      properties: {
        symbols: {
          type: 'array',
          items: { type: 'string' },
          example: ['2330', '2317', '2454'],
          description: '指定公司代碼（選填，預設前10大）',
        },
      },
    },
    required: false,
  })
  async triggerFinancialScraping(@Body('symbols') symbols?: string[]) {
    this.logger.log(
      `API: 手動觸發財報抓取 ${symbols ? `(${symbols.length}家)` : '(預設10家)'}`,
    );

    try {
      const result = await this.schedulerService.manualTriggerFinancialScraping(
        symbols,
      );

      return result;
    } catch (error) {
      return {
        success: false,
        message: error.message,
      };
    }
  }

  /**
   * 啟用排程
   */
  @Post('enable')
  @ApiOperation({
    summary: '啟用排程',
    description: '啟用自動排程任務',
  })
  async enableScheduler() {
    this.logger.log('API: 啟用排程');
    this.schedulerService.enableScheduler();

    return {
      success: true,
      message: '排程已啟用',
    };
  }

  /**
   * 停用排程
   */
  @Post('disable')
  @ApiOperation({
    summary: '停用排程',
    description: '停用自動排程任務（不影響手動觸發）',
  })
  async disableScheduler() {
    this.logger.log('API: 停用排程');
    this.schedulerService.disableScheduler();

    return {
      success: true,
      message: '排程已停用',
    };
  }
}
