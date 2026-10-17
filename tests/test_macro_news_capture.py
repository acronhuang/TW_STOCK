"""TDD: 總經、政策、國際與產業新聞的原料累積——時間用台北時間、可知時間要保守、單一來源失敗不影響其他。"""

import copy
from datetime import datetime, timedelta

import pytest

from scripts import macro_news_capture as m

pytestmark = pytest.mark.unit

NOW = datetime(2026, 10, 17, 23, 55)
RECENT = "Fri, 16 Oct 2026 15:00:00 GMT"  # 台北 10-16 23:00
OLD = "Mon, 01 Jun 2026 01:00:00 GMT"


def rss(*items):
    body = ""
    for title, link, published, desc in items:
        body += f"<item><title><![CDATA[{title}]]></title><link>{link}</link>"
        body += f"<pubDate>{published}</pubDate>" if published else ""
        body += f"<description><![CDATA[{desc}]]></description>" if desc else ""
        body += "</item>"
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>頻道</title>{body}</channel></rss>'


class Coll:
    def __init__(self):
        self.docs, self.inserts = [], []

    def find(self, query=None, projection=None):
        query = query or {}
        return [copy.deepcopy(d) for d in self.docs if all((d.get(f) in c["$in"]) if isinstance(c, dict) and "$in" in c else d.get(f) == c for f, c in query.items())]

    def insert_many(self, rows, ordered=True):
        self.inserts.append(len(rows))
        self.docs += [copy.deepcopy(r) for r in rows]

    def create_index(self, *args, **kwargs):
        pass


class Db(dict):
    def __missing__(self, name):
        self[name] = Coll()
        return self[name]


class Fetch:
    """依網址回傳內容；值是例外就丟出。沒登記的網址（Google 查詢）預設回一則新聞。"""

    def __init__(self, table=None, google=None):
        self.table, self.google, self.calls = table or {}, google, []

    def __call__(self, url):
        self.calls.append(url)
        if url in self.table:
            value = self.table[url]
        elif "news.google.com" in url:
            value = self.google(url) if callable(self.google) else (self.google if self.google is not None else rss((f"標題 {len(self.calls)} - 某報", f"http://g/{len(self.calls)}", RECENT, "")))
        else:
            value = rss(("官方新聞", f"http://x/{url[-12:]}", RECENT, "內文"), ("舊的官方新聞", f"http://x/old{url[-12:]}", OLD, ""))
        if isinstance(value, Exception):
            raise value
        return value


class Sleeper:
    def __init__(self):
        self.calls = []

    def __call__(self, seconds):
        self.calls.append(seconds)


def run(fetch=None, since=datetime(2026, 10, 14), days=2, industries=(), dry_run=False, db=None, sleep=None):
    db = db if db is not None else Db()
    return db, m.capture(db, NOW, since, days, dry_run, fetch or Fetch(), sleep or Sleeper(), industries)


@pytest.mark.parametrize("text, expected", [
    ("Fri, 16 Oct 2026 15:00:00 GMT", datetime(2026, 10, 16, 23, 0)),
    ("Fri, 16 Oct 2026 15:00:00 +0800", datetime(2026, 10, 16, 15, 0)),
    ("Fri, 16 Oct 2026 15:00:00 -0500", datetime(2026, 10, 17, 4, 0)),
    ("Fri, 16 Oct 2026 15:00:00 -0000", datetime(2026, 10, 16, 23, 0)),
    ("2026-10-16T15:00:00Z", datetime(2026, 10, 16, 23, 0)),
    ("2026-10-16T23:00:00+08:00", datetime(2026, 10, 16, 23, 0)),
])
def test_publication_times_become_taipei_time_without_a_timezone(text, expected):
    got = m.parse_time(text)
    assert got == expected and got.tzinfo is None and got.microsecond == 0


@pytest.mark.parametrize("text", ["", None, "  ", "yesterday", "32 Foo 2026", "2026-13-45", 5])
def test_unreadable_times_are_none(text):
    assert m.parse_time(text) is None


def test_feed_items_are_decoded_and_cleaned():
    feed = rss(("Minutes of the Board&#39;s meetings", "http://a", RECENT, "<p>第一段</p><p>第二段</p>"))
    item = m.parse_feed(feed)[0]
    assert item["title"] == "Minutes of the Board's meetings" and item["summary"] == "第一段 第二段"
    assert item["link"] == "http://a" and item["published"] == datetime(2026, 10, 16, 23, 0)


def test_whitespace_in_titles_is_collapsed_and_items_without_titles_are_skipped():
    feed = "<rss><channel><item><title>  兩行\n 標題  </title></item><item><title>  </title></item><item><link>x</link></item></channel></rss>"
    assert [i["title"] for i in m.parse_feed(feed)] == ["兩行 標題"]


