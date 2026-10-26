import numpy as np
import pandas as pd
from scipy import stats


def nw_t(values, lag=20):
    values = np.asarray(values, dtype=float)
    count = len(values)
    if count < 3 or not np.isfinite(values).all():
        return None
    deviation = values - values.mean()
    variance = float(deviation @ deviation)
    for offset in range(1, min(lag, count - 1) + 1):
        variance += 2 * (1 - offset / (lag + 1)) * float(deviation[offset:] @ deviation[:-offset])
    return float(values.mean() * count / np.sqrt(variance)) if variance > 0 else None


def drawdown(returns):
    nav = np.r_[1.0, np.cumprod(1 + returns)]
    return float(np.max(1 - nav / np.maximum.accumulate(nav)))


def summarize(dates, returns, benchmark, trades, annual_days=250):
    dates = pd.DatetimeIndex(dates)
    returns, benchmark = np.asarray(returns, float), np.asarray(benchmark, float)
    if (len(dates) < 2 or len(dates) != len(returns) or returns.shape != benchmark.shape
            or not np.isfinite(returns).all() or not np.isfinite(benchmark).all()
            or np.any(returns <= -1) or np.any(benchmark <= -1)):
        raise ValueError("daily returns must be aligned, finite and greater than -1")
    excess = returns - benchmark
    if np.any(excess <= -1):
        raise ValueError("excess returns must be greater than -1")
    annual = float(np.prod(1 + returns) ** (annual_days / len(returns)) - 1)
    annual_base = float(np.prod(1 + benchmark) ** (annual_days / len(benchmark)) - 1)
    deviation = float(np.std(excess, ddof=1))
    years = {}
    for year in sorted(set(dates.year)):
        mask = dates.year == year
        selected = dates[mask]
        if selected[0].month == 1 and selected[-1].month == 12 and mask.sum() >= 200:
            years[str(year)] = float(np.prod(1 + returns[mask]) - np.prod(1 + benchmark[mask]))
    daily_sr = float(excess.mean() / deviation) if deviation > 0 else None
    return {"trades": int(trades), "days": len(returns), "annual_return": annual,
            "annual_excess": annual - annual_base, "total_return": float(np.prod(1 + returns) - 1),
            "max_drawdown": drawdown(returns), "excess_drawdown": drawdown(excess),
            "daily_sr": daily_sr, "ir": daily_sr * np.sqrt(annual_days) if daily_sr is not None else None,
            "nw_t": nw_t(excess), "year_excess": years, "complete_years": len(years),
            "positive_years": sum(value > 0 for value in years.values())}


def deflated_sharpe(excess, trial_sharpes, trials):
    excess = np.asarray(excess, float)
    sample = np.asarray([value for value in trial_sharpes if value is not None], float)
    if len(excess) < 3 or len(sample) < 2 or trials < 2 or np.std(excess, ddof=1) == 0:
        return None
    spread = float(np.std(sample, ddof=1))
    if not np.isfinite(spread) or spread <= 0:
        return None
    euler = 0.5772156649015329
    expected = spread * ((1 - euler) * stats.norm.ppf(1 - 1 / trials)
                         + euler * stats.norm.ppf(1 - 1 / (trials * np.e)))
    sharpe = float(excess.mean() / np.std(excess, ddof=1))
    denominator = 1 - stats.skew(excess, bias=False) * sharpe
    denominator += (stats.kurtosis(excess, fisher=False, bias=False) - 1) / 4 * sharpe ** 2
    if not np.isfinite(denominator) or denominator <= 0:
        return None
    return float(stats.norm.cdf((sharpe - expected) * np.sqrt(len(excess) - 1) / np.sqrt(denominator)))


def funnel(train, validation, neighbors, correlation, dsr):
    def gate(mapping, keys, predicate):
        if any(mapping.get(key) is None or not np.isfinite(mapping[key]) for key in keys):
            return "missing"
        return "pass" if predicate() else "fail"

    layers = {
        "L1": gate(train, ["trades"], lambda: train["trades"] >= 100),
        "L2": gate(train, ["annual_excess"], lambda: train["annual_excess"] > 0),
        "L3": gate(train, ["ir", "excess_drawdown"], lambda: train["ir"] > 0.4 and train["excess_drawdown"] < 0.3),
        "L4": gate(train, ["positive_years", "complete_years"], lambda: train["complete_years"] == 9 and train["positive_years"] >= 6),
        "L5": "missing" if not neighbors or any(value is None for value in neighbors)
        else ("pass" if sum(neighbors) / len(neighbors) >= 0.7 else "fail"),
        "L6": gate(validation, ["annual_excess"], lambda: validation["annual_excess"] > 0),
        "L7": "missing" if correlation is None else ("pass" if correlation < 0.7 else "fail"),
        "L8": "missing" if dsr is None or train.get("nw_t") is None
        else ("pass" if dsr > 0.95 and train["nw_t"] >= 3 else "fail"),
    }
    cumulative, passed = {}, True
    for name, status in layers.items():
        passed = passed and status == "pass"
        cumulative[name] = passed
    return {"layers": layers, "cumulative": cumulative,
            "grade": "qualified" if all(cumulative.values()) else "research_only"}