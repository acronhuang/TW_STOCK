"""TDD: 新聞標題情緒每日入庫（news_sentiment）與詞典評分。"""

from datetime import datetime

import pytest

from src.ingest import news_sentiment, text_sentiment

pytestmark = pytest.mark.unit

DAY = datetime(2026, 10, 12)
NOW = datetime(2026, 10, 12, 23, 10)


def test_lexicon_score_is_the_share_of_positive_minus_negative_hits_in_percent():
    assert text_sentiment.score_text("台積電大漲創新高") == 100
    assert text_sentiment.score_text("外資賣超 股價下跌") == -100
    assert text_sentiment.score_text("漲多回檔") == 0
    assert text_sentiment.score_text("今天天氣不錯") == 0


def test_labels_follow_the_thresholds_used_by_the_live_analyzer():
    assert text_sentiment.label(None) == "無資料"
    assert [text_sentiment.label(s) for s in (50, 20, 0, -20, -50)] == ["強烈看多", "偏多", "中性", "偏空", "強烈看空"]


def test_summary_counts_positive_negative_and_neutral_titles_and_averages_the_score():
    titles = ["台積電大漲創新高", "外資賣超 股價下跌", "台積電法說會登場", "台積電獲利成長 看好"]

    summary = news_sentiment.summarize(titles)

    assert summary["count"] == 4 and summary["positive"] == 2 and summary["negative"] == 1 and summary["neutral"] == 1
    assert summary["score"] == 25.0 and summary["label"] == "偏多"


def test_no_titles_means_no_score_instead_of_a_fake_neutral_zero():
    summary = news_sentiment.summarize([])

    assert summary["count"] == 0 and summary["score"] is None and summary["label"] == "無資料"


def test_only_the_first_ten_titles_are_kept_as_evidence():
    summary = news_sentiment.summarize([f"新聞{i}" for i in range(25)])

    assert summary["count"] == 25 and len(summary["titles"]) == 10


def test_document_is_keyed_by_stock_day_and_source_with_a_taipei_midnight_date():
    doc = news_sentiment.build_doc("2330", "台積電", ["台積電大漲"], datetime(2026, 10, 12, 23, 10), NOW)

    assert doc["stock_id"] == "2330" and doc["date"] == DAY and doc["source"] == "google_news"
    assert doc["name"] == "台積電" and doc["score"] == 100 and doc["updated_at"] == NOW


class Collection:
    def __init__(self):
        self.ops = []

    def bulk_write(self, ops, ordered=False):
        self.ops.extend(ops)

        class Result:
            upserted_count = len(ops)
            modified_count = 0

        return Result()


def test_upsert_is_idempotent_per_stock_day_and_source():
    docs = [news_sentiment.build_doc("2330", "台積電", ["台積電大漲"], NOW, NOW)]
    collection = Collection()

    news_sentiment.upsert(collection, docs)

    assert collection.ops[0]._filter == {"stock_id": "2330", "date": DAY, "source": "google_news"}
    assert collection.ops[0]._upsert is True
    assert news_sentiment.upsert(Collection(), []) is None


def test_focus_universe_unions_holdings_core_list_and_latest_vcp_in_priority_order_without_duplicates():
    positions = [{"symbol": "2330"}, {"symbol": "2317"}]
    core = {"stocks": [{"symbol": "2317"}, {"symbol": "2454"}]}
    vcp = [{"symbol": "2454"}, {"symbol": "3008"}]

    assert news_sentiment.focus_codes(positions, core, vcp) == ["2330", "2317", "2454", "3008"]


def test_focus_universe_tolerates_missing_sources():
    assert news_sentiment.focus_codes([], None, []) == []
    assert news_sentiment.focus_codes([{"symbol": "2330"}, {"nope": 1}], {}, [{"symbol": None}]) == ["2330"]
