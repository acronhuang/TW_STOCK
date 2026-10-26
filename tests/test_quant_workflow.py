import json
from datetime import date

import numpy as np
import pytest

pytestmark = pytest.mark.unit


def test_registration_is_immutable_and_does_not_relabel_history_as_blind(tmp_path):
    from src.research_workflow.registry import register

    source = tmp_path / "prices.csv"
    source.write_text("date,symbol\n2020-01-01,2330\n")
    rules = {"cutoff": "2026-09-18", "historical_research": True}
    result = register(tmp_path / "study", rules, source)
    assert result["historical_research"] is True
    with pytest.raises(FileExistsError):
        register(tmp_path / "study", {**rules, "cutoff": "2026-10-01"}, source)


def test_data_revision_is_rejected_before_reading_prices(tmp_path):
    from src.research_workflow.registry import register, verify

    source = tmp_path / "prices.csv"
    source.write_text("original")
    register(tmp_path / "study", {"historical_research": True}, source)
    source.write_text("revised")
    with pytest.raises(ValueError, match="fingerprint"):
        verify(tmp_path / "study", source)


def test_ledger_keeps_failures_retries_and_hash_chain(tmp_path):
    from src.research_workflow.registry import append_attempt, read_attempts

    path = tmp_path / "ledger.jsonl"
    append_attempt(path, {"group": "A", "status": "error", "config": {"window": 20}})
    append_attempt(path, {"group": "A", "status": "ok", "config": {"window": 20}})
    records = read_attempts(path)
    assert [row["status"] for row in records] == ["error", "ok"]
    rows = path.read_text().splitlines()
    changed = json.loads(rows[0])
    changed["status"] = "ok"
    path.write_text(json.dumps(changed) + "\n" + rows[1] + "\n")
    with pytest.raises(ValueError, match="chain"):
        read_attempts(path)


def test_missing_metrics_never_pass_the_funnel():
    from src.research_workflow.metrics import funnel

    result = funnel({}, {}, neighbors=None, correlation=None, dsr=None)
    assert result["grade"] != "qualified"
    assert result["layers"]["L1"] == "missing"
    assert result["layers"]["L8"] == "missing"


def test_funnel_thresholds_and_incomplete_neighbors():
    from src.research_workflow.metrics import funnel

    train = {"trades": 100, "annual_excess": 0.1, "ir": 0.5,
             "excess_drawdown": 0.2, "positive_years": 6, "complete_years": 9, "nw_t": 4}
    validation = {"annual_excess": 0.02}
    result = funnel(train, validation, neighbors=[True] * 7 + [False] * 3,
                    correlation=0.69, dsr=0.96)
    assert result["grade"] == "qualified"
    assert funnel(train, validation, neighbors=[True, None], correlation=0.1, dsr=0.99)["layers"]["L5"] == "missing"
    assert funnel(train, validation, neighbors=[True], correlation=0.7, dsr=0.99)["layers"]["L7"] == "fail"
    assert funnel(train, validation, neighbors=[True], correlation=0.1, dsr=0.95)["layers"]["L8"] == "fail"


def test_metrics_use_compounding_and_do_not_fill_missing_returns():
    from src.research_workflow.metrics import summarize

    dates = np.array(["2020-01-02", "2020-01-03"], dtype="datetime64[D]")
    result = summarize(dates, np.array([0.1, -0.1]), np.zeros(2), 2)
    assert result["total_return"] == pytest.approx(-0.01)
    assert result["max_drawdown"] == pytest.approx(0.1)
    with pytest.raises(ValueError, match="finite"):
        summarize(dates, np.array([0.1, np.nan]), np.zeros(2), 2)


def test_random_generation_is_reproducible_and_globally_unique():
    from src.research_workflow.search import generate

    first = generate(43, 20, set())
    assert first == generate(43, 20, set())
    occupied = {json.dumps(row, sort_keys=True) for row in first}
    second = generate(44, 20, occupied)
    assert not occupied.intersection(json.dumps(row, sort_keys=True) for row in second)


def test_forward_period_cannot_be_opened_early(tmp_path):
    from src.research_workflow.registry import check_evaluation

    registration = {"rules": {"evaluation": ["2027-03-01", "2027-12-31"],
                               "earliest_evaluation": "2028-01-01"}}
    with pytest.raises(ValueError, match="early"):
        check_evaluation(registration, date(2027, 3, 1))


