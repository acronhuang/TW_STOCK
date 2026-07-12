import { Injectable } from '@nestjs/common';
import { InjectConnection } from '@nestjs/mongoose';
import { Connection } from 'mongoose';
import { CacheUtilService } from '@/common/utils/cache-util.service';

@Injectable()
export class HealthService {
  constructor(
    @InjectConnection() private connection: Connection,
    private cacheUtil: CacheUtilService,
  ) {}

  async check() {
    return {
      status: 'ok',
      timestamp: new Date().toISOString(),
      uptime: process.uptime(),
      environment: process.env.NODE_ENV || 'development',
    };
  }

  async checkDatabase() {
    const isConnected = this.connection.readyState === 1;

    return {
      status: isConnected ? 'ok' : 'error',
      connected: isConnected,
      database: this.connection.name,
      collections: await this.connection.db.listCollections().toArray(),
    };
  }

  async checkCache() {
    try {
      const testKey = 'health:check';
      await this.cacheUtil.set(testKey, 'ok', 10);
      const value = await this.cacheUtil.get(testKey);
      await this.cacheUtil.del(testKey);

      return {
        status: value === 'ok' ? 'ok' : 'error',
        connected: true,
      };
    } catch (error) {
      return {
        status: 'error',
        connected: false,
        error: error.message,
      };
    }
  }
}
