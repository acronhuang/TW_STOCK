# Research Signal Ledger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立跨所有研究與風控方法的不可覆寫訊號快照帳本，在 5/10/20 交易日成熟後計算成本後超額績效，並只允許降權或停用。

**Architecture:** 來源 adapter 把既有集合與 JSON/CSV 輸出轉成嚴格的 `ResearchSignalSnapshot`；append-only repository 寫入 snapshot 與 benchmark membership。獨立 evaluator 以還原價與 `tw_costs` 寫入 versioned outcomes；policy evaluator 只讀最新 outcome revision 並產出單向的狀態轉變。V1 為 observe-only，不改變 live 選股結果。

**Tech Stack:** Python 3.12, Pydantic 2, PyMongo, pytest, existing `src.backtesting.tw_costs` and `write_db` fixture.

**Spec:** `docs/designs/2026-10-10-research-signal-ledger-sdd.md`

## Global Constraints

- `.166` 是唯一權威測試環境；本機只作開發備份。
- 不導入 Dify，不修改 live 下單或既有選股規則。
- Snapshot collection 一律 append-only：禁止 update、replace、delete。
- outcome 的價格修訂只能新增 revision，禁止覆寫舊 outcome。
- V1 policy 預設 observe-only；無人工核准不得調高權重或重新啟用方法。
- 單元測試使用 fake repository；Mongo integration test 只能透過 `write_db` fixture，絕不連 production DB。
- 不自動 commit；提交由使用者既有 Git 流程處理。

---

### Task 1: 嚴格模型與集合名稱

**Files:**
- Create: `src/research_signal_ledger/__init__.py`
- Create: `src/research_signal_ledger/models.py`
- Modify: `src/domain/collections.py`
- Create: `tests/test_research_signal_ledger_models.py`

**Interfaces:**
- Produces `ResearchSignalSnapshot`, `ResearchBenchmarkSnapshot`, `ResearchSignalOutcome`, `CaptureRun`, `MethodStatus`, `SignalDirection`.
- Adds `COLL_RESEARCH_SIGNAL_SNAPSHOTS`, `COLL_RESEARCH_BENCHMARK_SNAPSHOTS`, `COLL_RESEARCH_SIGNAL_OUTCOMES`, `COLL_RESEARCH_SIGNAL_CAPTURE_RUNS`, `COLL_RESEARCH_METHOD_STATUS`, `COLL_RESEARCH_METHOD_STATUS_HISTORY`.

- [ ] **Step 1: Write failing model tests**

```python
from datetime import date, datetime, timezone
import pytest
from pydantic import ValidationError
from src.research_signal_ledger.models import ResearchSignalSnapshot, SignalDirection


def snapshot(**overrides):
    data = {
        "snapshot_key": "a" * 64,
        "source": "daily_picks",
        "source_event_id": "sha256:abc:2026-10-10",
        "symbol": "2330",
        "analysis_date": date(2026, 10, 10),
        "available_at": datetime(2026, 10, 10, 20, tzinfo=timezone.utc),
        "captured_at": datetime(2026, 10, 10, 21, tzinfo=timezone.utc),
        "signal_kind": "factor_rank",
        "direction": SignalDirection.LONG,
        "evaluation_enabled": True,
        "price_at_signal": 100.0,
        "source_payload": {"rank": 1},
        "benchmark_profile": "market_equal_weight_liquid_tw_v1",
        "rule_version": "daily_picks_v1",
    }
    return ResearchSignalSnapshot(**(data | overrides))


def test_snapshot_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        snapshot(unexpected="no")


def test_snapshot_rejects_non_taiwan_symbol():
    with pytest.raises(ValidationError):
        snapshot(symbol="AAPL")
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `/home/mdsadmin/Stock/.venv/bin/python3 -m pytest tests/test_research_signal_ledger_models.py -q`

Expected: import failure because the ledger module does not exist.

- [ ] **Step 3: Implement only the strict models and constants**

Use `StrictModel` semantics (`extra="forbid"`), exact 4-digit `Symbol`, timezone-aware timestamps validated by `field_validator`, and the collection constants listed above. Do not add Mongo access in this task.

- [ ] **Step 4: Run the focused test and then collection tests**

Run: `/home/mdsadmin/Stock/.venv/bin/python3 -m pytest tests/test_research_signal_ledger_models.py tests/test_collections.py -q`

Expected: pass.

### Task 2: Append-only repository and index contract

**Files:**
- Create: `src/research_signal_ledger/repository.py`
- Create: `tests/test_research_signal_ledger_repository.py`

**Interfaces:**
- `ResearchSignalLedgerRepository.insert_snapshots(snapshots) -> CaptureWriteResult`
- `ResearchSignalLedgerRepository.insert_benchmark(snapshot) -> bool`
- `ResearchSignalLedgerRepository.append_outcome(outcome) -> bool`
- `ResearchSignalLedgerRepository.latest_outcome(snapshot_key, horizon) -> ResearchSignalOutcome | None`
- `ResearchSignalLedgerRepository.record_capture_run(run) -> None`

- [ ] **Step 1: Write failing append-only tests with a fake collection**

```python
def test_duplicate_snapshot_is_idempotent_without_update(repository, snapshot):
    first = repository.insert_snapshots([snapshot])
    second = repository.insert_snapshots([snapshot])
    assert first.inserted == 1
    assert second.duplicates == 1
    assert repository.snapshots.update_calls == []


