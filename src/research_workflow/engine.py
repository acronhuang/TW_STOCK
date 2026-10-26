from dataclasses import asdict, dataclass, field
from datetime import timedelta

import numpy as np
import pandas as pd

from src.backtesting.portfolio import Portfolio
from src.backtesting.slippage import execution_price
from src.backtesting.tw_costs import FEE

from .search import FACTORS, HOLDS, THRESHOLDS, WINDOWS

CONSTRAINTS = ("can_buy", "can_sell", "eligible", "listed_on", "cash_dividend", "share_ratio")
PRICES = ("open", "close", "adj_open", "adj_close", "volume")


@dataclass
class Panel:
    dates: pd.DatetimeIndex
    symbols: list
    fields: dict
    verified: bool
    factors: dict = field(default_factory=dict)


def prepare(frame, strict=True):
    frame = frame.copy()
    required = {"date", "symbol", *PRICES}
    if not required.issubset(frame.columns) or frame.empty:
        raise ValueError("missing price data")
    frame["date"] = pd.to_datetime(frame["date"])
    frame["symbol"] = frame["symbol"].astype(str)
    if frame.duplicated(["date", "symbol"]).any():
        raise ValueError("duplicate date/symbol")
    verified = set(CONSTRAINTS).issubset(frame.columns)
    if strict and not verified:
        raise ValueError("missing point-in-time tradability or corporate-action data")
    for name in ("can_buy", "can_sell", "eligible"):
        if name in frame and (frame[name].isna().any() or not frame[name].isin([0, 1, False, True]).all()):
            raise ValueError("invalid tradability flags")
        if name not in frame:
            frame[name] = frame["volume"].gt(0)
    if "cash_dividend" not in frame:
        frame["cash_dividend"] = 0.0
    if "share_ratio" not in frame:
        frame["share_ratio"] = 1.0
    if frame[["cash_dividend", "share_ratio"]].isna().any().any():
        raise ValueError("unknown corporate action")
    if (frame["share_ratio"] <= 0).any() or (frame["cash_dividend"] < 0).any():
        raise ValueError("invalid corporate action")
    if "cash_payment_date" not in frame:
        frame["cash_payment_date"] = pd.NaT
    frame["cash_payment_date"] = pd.to_datetime(frame["cash_payment_date"])
    dividends = frame["cash_dividend"].gt(0)
    if frame.loc[dividends, "cash_payment_date"].isna().any():
        raise ValueError("actual dividend payment date required")
    if (frame.loc[dividends, "cash_payment_date"] < frame.loc[dividends, "date"]).any():
        raise ValueError("dividend payment precedes entitlement date")
    for name in PRICES:
        frame[name] = pd.to_numeric(frame[name], errors="raise")
        if (frame[name].dropna() < 0).any():
            raise ValueError("negative price or volume")
    frame = frame.sort_values(["date", "symbol"])
    dates = pd.DatetimeIndex(sorted(frame["date"].unique()))
    symbols = sorted(frame["symbol"].unique())
    fields = {name: frame.pivot(index="date", columns="symbol", values=name).reindex(index=dates, columns=symbols)
              for name in (*PRICES, "can_buy", "can_sell", "eligible", "cash_dividend", "share_ratio", "cash_payment_date")}
    if "listed_on" in frame:
        listing = pd.to_datetime(frame["listed_on"], errors="raise")
        if listing.isna().any():
            raise ValueError("unknown listing dates")
        frame["listed_on"] = listing
        fields["listed_on"] = frame.pivot(index="date", columns="symbol", values="listed_on").reindex(index=dates, columns=symbols)
    fields["value20"] = (fields["close"] * fields["volume"]).rolling(20, min_periods=20).mean()
    fields["observed"] = fields["close"].notna().cumsum()
    for name in ("industry", "industry_available_at"):
        if name in frame:
            fields[name] = frame.pivot(index="date", columns="symbol", values=name).reindex(index=dates, columns=symbols)
    return Panel(dates, symbols, fields, verified)


def validate_config(config):
    if (config.get("factor") not in FACTORS or config.get("window") not in WINDOWS
            or config.get("hold") not in HOLDS or config.get("threshold") not in THRESHOLDS
            or config.get("slots") not in (3, 5, 10) or config.get("rebalance") not in (5, 20)
            or not isinstance(config.get("reverse"), bool)):
        raise ValueError("configuration outside registered grid")


