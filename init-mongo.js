// MongoDB 初始化腳本
// 建立資料庫、集合與索引

db = db.getSiblingDB('tw_stock_analysis');

print('🚀 開始初始化台股分析資料庫...');

// ==================== 1. 核心行情資料 ====================

// 1.1 Tickers (個股行情)
db.createCollection('tickers');
db.tickers.createIndex({ date: -1, symbol: 1 }, { unique: true, name: 'idx_date_symbol_unique' });
db.tickers.createIndex({ symbol: 1, date: -1 }, { name: 'idx_symbol_date' });
db.tickers.createIndex({ date: -1 }, { name: 'idx_date' });
db.tickers.createIndex({ changePercent: -1 }, { name: 'idx_change_percent' });
db.tickers.createIndex({ volume: -1 }, { name: 'idx_volume' });
print('✅ 已建立 tickers 集合與索引');

// 1.2 Technical Indicators (技術指標)
db.createCollection('technical_indicators');
db.technical_indicators.createIndex({ symbol: 1, date: -1 }, { name: 'idx_symbol_date' });
db.technical_indicators.createIndex({ date: -1, symbol: 1 }, { name: 'idx_date_symbol' });
print('✅ 已建立 technical_indicators 集合與索引');

// ==================== 2. 財務報表資料 ====================

// 2.1 Financial Reports (財務報表)
db.createCollection('financial_reports');
db.financial_reports.createIndex({ symbol: 1, year: -1, quarter: -1 }, { unique: true, name: 'idx_symbol_year_quarter' });
db.financial_reports.createIndex({ year: -1, quarter: -1 }, { name: 'idx_year_quarter' });
print('✅ 已建立 financial_reports 集合與索引');

// 2.2 Monthly Revenue (月營收)
db.createCollection('monthly_revenues');
db.monthly_revenues.createIndex({ symbol: 1, year: -1, month: -1 }, { unique: true, name: 'idx_symbol_year_month' });
db.monthly_revenues.createIndex({ year: -1, month: -1 }, { name: 'idx_year_month' });
db.monthly_revenues.createIndex({ yoyGrowth: -1 }, { name: 'idx_yoy_growth' });
db.monthly_revenues.createIndex({ momGrowth: -1 }, { name: 'idx_mom_growth' });
print('✅ 已建立 monthly_revenues 集合與索引');

// 2.3 Profitability (獲利能力)
db.createCollection('profitability');
db.profitability.createIndex({ symbol: 1, year: -1, quarter: -1 }, { name: 'idx_symbol_year_quarter' });
db.profitability.createIndex({ roe: -1 }, { name: 'idx_roe' });
db.profitability.createIndex({ roa: -1 }, { name: 'idx_roa' });
db.profitability.createIndex({ netMargin: -1 }, { name: 'idx_net_margin' });
print('✅ 已建立 profitability 集合與索引');

// ==================== 3. 估值與股利 ====================

// 3.1 Valuation River (PE/PB 河流圖)
db.createCollection('valuation_rivers');
db.valuation_rivers.createIndex({ symbol: 1, date: -1 }, { name: 'idx_symbol_date' });
db.valuation_rivers.createIndex({ date: -1 }, { name: 'idx_date' });
db.valuation_rivers.createIndex({ pePercentile: 1 }, { name: 'idx_pe_percentile' });
db.valuation_rivers.createIndex({ pbPercentile: 1 }, { name: 'idx_pb_percentile' });
db.valuation_rivers.createIndex({ valuationScore: -1 }, { name: 'idx_valuation_score' });
print('✅ 已建立 valuation_rivers 集合與索引');

// 3.2 Dividends (股利政策)
db.createCollection('dividends');
db.dividends.createIndex({ symbol: 1, year: -1 }, { unique: true, name: 'idx_symbol_year' });
db.dividends.createIndex({ year: -1, dividendYield: -1 }, { name: 'idx_year_yield' });
db.dividends.createIndex({ year: -1, cashDividend: -1 }, { name: 'idx_year_cash' });
print('✅ 已建立 dividends 集合與索引');

