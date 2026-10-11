"""回測成交價格的單邊滑價壓力模型。"""


def execution_price(market_price: float, side: str, slippage_bps: float = 0.0) -> float:
    if market_price <= 0:
        raise ValueError("market_price must be positive")
    if slippage_bps < 0:
        raise ValueError("slippage_bps must be non-negative")
    if side not in {"buy", "sell"}:
        raise ValueError("side must be 'buy' or 'sell'")

    adjustment = slippage_bps / 10_000
    return market_price * (1 + adjustment if side == "buy" else 1 - adjustment)