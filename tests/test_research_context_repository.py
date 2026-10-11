"""TDD: 研究上下文 MongoDB repository 僅讀取白名單欄位。"""

from datetime import datetime

import pytest
from bson import Decimal128

from src.domain.collections import COLL_STOCK_FACTORS, COLL_TEAM_ANALYSIS
from src.research_context.repository import MongoResearchRepository


pytestmark = pytest.mark.integration


@pytest.fixture
def repository_db(write_db):
    for collection in (COLL_TEAM_ANALYSIS, COLL_STOCK_FACTORS):
        write_db[collection].delete_many({})
    yield write_db
    for collection in (COLL_TEAM_ANALYSIS, COLL_STOCK_FACTORS):
        write_db[collection].delete_many({})


def test_repository_returns_latest_allowlisted_team_summary(repository_db):
    repository_db[COLL_TEAM_ANALYSIS].insert_many(
        [
            {
                "symbol": "2330",
                "date": datetime(2026, 10, 7),
                "final_verdict": "買進",
                "consensus": {"tally": {"買進": 6}},
                "verify": {"status": "pending"},
            },
            {
                "symbol": "2330",
                "date": datetime(2026, 10, 8),
                "name": "台積電",
                "final_verdict": "持有",
                "consensus": {"tally": {"持有": 4}},
                "verify": {"status": "verified"},
                "role_reports": {"prompt": "must not escape"},
            },
        ]
    )

    result = MongoResearchRepository(repository_db).get_team_summary("2330")

    assert result.model_dump() == {
        "analysis_date": "2026-10-08",
        "final_verdict": "持有",
        "consensus_tally": {"持有": 4},
        "verify_status": "verified",
    }


def test_repository_returns_latest_factor_summary_with_decimal_values(repository_db):
    repository_db[COLL_STOCK_FACTORS].insert_many(
        [
            {
                "symbol": "2330",
                "date": datetime(2026, 10, 7),
                "pe": Decimal128("19.8"),
                "pb": Decimal128("4.7"),
            },
            {
                "symbol": "2330",
                "date": datetime(2026, 10, 8),
                "pe": Decimal128("20.1"),
                "pb": Decimal128("4.8"),
                "roe": Decimal128("28.0"),
                "rsi": Decimal128("52.0"),
                "dividend_yield": Decimal128("1.4"),
                "internal_note": "must not escape",
            },
        ]
    )

    result = MongoResearchRepository(repository_db).get_factor_summary("2330")

    assert result.model_dump() == {
        "date": "2026-10-08",
        "pe": 20.1,
        "pb": 4.8,
        "roe": 28.0,
        "rsi": 52.0,
        "dividend_yield": 1.4,
    }


def test_repository_returns_none_when_stock_has_no_research_data(repository_db):
    repository = MongoResearchRepository(repository_db)

    assert repository.get_team_summary("9999") is None
    assert repository.get_factor_summary("9999") is None