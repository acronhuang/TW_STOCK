"""TDD: PTT Stock 板每日討論熱度與標題情緒（個股提及數、推文數、情緒分數）。"""

from datetime import date, datetime

import pytest

from src.ingest import ptt

pytestmark = pytest.mark.unit

TODAY = date(2026, 10, 11)

PAGE = """
<div class="btn-group btn-group-paging">
  <a class="btn wide" href="/bbs/Stock/index1.html">最舊</a>
  <a class="btn wide" href="/bbs/Stock/index10441.html">&lsaquo; 上頁</a>
  <a class="btn wide disabled">下頁 &rsaquo;</a>
</div>
<div class="r-ent">
  <div class="nrec"><span class="hl f3">爆</span></div>
  <div class="title">
    <a href="/bbs/Stock/M.1791646400.A.DDD.html">[標的] 台積電 2330 法說後看多</a>
  </div>
  <div class="meta"><div class="author">alice</div><div class="date">10/10</div><div class="mark"></div></div>
</div>
<div class="r-ent">
  <div class="nrec"><span class="hl f2">23</span></div>
  <div class="title"><a href="/bbs/Stock/M.1791646401.A.AAA.html">[新聞] 聯電 擴產 受惠</a></div>
  <div class="meta"><div class="author">bob</div><div class="date"> 9/30</div></div>
</div>
<div class="r-ent">
  <div class="nrec"><span class="hl f1">X2</span></div>
  <div class="title"><a href="/bbs/Stock/M.1791646402.A.BBB.html">Re: [閒聊] 大盤今天好慘</a></div>
  <div class="meta"><div class="author">carol</div><div class="date">10/11</div></div>
</div>
<div class="r-ent">
  <div class="nrec"></div>
  <div class="title">(本文已被刪除) [dave]</div>
  <div class="meta"><div class="author">-</div><div class="date">10/11</div></div>
</div>
<div class="r-list-sep"></div>
<div class="r-ent">
  <div class="nrec"><span class="hl f2">15</span></div>
  <div class="title"><a href="/bbs/Stock/M.1.A.PIN.html">[公告] 置頂版規</a></div>
  <div class="meta"><div class="author">mod</div><div class="date"> 1/01</div></div>
</div>
"""


def test_index_page_posts_are_parsed_with_absolute_url_date_and_push_count():
    posts, _ = ptt.parse_index(PAGE, TODAY)

    first = posts[0]
    assert first == {"title": "[標的] 台積電 2330 法說後看多", "url": "https://www.ptt.cc/bbs/Stock/M.1791646400.A.DDD.html",
                     "author": "alice", "date": date(2026, 10, 10), "push": 100}
    assert posts[1]["push"] == 23 and posts[1]["date"] == date(2026, 9, 30)
    assert posts[2]["push"] == -20


def test_deleted_posts_and_the_pinned_section_below_the_separator_are_ignored():
    posts, _ = ptt.parse_index(PAGE, TODAY)

    assert [p["title"] for p in posts] == ["[標的] 台積電 2330 法說後看多", "[新聞] 聯電 擴產 受惠",
                                           "Re: [閒聊] 大盤今天好慘"]


def test_previous_page_link_is_returned_for_walking_back_in_time():
    _, previous = ptt.parse_index(PAGE, TODAY)

    assert previous == "https://www.ptt.cc/bbs/Stock/index10441.html"


def test_a_december_post_seen_in_january_belongs_to_the_previous_year():
    html = PAGE.replace("10/10", "12/30")

    posts, _ = ptt.parse_index(html, date(2027, 1, 2))

    assert posts[0]["date"] == date(2026, 12, 30)


@pytest.mark.parametrize("text,expected", [("爆", 100), ("23", 23), ("", 0), ("X1", -10), ("XX", -100), ("??", 0)])
def test_push_count_symbols(text, expected):
    assert ptt.push_count(text) == expected


UNIVERSE = [("2330", "台積電"), ("2303", "聯電"), ("2013", "中鋼構"), ("2002", "中鋼"), ("1234", "黑松"),
            ("2026", "某公司"), ("1101", "台泥"), ("5287", "數字")]


def test_codes_and_long_names_match_anywhere_in_the_title():
    matcher = ptt.Matcher(UNIVERSE)

    assert matcher.match("[標的] 台積電 2330 法說後看多") == {"2330"}
    assert matcher.match("[心得] 台積電法說觀察") == {"2330"}


def test_two_character_names_only_count_in_target_posts_because_they_are_often_ordinary_words():
    matcher = ptt.Matcher(UNIVERSE)

    assert matcher.match("[標的] 聯電 逢低布局") == {"2303"}
    assert matcher.match("Re: [標的] 聯電 逢低布局") == {"2303"}
    assert matcher.match("[新聞] 聯電 擴產 受惠") == set()
    assert matcher.match("[新聞] OpenAI 年化營收比先前透露的數字少") == set()
    assert matcher.match("[情報] 2303 聯電 9月營收") == {"2303"}


def test_a_longer_name_hides_the_shorter_name_it_contains():
    matcher = ptt.Matcher(UNIVERSE)

    assert matcher.match("[標的] 中鋼構 接單創新高") == {"2013"}


def test_years_dates_prices_and_larger_numbers_are_not_stock_codes():
    matcher = ptt.Matcher(UNIVERSE)

    assert matcher.match("[閒聊] 2026年的行情") == set()
    assert matcher.match("[閒聊] 目標價 2026元") == set()
    assert matcher.match("[閒聊] 成交 120260 張") == set()
    assert matcher.match("[標的] 黑松1234 觀察") == {"1234"}


