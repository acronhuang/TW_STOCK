"""三大法人買進／賣出分列（股數）。原本 institutional_flow 只存買賣超淨額。

每個來源都以「買進 − 賣出 = 買賣超」核對；不符代表欄位錯位，寧可不寫分列也不寫錯。
定義同 foreign_net：外資 = 外陸資 + 外資自營商；自營商 = 自行買賣 + 避險。
"""
from __future__ import annotations

from bson.decimal128 import Decimal128

FIELDS = ("foreign_buy", "foreign_sell", "trust_buy", "trust_sell", "dealer_buy", "dealer_sell")

_T86_COLUMNS = 19
_TOLERANCE = 1


class T86LayoutError(ValueError):
    """T86 標頭與預期欄位位置不符：寧可整批不寫，也不把數字存進錯的欄位。"""


# 欄位位置 → (必含字樣, 不得含字樣)；以字樣而非整句比對，措辭微調不誤報，欄位增減或換位會被抓到。
_T86_LAYOUT = {
    0: (("證券代號",), ()),
    1: (("證券名稱",), ()),
    2: (("外陸資", "買進"), ()), 3: (("外陸資", "賣出"), ()), 4: (("外陸資", "買賣超"), ()),
    5: (("外資自營商", "買進"), ("外陸資",)), 6: (("外資自營商", "賣出"), ("外陸資",)),
    7: (("外資自營商", "買賣超"), ("外陸資",)),
    8: (("投信", "買進"), ()), 9: (("投信", "賣出"), ()), 10: (("投信", "買賣超"), ()),
    11: (("自營商", "買賣超"), ("自行買賣", "避險", "外資")),
    12: (("自營商", "買進", "自行買賣"), ()), 13: (("自營商", "賣出", "自行買賣"), ()),
    14: (("自營商", "買賣超", "自行買賣"), ()),
    15: (("自營商", "買進", "避險"), ()), 16: (("自營商", "賣出", "避險"), ()),
    17: (("自營商", "買賣超", "避險"), ()),
    18: (("三大法人", "買賣超"), ()),
}


def check_t86_fields(fields) -> None:
    """標頭不是 19 欄或任一位置的欄名不符就拋 T86LayoutError（2026-07-19 曾因欄位錯位寫壞 91 萬列）。"""
    if not isinstance(fields, list) or len(fields) != _T86_COLUMNS:
        got = len(fields) if isinstance(fields, list) else fields
        raise T86LayoutError(f"T86 標頭不是 {_T86_COLUMNS} 欄：{got}")
    problems = []
    for index, (required, forbidden) in _T86_LAYOUT.items():
        name = "".join(str(fields[index]).split())
        if any(word not in name for word in required) or any(word in name for word in forbidden):
            problems.append(f"[{index}] 預期含 {'+'.join(required)}，實際「{fields[index]}」")
    if problems:
        raise T86LayoutError("T86 欄位位置與預期不符：" + "；".join(problems[:4]))


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
