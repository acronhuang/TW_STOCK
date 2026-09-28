"""TDD:交易日曆 + 新鮮度連假不誤報。純函式/mongomock → @unit。"""
from datetime import date, datetime
import pytest
from src.monitoring.market_calendar import is_market_open, trading_days_behind
from src.monitoring.data_quality import check_freshness

mongomock = pytest.importorskip("mongomock")


@pytest.mark.unit
def test_weekend_is_closed_no_api():
    assert is_market_open(date(2026, 9, 26)) is False   # 週六
    assert is_market_open(date(2026, 9, 27)) is False   # 週日


@pytest.mark.unit
def test_trading_days_behind_skips_holidays():
    # 09-24(四)最後資料 → 今日 09-29(二);09-25/28 休市、26/27 週末
    holidays = {date(2026, 9, 25), date(2026, 9, 28)}
    is_open = lambda d: d not in holidays and d.weekday() < 5
    n = trading_days_behind(date(2026, 9, 24), datetime(2026, 9, 29, 8, 0), is_open_fn=is_open)
    assert n == 0                                        # 中間全休市/週末 → 0 個交易日落後


@pytest.mark.unit
def test_trading_days_behind_counts_real_gap():
    is_open = lambda d: d.weekday() < 5                  # 無假日,純工作日
    # 09-21(一)最後 → 09-24(四):中間 22(二)、23(三) 兩個交易日
    n = trading_days_behind(date(2026, 9, 21), datetime(2026, 9, 24, 8, 0), is_open_fn=is_open)
    assert n == 2


@pytest.mark.unit
def test_check_freshness_holiday_not_stale():
    db = mongomock.MongoClient()["t"]
    db["stock_price"].insert_one({"date": datetime(2026, 9, 24), "close": 1})
    specs = {"stock_price": {"date_field": "date", "max_age_days": 4}}
    now = datetime(2026, 9, 29, 8, 0)                    # 日曆 5 天 > 4 → 原本會 stale
    holidays = {date(2026, 9, 25), date(2026, 9, 28)}
    is_open = lambda d: d not in holidays and d.weekday() < 5
    # 無 is_open_fn:日曆計 → stale
    assert check_freshness(db, specs, now=now)[0]["stale"] is True
    # 有 is_open_fn:交易日計(連假不算)→ 不 stale
    r = check_freshness(db, specs, now=now, is_open_fn=is_open)[0]
    assert r["stale"] is False and r["age_days"] == 0