@pytest.mark.parametrize("text", ["", None, "<rss></rss>", "not xml at all"])
def test_a_feed_with_no_items_gives_an_empty_list(text):
    assert m.parse_feed(text) == []


def test_external_entities_are_never_expanded():
    feed = '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a SYSTEM "file:///etc/passwd">]><rss><channel><item><title>&a; 標題</title></item></channel></rss>'
    assert m.parse_feed(feed)[0]["title"] == "&a; 標題"


def item(**over):
    base = {"title": "標題 - 某報", "link": "http://a", "summary": "內文", "published": datetime(2026, 10, 16, 23, 0)}
    base.update(over)
    return base


def test_an_official_row_keeps_the_text_and_the_time_it_became_knowable():
    row = m.news_row("cbc_rss", "policy", "official", "all", item(), NOW)
    assert row["kind"] == "policy" and row["source"] == "cbc_rss" and row["stock_id"] == "" and row["name"] == "all"
    assert row["title"] == "標題 - 某報" and row["body"] == "內文"
    assert row["published_at"] == row["available_at"] == datetime(2026, 10, 16, 23, 0) and row["captured_at"] == NOW
    assert row["meta"]["date_fallback"] is False and row["meta"]["link"] == "http://a" and row["meta"]["publisher"] is None


def test_a_topic_row_records_the_publisher_and_the_topic():
    row = m.news_row("google_news", "news_topic", "intl", "關稅 台灣", item(), NOW)
    assert row["kind"] == "news_topic" and row["meta"]["publisher"] == "某報" and row["meta"]["topic"] == "關稅 台灣" and row["meta"]["group"] == "intl"


def test_the_same_article_found_under_two_topics_is_the_same_item():
    a = m.news_row("google_news", "news_topic", "intl", "關稅 台灣", item(), NOW)
    b = m.news_row("google_news", "news_topic", "tw_policy", "央行 理監事會", item(), NOW)
    assert a["key"] == b["key"] and a["nkey"] == b["nkey"]


def test_official_items_are_identified_by_link_so_the_same_title_with_a_new_link_is_a_new_item():
    a = m.news_row("ey_rss", "policy", "official", "news", item(link="http://a"), NOW)
    b = m.news_row("ey_rss", "policy", "official", "news", item(link="http://b"), NOW)
    assert a["nkey"] != b["nkey"]


def test_a_correction_is_a_new_revision_of_the_same_item():
    a = m.news_row("cbc_rss", "policy", "official", "all", item(), NOW)
    corrected = m.news_row("cbc_rss", "policy", "official", "all", item(summary="更正"), NOW)
    again = m.news_row("cbc_rss", "policy", "official", "all", item(), datetime(2027, 1, 1))
    assert corrected["nkey"] == a["nkey"] and corrected["key"] != a["key"] and again["key"] == a["key"]


def test_a_missing_time_means_it_became_knowable_when_we_captured_it():
    row = m.news_row("google_news", "news_topic", "intl", "t", item(published=None), NOW)
    assert row["available_at"] == NOW and row["published_at"] is None and row["meta"]["date_fallback"] is True


def test_a_time_more_than_a_day_in_the_future_is_not_trusted():
    limit = NOW + timedelta(days=1)
    assert m.news_row("s", "policy", "g", "t", item(published=limit), NOW)["meta"]["date_fallback"] is False
    late = m.news_row("s", "policy", "g", "t", item(published=limit + timedelta(seconds=1)), NOW)
    assert late["meta"]["date_fallback"] is True and late["available_at"] == NOW


def test_official_items_older_than_the_cutoff_are_left_out_and_recent_ones_kept():
    db, result = run()
    rows = db["wiki_raw"].docs
    assert rows and all(r["available_at"] >= datetime(2026, 10, 14) for r in rows if r["kind"] == "policy")
    assert {r["title"] for r in rows if r["kind"] == "policy"} == {"官方新聞"}
    assert result["status"]["cbc_rss:all"] == "ok 看到 2 則，納入 1 則"


def test_a_failing_official_feed_is_reported_and_the_others_still_run():
    bad = dict.fromkeys([u for s, l, u in m.OFFICIAL_FEEDS if s == "cbc_rss"], TimeoutError("逾時"))
    db, result = run(Fetch(bad))
    assert result["status"]["cbc_rss:all"].startswith("失敗 TimeoutError")
    assert result["status"]["fed_rss:press_all"].startswith("ok")
    assert {r["source"] for r in db["wiki_raw"].docs} >= {"fed_rss", "ey_rss"} and "cbc_rss" not in {r["source"] for r in db["wiki_raw"].docs}


