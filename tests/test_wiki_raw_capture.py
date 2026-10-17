"""TDD: LLM Wiki 原始素材累積——只增不改、可重複執行、可知時間要保守。"""

import copy
from datetime import datetime

import pytest
from pymongo.errors import BulkWriteError

from scripts import wiki_raw_capture as w

pytestmark = pytest.mark.unit

NOW = datetime(2026, 10, 17, 23, 50)


def doc(**over):
    base = {
        "_id": "id1", "stock_id": "2330", "name": "台積電", "date": datetime(2026, 10, 16), "time": "181708",
        "subject": "公告本公司董事會決議", "detail": "1.事實發生日:115/10/16\r\n2.說明:略", "clause": "第31款",
        "market": "sii", "source": "mops", "fact_date": datetime(2026, 10, 16),
    }
    base.update(over)
    return base


@pytest.mark.parametrize(
    "day_text, expected",
    [("181708", (18, 17, 8)), ("95959", (9, 59, 59)), ("000000", (0, 0, 0)), (None, (23, 59, 59)), ("", (23, 59, 59)),
     ("246000", (23, 59, 59)), ("126099", (23, 59, 59)), ("abc", (23, 59, 59)), ("1234567", (23, 59, 59))],
)
def test_published_time_is_parsed_and_unknown_times_fall_back_to_end_of_day(day_text, expected):
    got = w.parse_published(datetime(2026, 10, 16, 5, 5), day_text)
    assert (got.hour, got.minute, got.second) == expected and got.date() == datetime(2026, 10, 16).date()


def test_an_announcement_row_carries_text_and_when_it_became_knowable():
    row = w.announcement_row(doc(), NOW)
    assert row["kind"] == "announcement" and row["source"] == "mops" and row["stock_id"] == "2330"
    assert row["title"] == "公告本公司董事會決議" and row["body"] == "1.事實發生日:115/10/16\n2.說明:略"
    assert row["published_at"] == row["available_at"] == datetime(2026, 10, 16, 18, 17, 8)
    assert row["captured_at"] == NOW and row["event_date"] == datetime(2026, 10, 16)
    assert row["meta"]["origin"] == "major_news" and row["meta"]["origin_id"] == "id1"


def test_a_missing_source_means_the_daily_openapi_snapshot():
    assert w.announcement_row(doc(source=None), NOW)["source"] == "openapi"


@pytest.mark.parametrize("over", [{"stock_id": ""}, {"stock_id": None}, {"date": None}, {"date": "2026-10-16"}, {"subject": "", "detail": ""}, {"subject": None, "detail": "  "}])
def test_unusable_announcements_are_skipped(over):
    assert w.announcement_row(doc(**over), NOW) is None


def test_same_content_gives_the_same_key_and_a_correction_is_a_new_revision_of_the_same_item():
    a, again = w.announcement_row(doc(), NOW), w.announcement_row(doc(), datetime(2026, 11, 1))
    corrected = w.announcement_row(doc(detail="更正後的說明"), NOW)
    assert a["key"] == again["key"]
    assert corrected["key"] != a["key"] and corrected["nkey"] == a["nkey"]


def test_different_time_or_subject_or_stock_are_different_items():
    base = w.announcement_row(doc(), NOW)
    for over in ({"time": "181709"}, {"subject": "另一則公告"}, {"stock_id": "2317"}):
        other = w.announcement_row(doc(**over), NOW)
        assert other["nkey"] != base["nkey"] and other["key"] != base["key"]


def test_line_endings_do_not_change_the_key():
    assert w.announcement_row(doc(detail="a\r\nb"), NOW)["key"] == w.announcement_row(doc(detail="a\nb"), NOW)["key"]


def test_a_title_row_keeps_the_title_verbatim_and_splits_out_the_publisher():
    row = w.title_row("0056", "元大高股息", "〈焦點股〉0056 股價再創新高 - 鉅亨網", datetime(2026, 10, 16, 23, 10), NOW)
    assert row["kind"] == "media_title" and row["source"] == "google_news" and row["body"] is None
    assert row["title"] == "〈焦點股〉0056 股價再創新高 - 鉅亨網" and row["meta"]["publisher"] == "鉅亨網"
    assert row["available_at"] == datetime(2026, 10, 16, 23, 10) and row["published_at"] is None


def test_a_title_without_a_fetch_time_is_knowable_from_when_we_captured_it():
    assert w.title_row("0056", "", "標題", None, NOW)["available_at"] == NOW


