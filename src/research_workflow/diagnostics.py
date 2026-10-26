import numpy as np
import pandas as pd
from scipy import stats


def industry_rank(scores, industries):
    if scores.shape != industries.shape or not scores.index.equals(industries.index) or not scores.columns.equals(industries.columns):
        raise ValueError("industry and scores must be aligned")
    result = pd.DataFrame(np.nan, index=scores.index, columns=scores.columns)
    for index in scores.index:
        values, groups = scores.loc[index], industries.loc[index]
        valid = np.isfinite(values) & groups.notna() & groups.ne("")
        ranked = values[valid].groupby(groups[valid]).rank(method="average", pct=True)
        result.loc[index, valid] = ranked - ranked.groupby(groups[valid]).transform("mean")
    return result


def rank_diagnostics(scores, returns, periods_per_year):
    scores, returns = np.asarray(scores, float), np.asarray(returns, float)
    if scores.shape != returns.shape or scores.ndim != 2 or periods_per_year <= 0:
        raise ValueError("aligned score/return matrices required")
    correlations, layers = [], []
    for score, future in zip(scores, returns, strict=True):
        valid = np.isfinite(score) & np.isfinite(future)
        score, future = score[valid], future[valid]
        if len(score) < 10 or len(np.unique(score)) < 10 or np.std(future) == 0:
            continue
        bins = pd.qcut(score, 10, labels=False, duplicates="drop")
        if len(np.unique(bins)) != 10:
            continue
        correlations.append(float(stats.spearmanr(score, future).statistic))
        layers.append([float(future[bins == level].mean()) for level in range(10)])
    if not correlations:
        return {"status": "insufficient", "periods": 0, "ic_mean": None, "icir": None,
                "decile_returns": None, "decile_monotonicity": None}
    mean = float(np.mean(correlations))
    deviation = float(np.std(correlations, ddof=1)) if len(correlations) > 1 else 0.0
    deciles = np.mean(layers, axis=0)
    return {"status": "ok", "periods": len(correlations), "ic_mean": mean,
            "ic_positive_fraction": float(np.mean(np.array(correlations) > 0)),
            "icir": mean / deviation * np.sqrt(periods_per_year) if deviation > 0 else None,
            "decile_returns": deciles.tolist(), "top_minus_bottom": float(deciles[-1] - deciles[0]),
            "decile_monotonicity": float(stats.spearmanr(np.arange(10), deciles).statistic) if np.std(deciles) > 0 else None,
            "return_unit": "arithmetic_gross_forward_period_return_not_executed_portfolio"}


def signal_diagnostics(panel, scores, config, start, end, universe=None):
    dates = panel.dates
    active = np.flatnonzero((dates >= pd.Timestamp(start)) & (dates <= pd.Timestamp(end)))
    selected = active[::config["rebalance"]]
    prices = panel.fields["adj_open"].to_numpy()
    eligible = panel.fields["eligible"].to_numpy() == True if universe is None else universe
    signed = -scores if config["reverse"] else scores
    outputs = {}
    for horizon in (1, 5, 20, 60):
        rows = selected[selected + 1 + horizon <= active[-1]]
        if not len(rows):
            outputs[str(horizon)] = {"status": "insufficient", "periods": 0, "ic_mean": None}
            continue
        entry, exit_price = prices[rows + 1], prices[rows + 1 + horizon]
        with np.errstate(divide="ignore", invalid="ignore"):
            forward = exit_price / entry - 1
        usable = eligible[rows] & np.isfinite(forward) & (entry > 0) & (exit_price > 0)
        forward = np.where(usable, forward, np.nan)
        outputs[str(horizon)] = rank_diagnostics(np.where(eligible[rows], signed[rows], np.nan), forward, 250 / config["rebalance"])
        outputs[str(horizon)]["unavailable_cells"] = int((~usable).sum())
    return {"horizons": outputs, "entry": "signal_close_then_next_open",
            "limitations": ["僅訊號診斷，未模擬每層成交、成本、停牌與資金限制；不作新增篩選門檻。"]}