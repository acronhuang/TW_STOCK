"""網頁補充搜尋測試。"""
from unittest.mock import Mock, patch

import pytest
import requests

from src.analysis.web_search import google_news_search, search_news_by_mode


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