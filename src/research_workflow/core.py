from dataclasses import asdict
from datetime import timedelta

import numpy as np
import pandas as pd

from src.backtesting.portfolio import Portfolio
from src.backtesting.slippage import execution_price
from src.backtesting.tw_costs import FEE

from .engine import Panel, apply_actions, prepare


def core_backtest(frame, rules, start, end):
    policy = rules["core"]
    risk, defensive = policy["risk_symbol"], policy["defensive_symbol"]
    weight = policy["weight"]
    if risk == defensive or weight != 0.6 or policy["window"] != 200:
        raise ValueError("core requires distinct ETFs, SMA200 and registered 60/40 allocation")
    panel = frame if isinstance(frame, Panel) else prepare(frame, rules.get("strict_tradability", True))
    if rules.get("strict_tradability", True) and not panel.verified:
        raise ValueError("core tradability evidence missing")
    if risk not in panel.symbols or defensive not in panel.symbols:
        raise ValueError("core ETF history missing")
    active = np.flatnonzero((panel.dates >= pd.Timestamp(start)) & (panel.dates <= pd.Timestamp(end)))
    if len(active) < 2 or panel.dates[active[-1]].date() < pd.Timestamp(end).date() - timedelta(days=7):
        raise ValueError("core date coverage missing")
    if panel.dates[active[0]].date() > pd.Timestamp(start).date() + timedelta(days=7):
        raise ValueError("core start coverage missing")
    for name in ("can_buy", "can_sell", "eligible", "cash_dividend", "share_ratio"):
        if panel.fields[name].iloc[active][[risk, defensive]].isna().any().any():
            raise ValueError("core ETF execution evidence coverage missing")
    average = panel.fields["adj_close"][risk].rolling(200, min_periods=200).mean()
    if not np.isfinite(average.iloc[active[0]]):
        raise ValueError("core SMA200 warmup missing")
    capital = float(rules["initial_cash"]) * weight
    tax = float(policy["tax_rate"])
    if not 0 <= tax <= 0.01:
        raise ValueError("core ETF tax rate required")
    slippage, lot = rules.get("slippage_bps", 10), rules.get("lot_size", 1000)
    if capital <= 0 or lot not in (1, 1000) or not 0 <= slippage < 1000:
        raise ValueError("invalid core execution settings")
    portfolio = Portfolio(initial_cash=capital, slippage_bps=slippage, tax_rate=tax)
    target, signal_date = None, None
    marks, dates, navs, cash, trades = {}, [], [], [], []
    receivables, receivable_values = [], []
    data = {name: values.to_numpy() for name, values in panel.fields.items()}
    columns = {symbol: column for column, symbol in enumerate(panel.symbols)}
    for index in active:
        stamp = panel.dates[index]
        text = stamp.date().isoformat()
        receivable_value = apply_actions(portfolio, data, index, columns, stamp, marks, receivables)
        for symbol, position in list(portfolio.positions.items()):
            price = panel.fields["open"].iloc[index][symbol]
            if target is not None and symbol != target and panel.fields["can_sell"].iloc[index][symbol] == True and np.isfinite(price) and price > 0:
                portfolio.sell(stamp.to_pydatetime(), symbol, position.shares, price)
                trade = asdict(portfolio.trades[-1])
                trade.update(date=text, signal_date=signal_date)
                trades.append(trade)
        if target is not None and not portfolio.positions:
            price = panel.fields["open"].iloc[index][target]
            if panel.fields["can_buy"].iloc[index][target] == True and panel.fields["eligible"].iloc[index][target] == True and np.isfinite(price) and price > 0:
                unit = execution_price(price, "buy", slippage) * (1 + FEE)
                shares = int(portfolio.cash / unit / lot) * lot
                if shares and portfolio.buy(stamp.to_pydatetime(), target, shares, price):
                    trade = asdict(portfolio.trades[-1])
                    trade.update(date=text, signal_date=signal_date)
                    trades.append(trade)
        for symbol in portfolio.positions:
            price = panel.fields["close"].iloc[index][symbol]
            if np.isfinite(price) and price > 0:
                marks[symbol] = price
            elif not (symbol in marks and panel.fields["can_buy"].iloc[index][symbol] == False and panel.fields["can_sell"].iloc[index][symbol] == False):
                raise ValueError("core valuation coverage missing")
        navs.append(float(portfolio.total_equity(marks) + receivable_value))
        dates.append(text)
        cash.append(float(portfolio.cash))
        receivable_values.append(float(receivable_value))
        signal = panel.fields["adj_close"].iloc[index][risk]
        if not np.isfinite(signal) or not np.isfinite(average.iloc[index]):
            raise ValueError("core signal coverage missing")
        target = risk if signal >= average.iloc[index] else defensive
        signal_date = text
    returns = np.array(navs) / np.r_[capital, navs[:-1]] - 1
    return {"initial_cash": capital, "dates": dates, "nav": navs, "cash": cash,
            "returns": returns.tolist(), "receivables": receivable_values, "trades": trades, "execution_verified": panel.verified,
            "policy": policy, "limitations": ["防禦 ETF 的商品與匯率暴露不等於黃金現貨；費稅依登記設定。"]}


def combine_sleeves(core, satellites, initial_cash):
    if not satellites or initial_cash <= 0:
        raise ValueError("funded satellite sleeves required")
    dates = core["dates"]
    if any(sleeve["dates"] != dates for sleeve in satellites):
        raise ValueError("portfolio sleeves must have identical dates")
    nav = np.array(core["nav"], float) + np.sum([sleeve["nav"] for sleeve in satellites], axis=0)
    if not np.isfinite(nav).all() or np.any(nav <= 0):
        raise ValueError("portfolio NAV must be finite and positive")
    returns = nav / np.r_[initial_cash, nav[:-1]] - 1
    return {"construction": "funded_60_core_40_equal_initial_satellite_sleeves",
            "dates": dates, "nav": nav.tolist(), "returns": returns.tolist()}