def test_a_feed_that_parses_to_nothing_counts_as_a_failure():
    empty = dict.fromkeys([u for s, l, u in m.OFFICIAL_FEEDS if s == "ey_rss"], "<html>blocked</html>")
    _, result = run(Fetch(empty))
    assert result["status"]["ey_rss:news"].startswith("失敗")


def test_google_stops_after_three_failures_in_a_row_instead_of_hammering():
    fetch = Fetch(google=lambda url: ConnectionError("429"))
    _, result = run(fetch)
    google_calls = [u for u in fetch.calls if "news.google.com" in u]
    skipped = [s for n, s in result["status"].items() if n.startswith("google:") and s.startswith("略過")]
    assert len(google_calls) == m.MAX_GOOGLE_FAILURES and len(skipped) == len(m.GOOGLE_TOPICS) - m.MAX_GOOGLE_FAILURES


def test_a_success_resets_the_failure_count():
    outcomes = iter([ConnectionError("x"), ConnectionError("x"), rss(("好 - 報", "http://g", RECENT, "")), ConnectionError("x"), ConnectionError("x")])
    fetch = Fetch(google=lambda url: next(outcomes, rss(("後面 - 報", "http://h", RECENT, ""))))
    _, result = run(fetch)
    assert not any(s.startswith("略過") for s in result["status"].values())


def test_only_the_newest_items_per_topic_are_kept():
    many = rss(*[(f"第 {i} 則 - 報", f"http://g/{i}", f"Fri, 16 Oct 2026 {i % 24:02d}:00:00 GMT", "") for i in range(40)])
    db, _ = run(Fetch(google=lambda url: many if "q=%E5%87%BA%E5%8F%A3" in url else rss()))
    topic_rows = [r for r in db["wiki_raw"].docs if r["kind"] == "news_topic"]
    assert len(topic_rows) == m.PER_TOPIC_LIMIT
    assert min(r["available_at"] for r in topic_rows) >= sorted(m.parse_time(f"Fri, 16 Oct 2026 {i % 24:02d}:00:00 GMT") for i in range(40))[-m.PER_TOPIC_LIMIT]


def test_google_queries_are_paused_between_requests_but_not_before_the_first():
    sleeper = Sleeper()
    run(sleep=sleeper, industries=["半導體業"])
    assert sleeper.calls == [m.GOOGLE_PAUSE] * (len(m.GOOGLE_TOPICS) + 1 - 1)


def test_the_google_url_asks_for_the_requested_number_of_days_and_quotes_the_topic():
    url = m.google_url("關稅 台灣", 3)
    assert "q=%E9%97%9C%E7%A8%85%20%E5%8F%B0%E7%81%A3%20when%3A3d&" in url and "hl=zh-TW" in url and "&when=" not in url


def test_industry_names_become_short_topics_without_stray_spaces():
    got = m.industry_topics([" 建材營造", "水 泥工業", "半導體業", "金融業", "電機機械", "X業"])
    assert got == [("industry", "建材營造 產業動態"), ("industry", "水泥 產業動態"), ("industry", "半導體 產業動態"),
                   ("industry", "金融 產業動態"), ("industry", "電機機械 產業動態"), ("industry", "X業 產業動態")]


def test_capture_is_idempotent_and_the_archive_keeps_what_the_source_drops():
    db, first = run(industries=["半導體業"])
    count = len(db["wiki_raw"].docs)
    assert first["added"] == count > 0
    _, second = run(Fetch(), db=db, industries=["半導體業"])
    assert second["added"] == 0 and len(db["wiki_raw"].docs) == count
    gone = {u: rss() for s, l, u in m.OFFICIAL_FEEDS}
    _, third = run(Fetch(gone, google=rss()), db=db)
    assert len(db["wiki_raw"].docs) == count


def test_the_same_article_under_several_topics_is_stored_once():
    db, result = run(Fetch(google=rss(("同一篇 - 某報", "http://same", RECENT, ""))))
    assert result["seen"] > 3 and len([r for r in db["wiki_raw"].docs if r["kind"] == "news_topic"]) == 1


def test_dry_run_counts_but_writes_nothing():
    db, result = run(dry_run=True)
    assert result["added"] > 0 and db["wiki_raw"].docs == [] and db["wiki_raw"].inserts == []


def test_every_row_is_market_level_not_a_stock():
    db, _ = run(industries=["金融業"])
    assert {r["stock_id"] for r in db["wiki_raw"].docs} == {""} and {r["kind"] for r in db["wiki_raw"].docs} == {"policy", "news_topic"}


