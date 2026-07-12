"""資料完整性測試 — 確保 MongoDB 集合與欄位健康"""
import pytest
from datetime import datetime, timedelta


class TestCollections:
    @pytest.mark.integration
    def test_stock_price_exists(self, db):
        count = db.stock_price.count_documents({})
        assert count > 100_000, f'stock_price 筆數異常: {count}'

    @pytest.mark.integration
    def test_stock_factors_exists(self, db):
        count = db.stock_factors.count_documents({})
        assert count > 1000

    @pytest.mark.integration
    def test_dividend_detail_exists(self, db):
        count = db.dividend_detail.count_documents({})
        assert count > 1000


class TestDataFreshness:
    @pytest.mark.integration
    def test_stock_price_recent(self, db):
        """stock_price 最新日期不超過 5 天"""
        latest = db.stock_price.find_one({}, {'date': 1}, sort=[('date', -1)])
        assert latest is not None
        date = latest['date']
        if isinstance(date, str):
            date = datetime.fromisoformat(date)
        age = (datetime.now() - date).days
        assert age <= 5, f'stock_price 最新日期距今 {age} 天'

    @pytest.mark.integration
    def test_stock_factors_recent(self, db):
        latest = db.stock_factors.find_one({}, {'date': 1}, sort=[('date', -1)])
        assert latest is not None
        date = latest['date']
        if isinstance(date, str):
            date = datetime.fromisoformat(date)
        age = (datetime.now() - date).days
        assert age <= 5, f'stock_factors 最新日期距今 {age} 天'


class TestDataQuality:
    @pytest.mark.integration
    def test_2330_has_price(self, db):
        rec = db.stock_price.find_one({'symbol': '2330'}, sort=[('date', -1)])
        assert rec is not None
        from bson import Decimal128
        close = rec.get('close')
        if isinstance(close, Decimal128):
            close = float(close.to_decimal())
        assert close > 100, f'台積電股價異常: {close}'

    @pytest.mark.integration
    def test_stock_factors_has_pe(self, db):
        """至少 500 支股票有 PE 資料"""
        count = len(db.stock_factors.distinct('symbol', {'pe_ratio': {'$ne': None}}))
        assert count > 500, f'有 PE 的股票數: {count}'

    @pytest.mark.integration
    def test_no_negative_pe(self, db):
        """PE 不應有大量負值"""
        neg_count = db.stock_factors.count_documents({'pe_ratio': {'$lt': 0}})
        total = db.stock_factors.count_documents({'pe_ratio': {'$ne': None}})
        if total > 0:
            neg_pct = neg_count / total
            assert neg_pct < 0.1, f'負 PE 比例過高: {neg_pct:.1%}'
