"""三大法人買進／賣出分列（股數）。原本 institutional_flow 只存買賣超淨額。

每個來源都以「買進 − 賣出 = 買賣超」核對；不符代表欄位錯位，寧可不寫分列也不寫錯。
定義同 foreign_net：外資 = 外陸資 + 外資自營商；自營商 = 自行買賣 + 避險。
"""
from __future__ import annotations

from bson.decimal128 import Decimal128

FIELDS = ("foreign_buy", "foreign_sell", "trust_buy", "trust_sell", "dealer_buy", "dealer_sell")

_T86_COLUMNS = 19
_TOLERANCE = 1


def _number(value) -> float | None:
    text = str(value if value is not None else "").replace(",", "").replace("+", "").strip()
    if text in ("", "--", "N/A", "-"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _build(blocks: dict[str, tuple]) -> dict:
    """blocks: {"foreign": (買, 賣, 淨), ...}，任一缺值或買賣淨不符就整筆放棄。"""
    out = {}
    for name, (buy, sell, net) in blocks.items():
        if None in (buy, sell, net) or abs((buy - sell) - net) > _TOLERANCE:
            return {}
        out[f"{name}_buy"], out[f"{name}_sell"] = Decimal128(str(buy)), Decimal128(str(sell))
    return out


def _sum(*values) -> float | None:
    numbers = [_number(v) for v in values]
    return None if None in numbers else sum(numbers)


def from_t86(row: list) -> dict:
    """TWSE T86 單列（19 欄）。"""
    if len(row) < _T86_COLUMNS:
        return {}
    return _build({
        "foreign": (_sum(row[2], row[5]), _sum(row[3], row[6]), _sum(row[4], row[7])),
        "trust": (_number(row[8]), _number(row[9]), _number(row[10])),
        "dealer": (_sum(row[12], row[15]), _sum(row[13], row[16]), _number(row[11])),
    })


def _first(row: dict, *keys):
    for key in keys:
        if key in row:
            return row[key]
    return None


def from_tpex_openapi(row: dict) -> dict:
    """TPEX OpenAPI tpex_3insti_daily_trading（只給最新日）。"""
    foreign = "ForeignInvestorsIncludeMainlandAreaInvestors"
    trust = "SecuritiesInvestmentTrustCompanies"
    return _build({
        "foreign": (_number(row.get(f"{foreign}-TotalBuy")), _number(row.get(f"{foreign}-TotalSell")),
                    _number(_first(row, f"{foreign}-Difference", "ForeignInvestorsInclude MainlandAreaInvestors-Difference"))),
        "trust": (_number(row.get(f"{trust}-TotalBuy")), _number(row.get(f"{trust}-TotalSell")),
                  _number(row.get(f"{trust}-Difference"))),
        "dealer": (_number(row.get("Dealers-TotalBuy")), _number(_first(row, "Dealers-TotalSell", "Dealers -TotalSell")),
                   _number(row.get("Dealers-Difference"))),
    })


def from_tpex_dated(row: list) -> dict:
    """TPEX 3itrade_hedge_result 單列：外資合計 8-10、投信 11-13、自營商合計 20-22（買、賣、淨）。"""
    if len(row) <= 22:
        return {}
    return _build({
        "foreign": tuple(_number(row[i]) for i in (8, 9, 10)),
        "trust": tuple(_number(row[i]) for i in (11, 12, 13)),
        "dealer": tuple(_number(row[i]) for i in (20, 21, 22)),
    })
