"""TDD: 17:30 的完整度報告不該為「晚間 20:00 才載入」的當日股價與因子發警報。"""

from datetime import datetime, timedelta

import pytest

from scripts import twse_openapi_sync as sync

pytestmark = pytest.mark.integration

TODAY = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
D1, D2 = TODAY - timedelta(days=1), TODAY - timedelta(days=2)
DEFER = ("stock_price", "stock_factors")


def lag_lines(fail_list, table):
    return [f for f in fail_list if f.startswith(f"❌ {table}:") and "落後" in f]


def rows(day, count):
    return [{"symbol": f"{1000 + i}", "date": day, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1} for i in range(count)]


@pytest.fixture
def db(write_db):
    for name in ("stock_price", "stock_factors", "day_trading_targets"):
        write_db[name].drop()
    write_db["stock_price"].insert_many(rows(D2, 4100) + rows(D1, 4100))          # 昨天完整，今天尚未載入
    write_db["stock_factors"].insert_many(rows(D1, 1900))
    write_db["day_trading_targets"].insert_one({"stock_id": "2330", "date": TODAY})   # 讓今天成為參考交易日
    return write_db


def test_deferral_applies_only_before_the_evening_pipeline_starts():
    assert sync.deferred_tables(datetime(2026, 10, 12, 17, 30)) == DEFER
    assert sync.deferred_tables(datetime(2026, 10, 12, 19, 59)) == DEFER
    assert sync.deferred_tables(datetime(2026, 10, 12, 20, 0)) == ()
    assert sync.deferred_tables(datetime(2026, 10, 12, 23, 0)) == ()


def test_by_default_a_table_one_trading_day_behind_is_reported(db):
    _, fail = sync.check_integrity(db)

    assert lag_lines(fail, "stock_price") and lag_lines(fail, "stock_factors")


def test_a_deferred_table_one_day_behind_is_ok_and_says_why(db):
    ok, fail = sync.check_integrity(db, defer_lag=DEFER)

    assert not lag_lines(fail, "stock_price") and not lag_lines(fail, "stock_factors")
    assert any(line.startswith("✅ stock_price:") and "晚間管線" in line for line in ok)
    assert any(line.startswith("✅ stock_factors:") and "晚間管線" in line for line in ok)


def test_a_deferred_table_two_days_behind_is_still_reported(db):
    db["stock_factors"].delete_many({})
    db["stock_factors"].insert_many(rows(D2, 1900))

    _, fail = sync.check_integrity(db, defer_lag=DEFER)

    assert lag_lines(fail, "stock_factors") and not lag_lines(fail, "stock_price")
