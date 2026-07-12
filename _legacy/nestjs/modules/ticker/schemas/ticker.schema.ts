import { Prop, Schema, SchemaFactory } from '@nestjs/mongoose';
import { Document, Schema as MongooseSchema } from 'mongoose';

export type TickerDocument = Ticker & Document;

/**
 * Ticker Schema - 個股每日行情
 * 包含價格、成交量、三大法人買賣超
 * 
 * 🔄 2026-02-20 Schema 更新：
 * - 所有金額欄位改用 Decimal128（確保精度）
 * - 移除相容欄位（close, volume 已統一為 closePrice, tradeVolume）
 * - 加入欄位驗證（價格邏輯、漲跌幅範圍）
 */
@Schema({ timestamps: true, collection: 'tickers' })
export class Ticker {
  @Prop({ 
    required: true, 
    index: true,
    validate: {
      validator: (v: string) => /^\d{4}-\d{2}-\d{2}$/.test(v),
      message: '日期格式必須為 YYYY-MM-DD'
    }
  })
  date: string; // YYYY-MM-DD

  @Prop({ 
    required: true, 
    index: true,
    validate: {
      validator: (v: string) => /^\d{4}$/.test(v),
      message: '股票代碼必須為 4 位數字'
    }
  })
  symbol: string; // 股票代碼

  @Prop({ required: true })
  name: string; // 股票名稱

  @Prop()
  type: string; // 類型 (股票/ETF)

  @Prop()
  exchange: string; // 交易所 (TWSE/TPEx)

  @Prop()
  market: string; // 市場類別

  // 價格資料（使用 Decimal128 確保精度）
  @Prop({ 
    required: true,
    type: MongooseSchema.Types.Decimal128,
    validate: {
      validator: function(v: any) {
        const num = parseFloat(v.toString());
        return num > 0;
      },
      message: '開盤價必須大於 0'
    }
  })
  openPrice: MongooseSchema.Types.Decimal128; // 開盤價

  @Prop({ 
    required: true,
    type: MongooseSchema.Types.Decimal128,
    validate: {
      validator: function(v: any) {
        const num = parseFloat(v.toString());
        return num > 0;
      },
      message: '最高價必須大於 0'
    }
  })
  highPrice: MongooseSchema.Types.Decimal128; // 最高價

  @Prop({ 
    required: true,
    type: MongooseSchema.Types.Decimal128,
    validate: {
      validator: function(v: any) {
        const num = parseFloat(v.toString());
        return num > 0;
      },
      message: '最低價必須大於 0'
    }
  })
  lowPrice: MongooseSchema.Types.Decimal128; // 最低價

  @Prop({ 
    required: true,
    type: MongooseSchema.Types.Decimal128,
    validate: {
      validator: function(v: any) {
        const num = parseFloat(v.toString());
        return num > 0;
      },
      message: '收盤價必須大於 0'
    }
  })
  closePrice: MongooseSchema.Types.Decimal128; // 收盤價

  // 🔄 相容欄位（過渡期保留，未來版本將移除）
  @Prop({ type: MongooseSchema.Types.Decimal128 })
  close?: MongooseSchema.Types.Decimal128; // @deprecated 請使用 closePrice

  @Prop({ type: MongooseSchema.Types.Decimal128 })
  change: MongooseSchema.Types.Decimal128; // 漲跌

  @Prop({ 
    type: MongooseSchema.Types.Decimal128,
    validate: {
      validator: function(v: any) {
        const num = parseFloat(v.toString());
        return num >= -10 && num <= 10;
      },
      message: '漲跌幅必須在 -10% ~ +10% 之間'
    }
  })
  changePercent: MongooseSchema.Types.Decimal128; // 漲跌幅 (%)

  // 成交資料
  @Prop({ 
    required: true,
    type: Number,
    validate: {
      validator: Number.isInteger,
      message: '成交量必須為整數'
    }
  })
  tradeVolume: number; // 成交量 (股)

  // 🔄 相容欄位（過渡期保留，未來版本將移除）
  @Prop({ type: Number })
  volume?: number; // @deprecated 請使用 tradeVolume

  @Prop({ type: MongooseSchema.Types.Decimal128 })
  tradeValue: MongooseSchema.Types.Decimal128; // 成交金額 (元)

  @Prop({ type: Number })
  transaction: number; // 成交筆數

  @Prop({ type: MongooseSchema.Types.Decimal128 })
  tradeWeight: MongooseSchema.Types.Decimal128; // 成交比重 (%)

  // 三大法人 (整合在行情中以優化查詢)
  @Prop({ 
    default: 0,
    type: MongooseSchema.Types.Decimal128
  })
  finiNetBuySell: MongooseSchema.Types.Decimal128; // 外資買賣超 (張)

  @Prop({ 
    default: 0,
    type: MongooseSchema.Types.Decimal128
  })
  sitcNetBuySell: MongooseSchema.Types.Decimal128; // 投信買賣超 (張)

  @Prop({ 
    default: 0,
    type: MongooseSchema.Types.Decimal128
  })
  dealersNetBuySell: MongooseSchema.Types.Decimal128; // 自營商買賣超 (張)

  // 時間戳記
  createdAt: Date;
  updatedAt: Date;
}

export const TickerSchema = SchemaFactory.createForClass(Ticker);

// 複合索引
TickerSchema.index({ date: -1, symbol: 1 }, { unique: true });
TickerSchema.index({ symbol: 1, date: -1 });
TickerSchema.index({ date: -1 });
TickerSchema.index({ changePercent: -1 });
TickerSchema.index({ tradeVolume: -1 }); // 更新為 tradeVolume

// Document Middleware - 價格邏輯驗證
TickerSchema.pre('save', function(next) {
  const high = parseFloat(this.highPrice.toString());
  const low = parseFloat(this.lowPrice.toString());
  const close = parseFloat(this.closePrice.toString());
  const open = parseFloat(this.openPrice.toString());
  
  // 驗證：最高價 >= 收盤價 >= 最低價
  if (high < close || close < low) {
    next(new Error('價格邏輯錯誤：highPrice >= closePrice >= lowPrice'));
    return;
  }
  
  // 驗證：最高價 >= 開盤價 >= 最低價
  if (high < open || open < low) {
    next(new Error('價格邏輯錯誤：highPrice >= openPrice >= lowPrice'));
    return;
  }
  
  // 同步相容欄位（過渡期）
  if (this.closePrice && !this.close) {
    this.close = this.closePrice;
  }
  
  if (this.tradeVolume && !this.volume) {
    this.volume = this.tradeVolume;
  }
  
  next();
});