def test_code_fingerprint_includes_reused_cost_and_portfolio_modules(monkeypatch):
    from src.research_workflow import registry

    seen = []
    original = registry.file_hash
    monkeypatch.setattr(registry, "file_hash", lambda path: seen.append(path.name) or original(path))
    registry.code_hash()
    assert {"portfolio.py", "tw_costs.py", "slippage.py"} <= set(seen)


def price_world(days=320, stocks=3):
    import pandas as pd

    rows = []
    for offset, stamp in enumerate(pd.bdate_range("2020-01-02", periods=days)):
        for column in range(stocks):
            price = 20 + offset * 0.02 + column
            rows.append({"date": stamp, "symbol": str(2300 + column), "open": price,
                         "close": price + 0.01, "adj_open": price, "adj_close": price + 0.01,
                         "volume": 2000000, "can_buy": True, "can_sell": True,
                         "eligible": True, "listed_on": "2000-01-01", "cash_dividend": 0.0,
                         "share_ratio": 1.0})
    return pd.DataFrame(rows)


def engine_rules():
    return {"initial_cash": 1000000, "max_positions": 10, "lot_size": 1000,
            "slippage_bps": 10, "strict_tradability": True, "min_listing_bars": 20,
            "min_value_20": 20000000}


def config():
    return {"factor": "momentum", "window": 5, "hold": 3, "slots": 3,
            "rebalance": 5, "reverse": False, "threshold": 0.0}


def test_backtest_executes_after_the_signal_and_uses_real_costs_and_board_lots():
    from src.research_workflow.engine import backtest

    result = backtest(price_world(), config(), engine_rules(), "2020-03-01", "2021-01-01")
    assert result["trades"]
    for trade in result["trades"]:
        assert trade["date"] > trade["signal_date"]
        assert trade["shares"] % 1000 == 0
        assert trade["commission"] > 0
    assert min(result["cash"]) >= 0
    assert result["execution_verified"] is True


def test_limit_up_and_suspension_prevent_buys_and_missing_constraints_are_not_assumed():
    from src.research_workflow.engine import backtest

    frame = price_world()
    frame["can_buy"] = False
    assert not backtest(frame, config(), engine_rules(), "2020-03-01", "2021-01-01")["trades"]
    with pytest.raises(ValueError, match="tradability"):
        backtest(frame.drop(columns="can_buy"), config(), engine_rules(), "2020-03-01", "2021-01-01")


def test_future_price_changes_do_not_change_prior_trades_or_nav():
    from src.research_workflow.engine import backtest

    frame = price_world()
    before = backtest(frame, config(), engine_rules(), "2020-03-01", "2021-01-01")
    modified = frame.copy()
    future = modified["date"] >= "2020-10-01"
    modified.loc[future, ["open", "close", "adj_open", "adj_close"]] *= 3
    after = backtest(modified, config(), engine_rules(), "2020-03-01", "2021-01-01")
    count = sum(stamp < "2020-10-01" for stamp in before["dates"])
    assert before["returns"][:count] == after["returns"][:count]
    assert [row for row in before["trades"] if row["date"] < "2020-10-01"] == [row for row in after["trades"] if row["date"] < "2020-10-01"]


def test_sell_orders_blocked_by_limit_down_are_retried():
    from src.research_workflow.engine import backtest

    frame = price_world()
    frame.loc[frame["date"] < "2020-04-01", "can_sell"] = False
    result = backtest(frame, config(), engine_rules(), "2020-03-01", "2020-05-01")
    sales = [row for row in result["trades"] if row["action"] == "SELL"]
    assert sales and all(row["date"] >= "2020-04-01" for row in sales)


def test_unknown_delisting_valuation_fails_instead_of_disappearing():
    from src.research_workflow.engine import backtest

    frame = price_world(stocks=1)
    frame = frame[frame["date"] < "2020-04-01"]
    with pytest.raises(ValueError, match="coverage"):
        backtest(frame, config(), engine_rules(), "2020-03-01", "2020-06-01")


