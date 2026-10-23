"""訊號驗證的統計工具：超額報酬矩陣、事件窗口加總、去重、同日基準比較、多重檢定、事前決定的判定規則。

純 numpy/scipy，不連資料庫。判定標準在看任何結果前就固定在這裡，不隨結果調整。
"""

import numpy as np
from scipy import stats

COST = 0.00585          # 台股來回成本約 0.585%（手續費 0.1425%×2 加證交稅 0.3%，未計折讓）
WINDOWS = {"1..5": (1, 5), "1..20": (1, 20), "2..21": (2, 21)}
PRIMARY = "2..21"       # 訊號日收盤後才知道，隔日收盤進場：從 t+2 起算，是可執行的保守窗口
DEDUPE_DAYS = 20        # 同一檔 20 個交易日內的重複訊號只留第一個，避免窗口重疊
RETURN_LIMIT = 0.15     # 單日報酬超過此值視為資料錯誤，當缺值
INDEX_JUMP = 0.12       # 等權指數計算時略過單日漲跌超過此值的個股
MIN_INDEX_STOCKS = 300  # 當天有價的股票不到這個數就不算指數
MIN_DAYS, MIN_EVENTS, FDR = 60, 300, 0.10
SUPPORTED, NOT_SUPPORTED, INSUFFICIENT = "支持", "不支持", "樣本不足"


def build_excess(close, limit=RETURN_LIMIT, jump=INDEX_JUMP, min_stocks=MIN_INDEX_STOCKS):
    """close: (日, 股) 還原收盤價，缺值為 NaN。回 (超額報酬矩陣, 等權市場日報酬)，第 0 列為 NaN。"""
    days, stocks = close.shape
    ret = np.full((days, stocks), np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        ret[1:] = close[1:] / close[:-1] - 1
    ret[~np.isfinite(ret)] = np.nan
    ret[np.abs(ret) > limit] = np.nan
    usable = np.where(np.abs(ret) <= jump, ret, np.nan)
    count = np.sum(~np.isnan(usable), axis=1)
    total = np.nansum(usable, axis=1)
    market = np.full(days, np.nan)
    enough = count >= min_stocks
    market[enough] = total[enough] / count[enough]
    return ret - market[:, None], market


class Windows:
    """事件後 [row+start, row+end] 日超額報酬的加總；窗口超出範圍或含缺值就是 NaN（缺價不當成 0）。"""

    def __init__(self, excess):
        self.days = excess.shape[0]
        width = excess.shape[1]
        self.total = np.vstack([np.zeros((1, width)), np.cumsum(np.nan_to_num(excess), axis=0)])
        self.missing = np.vstack([np.zeros((1, width), dtype=np.int32), np.cumsum(np.isnan(excess), axis=0, dtype=np.int32)])

    def sums(self, rows, cols, start, end):
        lo, hi = rows + start, rows + end
        inside = (lo >= 1) & (hi <= self.days - 1)
        lo_i, hi_i = np.clip(lo, 0, self.days - 1), np.clip(hi, 0, self.days - 1)
        total = self.total[hi_i + 1, cols] - self.total[lo_i, cols]
        gap = self.missing[hi_i + 1, cols] - self.missing[lo_i, cols]
        return np.where(inside & (gap == 0), total, np.nan)


def dedupe(rows, cols, gap=DEDUPE_DAYS):
    """同一檔 gap 個交易日內的後續事件丟掉（以最早保留的那個為準）。"""
    keep = np.zeros(len(rows), dtype=bool)
    last_col, last_row = -1, 0
    for i in np.lexsort((rows, cols)):
        if cols[i] != last_col or rows[i] - last_row > gap:
            keep[i] = True
            last_col, last_row = cols[i], rows[i]
    return rows[keep], cols[keep]


def day_means(rows, values):
    """同一天的事件先平均成一個值：同日的個股共享同一天的市場，不能當成互相獨立。"""
    ok = np.isfinite(values)
    days, inverse = np.unique(rows[ok], return_inverse=True)
    if len(days) == 0:
        return days, np.array([])
    return days, np.bincount(inverse, weights=values[ok]) / np.bincount(inverse)


def t_summary(values):
    values = np.asarray(values, dtype=float)
    n = len(values)
    if n < 2 or np.std(values, ddof=1) == 0:
        return {"days": n, "mean": float(np.mean(values)) if n else float("nan"), "t": float("nan"), "p": float("nan")}
    mean = float(np.mean(values))
    t = mean / (np.std(values, ddof=1) / np.sqrt(n))
    return {"days": n, "mean": mean, "t": float(t), "p": float(2 * stats.t.sf(abs(t), n - 1))}


def _paired(days_a, means_a, days_b, means_b):
    index = np.searchsorted(days_b, days_a)
    inside = index < len(days_b)
    matched = inside & (days_b[np.minimum(index, max(len(days_b) - 1, 0))] == days_a) if len(days_b) else np.zeros(len(days_a), bool)
    return means_a[matched] - means_b[index[matched]]


def versus_baseline(event_rows, event_values, base_days, base_means):
    """每個有事件的日子：事件日均 − 同日基準日均，再對這些日子做 t 檢定。"""
    days, means = day_means(event_rows, event_values)
    return t_summary(_paired(days, means, base_days, base_means))


def group_gap(rows_a, values_a, rows_b, values_b):
    """兩組事件在同一天都有時，A 組日均 − B 組日均，再對這些日子做 t 檢定。"""
    days_a, means_a = day_means(rows_a, values_a)
    days_b, means_b = day_means(rows_b, values_b)
    return t_summary(_paired(days_a, means_a, days_b, means_b))


def benjamini_hochberg(pvalues, q=FDR):
    """回傳與輸入同順序的布林陣列：控制偽發現率 q。NaN 視為不顯著。"""
    p = np.where(np.isnan(np.asarray(pvalues, dtype=float)), 1.0, np.asarray(pvalues, dtype=float))
    order = np.argsort(p)
    passed = p[order] <= q * np.arange(1, len(p) + 1) / len(p)
    significant = np.zeros(len(p), dtype=bool)
    if passed.any():
        significant[order[: np.max(np.nonzero(passed)[0]) + 1]] = True
    return significant


def decide(dev, hold, direction, hold_significant):
    """事前決定的判定：開發期與留存期的方向都與假設一致，且留存期的樣本足夠並通過 FDR 檢定才算支持。

    direction：+1 代表假設為正（進場訊號較同日基準好）、−1 代表假設為負（賣出訊號或被過濾掉的較差）。
    dev/hold：含 days、events、mean 的 dict。
    """
    for part in (dev, hold):
        if part["days"] < MIN_DAYS or part["events"] < MIN_EVENTS or not np.isfinite(part["mean"]):
            return INSUFFICIENT
    if np.sign(dev["mean"]) != direction or np.sign(hold["mean"]) != direction or not hold_significant:
        return NOT_SUPPORTED
    return SUPPORTED
