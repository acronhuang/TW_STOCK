"""台股交易成本模型(回測共用)。

- 手續費(brokerage):0.1425%/邊,買賣皆收,可打折(discount=券商折數,1.0=無折、0.28=28折)。
- 證交稅(securities transaction tax):**賣出**收 0.3%(當沖 0.15%);買進不收。
所有函式回「佔成交金額的百分比(percentage points)」,與回測報酬%同單位,可直接相減。
"""

FEE = 0.001425       # 手續費率(單邊)
TAX = 0.003          # 證交稅(賣出,一般)
TAX_DAYTRADE = 0.0015  # 當沖證交稅減半


def buy_cost_pct(discount: float = 1.0) -> float:
    """買進成本%(僅手續費)。"""
    return FEE * discount * 100


def sell_cost_pct(discount: float = 1.0, daytrade: bool = False) -> float:
    """賣出成本%(手續費+證交稅)。"""
    tax = TAX_DAYTRADE if daytrade else TAX
    return (FEE * discount + tax) * 100


def roundtrip_pct(discount: float = 1.0, daytrade: bool = False) -> float:
    """一買一賣總成本%(近似:佔進場金額)。無折=0.585%,6折=0.471%。"""
    return buy_cost_pct(discount) + sell_cost_pct(discount, daytrade)