def workflow_world(tmp_path):
    from src.research_workflow.workflow import initialize

    source = tmp_path / "prices.csv"
    price_world().to_csv(source, index=False)
    rules = {**engine_rules(), "historical_research": True, "cutoff": "2020-11-30",
             "search": ["2020-03-01", "2020-05-31"], "validation": ["2020-06-01", "2020-08-31"],
             "evaluation": ["2020-09-01", "2020-11-30"], "earliest_evaluation": "2020-12-01",
             "rounds": 1, "configs_per_round": 1, "random_seeds": [43, 1]}
    directory = tmp_path / "study"
    initialize(directory, rules, source)
    return directory


def test_workflow_separates_search_data_and_requires_a_locked_shortlist(tmp_path):
    import pandas as pd

    from src.research_workflow.workflow import evaluate, propose, run_group

    directory = workflow_world(tmp_path)
    search = pd.read_csv(directory / "data" / "search.csv")
    assert search["date"].max() <= "2020-05-31"
    propose(directory, "A", 1, [config()], "測試事前固定的動能假設")
    rows = run_group(directory, "A", 1)
    assert rows[0]["status"] == "ok"
    with pytest.raises(ValueError, match="lock"):
        evaluate(directory)


def test_workflow_reuses_only_valid_artifacts_and_records_retry(tmp_path):
    from src.research_workflow.registry import read_attempts
    from src.research_workflow.workflow import propose, run_group

    directory = workflow_world(tmp_path)
    propose(directory, "A", 1, [config()], "事前假設")
    first = run_group(directory, "A", 1)[0]
    assert len(read_attempts(directory / "ledger.jsonl")) == 1
    assert run_group(directory, "A", 1)[0]["checksum"] == first["checksum"]
    (directory / first["artifact"]).write_text("{}")
    retried = run_group(directory, "A", 1)[0]
    assert retried["checksum"] != first["checksum"]
    assert len(read_attempts(directory / "ledger.jsonl")) == 2


def test_workflow_never_counts_error_as_completed_research(tmp_path):
    from src.research_workflow.workflow import propose, report, run_group

    directory = workflow_world(tmp_path)
    propose(directory, "A", 1, [config()], "事前假設")
    run_group(directory, "A", 1)
    result = report(directory)
    assert result["study_complete"] is False
    assert result["qualified"] == []
    assert result["counts"]["A"]["attempts"] == 1
    assert "monkey_43" in result["missing_groups"]


def test_random_plans_use_the_same_budget_without_duplicate_configs(tmp_path):
    from src.research_workflow.workflow import controls, propose

    directory = workflow_world(tmp_path)
    propose(directory, "A", 1, [config()], "事前假設")
    plans = controls(directory)
    assert len(plans) == 2
    assert all(len(plan["configs"]) == 1 for plan in plans)
    keys = [json.dumps(row, sort_keys=True) for plan in plans for row in plan["configs"]]
    assert len(set(keys)) == 2
    assert json.dumps(config(), sort_keys=True) not in keys


def test_explicit_research_candidate_can_be_locked_but_not_promoted_to_qualified(tmp_path):
    from src.research_workflow.registry import digest
    from src.research_workflow.workflow import evaluate, lock, propose, run_group

    directory = workflow_world(tmp_path)
    propose(directory, "A", 1, [config()], "事前假設")
    run_group(directory, "A", 1)
    with pytest.raises(ValueError, match="qualified"):
        lock(directory, [digest(config())])
    locked = lock(directory, [digest(config())], allow_research_only=True)
    assert locked["research_only"] is True
    result = evaluate(directory)
    assert result["historical_research"] is True
    assert result["candidates"][0]["status"] == "ok"
    with pytest.raises(FileExistsError):
        evaluate(directory)


def test_modified_proposal_is_rejected_before_execution(tmp_path):
    from src.research_workflow.workflow import propose, run_group

    directory = workflow_world(tmp_path)
    propose(directory, "A", 1, [config()], "事前假設")
    path = directory / "plans" / "A_1.json"
    changed = json.loads(path.read_text())
    changed["configs"][0]["hold"] = 20
    path.write_text(json.dumps(changed))
    with pytest.raises(ValueError, match="proposal"):
        run_group(directory, "A", 1)


def test_data_audit_distinguishes_complete_inputs_from_missing_execution_data():
    from src.research_workflow.data import audit

    frame = price_world()
    assert audit(frame)["status"] == "ready_for_input_validation"
    missing = audit(frame.drop(columns=["cash_dividend", "can_buy"]))
    assert missing["status"] == "blocked"
    assert set(missing["missing_fields"]) == {"cash_dividend", "can_buy"}