def post(title, push=0, day=date(2026, 10, 10), url="u"):
    return {"title": title, "push": push, "date": day, "url": url, "author": "a"}


def test_aggregate_counts_mentions_pushes_and_title_sentiment_per_stock_and_day():
    matcher = ptt.Matcher(UNIVERSE)
    posts = [post("[標的] 台積電 大漲 創新高", 100, url="a"), post("[標的] 台積電 下跌 看空", -10, url="b"),
             post("[標的] 聯電 擴產", 5, url="c"), post("[標的] 台積電 2330 隔日", 3, date(2026, 10, 9), url="d")]

    rows = {(r["stock_id"], r["date"]): r for r in ptt.aggregate(posts, matcher)}

    tsmc = rows[("2330", datetime(2026, 10, 10))]
    assert tsmc["mentions"] == 2 and tsmc["push_sum"] == 90 and tsmc["bullish"] == 1 and tsmc["bearish"] == 1
    assert tsmc["source"] == "ptt" and tsmc["score"] == 0.0
    assert [p["url"] for p in tsmc["top_posts"]] == ["a", "b"]
    assert rows[("2330", datetime(2026, 10, 9))]["mentions"] == 1
    assert rows[("2303", datetime(2026, 10, 10))]["mentions"] == 1


def test_explicit_bull_and_bear_tags_shift_the_score():
    matcher = ptt.Matcher(UNIVERSE)

    [bull] = ptt.aggregate([post("[標的] 台積電 [多] 觀察")], matcher)
    [bear] = ptt.aggregate([post("[標的] 台積電 [空] 觀察")], matcher)

    assert bull["score"] == 20.0 and bear["score"] == -20.0


def test_the_trailing_direction_word_used_in_target_posts_also_shifts_the_score():
    matcher = ptt.Matcher(UNIVERSE)

    [bull] = ptt.aggregate([post("[標的] 2330 台積電 多")], matcher)
    [bear] = ptt.aggregate([post("[標的] 2330 台積電 空")], matcher)
    [plain] = ptt.aggregate([post("[標的] 多檔台積電觀察")], matcher)

    assert (bull["score"], bear["score"], plain["score"]) == (20.0, -20.0, 0.0)


def test_a_post_mentioning_two_stocks_counts_for_both():
    matcher = ptt.Matcher(UNIVERSE)

    rows = ptt.aggregate([post("[標的] 台積電 與 台泥 比較")], matcher)

    assert sorted(r["stock_id"] for r in rows) == ["1101", "2330"]


def test_buzz_ratio_compares_today_with_the_recent_baseline_and_needs_enough_history():
    assert ptt.buzz_ratio(10, [1, 1, 1, 1, 1]) == 5.5
    assert ptt.buzz_ratio(0, [4, 4, 4, 4, 4]) == 0.2
    assert ptt.buzz_ratio(10, [1, 1, 1]) is None


def test_attach_buzz_zero_fills_crawled_days_without_mentions_and_needs_enough_history():
    days = [datetime(2026, 10, d) for d in (1, 2, 3, 4, 5)]
    rows = [{"stock_id": "2330", "date": datetime(2026, 10, 6), "mentions": 10}]
    history = {("2330", days[0]): 1, ("2330", days[1]): 1}

    assert ptt.attach_buzz(rows, history, set(days))[0]["buzz_ratio"] == 7.86
    assert ptt.attach_buzz(rows, history, set(days[:3]))[0]["buzz_ratio"] is None


class FakeBoard:
    def __init__(self, pages):
        self.pages = pages
        self.fetched = []

    def __call__(self, url):
        self.fetched.append(url)
        return self.pages[url]


def page(day_label, previous, count=2):
    rows = "".join(
        f'<div class="r-ent"><div class="nrec"></div><div class="title"><a href="/bbs/Stock/M.{day_label}.{i}.html">'
        f'[標的] 台積電 {i}</a></div><div class="meta"><div class="author">a</div><div class="date">{day_label}</div></div></div>'
        for i in range(count))
    link = f'<a class="btn wide" href="{previous}">&lsaquo; 上頁</a>' if previous else ""
    return f'<div class="btn-group btn-group-paging">{link}</div>{rows}'


def test_crawl_walks_back_until_a_whole_page_is_older_than_the_cutoff_and_sleeps_between_pages():
    pages = {
        ptt.BOARD_URL: page("10/11", "/bbs/Stock/index3.html"),
        "https://www.ptt.cc/bbs/Stock/index3.html": page("10/10", "/bbs/Stock/index2.html"),
        "https://www.ptt.cc/bbs/Stock/index2.html": page("10/09", "/bbs/Stock/index1.html"),
        "https://www.ptt.cc/bbs/Stock/index1.html": page("10/08", None),
    }
    board, sleeps = FakeBoard(pages), []

    posts = ptt.crawl(board, today=date(2026, 10, 11), days_back=2, sleep=lambda s: sleeps.append(s), pause=1.0)

    assert {p["date"] for p in posts} == {date(2026, 10, 11), date(2026, 10, 10)}
    assert len(board.fetched) == 3          # 10/09 這頁整頁都早於截止日，停止，不抓更舊的
    assert sleeps == [1.0, 1.0]


def test_crawl_never_exceeds_the_page_limit():
    pages = {ptt.BOARD_URL: page("10/11", "/bbs/Stock/index9.html")}
    for n in range(9, 0, -1):
        pages[f"https://www.ptt.cc/bbs/Stock/index{n}.html"] = page("10/11", f"/bbs/Stock/index{n - 1}.html")

    board = FakeBoard(pages)
    ptt.crawl(board, today=date(2026, 10, 11), days_back=2, sleep=lambda s: None, max_pages=4)

    assert len(board.fetched) == 4
