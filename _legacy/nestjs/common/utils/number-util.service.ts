import { Injectable } from '@nestjs/common';
import numeral from 'numeral';

/**
 * 數字工具服務
 * 處理數字格式化與計算
 */
@Injectable()
export class NumberUtilService {
  /**
   * 格式化數字為千分位
   */
  formatNumber(value: number, format = '0,0'): string {
    return numeral(value).format(format);
  }

  /**
   * 格式化為百分比
   */
  formatPercent(value: number, decimals = 2): string {
    return numeral(value / 100).format(`0.[${'0'.repeat(decimals)}]%`);
  }

  /**
   * 格式化金額（萬/億）
   */
  formatAmount(value: number): string {
    if (value >= 100000000) {
      return numeral(value / 100000000).format('0.00') + '億';
    } else if (value >= 10000) {
      return numeral(value / 10000).format('0.00') + '萬';
    }
    return numeral(value).format('0,0');
  }

  /**
   * 計算變化率 (%)
   */
  calculateChange(current: number, previous: number): number {
    if (!previous || previous === 0) return 0;
    return ((current - previous) / previous) * 100;
  }

  /**
   * 計算平均值
   */
  average(values: number[]): number {
    if (!values || values.length === 0) return 0;
    const sum = values.reduce((acc, val) => acc + val, 0);
    return sum / values.length;
  }

  /**
   * 計算標準差
   */
  standardDeviation(values: number[]): number {
    if (!values || values.length === 0) return 0;
    const avg = this.average(values);
    const squareDiffs = values.map((value) => Math.pow(value - avg, 2));
    const avgSquareDiff = this.average(squareDiffs);
    return Math.sqrt(avgSquareDiff);
  }

  /**
   * 四捨五入到指定位數
   */
  round(value: number, decimals = 2): number {
    return Math.round(value * Math.pow(10, decimals)) / Math.pow(10, decimals);
  }

  /**
   * 安全除法（避免除以零）
   */
  safeDivide(numerator: number, denominator: number, defaultValue = 0): number {
    if (!denominator || denominator === 0) return defaultValue;
    return numerator / denominator;
  }

  /**
   * 計算百分位數
   */
  percentile(values: number[], percentile: number): number {
    if (!values || values.length === 0) return 0;
    const sorted = [...values].sort((a, b) => a - b);
    const index = (percentile / 100) * (sorted.length - 1);
    const lower = Math.floor(index);
    const upper = Math.ceil(index);
    const weight = index % 1;

    if (lower === upper) return sorted[lower];
    return sorted[lower] * (1 - weight) + sorted[upper] * weight;
  }

  /**
   * 檢查數值是否在範圍內
   */
  inRange(value: number, min: number, max: number): boolean {
    return value >= min && value <= max;
  }
}
