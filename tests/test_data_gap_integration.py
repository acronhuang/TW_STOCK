"""整合測試（真實 MongoDB，專用測試庫）：缺口回補的失敗路徑與假日列清理動作。"""

from datetime import datetime, timedelta

import pytest

from scripts import fix_phantom_dates
from scripts.data_gap_repair import MongoRegister
from src.data_gap import runner
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


def test_phantom_actions_relabel_merge_and_delete_rows_in_real_collections(write_db):
    lending, after_hours = write_db["securities_lending"], write_db["after_hours_trading"]
    lending.delete_many({})
    after_hours.delete_many({})
    d18, d20, d24 = datetime(2026, 9, 18), datetime(2026, 9, 20), datetime(2026, 9, 24)
    after_hours.insert_many([{"stock_id": "2330", "date": d20, "close": 1.0}, {"stock_id": "2317", "date": d20, "close": 2.0}])
    lending.insert_many([{"twse_code": "2330", "date": d24, "twse_volume": 1}, {"twse_code": "2330", "date": datetime(2026, 9, 25), "twse_volume": 9},
                         {"twse_code": "2317", "date": datetime(2026, 9, 25), "twse_volume": 7}])

    relabelled = fix_phantom_dates.apply_action(after_hours, {"op": "relabel", "collection": "after_hours_trading",
                                                              "from": "2026-09-20", "to": "2026-09-18"})
    merged = fix_phantom_dates.apply_action(lending, {"op": "merge", "collection": "securities_lending", "from": "2026-09-25",
                                                      "to": "2026-09-24", "key": "twse_code"})

    assert relabelled == 2 and after_hours.count_documents({"date": d18}) == 2 and after_hours.count_documents({"date": d20}) == 0
    assert merged == 2 and lending.count_documents({"date": datetime(2026, 9, 25)}) == 0
    assert {d["twse_code"]: d["twse_volume"] for d in lending.find({"date": d24})} == {"2330": 9, "2317": 7}

    deleted = fix_phantom_dates.apply_action(after_hours, {"op": "delete", "collection": "after_hours_trading", "from": "2026-09-18"})

    assert deleted == 2 and after_hours.count_documents({}) == 0