def test_a_title_has_no_publisher_when_there_is_no_separator_and_blank_ones_are_skipped():
    assert w.title_row("0056", "", "沒有來源", None, NOW)["meta"]["publisher"] is None
    assert w.title_row("0056", "", "  ", None, NOW) is None and w.title_row("", "", "標題", None, NOW) is None


def test_the_same_headline_for_two_stocks_is_two_rows_and_the_same_for_one_is_stable():
    a = w.title_row("0056", "", "標題 - X", None, NOW)
    assert a["key"] == w.title_row("0056", "", "標題 - X", None, datetime(2027, 1, 1))["key"]
    assert a["key"] != w.title_row("0050", "", "標題 - X", None, NOW)["key"]


class Coll:
    def __init__(self, docs=None):
        self.docs = list(docs or [])
        self.fail_with = None
        self.inserts = []

    def find(self, query=None, projection=None):
        query = query or {}
        out = []
        for d in self.docs:
            ok = True
            for field, cond in query.items():
                if isinstance(cond, dict) and "$in" in cond:
                    ok &= d.get(field) in cond["$in"]
                elif isinstance(cond, dict) and "$gte" in cond:
                    ok &= d.get(field) is not None and d[field] >= cond["$gte"]
                else:
                    ok &= d.get(field) == cond
            if ok:
                out.append(copy.deepcopy(d))
        return out

    def insert_many(self, rows, ordered=True):
        if self.fail_with:
            raise self.fail_with
        self.inserts.append(len(rows))
        self.docs += [copy.deepcopy(r) for r in rows]

    def create_index(self, *args, **kwargs):
        pass


class Db(dict):
    def __missing__(self, name):
        self[name] = Coll()
        return self[name]


def rows(n, prefix="t"):
    return [w.title_row(str(1000 + i), "", f"{prefix}{i}", None, NOW) for i in range(n)]


def test_insert_new_writes_only_what_is_not_there_and_counts_it():
    coll = Coll()
    assert w.insert_new(coll, rows(3)) == 3
    assert w.insert_new(coll, rows(5)) == 2
    assert len(coll.docs) == 5


def test_insert_new_drops_duplicates_inside_one_batch():
    coll = Coll()
    assert w.insert_new(coll, rows(2) + rows(2)) == 2 and len(coll.docs) == 2


def test_insert_new_works_across_chunk_boundaries():
    coll = Coll()
    assert w.insert_new(coll, rows(7), chunk=2) == 7 and coll.inserts == [2, 2, 2, 1]


def bulk_error(codes):
    return BulkWriteError({"writeErrors": [{"code": c, "index": i} for i, c in enumerate(codes)], "nInserted": 0})


def test_a_duplicate_key_race_with_another_writer_is_tolerated_and_not_counted():
    coll = Coll()
    coll.fail_with = bulk_error([w.DUPLICATE_KEY, w.DUPLICATE_KEY])
    assert w.insert_new(coll, rows(3)) == 1


def test_any_other_write_error_is_raised():
    coll = Coll()
    coll.fail_with = bulk_error([w.DUPLICATE_KEY, 121])
    with pytest.raises(BulkWriteError):
        w.insert_new(coll, rows(3))


def test_insert_new_never_modifies_what_it_already_wrote():
    coll = Coll()
    w.insert_new(coll, rows(2))
    before = copy.deepcopy(coll.docs)
    w.insert_new(coll, rows(2))
    assert coll.docs == before


def make_db():
    db = Db()
    db["major_news"] = Coll([
        doc(_id="a"), doc(_id="b", stock_id="2317", time="090000"),
        doc(_id="old", date=datetime(2026, 9, 1), subject="九月的公告"),
        doc(_id="bad", stock_id=""),
    ])
    db["media_news"] = Coll([
        {"stock_id": "0056", "name": "元大高股息", "fetched_at": datetime(2026, 10, 16, 23, 10), "titles": ["甲 - X", "乙 - Y", "甲 - X", 5, ""]},
        {"stock_id": "2330", "name": "台積電", "fetched_at": datetime(2026, 10, 16, 23, 11), "titles": ["丙 - Z"]},
    ])
    return db


SINCE = datetime(2026, 10, 14)