def test_outcome_revision_cannot_replace_prior_revision(repository, outcome):
    assert repository.append_outcome(outcome) is True
    assert repository.append_outcome(outcome) is False
    assert repository.outcomes.update_calls == []
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `/home/mdsadmin/Stock/.venv/bin/python3 -m pytest tests/test_research_signal_ledger_repository.py -q`

Expected: import failure.

- [ ] **Step 3: Implement repository behavior**

Create unique indexes from the SDD. Catch only `DuplicateKeyError` for idempotent duplicate snapshots/outcomes. Use `insert_one`/`insert_many(ordered=False)` for append-only collections. Repository must expose no update/delete methods for snapshots or outcomes.

- [ ] **Step 4: Add a `write_db` integration test for indexes**

Test the duplicate snapshot key and duplicate `(snapshot_key, horizon, revision)` outcome key are rejected by MongoDB. Use a unique test database supplied by `write_db`; do not instantiate a localhost production client.

- [ ] **Step 5: Run focused repository tests**

Run: `/home/mdsadmin/Stock/.venv/bin/python3 -m pytest tests/test_research_signal_ledger_repository.py -q`

Expected: pass.

### Task 3: Benchmark membership and maturity evaluator

**Files:**
- Create: `src/research_signal_ledger/benchmark.py`
- Create: `src/research_signal_ledger/evaluator.py`
- Create: `tests/test_research_signal_ledger_evaluator.py`

**Interfaces:**
- `build_market_benchmark(as_of, rows) -> ResearchBenchmarkSnapshot`
- `evaluate_snapshot(snapshot, benchmark, price_repository, horizons=(5, 10, 20), discount=1.0) -> list[ResearchSignalOutcome]`
- `PriceRepository.trading_prices(symbol, start_date) -> list[TradingPrice]`

- [ ] **Step 1: Write failing evaluator tests**

```python
import pytest
from src.research_signal_ledger.evaluator import evaluate_snapshot


def test_long_outcome_uses_next_trade_day_adjusted_price_and_roundtrip_cost(snapshot, benchmark, prices):
    outcomes = evaluate_snapshot(snapshot, benchmark, prices, horizons=(5,), discount=1.0)
    outcome = outcomes[0]
    assert outcome.entry_adj_close == 101.0
    assert outcome.exit_adj_close == 111.0
    assert outcome.gross_return_pct == pytest.approx((111 / 101 - 1) * 100)
    assert outcome.cost_pct == pytest.approx(0.585)
    assert outcome.net_return_pct == pytest.approx(outcome.gross_return_pct - 0.585)


def test_insufficient_trading_days_produces_no_outcome(snapshot, benchmark, short_prices):
    assert evaluate_snapshot(snapshot, benchmark, short_prices, horizons=(20,)) == []
```

- [ ] **Step 2: Run focused tests and verify they fail**

Run: `/home/mdsadmin/Stock/.venv/bin/python3 -m pytest tests/test_research_signal_ledger_evaluator.py -q`

Expected: import failure.

- [ ] **Step 3: Implement pure benchmark and evaluator functions**

Use `adj_close`, not `close`. Entry is the first available trading price strictly after `available_at`'s analysis date. Use `roundtrip_pct(discount)` and calculate LONG/SHORT/RISK_REDUCE direction correctly. Return no outcome for unripe windows or missing benchmark members; never substitute zero return.

- [ ] **Step 4: Add revision selection tests**

Assert that policy input receives only the largest revision per `(snapshot_key, horizon)` and retains the prior revision in history.

- [ ] **Step 5: Run focused tests**

Run: `/home/mdsadmin/Stock/.venv/bin/python3 -m pytest tests/test_research_signal_ledger_evaluator.py -q`

Expected: pass.

### Task 4: Source adapter registry and capture normalization

**Files:**
- Create: `src/research_signal_ledger/sources/__init__.py`
- Create: `src/research_signal_ledger/sources/base.py`
- Create: `src/research_signal_ledger/sources/daily_picks.py`
- Create: `src/research_signal_ledger/sources/team_analysis.py`
- Create: `src/research_signal_ledger/sources/core_watchlist.py`
- Create: `src/research_signal_ledger/sources/technical.py`
- Create: `src/research_signal_ledger/sources/chip.py`
- Create: `src/research_signal_ledger/sources/risk.py`
- Create: `src/research_signal_ledger/sources/on_demand.py`
- Create: `tests/test_research_signal_ledger_sources.py`