// ==================== 4. 籌碼資料 ====================

// 4.1 Shareholders (股東結構)
db.createCollection('shareholders');
db.shareholders.createIndex({ symbol: 1, date: -1 }, { name: 'idx_symbol_date' });
db.shareholders.createIndex({ symbol: 1, year: -1, quarter: -1 }, { name: 'idx_symbol_year_quarter' });
db.shareholders.createIndex({ date: -1 }, { name: 'idx_date' });
print('✅ 已建立 shareholders 集合與索引');

// 4.2 Director Holdings (董監持股)
db.createCollection('director_holdings');
db.director_holdings.createIndex({ symbol: 1, date: -1 }, { name: 'idx_symbol_date' });
print('✅ 已建立 director_holdings 集合與索引');

// 4.3 Institutional Trades (法人買賣)
db.createCollection('institutional_trades');
db.institutional_trades.createIndex({ symbol: 1, date: -1 }, { name: 'idx_symbol_date' });
db.institutional_trades.createIndex({ date: -1, finiNetBuy: -1 }, { name: 'idx_date_fini' });
print('✅ 已建立 institutional_trades 集合與索引');

// ==================== 5. 產業資料 ====================

// 5.1 Industries (產業分類)
db.createCollection('industries');
db.industries.createIndex({ code: 1 }, { unique: true, name: 'idx_code' });
db.industries.createIndex({ category: 1 }, { name: 'idx_category' });
print('✅ 已建立 industries 集合與索引');

// 5.2 Stock Industries (個股產業對應)
db.createCollection('stock_industries');
db.stock_industries.createIndex({ symbol: 1 }, { unique: true, name: 'idx_symbol' });
db.stock_industries.createIndex({ industryCode: 1 }, { name: 'idx_industry_code' });
print('✅ 已建立 stock_industries 集合與索引');

// 5.3 Industry Heats (產業熱度)
db.createCollection('industry_heats');
db.industry_heats.createIndex({ date: -1, heatScore: -1 }, { name: 'idx_date_heat' });
db.industry_heats.createIndex({ industryCode: 1, date: -1 }, { name: 'idx_industry_date' });
print('✅ 已建立 industry_heats 集合與索引');

// ==================== 6. 分析與策略 ====================

// 6.1 Volume Price Analysis (量價分析)
db.createCollection('volume_price_analysis');
db.volume_price_analysis.createIndex({ symbol: 1, date: -1 }, { name: 'idx_symbol_date' });
db.volume_price_analysis.createIndex({ date: -1, score: -1 }, { name: 'idx_date_score' });
print('✅ 已建立 volume_price_analysis 集合與索引');

// 6.2 Strategy Recommendations (策略推薦)
db.createCollection('strategy_recommendations');
db.strategy_recommendations.createIndex({ date: -1, confidence: -1 }, { name: 'idx_date_confidence' });
db.strategy_recommendations.createIndex({ symbol: 1, date: -1 }, { name: 'idx_symbol_date' });
print('✅ 已建立 strategy_recommendations 集合與索引');

// 6.3 Data Integrity Logs (資料完整性日誌)
db.createCollection('data_integrity_logs');
db.data_integrity_logs.createIndex({ date: -1 }, { name: 'idx_date' });
db.data_integrity_logs.createIndex({ collectionName: 1, date: -1 }, { name: 'idx_collection_date' });
print('✅ 已建立 data_integrity_logs 集合與索引');

// ==================== 7. 系統資料 ====================

// 7.1 System Logs (系統日誌)
db.createCollection('system_logs', {
  capped: true,
  size: 104857600, // 100MB
  max: 100000
});
print('✅ 已建立 system_logs 集合 (Capped)');

print('');
print('✨ 資料庫初始化完成！');
print('📊 已建立 17 個集合');
print('🔍 已建立 40+ 個索引');
print('');
print('💡 提示：使用 db.getCollectionNames() 查看所有集合');
print('💡 提示：使用 db.<collection>.getIndexes() 查看索引');