def test_capture_writes_recent_announcements_and_every_distinct_title_once():
    db = make_db()
    result = w.capture(db, SINCE, NOW)
    assert result == {"announcement": (2, 2), "media_title": (4, 3)}
    kinds = sorted(d["kind"] for d in db["wiki_raw"].docs)
    assert kinds == ["announcement"] * 2 + ["media_title"] * 3


def test_capture_is_idempotent():
    db = make_db()
    w.capture(db, SINCE, NOW)
    assert w.capture(db, SINCE, datetime(2026, 10, 18, 23, 50)) == {"announcement": (2, 0), "media_title": (4, 0)}


def test_capture_since_a_date_includes_older_announcements():
    db = make_db()
    assert w.capture(db, datetime(2026, 4, 1), NOW)["announcement"] == (3, 3)


def test_a_corrected_announcement_is_kept_as_a_new_revision_beside_the_old_one():
    db = make_db()
    w.capture(db, SINCE, NOW)
    db["major_news"].docs[0]["detail"] = "更正後的說明"
    assert w.capture(db, SINCE, NOW)["announcement"] == (2, 1)
    nkeys = [d["nkey"] for d in db["wiki_raw"].docs if d["kind"] == "announcement"]
    assert len(nkeys) == 3 and len(set(nkeys)) == 2


def test_a_title_that_disappears_from_the_source_stays_in_the_archive():
    db = make_db()
    w.capture(db, SINCE, NOW)
    db["media_news"].docs[0]["titles"] = ["新的 - Q"]
    w.capture(db, SINCE, NOW)
    titles = {d["title"] for d in db["wiki_raw"].docs if d["kind"] == "media_title"}
    assert {"甲 - X", "乙 - Y", "新的 - Q"} <= titles


def test_dry_run_counts_but_writes_nothing():
    db = make_db()
    assert w.capture(db, SINCE, NOW, dry_run=True) == {"announcement": (2, 2), "media_title": (4, 3)}
    assert db["wiki_raw"].docs == []


def test_the_source_collections_are_never_modified():
    db = make_db()
    before = copy.deepcopy((db["major_news"].docs, db["media_news"].docs))
    w.capture(db, SINCE, NOW)
    assert (db["major_news"].docs, db["media_news"].docs) == before


def test_stats_summarises_by_source_and_kind_with_month_counts():
    db = make_db()
    w.capture(db, datetime(2026, 4, 1), NOW)
    report = w.stats(db["wiki_raw"])
    ann = report["groups"][("mops", "announcement")]
    assert ann["n"] == 3 and ann["stocks"] == 2 and ann["lo"] == datetime(2026, 9, 1, 18, 17, 8)
    assert report["groups"][("google_news", "media_title")] == {"n": 3, "stocks": 2, "lo": datetime(2026, 10, 16, 23, 10), "hi": datetime(2026, 10, 16, 23, 11)}
    assert report["months"] == {"2026-09": 1, "2026-10": 5}


def test_main_capture_defaults_to_the_last_three_days_and_prints_counts(capsys):
    db = make_db()
    code = w.main(["capture"], db=db, now=lambda: datetime(2026, 10, 17, 23, 50))
    out = capsys.readouterr().out
    assert code == 0 and "announcement" in out and "新增" in out and "將新增" not in out
    assert len([d for d in db["wiki_raw"].docs if d["kind"] == "announcement"]) == 2


def test_main_dry_run_and_stats(capsys):
    db = make_db()
    w.main(["capture", "--dry-run"], db=db, now=lambda: NOW)
    assert "將新增" in capsys.readouterr().out and db["wiki_raw"].docs == []
    w.main(["capture"], db=db, now=lambda: NOW)
    w.main(["stats"], db=db, now=lambda: NOW)
    assert "mops" in capsys.readouterr().out


def test_the_published_time_has_no_sub_second_part_even_if_the_source_date_has_one():
    got = w.parse_published(datetime(2026, 10, 16, 5, 5, 7, 123456), "181708")
    assert got == datetime(2026, 10, 16, 18, 17, 8) and got.microsecond == 0


def test_main_capture_only_looks_back_three_days_by_default():
    db = Db()
    db["major_news"] = Coll([doc(_id="recent", date=datetime(2026, 10, 15)), doc(_id="stale", date=datetime(2026, 10, 12), subject="五天前的公告")])
    w.main(["capture"], db=db, now=lambda: datetime(2026, 10, 17, 23, 50))
    assert [d["meta"]["origin_id"] for d in db["wiki_raw"].docs] == ["recent"]