def factor(panel, name, window):
    key = (name, window)
    if key not in panel.factors:
        close = panel.fields["adj_close"]
        if name == "momentum":
            values = close / close.shift(window) - 1
        elif name == "ma_bias":
            values = close / close.rolling(window).mean() - 1
        elif name == "volatility":
            values = close.pct_change(fill_method=None).rolling(window).std()
        else:
            volume = panel.fields["volume"]
            values = volume / volume.rolling(window).mean() - 1
        panel.factors[key] = values.replace([np.inf, -np.inf], np.nan).to_numpy()
    return panel.factors[key]


def apply_actions(portfolio, data, index, columns, stamp, marks, receivables):
    due = [(payment, amount) for payment, amount in receivables if payment <= stamp]
    portfolio.cash += sum(amount for _, amount in due)
    receivables[:] = [(payment, amount) for payment, amount in receivables if payment > stamp]
    for symbol, position in list(portfolio.positions.items()):
        column = columns[symbol]
        dividend, ratio = data["cash_dividend"][index, column], data["share_ratio"][index, column]
        if not np.isfinite(dividend) or not np.isfinite(ratio):
            raise ValueError("held stock corporate-action coverage missing")
        if dividend:
            payment = pd.Timestamp(data["cash_payment_date"][index, column])
            if pd.isna(payment):
                raise ValueError("actual dividend payment date required")
            amount = position.shares * dividend
            if payment <= stamp:
                portfolio.cash += amount
            else:
                receivables.append((payment, amount))
        shares = position.shares * ratio
        if not np.isclose(shares, round(shares)):
            raise ValueError("fractional corporate-action entitlement requires explicit settlement")
        position.shares = round(shares)
        position.avg_price /= ratio
        if symbol in marks:
            marks[symbol] = (marks[symbol] - dividend) / ratio
    return sum(amount for _, amount in receivables)


