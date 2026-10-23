"""ATR（海龜法則的 N 值）與依波動度決定的停損、部位大小。純函式，不連網、不讀資料庫。

方法出自海龜交易法則（公開）：N＝真實波幅的 n 日 Wilder 平滑；停損＝進場價 − 2N；加碼間距＝½N。
這裡只做部位與停損的算術，不預測漲跌，也不保證報酬。缺值或資料不足一律回 None，不猜。
"""

LOT = 1000  # 台股一張
DEFAULT_PERIOD = 20
STOP_MULT = 2.0
ADD_STEP = 0.5


def _ok(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value == value and value > 0


def true_ranges(highs, lows, closes):
    """第一根沒有前收，只用高低差；其餘取三者最大。"""
    out = []
    for i, (high, low) in enumerate(zip(highs, lows)):
        if i == 0:
            out.append(high - low)
        else:
            out.append(max(high - low, abs(high - closes[i - 1]), abs(low - closes[i - 1])))
    return out


def atr(highs, lows, closes, period=DEFAULT_PERIOD):
    """Wilder 平滑：前 period 個真實波幅（不含第一根）的平均當起點，之後 ((period−1)×前值＋今值)÷period。"""
    n = len(closes)
    if period < 1 or not (len(highs) == len(lows) == n) or n < period + 1:
        return None
    values = (*highs, *lows, *closes)
    if not all(_ok(v) for v in values) or any(h < l for h, l in zip(highs, lows)):
        return None
    tr = true_ranges(highs, lows, closes)
    value = sum(tr[1:period + 1]) / period
    for today in tr[period + 1:]:
        value = ((period - 1) * value + today) / period
    return value


def stop_price(entry, n, mult=STOP_MULT):
    if not (_ok(entry) and _ok(n)):
        return None
    stop = entry - mult * n
    return stop if stop > 0 else None


def add_levels(entry, n, count=3, step=ADD_STEP):
    """獲利後的加碼價：進場價每上移 ½N 一檔。"""
    if not (_ok(entry) and _ok(n)) or count < 1:
        return []
    return [entry + step * n * k for k in range(1, count + 1)]


def position_pct(n_pct, risk_pct=1.0, mult=STOP_MULT):
    """停損時虧損剛好等於資金 risk_pct% 的部位占資金比例(%)：risk_pct ÷ (mult × N占股價%) × 100。"""
    if not (_ok(n_pct) and _ok(risk_pct) and _ok(mult)):
        return None
    return risk_pct / (mult * n_pct) * 100


def shares_for_risk(equity, entry, stop, risk_pct=1.0, lot=LOT):
    """停損時虧損不超過資金 risk_pct% 的股數，向下取整到 lot 的倍數；停損不低於進場價時回 None。"""
    if not (_ok(equity) and _ok(entry) and _ok(stop) and _ok(risk_pct)) or stop >= entry or lot < 1:
        return None
    raw = equity * risk_pct / 100 / (entry - stop)
    return int(raw // lot * lot)


def summary(highs, lows, closes, price, period=DEFAULT_PERIOD, risk_pct=1.0):
    """highs/lows/closes 是還原價序列；price 是現價（未還原）。N 依現價與還原收盤的比例換回現價單位。"""
    n_adjusted = atr(highs, lows, closes, period)
    if n_adjusted is None or not _ok(price):
        return None
    n = n_adjusted * price / closes[-1]
    stop = stop_price(price, n)
    n_pct = n / price * 100
    return {
        "period": period,
        "n": round(n, 2),
        "n_pct": round(n_pct, 2),
        "stop_2n": None if stop is None else round(stop, 2),
        "add_step": round(ADD_STEP * n, 2),
        "risk_pct": risk_pct,
        "position_pct": round(position_pct(n_pct, risk_pct), 1),
    }