def test_cli_audit_reports_missing_data_and_does_not_create_study(tmp_path, capsys):
    from scripts.quant_workflow import main

    source = tmp_path / "prices.csv"
    price_world().drop(columns="eligible").to_csv(source, index=False)
    assert main(["--study", str(tmp_path / "unused"), "audit", "--prices", str(source)]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "blocked"
    assert not (tmp_path / "unused").exists()


def test_mongo_adapter_only_reads_and_keeps_unknown_execution_fields_missing():
    from src.research_workflow.data import audit, mongo_prices

    class Collection:
        def find(self, query, projection):
            assert query["symbol"]["$in"] == ["2330"]
            assert set(query["date"]) == {"$gte", "$lte"}
            return [{"date": "2020-01-02", "symbol": "2330", "open": 100,
                     "close": 101, "adj_open": 90, "adj_close": 91, "volume": 100000}]

    frame = mongo_prices(["2330"], "2020-01-01", "2020-01-31", db={"stock_price": Collection()})
    assert audit(frame)["status"] == "blocked"
    assert "can_buy" not in frame


def test_listing_age_uses_observed_trading_sessions_not_weekday_approximation():
    from src.research_workflow.engine import backtest

    rules = {**engine_rules(), "min_listing_bars": 250}
    result = backtest(price_world(), config(), rules, "2020-03-01", "2020-06-01")
    assert not result["trades"]


def test_known_suspension_carries_last_price_but_never_executes():
    from src.research_workflow.engine import backtest

    frame = price_world(stocks=1)
    stopped = frame["date"].between("2020-03-04", "2020-03-10")
    frame.loc[stopped, ["open", "close", "adj_open", "adj_close"]] = np.nan
    frame.loc[stopped, ["can_buy", "can_sell"]] = False
    frame.loc[stopped, "volume"] = 0
    result = backtest(frame, config(), engine_rules(), "2020-03-01", "2020-05-01")
    assert result["trades"]
    assert not any("2020-03-04" <= row["date"] <= "2020-03-10" for row in result["trades"])


def test_unfilled_buy_is_retried_before_next_rebalance():
    from src.research_workflow.engine import backtest

    frame = price_world(stocks=1)
    frame.loc[frame["date"] == "2020-03-03", "can_buy"] = False
    result = backtest(frame, config(), engine_rules(), "2020-03-01", "2020-05-01")
    assert result["trades"][0]["date"] == "2020-03-04"
    assert result["trades"][0]["signal_date"] == "2020-03-02"


def test_future_listing_cannot_change_past_equal_weight_benchmark():
    from src.research_workflow.engine import backtest

    frame = price_world(stocks=1)
    before = backtest(frame, config(), engine_rules(), "2020-03-01", "2021-01-01", benchmark=True)
    newcomers = price_world(stocks=20)
    newcomers = newcomers[(newcomers["date"] >= "2020-10-01") & (newcomers["symbol"] != "2300")]
    import pandas as pd

    combined = pd.concat([frame, newcomers], ignore_index=True)
    after = backtest(combined, config(), engine_rules(), "2020-03-01", "2021-01-01", benchmark=True)
    count = sum(stamp < "2020-10-01" for stamp in before["dates"])
    assert before["returns"][:count] == after["returns"][:count]


def test_split_and_cash_dividend_do_not_create_or_destroy_portfolio_value():
    from src.research_workflow.engine import backtest

    frame = price_world(stocks=1)
    rules = {**engine_rules(), "slippage_bps": 0}
    holding = {**config(), "hold": 20, "rebalance": 20}
    ordinary = backtest(frame, holding, rules, "2020-03-01", "2020-04-01")
    event = frame["date"] == "2020-03-05"
    after_event = frame["date"] >= "2020-03-05"
    frame.loc[event, "share_ratio"] = 2.0
    frame.loc[event, "cash_dividend"] = 1.0
    frame["cash_payment_date"] = None
    frame.loc[event, "cash_payment_date"] = "2020-03-05"
    frame.loc[after_event, ["open", "close"]] = (frame.loc[after_event, ["open", "close"]] - 1) / 2
    changed = backtest(frame, holding, rules, "2020-03-01", "2020-04-01")
    index = changed["dates"].index("2020-03-05")
    assert changed["nav"][index] == pytest.approx(ordinary["nav"][index])


def test_newey_west_penalizes_positive_serial_correlation_and_dsr_counts_trials():
    from src.research_workflow.metrics import deflated_sharpe, nw_t

    rng = np.random.default_rng(5)
    values = np.repeat(rng.normal(0.001, 0.01, 100), 10)
    assert abs(nw_t(values, 20)) < abs(nw_t(values, 0))
    returns = rng.normal(0.001, 0.01, 1000)
    assert deflated_sharpe(returns, [0.01, 0.1, 0.2], 3) > deflated_sharpe(returns, [0.01, 0.1, 0.2], 1000)


def test_configuration_library_can_cover_full_preregistered_ai_and_control_budget():
    from pathlib import Path

    from src.research_workflow.search import generate

    rules = json.loads((Path(__file__).parents[1] / "research" / "tw_quant" / "rules.json").read_text())
    required = (2 + len(rules["random_seeds"])) * rules["rounds"] * rules["configs_per_round"]
    assert len(generate(43, required, set())) == required


def test_evidence_only_fills_no_action_defaults_inside_attested_coverage():
    from src.research_workflow.evidence import enrich

    frame = price_world(days=3, stocks=1).drop(columns=["cash_dividend", "share_ratio"])
    evidence = {"coverage": [{"symbol": "2300", "start": "2020-01-02", "end": "2020-01-03",
                              "kind": "corporate_actions", "complete": True, "source": "verified_fixture"}],
                "actions": [{"symbol": "2300", "date": "2020-01-03", "cash_dividend": 2.0,
                             "share_ratio": 1.0, "cash_payment_date": "2020-01-03", "source": "verified_fixture"}]}
    got = enrich(frame, evidence)
    assert got["cash_dividend"].iloc[:2].tolist() == [0.0, 2.0]
    assert got["share_ratio"].iloc[:2].tolist() == [1.0, 1.0]
    assert np.isnan(got["cash_dividend"].iloc[2])
    assert got["evidence_hash"].nunique() == 1


def test_price_adjustment_ratio_cannot_be_used_as_share_entitlement():
    from src.research_workflow.evidence import enrich

    with pytest.raises(ValueError, match="share_ratio"):
        enrich(price_world(days=3), {"actions": [{"symbol": "2300", "date": "2020-01-03",
                                                "ratio": 1.294044, "source": "TWSE_TWTAUU"}]})


def test_membership_evidence_cannot_backfill_before_it_was_available():
    from src.research_workflow.evidence import enrich

    frame = price_world(days=3, stocks=1).drop(columns=["eligible", "listed_on"])
    evidence = {"membership": [{"symbol": "2300", "start": "2020-01-01", "end": "2020-01-31",
                                "eligible": True, "listed_on": "2000-01-01", "industry": "電子",
                                "available_at": "2020-01-03", "source": "dated_snapshot"}]}
    got = enrich(frame, evidence)
    assert got["eligible"].isna().iloc[0]
    assert got["eligible"].iloc[1] == True
    assert got["industry_available_at"].iloc[1] == "2020-01-03"


def test_industry_neutral_scores_strip_group_level_and_preserve_unknowns():
    import pandas as pd

    from src.research_workflow.diagnostics import industry_rank

    scores = pd.DataFrame([[1.0, 2.0, 100.0, 200.0, 9.0]])
    groups = pd.DataFrame([["A", "A", "B", "B", None]])
    got = industry_rank(scores, groups)
    assert got.iloc[0, :4].tolist() == [-0.25, 0.25, -0.25, 0.25]
    assert np.isnan(got.iloc[0, 4])


def test_rank_diagnostics_recognize_planted_reverse_and_insufficient_signals():
    from src.research_workflow.diagnostics import rank_diagnostics

    scores = np.tile(np.arange(30, dtype=float), (12, 1))
    returns = scores * 0.001
    positive = rank_diagnostics(scores, returns, 52)
    negative = rank_diagnostics(scores, -returns, 52)
    assert positive["ic_mean"] == pytest.approx(1)
    assert positive["decile_monotonicity"] == pytest.approx(1)
    assert negative["ic_mean"] == pytest.approx(-1)
    assert negative["decile_monotonicity"] == pytest.approx(-1)
    missing = rank_diagnostics(scores[:, :3], returns[:, :3], 52)
    assert missing["status"] == "insufficient"
    assert missing["ic_mean"] is None


def test_neutralization_requires_point_in_time_industry_evidence():
    from src.research_workflow.engine import backtest

    frame = price_world()
    frame["industry"] = "電子"
    frame["industry_available_at"] = "2026-10-26"
    with pytest.raises(ValueError, match="industry"):
        backtest(frame, config(), {**engine_rules(), "industry_neutral": True}, "2020-03-01", "2020-05-01")


def core_world():
    frame = price_world(days=420, stocks=2)
    frame["symbol"] = frame["symbol"].map({"2300": "0050", "2301": "00635U"})
    return frame


def core_rules():
    return {**engine_rules(), "core": {"enabled": True, "risk_symbol": "0050",
                                       "defensive_symbol": "00635U", "window": 200,
                                       "weight": 0.6, "tax_rate": 0.001}}


def test_core_uses_sma200_next_open_and_actual_sixty_percent_capital():
    from src.research_workflow.core import core_backtest

    got = core_backtest(core_world(), core_rules(), "2021-01-04", "2021-06-01")
    assert got["initial_cash"] == 600000
    assert got["trades"]
    assert got["trades"][0]["symbol"] == "0050"
    assert got["trades"][0]["date"] > got["trades"][0]["signal_date"]
    assert got["cash"][0] == 600000
    assert min(got["cash"]) >= 0


def test_core_switches_to_defensive_etf_and_refuses_missing_history():
    from src.research_workflow.core import core_backtest

    frame = core_world()
    down = (frame["symbol"] == "0050") & (frame["date"] >= "2021-02-01")
    frame.loc[down, ["open", "close", "adj_open", "adj_close"]] *= 0.5
    got = core_backtest(frame, core_rules(), "2021-01-04", "2021-06-01")
    assert any(row["symbol"] == "00635U" and row["action"] == "BUY" for row in got["trades"])
    with pytest.raises(ValueError, match="core"):
        core_backtest(frame[frame["symbol"] == "0050"], core_rules(), "2021-01-04", "2021-06-01")


def test_sixty_forty_combination_uses_sleeve_currency_nav_not_average_returns():
    from src.research_workflow.core import combine_sleeves

    result = combine_sleeves({"dates": ["2020-01-02", "2020-01-03"], "nav": [600000, 606000]},
                            [{"dates": ["2020-01-02", "2020-01-03"], "nav": [400000, 392000]}], 1000000)
    assert result["returns"] == pytest.approx([0.0, -0.002])
    assert result["nav"] == [1000000, 998000]


def test_unpaid_dividend_is_receivable_not_spendable_cash():
    from src.research_workflow.engine import backtest

    frame = price_world(stocks=1)
    frame["cash_payment_date"] = None
    event = frame["date"] == "2020-03-05"
    frame.loc[event, "cash_dividend"] = 2.0
    frame.loc[event, "cash_payment_date"] = "2020-03-20"
    frame.loc[frame["date"] >= "2020-03-05", ["open", "close"]] -= 2
    result = backtest(frame, {**config(), "hold": 60, "rebalance": 20}, engine_rules(), "2020-03-01", "2020-04-01")
    before = result["dates"].index("2020-03-04")
    ex_date = result["dates"].index("2020-03-05")
    assert result["cash"][before] == result["cash"][ex_date]
    assert result["receivables"][ex_date] > 0
    assert result["receivables"][result["dates"].index("2020-03-20")] == 0


def test_dividend_without_actual_payment_date_blocks_strict_execution():
    from src.research_workflow.engine import prepare

    frame = price_world()
    frame.loc[0, "cash_dividend"] = 1.0
    with pytest.raises(ValueError, match="payment"):
        prepare(frame, strict=True)


def test_cli_can_apply_explicit_evidence_without_weakening_audit(tmp_path, capsys):
    from scripts.quant_workflow import main

    frame = price_world(days=3, stocks=1).drop(columns=["cash_dividend", "share_ratio"])
    source = tmp_path / "prices.csv"
    frame.to_csv(source, index=False)
    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps({"coverage": [{"symbol": "2300", "start": "2020-01-02", "end": "2020-01-06",
                                                  "kind": "corporate_actions", "complete": True, "source": "fixture"}]}))
    assert main(["audit", "--prices", str(source), "--evidence", str(evidence)]) == 0
    assert json.loads(capsys.readouterr().out)["evidence_hash"]


