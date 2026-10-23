"""風險暴露調整的統計工具：逐日橫斷面回歸（Fama-MacBeth）、Newey-West、滾動暴露。

問題：訊號相對同日同前提個股的超額報酬，是不是只因為訊號個股剛好有較高的 Beta、波動度、小型股或動能暴露？
做法：每個有事件的日子，用「該日事件」與「該日沒有近期訊號的控制個股」做一次橫斷面回歸，
y＝訊號日後的窗口報酬，X＝標準化的暴露，D＝事件虛擬變數；取 D 的係數，再對日子取平均並做 Newey-West 檢定。
純 numpy/pandas，不連資料庫。
"""

import numpy as np
import pandas as pd

MIN_CONTROLS = 100   # 該日控制個股少於這個數就不做回歸
WINSOR = 0.01        # 暴露在每個橫斷面先縮尾 1% / 99%
NW_LAG = 20          # 窗口 20 個交易日、彼此重疊，所以日係數有自相關
EXPOSURE_WINDOW, EXPOSURE_MIN_OBS = 60, 40
MOM_LONG, MOM_SKIP = 120, 20  # 中期動能：t−120 到 t−20 的報酬（略過最近一個月）


def winsorize(x, p):
    low, high = np.percentile(x, [100 * p, 100 * (1 - p)])
    return np.clip(x, low, high)


def zscore(x):
    spread = x.std()
    return None if spread == 0 else (x - x.mean()) / spread


def date_gamma(y, X, d, min_controls=MIN_CONTROLS, winsor=WINSOR):
    """單日橫斷面回歸，回事件虛擬變數的係數；事件為 0、控制組太少、暴露無變異或共線時回 None。"""
    y, d = np.asarray(y, dtype=float), np.asarray(d, dtype=float)
    n, events = len(y), int(d.sum())
    if events < 1 or n - events < min_controls:
        return None
    columns = [np.ones(n)]
    for j in range(X.shape[1]):
        column = winsorize(X[:, j], winsor) if winsor else X[:, j]
        z = zscore(column)
        if z is None:
            return None
        columns.append(z)
    design = np.column_stack([*columns, d])
    if np.linalg.matrix_rank(design) < design.shape[1]:
        return None
    return float(np.linalg.lstsq(design, y, rcond=None)[0][-1])


def newey_west_mean_t(rows, values, lag=NW_LAG):
    """對「各日的係數」做平均與 Newey-West t；日期不連續的缺口當成零偏差（缺日不貢獻也不拉高精度）。"""
    rows, values = np.asarray(rows, dtype=int), np.asarray(values, dtype=float)
    n = len(values)
    if n < 2:
        return float("nan"), float("nan")
    mean = float(values.mean())
    deviation = np.zeros(rows.max() - rows.min() + 1)
    deviation[rows - rows.min()] = values - mean
    total = float(np.sum(deviation ** 2))
    for k in range(1, min(lag, len(deviation) - 1) + 1):
        total += 2 * (1 - k / (lag + 1)) * float(np.sum(deviation[:-k] * deviation[k:]))
    variance = total / n ** 2
    return mean, (mean / np.sqrt(variance) if variance > 0 else float("nan"))


def exposures(close, ret, market, value):
    """回傳 (日, 股) 的暴露矩陣：beta（對等權指數 60 日）、vol（60 日日報酬標準差）、size（對數成交值）、
    mom（t−120 到 t−20 的報酬）、short（t−20 到 t 的報酬）。都只用 t 日（含）以前的資料。"""
    r, m = pd.DataFrame(ret), pd.Series(market)
    window = dict(window=EXPOSURE_WINDOW, min_periods=EXPOSURE_MIN_OBS)
    beta = r.rolling(**window).cov(m).div(m.rolling(**window).var(), axis=0)
    c = pd.DataFrame(close)
    with np.errstate(divide="ignore", invalid="ignore"):
        size = np.log(np.asarray(value, dtype=float))
    return {
        "beta": beta.to_numpy(),
        "vol": r.rolling(**window).std().to_numpy(),
        "size": np.where(np.isfinite(size), size, np.nan),
        "mom": (c.shift(MOM_SKIP) / c.shift(MOM_LONG) - 1).to_numpy(),
        "short": (c / c.shift(MOM_SKIP) - 1).to_numpy(),
    }
