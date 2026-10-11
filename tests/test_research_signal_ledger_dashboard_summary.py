"""TDD: 帳本 dashboard 的方法彙總（純資料，不依賴 Streamlit，也沒有任何寫入）。"""

from dataclasses import dataclass
from datetime import date

import pytest

from dashboard.pages.research_signal_ledger import (
    HORIZONS,
    method_summary,
    status_label,
)


pytestmark = pytest.mark.unit


@dataclass(frozen=True)
class Row:
    source: str
    signal_kind: str
    rule_version: str
    analysis_date: date
    gross_return_pct: float
    net_return_pct: float
    excess_mkt_pct: float | None
    hit: bool | None


def row(source="daily_picks", kind="factor_rank", day=1, gross=2.0, net=1.4, excess=1.0, hit=True):
    return Row(source, kind, "v1", date(2026, 10, day), gross, net, excess, hit)


def test_rows_are_summarised_per_method_with_sample_size_and_means():
    summary = method_summary(
        [row(day=1, gross=4.0, net=3.4, excess=2.0), row(day=2, gross=2.0, net=1.4, excess=0.0)]
    )

    assert len(summary) == 1
    entry = summary[0]
    assert (entry["source"], entry["signal_kind"]) == ("daily_picks", "factor_rank")
    assert entry["samples"] == 2
    assert entry["analysis_days"] == 2
    assert entry["mean_gross_pct"] == pytest.approx(3.0)
    assert entry["mean_net_pct"] == pytest.approx(2.4)
    assert entry["mean_excess_pct"] == pytest.approx(1.0)


def test_hit_rate_only_counts_rows_with_a_hit_verdict():
    summary = method_summary([row(hit=True), row(hit=False), row(hit=None), row(hit=True)])

    assert summary[0]["hit_rate_pct"] == pytest.approx(200 / 3)


def test_hit_rate_is_none_when_no_row_is_measurable():
    assert method_summary([row(hit=None)])[0]["hit_rate_pct"] is None


def test_excess_ignores_rows_without_a_benchmark():
    summary = method_summary([row(excess=3.0), row(excess=None)])

    assert summary[0]["mean_excess_pct"] == pytest.approx(3.0)


def test_methods_are_listed_separately_and_sorted_by_name():
    summary = method_summary([row("technical", "vcp"), row("chip", "chip_verdict"), row("chip", "chip_verdict")])

    assert [(e["source"], e["samples"]) for e in summary] == [("chip", 2), ("technical", 1)]


def test_a_thin_sample_is_flagged_so_it_is_not_over_read():
    summary = method_summary([row(day=1)])

    assert summary[0]["thin"] is True


def test_no_rows_yield_an_empty_summary():
    assert method_summary([]) == []


def test_status_label_distinguishes_all_states_and_the_unknown_case():
    assert status_label(None) == "尚無狀態（觀察中）"
    assert "降權" in status_label("degraded")
    assert "停用" in status_label("disabled")
    assert status_label("observe") != status_label("active")


def test_the_page_offers_the_three_supported_horizons_only():
    assert HORIZONS == (5, 10, 20)


@dataclass(frozen=True)
class Out:
    snapshot_key: str
    revision: int
    gross_return_pct: float
    net_return_pct: float
    excess_mkt_pct: float | None
    hit: bool | None


def snap(key, enabled=True, source="daily_picks", kind="factor_rank"):
    return {
        "snapshot_key": key,
        "source": source,
        "signal_kind": kind,
        "rule_version": "v1",
        "analysis_date": "2026-10-08",
        "evaluation_enabled": enabled,
    }


def test_joined_rows_use_only_the_latest_revision_of_each_outcome():
    from dashboard.pages.research_signal_ledger import joined_rows

    rows = joined_rows(
        [snap("a")],
        [Out("a", 1, 1.0, 0.4, 0.0, False), Out("a", 2, 5.0, 4.4, 3.0, True)],
    )

    assert [(r.net_return_pct, r.hit) for r in rows] == [(4.4, True)]


def test_joined_rows_skip_snapshots_that_are_not_evaluable_or_have_no_outcome():
    from dashboard.pages.research_signal_ledger import joined_rows

    rows = joined_rows(
        [snap("a", enabled=False), snap("b"), snap("c")],
        [Out("a", 1, 1.0, 0.4, 0.0, True), Out("b", 1, 2.0, 1.4, 1.0, True)],
    )

    assert [r.snapshot_key if hasattr(r, "snapshot_key") else r.net_return_pct for r in rows] == [1.4]


def test_the_page_module_has_no_write_path():
    import inspect

    import dashboard.pages.research_signal_ledger as page

    source = inspect.getsource(page)
    for forbidden in (".insert_", ".update_", ".replace_", ".delete_", "save_method_status", "append_outcome"):
        assert forbidden not in source, f"read-only page must not contain {forbidden}"