**Interfaces:**
- `SignalSource.collect(as_of: date) -> SourceCollectionResult`
- `SourceCollectionResult(source, snapshots, status, message)` where status is `captured`, `no_output`, `unsupported`, or `failed`.
- `build_default_sources(read_repository) -> list[SignalSource]`

- [ ] **Step 1: Write failing source normalization tests**

```python
def test_daily_picks_emits_one_snapshot_per_symbol_and_strategy(fake_files):
    source = DailyPicksSource(fake_files)
    result = source.collect(date(2026, 10, 10))
    assert result.status == "captured"
    assert {(s.symbol, s.signal_kind) for s in result.snapshots} == {
        ("2330", "factor_rank"), ("2330", "hsieh_value")
    }


def test_missing_on_demand_output_is_not_a_capture_failure(fake_repository):
    result = OnDemandSource(fake_repository).collect(date(2026, 10, 10))
    assert result.status == "no_output"
    assert result.snapshots == []
```

- [ ] **Step 2: Run focused tests and verify they fail**

Run: `/home/mdsadmin/Stock/.venv/bin/python3 -m pytest tests/test_research_signal_ledger_sources.py -q`

Expected: import failure.

- [ ] **Step 3: Implement adapters with explicit source coverage**

Map daily picks to factor rank, SenVision, Hsieh value, Hsieh growth, Agan moat, quality growth. Map team analysis to final verdict/news value; core watchlist to 2560, MA/institutional, volume-price and rebound; technical to SenVision, OBV, VCP and dual signal; chip to main-force/retail and holder concentration; risk to PKU, risk deliberation and post-trigger. Mark an unavailable Hsieh dividend/deep-analysis/watchlist, pairs or live-advisor run as `no_output` rather than inventing a signal.

- [ ] **Step 4: Add immutability-key tests**

Test that a changed `rule_version` creates a distinct snapshot key; a repeated source event produces the same key; `source_event_id="latest"` is rejected.

- [ ] **Step 5: Run source tests**

Run: `/home/mdsadmin/Stock/.venv/bin/python3 -m pytest tests/test_research_signal_ledger_sources.py -q`

Expected: pass.

### Task 5: Capture and evaluation CLIs

**Files:**
- Create: `scripts/capture_research_signals.py`
- Create: `scripts/evaluate_research_signals.py`
- Create: `tests/test_capture_research_signals_cli.py`
- Create: `tests/test_evaluate_research_signals_cli.py`

**Interfaces:**
- `capture_research_signals.py --as-of YYYY-MM-DD`
- `evaluate_research_signals.py --horizons 5,10,20 --as-of YYYY-MM-DD`

- [ ] **Step 1: Write failing CLI tests**

```python
def test_capture_cli_records_failed_source_without_blocking_other_sources(monkeypatch, capsys):
    monkeypatch.setattr(module, "build_default_sources", lambda _: [FailingSource(), GoodSource()])
    assert module.main(["--as-of", "2026-10-10"]) == 1
    assert "good_source captured=1" in capsys.readouterr().out


def test_evaluation_cli_skips_unripe_snapshot(monkeypatch):
    monkeypatch.setattr(module, "load_eligible_snapshots", lambda *_: [UNRIPE_SNAPSHOT])
    assert module.main(["--horizons", "5,10,20", "--as-of", "2026-10-10"]) == 0
    assert FAKE_REPOSITORY.outcomes == []
```

- [ ] **Step 2: Run focused tests and verify they fail**

Run: `/home/mdsadmin/Stock/.venv/bin/python3 -m pytest tests/test_capture_research_signals_cli.py tests/test_evaluate_research_signals_cli.py -q`

Expected: import failure.

- [ ] **Step 3: Implement orchestration**

Capture all adapters, append capture run, write a deduplicated `schedule_alerts` only for failed adapters, and return nonzero after recording all source results. Evaluation appends only mature outcomes and reports unripe/missing-price counts separately.

- [ ] **Step 4: Run focused CLI tests**

Run: `/home/mdsadmin/Stock/.venv/bin/python3 -m pytest tests/test_capture_research_signals_cli.py tests/test_evaluate_research_signals_cli.py -q`

Expected: pass.

### Task 6: One-way policy evaluator and observe-only consumer contract

**Files:**
- Create: `src/research_signal_ledger/policy.py`
- Create: `scripts/evaluate_research_method_policy.py`
- Create: `tests/test_research_signal_ledger_policy.py`
- Modify: `src/strategy/integrated_strategy_v21.py`
- Modify: `scripts/daily_recommendations.py`

