"""整合測試（真實 MongoDB，專用測試庫）：缺口回補的失敗路徑與快照表依真實日期重建。"""

from datetime import datetime, timedelta

import pytest

from scripts import redate_snapshot_tables
from scripts.data_gap_repair import MongoRegister
from src.data_gap import redate, runner
from src.data_gap.models import Gap

pytestmark = pytest.mark.integration

START = datetime(2026, 10, 12, 6, 10)


def test_a_repair_that_keeps_failing_ends_as_failed_with_one_alert_and_stays_failed_across_restarts(write_db):
    write_db["data_gap_register"].delete_many({})
    write_db["schedule_alerts"].delete_many({})
    attempts = []

    def execute(command):
        attempts.append(command)
        raise RuntimeError("upstream blocked")

    def alert(message):
        write_db["schedule_alerts"].insert_one({"ts": START, "source": "data_gap_repair", "message": message, "resolved": False})

    def one_run(day_offset):
        # 每次都重新建立 register，模擬 06:10 的排程每天重新啟動一次程序
        return runner.run(detect=lambda: ([Gap("stock_price", "20260915")], frozenset()), execute=execute,
                          register=MongoRegister(write_db["data_gap_register"]), alert=alert,
                          now=START + timedelta(days=day_offset), apply=True, max_attempts=3)

    for day in range(3):
        one_run(day)
    doc = write_db["data_gap_register"].find_one({"_id": "stock_price:20260915:gap"})

    assert doc["status"] == "failed" and doc["attempts"] == 3 and "upstream blocked" in doc["last_error"]
    assert write_db["schedule_alerts"].count_documents({}) == 1
    assert len(attempts) == 3

    one_run(3)

    assert len(attempts) == 3 and write_db["schedule_alerts"].count_documents({}) == 1


def test_rebuild_moves_stamps_to_their_true_day_and_collapses_holiday_duplicates(write_db):
    source, destination = write_db["rd_source"], write_db["rd_destination"]
    source.delete_many({})
    destination.drop()
    calendar = ["2026-09-17", "2026-09-18", "2026-09-21", "2026-09-22"]
    for day, volume in (("2026-09-20", 5), ("2026-09-21", 5), ("2026-09-22", 7)):
        source.insert_one({"stock_id": "2330", "date": datetime.strptime(day, "%Y-%m-%d"), "volume": volume})

    mapping = redate.day_map(["2026-09-20", "2026-09-21", "2026-09-22"], calendar, "data")
    stats = redate_snapshot_tables.rebuild(source, destination, "stock_id", mapping)

    assert stats["copied"] == 2
    assert {d["date"].strftime("%Y-%m-%d"): d["volume"] for d in destination.find({})} == {"2026-09-18": 5, "2026-09-21": 7}
    assert "uq_build" not in destination.index_information()


def test_rebuild_reports_rows_whose_stamp_has_no_true_day(write_db):
    source, destination = write_db["rd_source2"], write_db["rd_destination2"]
    source.delete_many({})
    destination.drop()
    source.insert_one({"stock_id": "2330", "date": datetime(2026, 9, 1), "volume": 1})

    stats = redate_snapshot_tables.rebuild(source, destination, "stock_id", {"2026-09-01": None})

    assert stats == {"copied": 0, "skipped_no_target": 1, "days": 0}
