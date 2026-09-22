"""資料品質監控測試 —— 新鮮度 / 覆蓋率 / 文件驗證。"""
from datetime import datetime, timedelta

import pytest

from src.monitoring.data_quality import (check_coverage, check_freshness,
                                         run_health_check, validate_document)


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *a, **k):
        # 依第一個排序鍵 desc（測試資料已預排）
        return self

    def limit(self, n):
        return self._docs[:n]


class _Coll:
    def __init__(self, docs):
        self._docs = docs

    def find(self, *a, **k):
        return _Cursor(self._docs)

    def find_one(self, *a, **k):
        return self._docs[0] if self._docs else None

    def count_documents(self, *a, **k):
        return len(self._docs)


class _DB:
    def __init__(self, data):
        self._data = data

    def __getitem__(self, name):
        return _Coll(self._data.get(name, []))


@pytest.mark.unit
def test_check_freshness_flags_stale_collection():
    today = datetime(2026, 9, 22)
    db = _DB({
        "stock_price": [{"date": today - timedelta(days=1)}],   # 新鮮
        "financial_reports": [{"date": today - timedelta(days=40)}],  # 過期
    })
    specs = {
        "stock_price": {"date_field": "date", "max_age_days": 3},
        "financial_reports": {"date_field": "date", "max_age_days": 30},
    }
    result = check_freshness(db, specs, now=today)
    by = {r["collection"]: r for r in result}
    assert by["stock_price"]["stale"] is False
    assert by["financial_reports"]["stale"] is True
    assert by["financial_reports"]["age_days"] == 40


@pytest.mark.unit
def test_check_freshness_flags_empty_collection():
    db = _DB({"stock_price": []})
    result = check_freshness(db, {"stock_price": {"date_field": "date", "max_age_days": 3}},
                             now=datetime(2026, 9, 22))
    assert result[0]["stale"] is True
    assert result[0]["latest"] is None


@pytest.mark.unit
def test_check_freshness_parses_string_dates():
    """部分集合日期存為字串（如 macro_indicators 'date'），須能解析算齡。"""
    today = datetime(2026, 9, 22)
    db = _DB({
        "macro_indicators": [{"date": "2026-09-22"}],       # 新鮮字串日
        "monthly_revenue": [{"ym": "2026-06"}],             # 過期字串月
    })
    r = check_freshness(db, {
        "macro_indicators": {"date_field": "date", "max_age_days": 5},
        "monthly_revenue": {"date_field": "ym", "max_age_days": 40},
    }, now=today)
    by = {x["collection"]: x for x in r}
    assert by["macro_indicators"]["age_days"] == 0 and by["macro_indicators"]["stale"] is False
    assert by["monthly_revenue"]["stale"] is True   # 2026-06 距 09-22 > 40 天


@pytest.mark.unit
def test_check_coverage():
    db = _DB({"tickers": [{"s": i} for i in range(1500)]})
    ok = check_coverage(db, "tickers", min_count=1000)
    low = check_coverage(db, "tickers", min_count=2000)
    assert ok["ok"] is True and ok["count"] == 1500
    assert low["ok"] is False


@pytest.mark.unit
def test_validate_document_range_rules():
    rules = {"pe": (0, 100), "eps": (-50, 100)}
    assert validate_document({"pe": 15, "eps": 3.2}, rules) == []
    v = validate_document({"pe": 250, "eps": 3.2}, rules)
    assert len(v) == 1 and "pe" in v[0]


@pytest.mark.unit
def test_validate_document_missing_field():
    rules = {"pe": (0, 100)}
    v = validate_document({"eps": 1}, rules)
    assert any("pe" in x and "缺" in x for x in v)


@pytest.mark.unit
def test_run_health_check_aggregates_and_flags():
    today = datetime(2026, 9, 22)
    db = _DB({
        "stock_price": [{"date": today}],
        "financial_reports": [{"date": today - timedelta(days=99)}],
        "tickers": [{"s": i} for i in range(1500)],
    })
    config = {
        "freshness": {
            "stock_price": {"date_field": "date", "max_age_days": 3},
            "financial_reports": {"date_field": "date", "max_age_days": 30},
        },
        "coverage": {"tickers": 1000},
    }
    report = run_health_check(db, config, now=today)
    assert report["ok"] is False           # financial_reports 過期
    assert report["stale_count"] == 1
    assert any("financial_reports" in a for a in report["alerts"])
