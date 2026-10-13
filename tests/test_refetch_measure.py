"""TDD: 每小時重抓量測——只改時間戳記不算變動、內容變了要算、新文件另計、沒有可比對文件不給假的 0%。"""

import json

import pytest
from bson.decimal128 import Decimal128

from src.ops import refetch_measure as rm

pytestmark = pytest.mark.unit


def test_the_hash_ignores_the_id_and_timestamps_but_not_real_fields():
    a = {"_id": 1, "stock_id": "1101", "CashEarningsDistribution": Decimal128("1.5"), "updated_at": "2026-10-13T09:05"}
    b = {"_id": 2, "stock_id": "1101", "CashEarningsDistribution": Decimal128("1.5"), "updated_at": "2026-10-13T10:05"}

    assert rm.content_hash(a) == rm.content_hash(b)
    assert rm.content_hash(a) != rm.content_hash({**a, "CashEarningsDistribution": Decimal128("1.6")})


def test_compare_counts_changed_unchanged_and_new_separately():
    previous = {"a": "h1", "b": "h2", "c": "h3"}
    current = {"a": "h1", "b": "CHANGED", "d": "h4"}

    assert rm.compare(previous, current) == {"touched": 3, "compared": 2, "changed": 1, "new": 1}


def test_report_adds_up_consecutive_pairs_per_collection():
    def snap(ts, mapping):
        return {"ts": ts, "collections": {"dividend_detail": mapping}}

    snaps = [snap("t1", {"a": "1", "b": "1"}), snap("t2", {"a": "1", "b": "2"}), snap("t3", {"a": "1", "b": "2"})]

    row = rm.report(snaps)["dividend_detail"]

    assert row == {"touched": 4, "compared": 4, "changed": 1, "new": 0, "hours": 2}


def test_hourly_codes_reads_the_stocks_the_run_processed(tmp_path):
    log = tmp_path / "hourly_update_20261013_090501.log"
    log.write_text("09:05:16 | INFO |    [1/100] 1101... ✅ 13 筆\n09:05:17 | INFO |    [2/100] 1101B... ✅ 8 筆\n其他行\n", encoding="utf-8")

    assert rm.hourly_codes(log) == {"1101", "1101B"}


def test_snapshots_round_trip_and_a_missing_file_is_empty_not_an_error(tmp_path):
    path = tmp_path / "m.jsonl"
    assert rm.load_snapshots(path) == []
    path.write_text(json.dumps({"ts": "t", "collections": {}}) + "\n\n", encoding="utf-8")

    assert rm.load_snapshots(path) == [{"ts": "t", "collections": {}}]


def test_with_nothing_to_compare_the_report_is_not_a_zero_percent(tmp_path, capsys):
    from scripts import measure_hourly_refetch as script

    path = tmp_path / "m.jsonl"
    path.write_text(json.dumps({"ts": "2026-10-13T10:50", "collections": {"dividend_detail": {"a": "1"}}}) + "\n", encoding="utf-8")

    assert script.run_report(path) == 1
    assert "至少要 2 份" in capsys.readouterr().out

    second = {"ts": "2026-10-13T11:50", "collections": {"dividend_detail": {"b": "1"}}}
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(second) + "\n")
    assert script.run_report(path) == 0
    assert "無可比對文件" in capsys.readouterr().out
