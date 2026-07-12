"""
品質成長篩選 —— 高 ROE/高營益率/獲利動能向上的「護城河成長股」
==============================================================
補存股法的空缺：有些公司體質極佳(高ROE、高營益率、EPS與營收皆成長)，
但股價貴(殖利率<4%)或盈餘累積不足，不符謝富旭「高息厚實存股」定位 → 被擋下。
本篩選只看「品質 + 成長動能」，不看殖利率/盈餘倍數，專抓這類優質成長股。

條件(全用實際財報，無預測)：
  ① TTM ROE ≥ 15%            護城河:持續高獲利
  ② 最新季營益率 ≥ 10%       定價力/護城河
  ③ EPS 年增 ≥ 10%           獲利成長(近4季 vs 去年同4季)
  ④ 月營收 YoY ≥ 0           最新動能未轉弱(領先)
  ⑤ 季營收 YoY ≥ 0           同期營收成長
  ⑥ 負債比 < 50%             穩健
流動性僅附 avg_lots 標記，不排除(關貿這類冷門優質股仍列出)。
"""
from datetime import timedelta
from typing import Dict, List, Optional


def _f(v):
    try:
        return float(v.to_decimal()) if hasattr(v, 'to_decimal') else float(v)
    except (TypeError, ValueError, AttributeError):
        return None


class QualityGrowthScreen:
    ROE_MIN = 15.0
    OPM_MIN = 10.0
    EPS_YOY_MIN = 10.0
    DEBT_MAX = 50.0

    def __init__(self, db):
        self.db = db
        self._latest = db.stock_price.find_one(sort=[('date', -1)])['date']

    def _active_universe(self) -> List[str]:
        cutoff = self._latest - timedelta(days=10)
        return [s for s in self.db.stock_price.distinct('symbol', {'date': {'$gte': cutoff}})
                if isinstance(s, str) and s.isdigit() and len(s) == 4]

    def _roe_debt_opm(self, symbol: str):
        """回 (TTM_ROE, 負債比, 最新季營益率)。ROE 用 TTM(近4單季淨利/權益)。"""
        qs = list(self.db.quarterly_earnings.find(
            {'symbol': symbol}, {'income': 1, 'balance': 1}
        ).sort([('year', -1), ('season', -1)]).limit(4))
        if not qs:
            return None, None, None
        nis = [_f((q.get('income') or {}).get('net_income')) for q in qs]
        eq = next((_f((q.get('balance') or {}).get('total_equity'))
                   for q in qs if (q.get('balance') or {}).get('total_equity')), None)
        roe = sum(nis) / eq * 100 if (len(nis) == 4 and all(x is not None for x in nis) and eq) else None
        b = qs[0].get('balance') or {}
        ta, tl = _f(b.get('total_assets')), _f(b.get('total_liabilities'))
        debt = tl / ta * 100 if (ta and tl is not None) else None
        opm = _f((qs[0].get('income') or {}).get('operating_margin'))
        return roe, debt, opm

    def screen(self, top: Optional[int] = None) -> List[dict]:
        """回品質成長股，依 ROE 排序。每檔附 roe/opm/eps_yoy/mrev/qrev/avg_lots。"""
        from src.strategy.eps_metrics import ttm_eps_yoy
        from src.strategy.revenue_metrics import monthly_rev_yoy, quarterly_rev_yoy
        from src.strategy.screen_liquidity import avg_volume_lots
        results = []
        for sym in self._active_universe():
            roe, debt, opm = self._roe_debt_opm(sym)
            if roe is None or roe < self.ROE_MIN:
                continue
            if debt is None or debt >= self.DEBT_MAX:
                continue
            if opm is None or opm < self.OPM_MIN:
                continue
            eps, eyoy = ttm_eps_yoy(self.db, sym)
            if eyoy is None or eyoy < self.EPS_YOY_MIN:
                continue
            myoy = monthly_rev_yoy(self.db, sym)
            qyoy = quarterly_rev_yoy(self.db, sym)
            if myoy is None or myoy < 0 or qyoy is None or qyoy < 0:
                continue
            doc = self.db.stock_price.find_one({'symbol': sym}, sort=[('date', -1)])
            results.append({
                'symbol': sym, 'name': (doc or {}).get('name', ''),
                'price': _f((doc or {}).get('close')),
                'roe': round(roe, 1), 'debt_ratio': round(debt, 1),
                'opm': round(opm, 1), 'ttm_eps': eps, 'eps_yoy': eyoy,
                'mrev_yoy': myoy, 'qrev_yoy': qyoy,
                'avg_lots': round(avg_volume_lots(self.db, sym), 0),
            })
        results.sort(key=lambda x: -x['roe'])
        return results[:top] if top else results

    def line_message(self, top: int = 15) -> str:
        """品質成長榜 LINE：高ROE+高營益率+獲利/月/季營收三動能皆正（護城河成長股）。"""
        picks = self.screen()
        d = self._latest.strftime('%m/%d') if hasattr(self._latest, 'strftime') else str(self._latest)[:10]
        L = [f"🚀 品質成長榜 ({d})  共{len(picks)}檔",
             f"  〔ROE≥{self.ROE_MIN:.0f}%·營益率≥{self.OPM_MIN:.0f}%·EPS年增≥{self.EPS_YOY_MIN:.0f}%·月/季營收YoY≥0·負債<{self.DEBT_MAX:.0f}%〕",
             "  → 護城河成長股(非高息存股,股價多偏貴)\n"]
        for r in picks[:top]:
            thin = '⚠' if (r['avg_lots'] or 0) < 300 else ''
            L.append(f"{thin}{r['symbol']} {r['name']} {r['price']:g} ROE{r['roe']:.0f}% "
                     f"營益率{r['opm']:.0f}% EPS年增{r['eps_yoy']:+.0f}% 月營收{r['mrev_yoy']:+.0f}%")
        if len(picks) > top:
            L.append(f"  …另 {len(picks)-top} 檔(完整清單見查詢)")
        return '\n'.join(L)