**Interfaces:**
- `evaluate_method_status(outcomes, prior_status, policy) -> MethodStatusDecision`
- `MethodStatusDecision(state, effective_weight, failure_streak, reason)`
- `load_method_status(source, signal_kind) -> MethodStatus | None`

- [ ] **Step 1: Write failing policy tests**

```python
def test_policy_stays_observe_until_sample_and_day_minimums_are_met():
    decision = evaluate_method_status(outcomes=make_outcomes(n=59, days=20), prior_status=None, policy=POLICY)
    assert decision.state == "observe"
    assert decision.effective_weight == 1.0


def test_two_consecutive_failures_only_degrade_weight():
    decision = evaluate_method_status(outcomes=failing_outcomes(n=60, days=20), prior_status=ACTIVE_WITH_ONE_FAILURE, policy=POLICY)
    assert decision.state == "degraded"
    assert decision.effective_weight == 0.75


def test_automatic_policy_never_reenables_or_increases_weight():
    decision = evaluate_method_status(outcomes=winning_outcomes(n=80, days=30), prior_status=DISABLED, policy=POLICY)
    assert decision.state == "disabled"
    assert decision.effective_weight == 0.0
```

- [ ] **Step 2: Run focused tests and verify they fail**

Run: `/home/mdsadmin/Stock/.venv/bin/python3 -m pytest tests/test_research_signal_ledger_policy.py -q`

Expected: import failure.

- [ ] **Step 3: Implement policy and CLI**

Use the SDD's 60-signal, 20-analysis-day, 20-day horizon and two-consecutive-failure thresholds. Append status history and alert only on transition. Reject a requested automatic weight increase or disabled-to-active transition.

- [ ] **Step 4: Add observe-only integration points**

Add a non-enforcing status lookup to v21 and daily recommendations that logs/shows a method state but leaves ranking and weight unchanged. No enforcement flag is enabled in this task.

- [ ] **Step 5: Run focused policy and affected strategy tests**

Run: `/home/mdsadmin/Stock/.venv/bin/python3 -m pytest tests/test_research_signal_ledger_policy.py tests/test_backtest_v21_costs.py tests/test_analysis_new.py -q`

Expected: pass.

### Task 7: Scheduling, dashboard read model, documentation and full regression

**Files:**
- Modify: `scripts/evening_pipeline.sh`
- Modify: `deploy/crontab.txt`
- Create: `dashboard/pages/research_signal_ledger.py`
- Create: `tests/test_research_signal_ledger_dashboard.py`
- Modify: `docs/designs/2026-10-10-research-signal-ledger-sdd.md`
- Modify: `docs/reports/2026-10-10-selection-method-backtest-inventory.md`

- [ ] **Step 1: Write failing dashboard/read-model tests**

```python
def test_ledger_page_uses_latest_outcome_revision_and_never_mutates_status(fake_repository):
    rows = ledger_read_model(fake_repository, horizon=20)
    assert rows[0]["net_return_pct"] == 3.2
    assert fake_repository.write_calls == []
```

- [ ] **Step 2: Run focused test and verify it fails**

Run: `/home/mdsadmin/Stock/.venv/bin/python3 -m pytest tests/test_research_signal_ledger_dashboard.py -q`

Expected: import failure.

- [ ] **Step 3: Wire schedules after implementation tests pass**

Add capture as the final producer step in `evening_pipeline.sh`. Add evaluation after daily price synchronization and policy after evaluation in `deploy/crontab.txt`. Use production venv paths and separate named logs. Do not enable any live weighting enforcement.

- [ ] **Step 4: Implement the read-only dashboard page**

Show source, signal kind, rule version, capture freshness, sample size, 5/10/20 gross/net/excess, status and reason. Do not add controls that modify status or thresholds.

- [ ] **Step 5: Update documents and run full regression**

Run: `/home/mdsadmin/Stock/.venv/bin/python3 -m pytest tests/ -m "not slow" -k "not api" -q`

Expected: all existing tests plus ledger tests pass. Then run `git diff --check` only over touched ledger files, scripts, tests and documentation.

## Self-Review

- Spec coverage: Tasks 1-2 implement immutable contracts; Task 3 implements 5/10/20 net/excess evaluation; Task 4 covers every inventory source group; Task 5 captures and evaluates without a blocking source failure; Task 6 enforces one-way downgrade governance; Task 7 schedules and exposes the read-only result.
- Completeness scan: every task contains concrete steps, and each introduced interface is defined in an earlier task.
- Type consistency: every later task consumes the model names, repository methods and outcome fields created in Tasks 1-3.

## Execution Handoff

Plan saved to `docs/superpowers/plans/2026-10-10-research-signal-ledger.md`. Execute it either with a fresh subagent per task and review gates, or inline in this session with task-level validation checkpoints.
