"""
選股共用：流動性過濾
====================
過濾「掛單買不到/會墊高成本」的冷門股——選股清單只該列散戶能正常進出的標的。
供 HsiehValueScreen / AganMoatScreen 等共用。
"""

MIN_VOL_LOTS = 300   # 近20日均量門檻(張/日)；散戶可正常進出


def avg_volume_lots(db, symbol, days=20):
    """回近 days 日平均成交量(張)。"""
    vals = []
    for p in db.stock_price.find({'symbol': symbol}, {'volume': 1}).sort('date', -1).limit(days):
        v = p.get('volume')
        try:
            vals.append(float(v.to_decimal()) if hasattr(v, 'to_decimal') else float(v))
        except (TypeError, ValueError, AttributeError):
            pass
    return sum(vals) / len(vals) / 1000 if vals else 0.0


def is_liquid(db, symbol, min_lots=MIN_VOL_LOTS, days=20):
    """近 days 日均量是否達門檻(可正常買賣)。"""
    return avg_volume_lots(db, symbol, days) >= min_lots
