"""回測用:把 stock_price 文件的 OHLC 就地換成還原價(後復權)。

為什麼要有這支:回測一律該用還原價,否則除權息會被記成假跌
(實測 2026-07-20:除權息當日中位數 -3.40% 是純粹的假跌)。
而且四個價格欄位**必須一起換** —— 只換 close 會讓還原後的 close 對上
未還原的 open/high/low,pattern 類回測(進場用 open、出場用 close)會算出垃圾。

adj_* 為空時保留原值(全庫僅 23 筆,是 close 本身就缺的舊資料洞)。

用法:
    from _adj_price import ADJ_PROJ, use_adjusted
    docs = list(db.stock_price.find(q, {..., **ADJ_PROJ}).sort('date', 1))
    use_adjusted(docs)
"""

_PAIRS = (("open", "adj_open"), ("high", "adj_high"),
          ("low", "adj_low"), ("close", "adj_close"))

# 併進既有 projection 用
ADJ_PROJ = {"adj_open": 1, "adj_high": 1, "adj_low": 1, "adj_close": 1}


def use_adjusted(docs):
    """就地把每個 doc 的 open/high/low/close 換成 adj_*。回傳同一個 list。"""
    for d in docs:
        for raw, adj in _PAIRS:
            v = d.get(adj)
            if v is not None:
                d[raw] = v
    return docs


def use_adjusted_df(df):
    """DataFrame 版:把 open/high/low/close 欄換成 adj_* (缺值回退原欄)。"""
    for raw, adj in _PAIRS:
        if adj in df.columns and raw in df.columns:
            df[raw] = df[adj].where(df[adj].notna(), df[raw])
        elif adj in df.columns:
            df[raw] = df[adj]
    return df.drop(columns=[a for _, a in _PAIRS if a in df.columns])
