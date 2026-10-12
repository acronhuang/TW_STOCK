"""TDD: 上櫃／興櫃重大訊息——MOPS 清單與明細解析、與既有資料對帳、TPEX OpenAPI 轉換。"""

from datetime import datetime

import pytest

from src.data_gap import mops_major as mm

pytestmark = pytest.mark.unit

NOW = datetime(2026, 10, 12, 23, 30)


def list_payload(rows, code=200):
    return {"code": code, "message": "查詢成功", "result": {"titles": [], "data": rows}}


def list_row(day="115/10/08", clock="17:36:36", code="6804", name="明係", subject="公告庫藏股", kind="otc", serial=1):
    params = {"companyId": code, "marketKind": kind, "enterDate": day.replace("/", ""), "serialNumber": serial}
    return [day, clock, code, name, subject, {"apiName": "t05st02_detail", "parameters": params}]


def detail_payload(serial=1, clause="35", fact="115/10/07", subject="公告庫藏股\r\n買回達百分之二", detail="1.日期\r\n2.數量"):
    return {"code": 200, "result": {"marketName": "上櫃公司", "companyId": "6804",
                                    "data": [[serial, "115/10/08", "17:36:36", "吳", "財務協理", "02", subject, clause, fact, detail]]}}


# ── 日期與時間 ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("text, expected", [("115/10/07", datetime(2026, 10, 7)), ("1151007", datetime(2026, 10, 7)),
                                            ("", None), ("abc", None), ("115/13/40", None)])
def test_roc_dates_in_both_notations_are_read(text, expected):
    assert mm.roc_date(text) == expected


@pytest.mark.parametrize("text, expected", [("17:31:28", "173128"), ("211554", "211554"), ("70003", "070003"),
                                            ("", None), ("1215", None), ("25:00:00", None), ("9x", None)])
def test_clock_times_are_normalised_to_six_digits(text, expected):
    assert mm.clock(text) == expected


# ── 清單解析 ──────────────────────────────────────────────────────────────
def test_the_list_is_parsed_into_rows_with_market_date_time_and_the_detail_parameters():
    rows = mm.parse_list(list_payload([list_row(), list_row(clock="07:00:03", code="4747", name="強生*", kind="rotc", serial=2)]))

    assert rows[0]["stock_id"] == "6804" and rows[0]["market"] == "otc" and rows[0]["date"] == datetime(2026, 10, 8)
    assert rows[0]["time"] == "173636" and rows[0]["params"]["serialNumber"] == 1
    assert rows[1]["market"] == "rotc" and rows[1]["time"] == "070003" and rows[1]["name"] == "強生*"


def test_a_failed_or_malformed_response_yields_no_rows_instead_of_partial_garbage():
    assert mm.parse_list(list_payload([], code=500)) == []
    assert mm.parse_list({}) == []
    assert mm.parse_list(list_payload([["115/10/08", "17:36:36", "6804"]])) == []     # 欄位不足的列整筆略過


def test_only_the_requested_markets_are_kept_and_public_company_rows_are_dropped():
    rows = mm.parse_list(list_payload([list_row(kind="otc"), list_row(code="1", kind="sii"), list_row(code="2", kind="pub")]))

    assert [r["market"] for r in mm.only_markets(rows, ("otc", "rotc"))] == ["otc"]


# ── 對帳 ─────────────────────────────────────────────────────────────────
def doc(stock_id="6804", day=datetime(2026, 10, 8), time="173636", subject="公告庫藏股"):
    return {"stock_id": stock_id, "date": day, "time": time, "subject": subject}


def test_existing_documents_are_recognised_whatever_their_time_notation():
    keys = mm.existing_keys([doc(time="70003", day=datetime(2026, 10, 8), stock_id="2002"), doc(time="173636")])

    assert mm.is_known({"stock_id": "2002", "date": datetime(2026, 10, 8), "time": "070003", "subject": "x"}, keys)
    assert mm.is_known({"stock_id": "6804", "date": datetime(2026, 10, 8), "time": "173636", "subject": "x"}, keys)
    assert not mm.is_known({"stock_id": "6804", "date": datetime(2026, 10, 8), "time": "173637", "subject": "x"}, keys)


def test_a_document_without_a_readable_time_falls_back_to_the_subject_text():
    keys = mm.existing_keys([doc(time="", subject="公告  庫藏股\r\n買回")])

    assert mm.is_known({"stock_id": "6804", "date": datetime(2026, 10, 8), "time": "173636", "subject": "公告 庫藏股 買回"}, keys)


def test_only_rows_absent_from_the_database_are_reported_missing():
    rows = mm.parse_list(list_payload([list_row(), list_row(clock="18:00:00", subject="另一則")]))
    keys = mm.existing_keys([doc()])

    assert [r["time"] for r in mm.missing(rows, keys)] == ["180000"]


def test_a_repeat_with_the_same_subject_at_a_different_time_is_not_mistaken_for_the_known_one():
    rows = mm.parse_list(list_payload([list_row(), list_row(clock="18:00:00")]))

    assert mm.coverage(rows, mm.existing_keys([doc()])) == (2, 1)


def test_coverage_counts_how_many_of_the_official_rows_we_already_hold():
    rows = mm.parse_list(list_payload([list_row(), list_row(clock="18:00:00", subject="另一則")]))

    assert mm.coverage(rows, mm.existing_keys([doc()])) == (2, 1)