def backtest(frame, config, rules, start, end, benchmark=False):
    validate_config(config)
    strict = rules.get("strict_tradability", True)
    panel = frame if isinstance(frame, Panel) else prepare(frame, strict)
    if strict and not panel.verified:
        raise ValueError("missing point-in-time tradability")
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    if (start > end or panel.dates.min().date() > start.date() + timedelta(days=7)
            or panel.dates.max().date() < end.date() - timedelta(days=7)):
        raise ValueError("price coverage does not span requested period")
    active = np.flatnonzero((panel.dates >= start) & (panel.dates <= end))
    if len(active) < 2:
        raise ValueError("insufficient price coverage")
    data = {name: values.to_numpy() for name, values in panel.fields.items()}
    scores = strategy_scores(panel, config, rules)
    universe = signal_universe(panel, rules)
    capital = float(rules["initial_cash"])
    slippage = float(rules.get("slippage_bps", 10))
    lot = int(rules.get("lot_size", 1000))
    if not np.isfinite(capital) or capital <= 0 or not 0 <= slippage < 1000 or lot not in (1, 1000):
        raise ValueError("invalid capital, lot size or slippage")
    portfolio = Portfolio(initial_cash=capital, slippage_bps=slippage)
    columns = {symbol: column for column, symbol in enumerate(panel.symbols)}
    slots = len(panel.symbols) if benchmark else min(config["slots"], rules.get("max_positions", 10))
    weight = min(0.1, 1 / slots)
    marks, entered, pending_buy, pending_sell, signals = {}, {}, {}, {}, {}
    returns, navs, cash, dates, exposure = [], [], [], [], []
    receivables, receivable_values = [], []
    trade_records = []
    previous_nav = capital
    for index in active:
        stamp = panel.dates[index]
        stamp_text = stamp.date().isoformat()
        receivable_value = apply_actions(portfolio, data, index, columns, stamp, marks, receivables)
        for symbol in portfolio.positions:
            if index - entered[symbol] >= config["hold"]:
                pending_sell.setdefault(symbol, panel.dates[index - 1].date().isoformat())
        for symbol, signal_date in list(pending_sell.items()):
            column = columns[symbol]
            price = data["open"][index, column]
            if data["can_sell"][index, column] != True or not np.isfinite(price) or price <= 0:
                continue
            if portfolio.sell(stamp.to_pydatetime(), symbol, portfolio.positions[symbol].shares, price):
                trade = asdict(portfolio.trades[-1])
                trade.update(date=stamp_text, signal_date=signal_date)
                trade_records.append(trade)
                entered.pop(symbol)
                pending_sell.pop(symbol)
        opening_equity = portfolio.total_equity(marks) + receivable_value
        for symbol, signal_date in list(pending_buy.items()):
            column = columns[symbol]
            price = data["open"][index, column]
            if portfolio.has_position(symbol):
                pending_buy.pop(symbol)
                continue
            if (len(portfolio.positions) >= slots
                    or data["can_buy"][index, column] != True or data["eligible"][index, column] != True
                    or not np.isfinite(price) or price <= 0):
                continue
            budget = min(portfolio.cash, opening_equity * weight)
            unit = execution_price(price, "buy", slippage) * (1 + FEE)
            shares = int(budget / unit / lot) * lot
            if shares and portfolio.buy(stamp.to_pydatetime(), symbol, shares, price):
                entered[symbol] = index
                signals[symbol] = signal_date
                trade = asdict(portfolio.trades[-1])
                trade.update(date=stamp_text, signal_date=signal_date)
                trade_records.append(trade)
                pending_buy.pop(symbol)
        for symbol in panel.symbols:
            column = columns[symbol]
            close = data["close"][index, column]
            if np.isfinite(close) and close > 0:
                marks[symbol] = close
            elif portfolio.has_position(symbol):
                known_suspension = (data["can_buy"][index, column] == False
                                    and data["can_sell"][index, column] == False and symbol in marks)
                if not known_suspension:
                    raise ValueError("held stock valuation coverage missing; no assumed delisting price")
        nav = portfolio.total_equity(marks) + receivable_value
        returns.append(float(nav / previous_nav - 1))
        navs.append(float(nav))
        cash.append(float(portfolio.cash))
        receivable_values.append(float(receivable_value))
        exposure.append(float(1 - portfolio.cash / nav))
        dates.append(stamp_text)
        previous_nav = nav
        rebalance = config["rebalance"]
        if (index - active[0]) % rebalance == 0:
            pending_buy = {}
            eligible = []
            for column, symbol in enumerate(panel.symbols):
                value = scores[index, column]
                signed = -value if config["reverse"] else value
                if (universe[index, column]
                        and (benchmark or (np.isfinite(signed) and signed > config["threshold"]))):
                    eligible.append((0.0 if benchmark else -signed, symbol))
            if benchmark:
                slots = max(1, len(eligible))
                weight = min(0.1, 1 / slots)
            for _, symbol in sorted(eligible):
                if not portfolio.has_position(symbol):
                    pending_buy[symbol] = stamp_text
    return {"dates": dates, "returns": returns, "nav": navs, "cash": cash, "exposure": exposure,
            "initial_cash": capital, "receivables": receivable_values,
            "trades": trade_records, "execution_verified": panel.verified,
            "open_positions": sorted(portfolio.positions), "liquidation": "mark_to_market_not_forced",
            "benchmark": "equal_weight_same_cost_board_lots" if benchmark else None,
            "limitations": [] if panel.verified else ["缺少歷史可交易、股票池或公司行動資料；僅探索，不可正式達標"]}


def strategy_scores(panel, config, rules):
    scores = factor(panel, config["factor"], config["window"])
    if not rules.get("industry_neutral", False):
        return scores
    from .diagnostics import industry_rank

    if "industry" not in panel.fields or "industry_available_at" not in panel.fields:
        raise ValueError("point-in-time industry evidence required")
    available = panel.fields["industry_available_at"].apply(pd.to_datetime)
    for stamp in available.index:
        known = available.loc[stamp].dropna()
        if any(value.to_pydatetime() > stamp.to_pydatetime().replace(hour=13, minute=30) for value in known):
            raise ValueError("industry classification was not available at signal time")
    industries = panel.fields["industry"].where(available.notna())
    values = pd.DataFrame(scores, index=panel.dates, columns=panel.symbols)
    return industry_rank(values, industries).to_numpy()


def signal_universe(panel, rules):
    values = panel.fields["value20"].to_numpy()
    usable = ((panel.fields["eligible"].to_numpy() == True)
              & (panel.fields["observed"].to_numpy() >= rules.get("min_listing_bars", 250))
              & np.isfinite(values) & (values >= rules.get("min_value_20", 20000000)))
    if "listed_on" in panel.fields:
        listing = panel.fields["listed_on"].to_numpy(dtype="datetime64[ns]")
        usable &= ~np.isnat(listing) & (listing <= panel.dates.to_numpy(dtype="datetime64[ns]")[:, None])
    return usable