"""
闕又上「阿甘投資法」—— 景氣燈號擇時 + 護城河龍頭選股
======================================================
阿甘投資法本質：指數(0050/S&P500) + 景氣對策信號擇時 + 資產配置。
依公開受訪整理的可量化規則實作。

A. 景氣燈號擇時（招牌紀律）
   國發會景氣對策信號分數(9~45) → 燈號 → 進出場：
     藍燈/黃藍燈(景氣低迷) → 分批進場(便宜)；綠燈 → 持有；黃紅燈/紅燈(過熱) → 減碼/出場。
   資料：macro_indicators(indicator='leading').data.signal_score（月更，macro_sync --set-signal 維護）。

B. 護城河龍頭選股（品質型，有別於謝富旭高殖利率）
   ① 大型龍頭(市值前段) ② 高ROE(護城河,持續獲利) ③ 低負債 ④ 長期連續配息。
"""
from datetime import timedelta
from typing import Dict, List, Optional


def _f(v):
    try:
        return float(v.to_decimal()) if hasattr(v, 'to_decimal') else float(v)
    except Exception:
        return None


# ── A. 景氣燈號擇時 ──────────────────────────────────────────────────────
def agan_market_signal(db) -> Optional[Dict]:
    """讀景氣對策信號分數 → 燈號 + 阿甘進出場訊號。無資料回 None。"""
    d = db.macro_indicators.find_one({'indicator': 'leading'}, sort=[('date', -1)])
    score = (d.get('data') or {}).get('signal_score') if d else None
    if score is None:
        return None
    score = float(score)
    if score <= 16:
        light, action = '藍燈', '🔵 分批進場（景氣低迷，分10次布局便宜區）'
    elif score <= 22:
        light, action = '黃藍燈', '🔵 開始布局（注意性燈號，可分批進場）'
    elif score <= 31:
        light, action = '綠燈', '🟢 持有（景氣穩定，不動）'
    elif score <= 37:
        light, action = '黃紅燈', '🟠 減碼（景氣轉熱，留意過熱）'
    else:
        light, action = '紅燈', '🔴 出場（景氣過熱，一次出清攻擊性資產）'
    return {'score': score, 'light': light, 'action': action,
            'date': (d.get('data') or {}).get('date') or d.get('date')}