# ── 明細轉文件 ───────────────────────────────────────────────────────────
def test_a_detail_becomes_a_major_news_document_with_the_same_shape_as_the_twse_ones():
    row = mm.parse_list(list_payload([list_row()]))[0]

    out = mm.detail_to_doc(row, detail_payload(), NOW)

    assert out["stock_id"] == "6804" and out["name"] == "明係" and out["market"] == "otc" and out["source"] == "mops"
    assert out["date"] == datetime(2026, 10, 8) and out["time"] == "173636" and out["fact_date"] == datetime(2026, 10, 7)
    assert out["clause"] == "第35款" and out["subject"].startswith("公告庫藏股") and "1.日期" in out["detail"]
    assert out["updated_at"] == NOW


def test_the_detail_whose_serial_matches_is_used_when_several_come_back():
    row = mm.parse_list(list_payload([list_row(serial=2)]))[0]
    payload = detail_payload(serial=1, subject="第一則")
    payload["result"]["data"].append(detail_payload(serial=2, subject="第二則")["result"]["data"][0])

    assert mm.detail_to_doc(row, payload, NOW)["subject"] == "第二則"


def test_a_failed_or_empty_detail_gives_no_document_so_the_row_stays_missing_for_the_next_run():
    row = mm.parse_list(list_payload([list_row()]))[0]

    assert mm.detail_to_doc(row, {"code": 500, "result": None}, NOW) is None
    assert mm.detail_to_doc(row, {"code": 200, "result": {"data": []}}, NOW) is None


def test_a_406_no_match_detail_still_stores_the_listed_row_so_it_is_not_retried_forever():
    row = mm.parse_list(list_payload([list_row(code="9103", name="美德醫療-DR", subject="MKH GLOVE", kind="sii")]))[0]

    out = mm.detail_to_doc(row, {"code": 406, "message": "查無相符資料", "result": None}, NOW)

    assert out["subject"] == "MKH GLOVE" and out["detail"] == "" and out["detail_missing"] is True
    assert out["stock_id"] == "9103" and out["time"] == "173636" and out["market"] == "sii"


class FakeCollection:
    def __init__(self, docs=()):
        self.docs = list(docs)
        self.writes = []

    def find(self, query, projection=None):
        low, high = query["date"]["$gte"], query["date"]["$lte"]
        return [d for d in self.docs if low <= d["date"] <= high]

    def update_one(self, flt, update, upsert=False):
        self.writes.append(flt)
        self.docs.append(update["$set"])


def test_save_new_skips_known_rows_and_keeps_two_same_subject_notices_with_different_times():
    col = FakeCollection([doc(time="173636")])
    a = {**doc(time="173636"), "market": "otc"}                       # 已在庫
    b = {**doc(time="180000"), "market": "otc"}                       # 同主旨、不同時間
    c = {**doc(time="180000"), "market": "otc"}                       # 同一批重複出現

    saved = mm.save_new(col, [a, b, c])

    assert saved == 1 and col.writes == [{"stock_id": "6804", "date": datetime(2026, 10, 8), "time": "180000", "subject": "公告庫藏股"}]


def test_save_new_with_nothing_to_save_does_not_touch_the_collection():
    col = FakeCollection()

    assert mm.save_new(col, []) == 0 and col.writes == []


# ── 補洞流程（抓取以函式注入）─────────────────────────────────────────────
def test_reconcile_fetches_details_only_for_missing_rows_and_keeps_failures_out_of_the_result():
    rows = mm.parse_list(list_payload([list_row(), list_row(clock="18:00:00", subject="B"), list_row(clock="19:00:00", subject="C")]))
    asked = []

    def fetch(params):
        asked.append(params["serialNumber"])
        if len(asked) == 2:
            raise OSError("timeout")
        return detail_payload(subject="補抓")

    result = mm.reconcile(rows, mm.existing_keys([doc()]), ("otc",), fetch, NOW)

    assert result["missing"] == 2 and len(asked) == 2          # 已在庫的那一筆沒有再呼叫明細
    assert len(result["docs"]) == 1 and result["failed"] == 1


def test_reconcile_in_dry_run_style_reports_missing_without_calling_the_detail_endpoint():
    rows = mm.parse_list(list_payload([list_row(), list_row(clock="18:00:00")]))

    result = mm.reconcile(rows, set(), ("otc",), None, NOW)

    assert result["missing"] == 2 and result["docs"] == [] and result["failed"] == 0


# ── TPEX OpenAPI 每日資料 ───────────────────────────────────────────────
def test_a_tpex_openapi_row_becomes_the_same_document_shape():
    row = {"Date": "1151012", "發言日期": "1151011", "發言時間": "70004", "SecuritiesCompanyCode": "4747", "CompanyName": "強生*",
           "主旨": "公告面額變更", "符合條款": "第53款", "事實發生日": "1150624", "說明": "1.事實發生日"}

    out = mm.tpex_doc(row, NOW)

    assert out["stock_id"] == "4747" and out["market"] == "otc" and out["source"] == "tpex_openapi"
    assert out["date"] == datetime(2026, 10, 11) and out["time"] == "070004" and out["fact_date"] == datetime(2026, 6, 24)
    assert out["clause"] == "第53款" and out["detail"] == "1.事實發生日"


def test_a_tpex_row_without_a_code_or_date_is_dropped():
    assert mm.tpex_doc({"發言日期": "1151011", "發言時間": "1", "SecuritiesCompanyCode": ""}, NOW) is None
    assert mm.tpex_doc({"發言日期": "", "SecuritiesCompanyCode": "4747"}, NOW) is None
