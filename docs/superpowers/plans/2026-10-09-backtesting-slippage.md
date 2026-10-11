# Backtesting Slippage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在兩套唯讀回測引擎加入可重現、預設關閉的單邊滑價壓力條件。

**Architecture:** 建立一個不依賴資料庫的成交價純函式；Portfolio 與 v21 僅在下單時計算成交價，估值與訊號繼續使用市場價。CLI 與 dashboard 只暴露明確的研究參數。

**Tech Stack:** Python 3.12, pytest, Streamlit, existing `tw_costs`.

**Spec:** `docs/designs/2026-10-09-backtesting-slippage-sdd.md`

## Global Constraints

- 正式機 `.166` 是權威測試環境。
- 預設 `slippage_bps=0.0`，不得改變既有回測結果。
- 不連正式 MongoDB 執行測試，不改 live 選股、交易或排程。
- 每項工作遵循 red -> minimal green -> focused regression；不自行部署或重啟服務。

---

### Task 1: 成交價純函式

**Files:** Create `src/backtesting/slippage.py`; Create `tests/test_backtesting_slippage.py`.

**Interfaces:** Produces `execution_price(market_price: float, side: str, slippage_bps: float = 0.0) -> float`.

**Status:** Complete on 2026-10-09. Red: missing `slippage` module; green: 4 pure-function tests passed on `.166`.

- [ ] **Step 1: Write failing tests**

```python
import pytest
from src.backtesting.slippage import execution_price

def test_execution_price_moves_against_the_trade_direction():
    assert execution_price(100, "buy", 10) == pytest.approx(100.1)
    assert execution_price(100, "sell", 10) == pytest.approx(99.9)

@pytest.mark.parametrize("market_price, side, bps", [(0, "buy", 0), (100, "hold", 0), (100, "buy", -1)])
def test_execution_price_rejects_invalid_inputs(market_price, side, bps):
    with pytest.raises(ValueError):
        execution_price(market_price, side, bps)
```

- [ ] **Step 2: Run red test**

Run: `/home/mdsadmin/Stock/.venv/bin/python3 -m pytest tests/test_backtesting_slippage.py -v`

Expected: import failure because `slippage.py` does not exist.

- [ ] **Step 3: Implement minimum function**

```python
def execution_price(market_price: float, side: str, slippage_bps: float = 0.0) -> float:
    if market_price <= 0 or slippage_bps < 0 or side not in {"buy", "sell"}:
        raise ValueError("invalid execution price input")
    multiplier = 1 + slippage_bps / 10_000 if side == "buy" else 1 - slippage_bps / 10_000
    return market_price * multiplier
```

- [ ] **Step 4: Run green test**

Run: `/home/mdsadmin/Stock/.venv/bin/python3 -m pytest tests/test_backtesting_slippage.py -v`

Expected: all tests pass.

### Task 2: 共用 Portfolio 與 Backtest 接線

**Files:** Modify `src/backtesting/portfolio.py`; Modify `src/backtesting/backtest.py`; Modify `tests/test_backtesting_costs.py`.

**Interfaces:** Consumes `execution_price`; adds `slippage_bps: float = 0.0` to `Portfolio` and `Backtest` constructors.

**Status:** Complete on 2026-10-09. Red: `Portfolio` rejected `slippage_bps`; green: common Portfolio and Backtest wiring passed focused regression.

- [ ] **Step 1: Write failing test**

```python
def test_portfolio_applies_slippage_before_taiwan_costs():
    portfolio = Portfolio(initial_cash=101_500, slippage_bps=10)
    assert portfolio.buy(datetime(2026, 10, 9), "2330", 1000, 100)
    assert portfolio.trades[0].price == pytest.approx(100.1)
    assert portfolio.get_position("2330").avg_price == pytest.approx(100.2426425)
```

- [ ] **Step 2: Run red test**

Run: `/home/mdsadmin/Stock/.venv/bin/python3 -m pytest tests/test_backtesting_costs.py::test_portfolio_applies_slippage_before_taiwan_costs -v`

Expected: `Portfolio.__init__` rejects `slippage_bps`.

- [ ] **Step 3: Implement minimum wiring**

Import `execution_price`; store `slippage_bps`; compute execution price at the start of `buy` and `sell`; pass the new argument from `Backtest` to `Portfolio`. Keep `total_market_value` unchanged.

- [ ] **Step 4: Run green tests**

Run: `/home/mdsadmin/Stock/.venv/bin/python3 -m pytest tests/test_backtesting_costs.py tests/test_backtesting_slippage.py -v`

Expected: all tests pass.

### Task 3: v21、CLI 與 dashboard 壓力參數

**Files:** Modify `scripts/backtest_integrated_v21.py`; Modify `dashboard/pages/backtest_viz.py`; Modify `tests/test_backtest_v21_costs.py`.

**Interfaces:** Adds `slippage_bps: float = 0.0` to `BacktestV21`; CLI option `--slippage-bps`; dashboard numeric input passed to `Backtest`.

**Status:** Complete on 2026-10-09. Red: v21 daily exit ignored 10 bps slippage; green: 35-test focused regression and final production-wide `260 passed, 13 skipped, 11 deselected` non-slow/non-API suite. Fixed 0/10/25/50 bps production scenarios completed on 2026-10-10; see the SDD results table. The separate `--no-cost` comparison remains pending.

- [ ] **Step 1: Write failing v21 test**

```python
def build_backtester(slippage_bps):
    backtester = BacktestV21.__new__(BacktestV21)
    backtester.strategy_v21 = FakeExitStrategy()
    backtester.positions = {"2330": {"shares": 1000, "entry_price": 100.0, "entry_date": "2026-10-01"}}
    backtester.capital = backtester.total_fees = backtester.total_taxes = 0.0
    backtester.fee_rate, backtester.fee_discount, backtester.tax_rate, backtester.min_fee = 0.001425, 0.6, 0.003, 20.0
    backtester.slippage_bps, backtester.trades = slippage_bps, []
    return backtester

def test_daily_exit_applies_slippage_before_fee_and_tax():
    backtester = build_backtester(slippage_bps=10)
    backtester.check_daily_exits("2026-10-09")
    assert backtester.trades[0]["price"] == pytest.approx(99.9)
    assert backtester.capital == pytest.approx(99_514.8855)
```

- [ ] **Step 2: Run red test**

Run: `/home/mdsadmin/Stock/.venv/bin/python3 -m pytest tests/test_backtest_v21_costs.py::test_daily_exit_applies_slippage_before_fee_and_tax -v`

Expected: constructor or result assertion fails because v21 ignores slippage.

- [ ] **Step 3: Implement minimum wiring**

Apply sell execution price in `_execute_sell`, buy execution price in `_execute_buy` and quantity affordability, add `--slippage-bps`, include it in `cost_kw` and saved `backtest_config`. Add the dashboard `單邊滑價 bps` input and pass it into `Backtest`.

- [ ] **Step 4: Run focused and full regression**

Run: `/home/mdsadmin/Stock/.venv/bin/python3 -m pytest tests/test_backtesting_costs.py tests/test_backtesting_slippage.py tests/test_backtest_v21_costs.py tests/test_analysis_new.py -q`

Then: `/home/mdsadmin/Stock/.venv/bin/python3 -m pytest tests/ -m "not slow" -k "not api" -q`

Expected: all pass; no deployment is run.