# ── B. 護城河龍頭選股 ────────────────────────────────────────────────────
class AganMoatScreen:
    """阿甘護城河龍頭篩選：大型龍頭 + 高ROE + 低負債 + 長期連配。"""

    TOP_MKTCAP = 200       # 市值前 N 視為大型龍頭(阿甘偏好大型優質/指數成分)
    ROE_MIN = 15.0         # 護城河：高且穩定 ROE
    DEBT_MAX = 50.0        # 穩健
    PAYOUT_YEARS_MIN = 5   # 阿甘重長期，連配年數較嚴

    def __init__(self, db):
        self.db = db
        self._latest = db.stock_price.find_one(sort=[('date', -1)])['date']

    def _large_caps(self) -> Dict[str, dict]:
        """市值前 TOP_MKTCAP 大型股 {symbol: {name, price, mktcap}}（市值=發行股數×最新收盤）。"""
        latest_px = {}
        for d in self.db.stock_price.aggregate([
            {'$sort': {'date': -1}},
            {'$group': {'_id': '$symbol', 'close': {'$first': '$close'},
                        'name': {'$first': '$name'}}}], allowDiskUse=True):
            latest_px[d['_id']] = d
        shares = {d['stock_id']: _f(d.get('outstanding_shares'))
                  for d in self.db.taiwan_stock_info.find(
                      {'outstanding_shares': {'$ne': None}}, {'stock_id': 1, 'outstanding_shares': 1})}
        cutoff = self._latest - timedelta(days=10)
        active = set(s for s in self.db.stock_price.distinct('symbol', {'date': {'$gte': cutoff}})
                     if isinstance(s, str) and s.isdigit() and len(s) == 4)
        caps = []
        for s in active:
            px, sh = latest_px.get(s), shares.get(s)
            c = _f((px or {}).get('close')) if px else None
            if c and sh:
                caps.append((s, c * sh, c, (px or {}).get('name', '')))
        caps.sort(key=lambda x: -x[1])
        return {s: {'name': nm, 'price': c, 'mktcap': mc} for s, mc, c, nm in caps[:self.TOP_MKTCAP]}

    def _latest_roe_debt(self, symbol: str):
        """回 (TTM_ROE, 負債比)。
        ROE 用 **TTM(近4單季淨利加總/權益)** ——避免 stored.roe 的單季×4 年化失真
        (如宜鼎 Q1強 ×4=149%，TTM 才是真實年ROE 49%)。負債比用最新季。"""
        qs = list(self.db.quarterly_earnings.find(
            {'symbol': symbol}, {'income.net_income': 1, 'balance': 1}
        ).sort([('year', -1), ('season', -1)]).limit(4))
        if not qs:
            return None, None
        nis = [_f((q.get('income') or {}).get('net_income')) for q in qs]
        nis = [x for x in nis if x is not None]
        eq = next((_f((q.get('balance') or {}).get('total_equity'))
                   for q in qs if (q.get('balance') or {}).get('total_equity')), None)
        roe = sum(nis) / eq * 100 if (len(nis) == 4 and eq) else None
        b = qs[0].get('balance') or {}
        ta, tl = _f(b.get('total_assets')), _f(b.get('total_liabilities'))
        debt = tl / ta * 100 if (ta and tl is not None) else None
        return roe, debt

    def _payout_years(self, symbol: str) -> int:
        yrs = self.db.dividend_detail.distinct(
            'year', {'stock_id': symbol, 'cash_earnings_distribution': {'$gt': 0}})
        return len([y for y in yrs if str(y).isdigit()])

    def screen(self, top: Optional[int] = None, require_liquid: bool = True) -> List[dict]:
        """回通過條件的大型龍頭，依 ROE 排序。
        require_liquid=True：排除冷門股(只列買得到的，每日 LINE 用)。
        require_liquid=False：列出全部優質股，流動性僅附 avg_lots 標記不排除。"""
        from src.strategy.screen_liquidity import avg_volume_lots, MIN_VOL_LOTS
        results = []
        for sym, m in self._large_caps().items():
            lots = avg_volume_lots(self.db, sym)
            if require_liquid and lots < MIN_VOL_LOTS:
                continue
            roe, debt = self._latest_roe_debt(sym)
            years = self._payout_years(sym)
            if (roe is not None and roe >= self.ROE_MIN
                    and debt is not None and debt < self.DEBT_MAX
                    and years >= self.PAYOUT_YEARS_MIN):
                results.append({'symbol': sym, 'name': m['name'], 'price': m['price'],
                                'roe': round(roe, 1), 'debt_ratio': round(debt, 1),
                                'payout_years': years, 'avg_lots': round(lots, 0)})
        results.sort(key=lambda x: -x['roe'])
        return results[:top] if top else results

    def line_message(self, top: int = 15) -> str:
        picks = self.screen()
        d = self._latest.strftime('%m/%d') if hasattr(self._latest, 'strftime') else str(self._latest)[:10]
        sig = agan_market_signal(self.db)
        L = [f"🎯 阿甘投資法 ({d})"]
        if sig:
            sm = str(sig.get('date') or '')[:7]                 # 信號月份 YYYY-MM
            stale = ''
            if sm and hasattr(self._latest, 'year'):           # 信號落後現在>2個月→過期警示
                gap = (self._latest.year - int(sm[:4])) * 12 + (self._latest.month - int(sm[5:7]))
                if gap >= 3:
                    stale = ' ⚠️信號過期,請更新'
            L.append(f"  景氣{sig['light']}({sig['score']:.0f}分·{sm}){stale} → {sig['action']}")
            L.append("  ※景氣位階訊號,與北大技術面互補非衝突")
        L.append(f"  護城河龍頭(市值前{self.TOP_MKTCAP}·ROE≥{self.ROE_MIN:.0f}%·負債<{self.DEBT_MAX:.0f}%·連配≥{self.PAYOUT_YEARS_MIN}年) 共{len(picks)}檔\n")
        for r in picks[:top]:
            L.append(f"{r['symbol']} {r['name']} {r['price']:g} ROE{r['roe']:.0f}% 負債{r['debt_ratio']:.0f}% 連配{r['payout_years']}年")
        return '\n'.join(L)
