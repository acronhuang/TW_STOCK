"""TDD: MOPS 對帳補洞的整段流程（清單→比對→明細→寫入→紀錄），以假的 MOPS 與測試庫驗證。"""

from datetime import datetime

import pytest

from scripts import mops_major_sync as sync

pytestmark = pytest.mark.integration

DAY = datetime(2026, 10, 8)


def row(clock, code="6804", subject="公告庫藏股", kind="otc", serial=1):
    params = {"companyId": code, "marketKind": kind, "enterDate": "1151008", "serialNumber": serial}
    return ["115/10/08", clock, code, "明係", subject, {"apiName": "t05st02_detail", "parameters": params}]


class FakeMops:
    def __init__(self, rows, broken=()):
        self.rows, self.broken, self.detail_calls = rows, set(broken), []

    def day_list(self, day):
        return {"code": 200, "result": {"data": self.rows}}

    def detail(self, params):
        self.detail_calls.append((params["companyId"], params["serialNumber"]))
        if params["companyId"] in self.broken:
            raise OSError("timeout")
        return {"code": 200, "result": {"data": [[params["serialNumber"], "115/10/08", "17:36:36", "吳", "協理", "02", "公告庫藏股", "35", "115/10/08", "內文"]]}}


@pytest.fixture
def db(write_db):
    write_db["major_news"].drop()
    write_db["mops_reconcile_log"].drop()
    return write_db


def test_dry_run_counts_what_is_missing_and_writes_nothing(db):
    mops = FakeMops([row("17:36:36"), row("18:00:00", code="4747")])

    stats = sync.run_day(db, mops, DAY, ("otc", "rotc"), apply=False)

    assert stats["missing"] == 2 and stats["filled"] == 0 and mops.detail_calls == []
    assert db["major_news"].count_documents({}) == 0 and db["mops_reconcile_log"].count_documents({}) == 0


def test_apply_writes_full_documents_logs_the_run_and_a_rerun_finds_nothing_missing(db):
    mops = FakeMops([row("17:36:36"), row("18:00:00", subject="同主旨", serial=2), row("18:30:00", subject="同主旨", serial=3)])

    stats = sync.run_day(db, mops, DAY, ("otc",), apply=True)
    again = sync.run_day(db, FakeMops(mops.rows), DAY, ("otc",), apply=True)

    assert stats["filled"] == 3 and db["major_news"].count_documents({"market": "otc", "source": "mops"}) == 3
    assert db["major_news"].find_one({"time": "173636"})["detail"] == "內文"
    assert again["missing"] == 0 and db["mops_reconcile_log"].count_documents({}) == 2


def test_a_failing_detail_is_not_written_and_is_retried_by_the_next_run(db):
    mops = FakeMops([row("17:36:36"), row("18:00:00", code="4747")], broken=("4747",))

    stats = sync.run_day(db, mops, DAY, ("otc",), apply=True)
    retry = sync.run_day(db, FakeMops(mops.rows), DAY, ("otc",), apply=True)

    assert stats["filled"] == 1 and stats["failed"] == 1
    assert retry["missing"] == 1 and retry["filled"] == 1 and db["major_news"].count_documents({}) == 2


def test_documents_from_the_twse_openapi_with_a_five_digit_time_count_as_already_held(db):
    db["major_news"].insert_one({"stock_id": "2002", "date": DAY, "time": "70003", "subject": "公告", "name": "中鋼"})
    mops = FakeMops([row("07:00:03", code="2002", subject="公告", kind="sii")])

    stats = sync.run_day(db, mops, DAY, ("sii",), apply=True)

    assert stats["missing"] == 0 and db["major_news"].count_documents({}) == 1