def test_mongo_adapter_accepts_explicit_taiwan_etf_codes_without_expanding_stock_query():
    from src.research_workflow.data import mongo_prices

    class Collection:
        def find(self, query, projection):
            assert query["symbol"]["$in"] == ["0050", "00635U"]
            return []

    assert mongo_prices(["0050", "00635U"], "2020-01-01", "2020-01-31", db={"stock_price": Collection()}).empty


def test_workflow_wires_rank_diagnostics_into_successful_results(tmp_path):
    from src.research_workflow.workflow import propose, run_group, valid_result

    directory = workflow_world(tmp_path)
    propose(directory, "A", 1, [config()], "事前假設")
    row = run_group(directory, "A", 1)[0]
    result = valid_result(directory, row)
    assert "signal_diagnostics" in result
    assert result["signal_diagnostics"]["horizons"]["20"]["status"] == "insufficient"


def test_workflow_funds_core_and_satellites_before_evaluating_board_lots(tmp_path):
    import pandas as pd

    from src.research_workflow.registry import digest
    from src.research_workflow.workflow import evaluate, initialize, lock, propose, run_group

    equity = price_world(days=420, stocks=3)
    source = tmp_path / "combined.csv"
    pd.concat([equity, core_world()], ignore_index=True).to_csv(source, index=False)
    rules = {**core_rules(), "historical_research": True, "cutoff": "2021-06-01",
             "search": ["2020-03-01", "2020-05-31"], "validation": ["2020-06-01", "2020-12-31"],
             "evaluation": ["2021-01-04", "2021-06-01"], "earliest_evaluation": "2021-06-02",
             "rounds": 1, "configs_per_round": 1, "random_seeds": [43]}
    directory = tmp_path / "funded"
    initialize(directory, rules, source)
    propose(directory, "A", 1, [config()], "事前假設")
    run_group(directory, "A", 1)
    lock(directory, [digest(config())], allow_research_only=True)
    result = evaluate(directory)
    funded = result["portfolios"]["AI"]
    assert funded["core"]["initial_cash"] == 600000
    assert funded["satellites"][0]["capital"] == 400000
    assert funded["construction"] == "funded_60_core_40_equal_initial_satellite_sleeves"


