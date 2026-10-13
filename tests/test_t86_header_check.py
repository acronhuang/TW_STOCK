"""TDD: T86 標頭檢查——欄位位置不符就拒絕整批，而不是把數字存進錯的欄位（2026-07-19 的教訓）。"""

import json
import sys
from pathlib import Path

import pytest

from src.chip_analysis import inst_buysell

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import twse_daily_update as tdu  # noqa: E402

pytestmark = pytest.mark.unit

REAL_FIELDS = [
    "證券代號", "證券名稱", "外陸資買進股數(不含外資自營商)", "外陸資賣出股數(不含外資自營商)",
    "外陸資買賣超股數(不含外資自營商)", "外資自營商買進股數", "外資自營商賣出股數", "外資自營商買賣超股數",
    "投信買進股數", "投信賣出股數", "投信買賣超股數", "自營商買賣超股數", "自營商買進股數(自行買賣)",
    "自營商賣出股數(自行買賣)", "自營商買賣超股數(自行買賣)", "自營商買進股數(避險)", "自營商賣出股數(避險)",
    "自營商買賣超股數(避險)", "三大法人買賣超股數",
]
ROW = ["2330", "台積電  ", "100", "50", "50", "0", "0", "0", "10", "5", "5", "3", "2", "1", "1", "2", "1", "1", "58"]


def test_the_real_header_passes_and_spacing_or_wording_noise_does_not_matter():
    inst_buysell.check_t86_fields(REAL_FIELDS)
    inst_buysell.check_t86_fields([f" {name.replace('買賣超', '買賣超 ')} " for name in REAL_FIELDS])


def test_a_header_missing_the_foreign_dealer_group_is_rejected():
    short = REAL_FIELDS[:5] + REAL_FIELDS[8:]   # 少了 3 欄：舊版程式正是這樣被錯位

    with pytest.raises(inst_buysell.T86LayoutError, match="19"):
        inst_buysell.check_t86_fields(short)


def test_two_columns_swapped_at_the_same_length_are_rejected():
    swapped = list(REAL_FIELDS)
    swapped[10], swapped[11] = swapped[11], swapped[10]   # 投信淨買超 與 自營商淨買超 對調

    with pytest.raises(inst_buysell.T86LayoutError, match=r"\[10\]|\[11\]"):
        inst_buysell.check_t86_fields(swapped)


@pytest.mark.parametrize("bad", [None, "證券代號", [], REAL_FIELDS + ["多一欄"]])
def test_no_header_or_a_wrong_length_header_is_rejected_not_waved_through(bad):
    with pytest.raises(inst_buysell.T86LayoutError):
        inst_buysell.check_t86_fields(bad)


class FakeResponse:
    def __init__(self, payload):
        self.text = json.dumps(payload, ensure_ascii=False)

    def raise_for_status(self):
        pass


def payload(fields):
    return {"stat": "OK", "date": "20261012", "fields": fields, "data": [ROW]}


def test_the_fetch_refuses_a_batch_whose_header_moved_and_reads_one_whose_header_matches(monkeypatch):
    swapped = list(REAL_FIELDS)
    swapped[10], swapped[11] = swapped[11], swapped[10]

    monkeypatch.setattr(tdu.requests, "get", lambda *a, **k: FakeResponse(payload(swapped)))
    with pytest.raises(inst_buysell.T86LayoutError):
        tdu.fetch_twse_institutional("2026-10-12")

    monkeypatch.setattr(tdu.requests, "get", lambda *a, **k: FakeResponse(payload(REAL_FIELDS)))
    records = tdu.fetch_twse_institutional("2026-10-12")
    assert len(records) == 1 and records[0]["stock_id"] == "2330"
    assert float(records[0]["trust_net"].to_decimal()) == 5 and float(records[0]["total_net"].to_decimal()) == 58
