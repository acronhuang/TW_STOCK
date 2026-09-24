"""網頁補充搜尋測試。"""
from unittest.mock import Mock, patch

import pytest
import requests

from src.analysis.web_search import google_news_search, search_news_by_mode


@pytest.fixture(autouse=True)
def _clear_news_cache():
    """每測試前清快取，避免 TTL 快取跨測試污染。"""
    from src.analysis import web_search as ws
    ws.clear_news_cache()
    yield
    ws.clear_news_cache()


@pytest.mark.unit
def test_google_news_search_returns_title_url_and_source():
    response = Mock()
    response.raise_for_status.return_value = None
    response.text = """<?xml version="1.0"?>
    <rss><channel><item>
      <title>台股市場快訊 - 範例新聞</title>
      <link>https://example.com/news</link>
      <pubDate>Thu, 04 Sep 2026 01:00:00 GMT</pubDate>
    </item></channel></rss>"""

    with patch('src.analysis.web_search.requests.get', return_value=response):
        results = google_news_search('台股', max_items=1)

    assert results == [{
        'title': '台股市場快訊 - 範例新聞',
        'url': 'https://example.com/news',
        'published_at': 'Thu, 04 Sep 2026 01:00:00 GMT',
        'source': 'Google News RSS · 繁中解讀',
    }]


@pytest.mark.unit
def test_google_news_search_deduplicates_by_url():
    """同一連結重複出現時只保留第一筆，避免外部證據被灌水。"""
    response = Mock()
    response.raise_for_status.return_value = None
    response.text = """<rss><channel>
      <item><title>Fed A</title><link>https://ex.com/fed</link><pubDate>t1</pubDate></item>
      <item><title>Fed A (dup)</title><link>https://ex.com/fed</link><pubDate>t2</pubDate></item>
      <item><title>Fed B</title><link>https://ex.com/other</link><pubDate>t3</pubDate></item>
    </channel></rss>"""

    with patch('src.analysis.web_search.requests.get', return_value=response):
        results = google_news_search('Fed', max_items=5)

    assert [r['url'] for r in results] == ['https://ex.com/fed', 'https://ex.com/other']


@pytest.mark.unit
def test_google_news_search_fails_open_on_request_error():
    with patch('src.analysis.web_search.requests.get', side_effect=requests.RequestException):
        assert google_news_search('台股') == []


@pytest.mark.unit
def test_google_news_search_uses_english_us_feed_and_priority_sources():
    response = Mock()
    response.raise_for_status.return_value = None
    response.text = '<rss><channel></channel></rss>'

    with patch('src.analysis.web_search.requests.get', return_value=response) as get:
        google_news_search('Fed rate hike', region='international_en')

    assert get.call_args.kwargs['params'] == {
        'q': 'Fed rate hike (site:reuters.com OR site:bloomberg.com OR site:cnbc.com OR site:ft.com)',
        'hl': 'en-US', 'gl': 'US', 'ceid': 'US:en',
    }


@pytest.mark.unit
def test_combined_news_mode_keeps_taiwan_and_english_results_separate():
    with patch('src.analysis.web_search.google_news_search', side_effect=[
        [{'title': '繁中解讀'}], [{'title': 'English original'}],
    ]):
        grouped = search_news_by_mode('Fed rate hike', '綜合：繁中＋英文原始')

    assert grouped == {
        '繁中解讀': [{'title': '繁中解讀'}],
        '國際英文原始新聞': [{'title': 'English original'}],
    }


@pytest.mark.unit
def test_all_sources_mode_keeps_every_region_separate():
    with patch('src.analysis.web_search.google_news_search', side_effect=[
        [{'title': '繁中'}], [{'title': 'English'}], [{'title': '日本'}],
        [{'title': '中國'}], [{'title': '香港'}],
    ]):
        grouped = search_news_by_mode('AI supply chain', '綜合：所有來源')

    assert list(grouped) == ['繁中解讀', '國際英文原始新聞', '日本新聞', '中國新聞（簡中）', '香港新聞（繁中）']
    assert [items[0]['title'] for items in grouped.values()] == ['繁中', 'English', '日本', '中國', '香港']

