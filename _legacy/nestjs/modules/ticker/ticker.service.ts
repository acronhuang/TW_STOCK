import { Injectable, NotFoundException } from '@nestjs/common';
import { InjectModel } from '@nestjs/mongoose';
import { Model } from 'mongoose';
import { Ticker, TickerDocument } from './schemas/ticker.schema';
import { DateUtilService } from '@/common/utils/date-util.service';
import { CacheUtilService } from '@/common/utils/cache-util.service';

@Injectable()
export class TickerService {
  constructor(
    @InjectModel(Ticker.name)
    private tickerModel: Model<TickerDocument>,
    private dateUtil: DateUtilService,
    private cacheUtil: CacheUtilService,
  ) {}

  /**
   * 取得單一股票最新資料
   */
  async getLatest(symbol: string): Promise<Ticker> {
    const cacheKey = this.cacheUtil.tickerKey(symbol);

    return this.cacheUtil.getOrSet(
      cacheKey,
      async () => {
        const ticker = await this.tickerModel
          .findOne({ symbol })
          .sort({ date: -1 })
          .lean()
          .exec();

        if (!ticker) {
          throw new NotFoundException(`找不到股票代碼: ${symbol}`);
        }

        return ticker;
      },
      60 * 1000, // 快取 60 秒 (需使用毫秒)
    );
  }

  /**
   * 取得單一股票指定日期資料
   */
  async getByDate(symbol: string, date: string): Promise<Ticker> {
    const cacheKey = this.cacheUtil.tickerKey(symbol, date);

    return this.cacheUtil.getOrSet(
      cacheKey,
      async () => {
        const ticker = await this.tickerModel
          .findOne({ symbol, date })
          .lean()
          .exec();

        if (!ticker) {
          throw new NotFoundException(`找不到 ${symbol} 在 ${date} 的資料`);
        }

        return ticker;
      },
      300 * 1000, // 快取 5 分鐘
    );
  }

  /**
   * 取得單一股票歷史資料
   */
  async getHistory(
    symbol: string,
    startDate?: string,
    endDate?: string,
    days = 60,
  ): Promise<Ticker[]> {
    const query: any = { symbol };

    if (startDate && endDate) {
      query.date = { $gte: startDate, $lte: endDate };
    } else if (startDate) {
      query.date = { $gte: startDate };
    } else {
      // 預設取最近 N 天
      const end = endDate || this.dateUtil.yesterday();
      const start = this.dateUtil.daysAgo(days);
      query.date = { $gte: start, $lte: end };
    }

    return this.tickerModel
      .find(query)
      .sort({ date: -1 })
      .limit(days)
      .lean()
      .exec();
  }

  /**
   * 取得指定日期全市場資料
   */
  async getByDateAll(date: string): Promise<Ticker[]> {
    const cacheKey = `tickers:all:${date}`;

    return this.cacheUtil.getOrSet(
      cacheKey,
      async () => {
        return this.tickerModel.find({ date }).sort({ symbol: 1 }).lean().exec();
      },
      300 * 1000, // 5 分鐘
    );
  }

  /**
   * 取得漲幅排行
   */
  async getTopGainers(date?: string, limit = 20): Promise<Ticker[]> {
    const queryDate = date || this.dateUtil.yesterday();
    const cacheKey = this.cacheUtil.rankingKey('gainers', queryDate);

    return this.cacheUtil.getOrSet(
      cacheKey,
      async () => {
        return this.tickerModel
          .find({ date: queryDate, changePercent: { $gt: 0 } })
          .sort({ changePercent: -1 })
          .limit(limit)
          .lean()
          .exec();
      },
      60 * 1000, // 60 秒
    );
  }

  /**
   * 取得跌幅排行
   */
  async getTopLosers(date?: string, limit = 20): Promise<Ticker[]> {
    const queryDate = date || this.dateUtil.yesterday();
    const cacheKey = this.cacheUtil.rankingKey('losers', queryDate);

    return this.cacheUtil.getOrSet(
      cacheKey,
      async () => {
        return this.tickerModel
          .find({ date: queryDate, changePercent: { $lt: 0 } })
          .sort({ changePercent: 1 })
          .limit(limit)
          .lean()
          .exec();
      },
      60 * 1000, // 60 秒
    );
  }

  /**
   * 取得成交量排行
   */
  async getTopVolume(date?: string, limit = 20): Promise<Ticker[]> {
    const queryDate = date || this.dateUtil.yesterday();
    const cacheKey = this.cacheUtil.rankingKey('volume', queryDate);

    return this.cacheUtil.getOrSet(
      cacheKey,
      async () => {
        return this.tickerModel
          .find({ date: queryDate })
          .sort({ volume: -1 })
          .limit(limit)
          .lean()
          .exec();
      },
      60 * 1000, // 60 秒
    );
  }

  /**
   * 建立或更新股票資料
   */
  async upsert(tickerData: Partial<Ticker>): Promise<Ticker> {
    const { symbol, date } = tickerData;

    return this.tickerModel
      .findOneAndUpdate(
        { symbol, date },
        { $set: tickerData },
        { upsert: true, new: true },
      )
      .lean()
      .exec();
  }

  /**
   * 批次建立或更新
   */
  async bulkUpsert(tickersData: Partial<Ticker>[]): Promise<number> {
    const operations = tickersData.map((data) => ({
      updateOne: {
        filter: { symbol: data.symbol, date: data.date },
        update: { $set: data },
        upsert: true,
      },
    }));

    const result = await this.tickerModel.bulkWrite(operations);
    return result.upsertedCount + result.modifiedCount;
  }
}
