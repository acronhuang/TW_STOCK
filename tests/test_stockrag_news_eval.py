"""TDD: 新聞與重大訊息查詢集的命中判定（純函式）。"""

from datetime import datetime

import pytest

from scripts import stockrag_news_eval as ev

pytestmark = pytest.mark.unit


def hit(symbol, day, content="主旨：公告買回庫藏股"):
    return {"symbol": symbol, "event_date": datetime.strptime(day, "%Y-%m-%d"), "content": content}


def test_an_entity_expectation_needs_the_same_company_and_the_same_event_day():
    spec = {"symbol": "2474", "date": "2026-09-23"}

    assert ev.hit_matches(hit("2474", "2026-09-23"), spec)
    assert not ev.hit_matches(hit("2474", "2026-09-22"), spec)
    assert not ev.hit_matches(hit("2475", "2026-09-23"), spec)


def test_a_topical_expectation_matches_on_the_text_of_the_notice():
    spec = {"title_regex": "買回.*庫藏股"}

    assert ev.hit_matches(hit("1432", "2026-09-02"), spec)
    assert not ev.hit_matches(hit("1432", "2026-09-02", content="主旨：財務主管異動"), spec)


def test_rank_is_the_first_matching_position_and_none_when_nothing_matches():
    spec = {"symbol": "2474", "date": "2026-09-23"}

    assert ev.rank_of([hit("1", "2026-09-23"), hit("2474", "2026-09-23")], spec) == 2
    assert ev.rank_of([hit("1", "2026-09-23")], spec) is None


def test_the_intraday_cutoffs_sit_one_second_either_side_of_the_statement_time():
    before, at = ev.intraday_cutoffs("2026-10-08", "164608")

    assert before == datetime(2026, 10, 8, 16, 46, 7) and at == datetime(2026, 10, 8, 16, 46, 8)


def test_several_query_files_are_merged_with_the_first_file_defining_the_settings():
    main = {"k": 5, "decision_as_of": "2026-10-11", "thresholds": {"recall": 0.9, "mrr": 0.8}, "pit_sweep_as_of": ["2026-09-15"],
            "queries": [{"id": "e-1"}], "pit_cases": [{"id": "p-1"}]}
    holdout = {"k": 3, "decision_as_of": "2000-01-01", "thresholds": {"recall": 0.0, "mrr": 0.0}, "pit_sweep_as_of": [],
               "queries": [{"id": "n-2"}], "pit_cases": []}

    merged = ev.merge_specs([main, holdout])

    assert merged["k"] == 5 and merged["thresholds"] == {"recall": 0.9, "mrr": 0.8} and merged["decision_as_of"] == "2026-10-11"
    assert [q["id"] for q in merged["queries"]] == ["e-1", "n-2"] and [c["id"] for c in merged["pit_cases"]] == ["p-1"]