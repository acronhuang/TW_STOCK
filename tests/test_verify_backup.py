"""TDD: 還原演練要連帳本與指紋鏈一起檢查，而且關鍵表清單包含補不回來的資料。"""

from datetime import datetime

import pytest
from bson.decimal128 import Decimal128

from scripts import verify_backup as drill
from src.ops import audit_chain as chain

pytestmark = pytest.mark.integration


@pytest.fixture
def db(write_db):
    for name in (*chain.LEDGERS, chain.CHAIN):
        write_db[name].drop()
    write_db["portfolio_trades"].insert_many([
        {"symbol": "2330", "price": Decimal128("1100.5"), "date": datetime(2026, 10, 9)},
        {"symbol": "2317", "price": Decimal128("210.0"), "date": datetime(2026, 10, 9)},
    ])
    return write_db


def test_a_restored_ledger_that_matches_its_chain_passes(db):
    chain.register(db, "portfolio_trades", datetime(2026, 10, 13))

    ok, line = drill.restored_chain_line(db)

    assert ok and "2 筆通過" in line


def test_a_restored_ledger_row_that_differs_from_the_chain_fails(db):
    chain.register(db, "portfolio_trades", datetime(2026, 10, 13))
    db["portfolio_trades"].update_one({"symbol": "2330"}, {"$set": {"price": Decimal128("1")}})

    ok, line = drill.restored_chain_line(db)

    assert not ok and "1 項異常" in line


def test_a_backup_without_any_chain_fails_instead_of_passing_an_empty_check(db):
    ok, line = drill.restored_chain_line(db)

    assert not ok and "沒有鏈" in line


def test_the_key_tables_include_the_data_that_cannot_be_rebuilt():
    for name in ("research_signal_snapshots", "portfolio_trades", "audit_chain", "wiki_raw", "team_analysis", "verdict_detail"):
        assert name in drill.KEY_COLLECTIONS


def test_a_restored_ledger_missing_a_row_the_chain_remembers_fails(db):
    chain.register(db, "portfolio_trades", datetime(2026, 10, 13))
    db["portfolio_trades"].delete_one({"symbol": "2317"})

    ok, line = drill.restored_chain_line(db)

    assert not ok and "1 項異常" in line