def test_rank_diagnostics_handle_tied_quantiles_without_nonfinite_json():
    from src.research_workflow.diagnostics import rank_diagnostics

    scores = np.tile(np.r_[np.zeros(20), np.arange(1, 11)], (3, 1))
    result = rank_diagnostics(scores, scores * 0.01, 52)
    assert result["status"] == "insufficient"
    json.dumps(result, allow_nan=False)


def test_signal_diagnostics_uses_exact_backtest_eligibility():
    from src.research_workflow.diagnostics import signal_diagnostics
    from src.research_workflow.engine import prepare, signal_universe, strategy_scores

    frame = price_world(stocks=30)
    rules = {**engine_rules(), "min_value_20": 1e20}
    panel = prepare(frame)
    universe = signal_universe(panel, rules)
    assert not universe.any()
    got = signal_diagnostics(panel, strategy_scores(panel, config(), rules), config(), "2020-03-01", "2020-12-31", universe)
    assert all(row["status"] == "insufficient" for row in got["horizons"].values())


def test_core_refuses_partial_defensive_etf_history_even_before_switching():
    from src.research_workflow.core import core_backtest

    frame = core_world()
    frame = frame[(frame["symbol"] != "00635U") | (frame["date"] >= "2021-03-01")]
    with pytest.raises(ValueError, match="core"):
        core_backtest(frame, core_rules(), "2021-01-04", "2021-06-01")


def test_source_inventory_never_confuses_record_presence_with_complete_history():
    from src.research_workflow.data import source_inventory

    class Collection:
        def count_documents(self, query):
            return 3

    db = {name: Collection() for name in ("stock_price", "corporate_actions", "dividend_detail", "dividend_results", "taiwan_stock_info", "delisting")}
    result = source_inventory(["2330"], "2020-01-01", "2020-12-31", db=db)
    assert result["certified_complete"] is False
    assert result["status"] == "requires_source_attestation"
    assert result["corporate_actions_semantics"] == "price_adjustment_ratio_not_share_entitlement"