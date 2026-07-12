import { Injectable } from '@nestjs/common';
import { DateTime } from 'luxon';

/**
 * 日期工具服務
 * 處理台股交易日期相關邏輯
 */
@Injectable()
export class DateUtilService {
  private readonly timezone = 'Asia/Taipei';

  /**
   * 取得當前台北時間
   */
  now(): DateTime {
    return DateTime.now().setZone(this.timezone);
  }

  /**
   * 格式化日期為 YYYY-MM-DD
   */
  formatDate(date: Date | string | DateTime): string {
    let dt: DateTime;

    if (date instanceof DateTime) {
      dt = date;
    } else if (typeof date === 'string') {
      dt = DateTime.fromISO(date);
    } else {
      dt = DateTime.fromJSDate(date);
    }

    return dt.setZone(this.timezone).toFormat('yyyy-MM-dd');
  }

  /**
   * 取得昨日日期
   */
  yesterday(): string {
    return this.now().minus({ days: 1 }).toFormat('yyyy-MM-dd');
  }

  /**
   * 取得 N 天前的日期
   */
  daysAgo(days: number): string {
    return this.now().minus({ days }).toFormat('yyyy-MM-dd');
  }

  /**
   * 取得日期範圍
   */
  getDateRange(startDate: string, endDate: string): string[] {
    const start = DateTime.fromISO(startDate);
    const end = DateTime.fromISO(endDate);
    const dates: string[] = [];

    let current = start;
    while (current <= end) {
      dates.push(current.toFormat('yyyy-MM-dd'));
      current = current.plus({ days: 1 });
    }

    return dates;
  }

  /**
   * 檢查是否為交易日 (排除週末)
   * TODO: 整合台股休市日曆
   */
  isTradingDay(date: string | DateTime): boolean {
    const dt = typeof date === 'string' ? DateTime.fromISO(date) : date;
    const weekday = dt.weekday;
    return weekday !== 6 && weekday !== 7; // 1-5 = 週一至週五
  }

  /**
   * 取得上一個交易日
   */
  getLastTradingDay(date?: string): string {
    let current = date ? DateTime.fromISO(date) : this.now();

    do {
      current = current.minus({ days: 1 });
    } while (!this.isTradingDay(current));

    return current.toFormat('yyyy-MM-dd');
  }

  /**
   * 將民國年轉西元年
   */
  rocToWestern(rocYear: number): number {
    return rocYear + 1911;
  }

  /**
   * 將西元年轉民國年
   */
  westernToRoc(westernYear: number): number {
    return westernYear - 1911;
  }

  /**
   * 取得當前季度
   */
  getCurrentQuarter(): { year: number; quarter: number } {
    const now = this.now();
    return {
      year: now.year,
      quarter: Math.ceil(now.month / 3),
    };
  }

  /**
   * 取得上一季度
   */
  getLastQuarter(): { year: number; quarter: number } {
    const now = this.now();
    let year = now.year;
    let quarter = Math.ceil(now.month / 3) - 1;

    if (quarter === 0) {
      year -= 1;
      quarter = 4;
    }

    return { year, quarter };
  }
}
