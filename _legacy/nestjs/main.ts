import { NestFactory } from '@nestjs/core';
import { ValidationPipe, Logger } from '@nestjs/common';
import { SwaggerModule, DocumentBuilder } from '@nestjs/swagger';
import { NestExpressApplication } from '@nestjs/platform-express';
import { join } from 'path';
import { AppModule } from './app.module';

async function bootstrap() {
  const logger = new Logger('Bootstrap');
  const app = await NestFactory.create<NestExpressApplication>(AppModule);

  // 設定靜態檔案目錄
  app.useStaticAssets(join(__dirname, '..', 'public'), {
    prefix: '/public/',
  });

  // 設定模板引擎（Handlebars）
  app.setBaseViewsDir(join(__dirname, '..', 'views'));
  app.setViewEngine('hbs');

  // 註冊 Handlebars helpers
  const hbs = require('hbs');
  
  // 格式化數字（加千分位）
  hbs.registerHelper('formatNumber', function (value: number) {
    if (value === null || value === undefined) return '-';
    return value.toLocaleString('zh-TW', { maximumFractionDigits: 0 });
  });
  
  // 格式化百分比
  hbs.registerHelper('formatPercent', function (value: number) {
    if (value === null || value === undefined) return '-';
    return (value * 100).toFixed(2) + '%';
  });
  
  // 數學運算 - 除法
  hbs.registerHelper('divide', function (a: number, b: number) {
    if (!b) return 0;
    return a / b;
  });
  
  // 數學運算 - 減法
  hbs.registerHelper('subtract', function (a: number, b: number) {
    return a - b;
  });
  
  // 比較運算 - 大於
  hbs.registerHelper('gt', function (a: number, b: number) {
    return a > b;
  });
  
  // 比較運算 - 小於
  hbs.registerHelper('lt', function (a: number, b: number) {
    return a < b;
  });
  
  // 比較運算 - 等於
  hbs.registerHelper('eq', function (a: any, b: any) {
    return a == b;
  });
  
  // JSON stringify
  hbs.registerHelper('json', function (context: any) {
    return JSON.stringify(context);
  });

  // 全域驗證管道
  app.useGlobalPipes(
    new ValidationPipe({
      transform: true,
      whitelist: true,
      forbidNonWhitelisted: true,
    }),
  );

  // CORS 設定
  app.enableCors({
    origin: process.env.CORS_ORIGIN || '*',
    credentials: true,
  });

  // API 前綴（排除 view 路由）
  app.setGlobalPrefix('api/v1', {
    exclude: ['view', 'view/(.*)', 'public/(.*)'],
  });

  // Swagger API 文檔
  if (process.env.SWAGGER_ENABLED !== 'false') {
    const config = new DocumentBuilder()
      .setTitle('台股智能分析系統 API')
      .setDescription(
        '提供完整的台股資料查詢、技術分析、財務分析、籌碼分析與估值分析功能',
      )
      .setVersion('2.1.0')
      .addTag('tickers', '個股行情')
      .addTag('technical', '技術分析')
      .addTag('financial', '財務報表')
      .addTag('revenue', '月營收')
      .addTag('profitability', '獲利分析')
      .addTag('dividend', '股利政策')
      .addTag('valuation', '估值分析')
      .addTag('institutional', '法人買賣')
      .addTag('shareholder', '股東結構')
      .addTag('industry', '產業分析')
      .addTag('strategy', '交易策略')
      .addTag('system', '系統管理')
      .build();

    const document = SwaggerModule.createDocument(app, config);
    SwaggerModule.setup(
      process.env.SWAGGER_PATH || 'api-docs',
      app,
      document,
      {
        customSiteTitle: '台股智能分析系統 API 文檔',
        customCss: '.swagger-ui .topbar { display: none }',
      },
    );

    logger.log(
      `📚 Swagger 文檔已啟用: http://localhost:${process.env.PORT || 3000}/${process.env.SWAGGER_PATH || 'api-docs'}`,
    );
  }

  const port = process.env.PORT || 3000;
  await app.listen(port);

  logger.log(`🚀 應用程式已啟動: http://localhost:${port}`);
  logger.log(`📊 API 端點: http://localhost:${port}/api/v1`);
  logger.log(`💾 MongoDB: ${process.env.MONGODB_URI || 'mongodb://localhost:27018/tw_stock_analysis'}`);
  logger.log(`⚡ Redis: ${process.env.REDIS_HOST || 'localhost'}:${process.env.REDIS_PORT || 6380}`);
}

bootstrap();
