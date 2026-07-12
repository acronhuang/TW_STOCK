import { Injectable, Inject } from '@nestjs/common';
import { CACHE_MANAGER } from '@nestjs/cache-manager';
import { Cache } from 'cache-manager';

/**
 * 快取工具服務
 * 提供統一的快取 Key 生成與管理
 */
@Injectable()
export class CacheUtilService {
  constructor(@Inject(CACHE_MANAGER) private cacheManager: Cache) {}

  /**
   * 生成快取 Key
   */
  generateKey(prefix: string, params: Record<string, any>): string {
    const paramStr = Object.entries(params)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([key, value]) => `${key}:${value}`)
      .join(':');
    return `${prefix}:${paramStr}`;
  }

  /**
   * 取得快取
   */
  async get<T>(key: string): Promise<T | undefined> {
    return await this.cacheManager.get<T>(key);
  }

  /**
   * 設定快取
   */
  async set(key: string, value: any, ttl?: number): Promise<void> {
    await this.cacheManager.set(key, value, ttl);
  }

  /**
   * 刪除快取
   */
  async del(key: string): Promise<void> {
    await this.cacheManager.del(key);
  }

  /**
   * 清空所有快取
   */
  async reset(): Promise<void> {
    await this.cacheManager.reset();
  }

  /**
   * 取得或設定快取
   */
  async getOrSet<T>(
    key: string,
    factory: () => Promise<T>,
    ttl?: number,
  ): Promise<T> {
    let value = await this.get<T>(key);

    if (value === undefined) {
      value = await factory();
      await this.set(key, value, ttl);
    }

    return value;
  }

  /**
   * 產生個股快取 Key
   */
  tickerKey(symbol: string, date?: string): string {
    return date
      ? `ticker:${symbol}:${date}`
      : `ticker:${symbol}:latest`;
  }

  /**
   * 產生技術指標快取 Key
   */
  technicalKey(symbol: string, date?: string): string {
    return date
      ? `technical:${symbol}:${date}`
      : `technical:${symbol}:latest`;
  }

  /**
   * 產生財報快取 Key
   */
  financialKey(symbol: string, year: number, quarter: number): string {
    return `financial:${symbol}:${year}:Q${quarter}`;
  }

  /**
   * 產生產業快取 Key
   */
  industryKey(code: string): string {
    return `industry:${code}`;
  }

  /**
   * 產生排行榜快取 Key
   */
  rankingKey(type: string, date: string): string {
    return `ranking:${type}:${date}`;
  }
}