@pytest.mark.unit
def test_google_news_search_truncates_overlong_title():
    """資源耗用/XSS 面縮小：過長標題被截斷。"""
    from src.analysis.web_search import MAX_TITLE_LEN
    response = Mock()
    response.raise_for_status.return_value = None
    response.text = ("<rss><channel><item><title>" + "A" * 5000 +
                     "</title><link>https://x/y</link></item></channel></rss>")
    with patch('src.analysis.web_search.requests.get', return_value=response):
        results = google_news_search('q', max_items=1)
    assert len(results[0]['title']) <= MAX_TITLE_LEN


@pytest.mark.unit
def test_sanitize_markdown_text_escapes_link_injection():
    from src.analysis.web_search import sanitize_markdown_text
    out = sanitize_markdown_text("evil](javascript:alert(1)) [x")
    assert "](" not in out           # 連結語法被轉義
    assert "\n" not in sanitize_markdown_text("a\nb")


@pytest.mark.unit
def test_safe_external_url_allows_http_only():
    from src.analysis.web_search import safe_external_url
    assert safe_external_url("https://reuters.com/x") == "https://reuters.com/x"
    assert safe_external_url("http://a.com") == "http://a.com"
    assert safe_external_url("javascript:alert(1)") == ""
    assert safe_external_url("data:text/html,<script>") == ""
    assert safe_external_url("") == ""


# ── NewsCache (M2)：TTL 快取，降低外部呼叫（CWE-400）──
def _rss_response(title="A", url="https://x/a"):
    resp = Mock()
    resp.raise_for_status.return_value = None
    resp.text = f'<rss><channel><item><title>{title}</title><link>{url}</link></item></channel></rss>'
    return resp


@pytest.mark.unit
def test_news_cache_ttl_hit_avoids_second_request(monkeypatch):
    from src.analysis import web_search as ws
    monkeypatch.setattr(ws, "_clock", lambda: 1000.0)
    with patch("src.analysis.web_search.requests.get", return_value=_rss_response()) as get:
        r1 = ws.google_news_search("台股", max_items=1)
        r2 = ws.google_news_search("台股", max_items=1)  # TTL 內
    assert r1 == r2
    assert get.call_count == 1  # 第二次走快取，不觸發 requests


@pytest.mark.unit
def test_news_cache_refetches_after_ttl_expiry(monkeypatch):
    from src.analysis import web_search as ws
    now = {"v": 0.0}
    monkeypatch.setattr(ws, "_clock", lambda: now["v"])
    with patch("src.analysis.web_search.requests.get", return_value=_rss_response()) as get:
        ws.google_news_search("台股", max_items=1)
        now["v"] = ws.NEWS_CACHE_TTL + 1  # 過期
        ws.google_news_search("台股", max_items=1)
    assert get.call_count == 2


@pytest.mark.unit
def test_news_cache_does_not_cache_failures(monkeypatch):
    from src.analysis import web_search as ws
    monkeypatch.setattr(ws, "_clock", lambda: 5.0)
    with patch("src.analysis.web_search.requests.get",
               side_effect=requests.RequestException) as get:
        assert ws.google_news_search("台股") == []
        assert ws.google_news_search("台股") == []
    assert get.call_count == 2  # 失敗不快取，允許重試


@pytest.mark.unit
def test_google_news_search_bounds_work_to_max_items():
    """大量 item 也只回 max_items（有界工作量，降 ReDoS/資源耗用）。"""
    items = "".join(
        f"<item><title>T{i}</title><link>https://x/{i}</link></item>" for i in range(500))
    resp = Mock()
    resp.raise_for_status.return_value = None
    resp.text = f"<rss><channel>{items}</channel></rss>"
    with patch("src.analysis.web_search.requests.get", return_value=resp):
        results = google_news_search("q", max_items=3)
    assert len(results) == 3