def test_main_defaults_to_the_last_three_days_for_official_feeds(capsys):
    table = {u: rss(("三天內 - x", "http://in", "Wed, 14 Oct 2026 16:00:00 GMT", ""), ("三天外 - x", "http://out", "Tue, 13 Oct 2026 15:00:00 GMT", "")) for s, l, u in m.OFFICIAL_FEEDS}
    db = Db()
    code = m.main(["capture"], db=db, now=lambda: NOW, fetch=Fetch(table, google=rss()), sleep=Sleeper(), industries=[])
    titles = {r["title"] for r in db["wiki_raw"].docs if r["kind"] == "policy"}
    assert code == 0 and titles == {"三天內 - x"}
    assert "新增" in capsys.readouterr().out


def test_main_exits_nonzero_when_an_official_feed_failed_but_not_when_only_google_did(capsys):
    bad = dict.fromkeys([u for s, l, u in m.OFFICIAL_FEEDS if s == "fed_rss"], OSError("x"))
    assert m.main(["capture"], db=Db(), now=lambda: NOW, fetch=Fetch(bad), sleep=Sleeper(), industries=[]) == 1
    assert "失敗" in capsys.readouterr().out
    assert m.main(["capture"], db=Db(), now=lambda: NOW, fetch=Fetch(google=lambda u: OSError("x")), sleep=Sleeper(), industries=[]) == 0


def test_main_dry_run_and_since_are_passed_through(capsys):
    db = Db()
    m.main(["capture", "--dry-run", "--since", "2026-01-01", "--days", "5"], db=db, now=lambda: NOW, fetch=Fetch(), sleep=Sleeper(), industries=[])
    out = capsys.readouterr().out
    assert db["wiki_raw"].docs == [] and "將新增" in out


def test_the_default_google_window_is_two_days():
    fetch = Fetch()
    m.main(["capture"], db=Db(), now=lambda: NOW, fetch=fetch, sleep=Sleeper(), industries=[])
    assert all("%20when%3A2d&" in u for u in fetch.calls if "news.google.com" in u)


def test_without_an_explicit_list_every_system_industry_gets_a_query():
    from src.ops.readonly_tools import INDUSTRIES

    fetch = Fetch()
    m.main(["capture"], db=Db(), now=lambda: NOW, fetch=fetch, sleep=Sleeper())
    assert len([u for u in fetch.calls if "news.google.com" in u]) == len(m.GOOGLE_TOPICS) + len(INDUSTRIES)


def test_fractional_seconds_are_dropped_from_iso_times():
    assert m.parse_time("2026-10-16T15:00:00.987654Z") == datetime(2026, 10, 16, 23, 0, 0)


def test_the_dublin_core_date_is_used_when_there_is_no_pubdate():
    feed = "<rss><channel><item><title>甲</title><dc:date>2026-10-16T15:00:00Z</dc:date></item></channel></rss>"
    assert m.parse_feed(feed)[0]["published"] == datetime(2026, 10, 16, 23, 0)


def test_a_topic_article_is_identified_by_its_title_not_its_link():
    a = m.news_row("google_news", "news_topic", "intl", "t", item(link="http://one"), NOW)
    b = m.news_row("google_news", "news_topic", "intl", "t", item(link="http://two"), NOW)
    assert a["nkey"] == b["nkey"]


def test_capture_makes_sure_the_unique_key_index_exists():
    class Indexed(Coll):
        def create_index(self, spec, **kwargs):
            self.indexes = getattr(self, "indexes", []) + [(spec, kwargs)]

    db = Db()
    db["wiki_raw"] = Indexed()
    run(db=db)
    assert ("key", {"unique": True}) in db["wiki_raw"].indexes


def test_articles_older_than_the_query_window_are_dropped_but_undated_ones_are_kept():
    feed = rss(("新的 - 報", "http://n", RECENT, ""), ("很舊的 - 報", "http://o", "Wed, 01 Aug 2018 01:00:00 GMT", ""), ("沒日期 - 報", "http://u", "", ""))
    db, _ = run(Fetch(google=lambda url: feed if "q=%E5%87%BA%E5%8F%A3" in url else rss()))
    assert {r["title"] for r in db["wiki_raw"].docs if r["kind"] == "news_topic"} == {"新的 - 報", "沒日期 - 報"}


def test_the_window_edge_is_one_day_beyond_the_requested_days():
    edge = (NOW - timedelta(days=3)).strftime("%a, %d %b %Y %H:%M:%S +0800")
    just_over = (NOW - timedelta(days=3, seconds=1)).strftime("%a, %d %b %Y %H:%M:%S +0800")
    feed = rss(("剛好 - 報", "http://e", edge, ""), ("超過 - 報", "http://j", just_over, ""))
    db, _ = run(Fetch(google=lambda url: feed if "q=%E5%87%BA%E5%8F%A3" in url else rss()), days=2)
    assert {r["title"] for r in db["wiki_raw"].docs if r["kind"] == "news_topic"} == {"剛好 - 報"}
