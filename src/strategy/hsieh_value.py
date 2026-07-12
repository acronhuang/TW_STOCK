"""
謝富旭深度價值存股法 —— 全市場演算法篩選（取代手選清單）
==========================================================
依謝富旭公開受訪整理的可量化條件，對全市場逐股篩選：

  ① 負債比 < 60%               財務穩健
  ② 流動比 > 100%              （速動比代理；官方財報摘要無存貨欄）
  ③ 未分配盈餘(保留盈餘) ≥ 2 倍股本  累積獲利厚實
  ④ 營益率衰退幅度 < 營收衰退幅度    核心競爭力（衰退期仍維持獲利能力）
  ⑤ 殖利率 ≥ 門檻              穩定配息（重填息）
  ⑥ 連續配息 ≥ 3 年            配息持續性

資料來源：quarterly_earnings.balance / income、stock_factors、dividend_detail。
（442 資金配置、大盤跌>10% 減碼屬操作紀律，不在選股篩選內。）
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional


def _f(v):
    try:
        return float(v.to_decimal()) if hasattr(v, 'to_decimal') else float(v)
    except Exception:
        return None


class HsiehValueScreen:
    """謝富旭存股法全市場篩選器。"""

    DEBT_MAX = 60.0          # 負債比上限 %
    CURRENT_MIN = 100.0      # 流動比下限 %
    RETAINED_MIN = 2.0       # 未分配盈餘/股本 下限(倍)
    YIELD_MIN = 4.0          # 殖利率下限 %
    PAYOUT_YEARS_MIN = 3     # 連續配息年數下限

    def __init__(self, db):
        self.db = db
        self._latest = db.stock_price.find_one(sort=[('date', -1)])['date']

    # ── 資料載入 ───────────────────────────────────────────────────────
    def _active_universe(self) -> List[str]:
        cutoff = self._latest - timedelta(days=10)
        return [s for s in self.db.stock_price.distinct('symbol', {'date': {'$gte': cutoff}})
                if isinstance(s, str) and s.isdigit() and len(s) == 4]

    def _latest_quarters(self) -> Dict[str, dict]:
        """每股最新季的 balance/income/year/season。"""
        out = {}
        for q in self.db.quarterly_earnings.aggregate([
            {'$sort': {'year': -1, 'season': -1}},
            {'$group': {'_id': '$symbol', 'b': {'$first': '$balance'},
                        'i': {'$first': '$income'}, 'y': {'$first': '$year'},
                        's': {'$first': '$season'}}},
        ]):
            out[q['_id']] = q
        return out

    def _dividend_yield(self, symbol: str) -> Optional[float]:
        rec = self.db.stock_factors.find_one(
            {'symbol': symbol, 'dividend_yield': {'$ne': None}},
            {'dividend_yield': 1}, sort=[('date', -1)])
        return _f(rec.get('dividend_yield')) if rec else None

    def _payout_years(self, symbol: str) -> int:
        """近年有現金股利的年度數（民國年）。"""
        yrs = self.db.dividend_detail.distinct(
            'year', {'stock_id': symbol, 'cash_earnings_distribution': {'$gt': 0}})
        return len([y for y in yrs if str(y).isdigit()])

    # ── 單股評估 ───────────────────────────────────────────────────────
    def evaluate(self, symbol: str, q: dict) -> Optional[dict]:
        """回單股各條件數值 + 是否通過；資料不足回 None。"""
        b, i = q.get('b') or {}, q.get('i') or {}
        ta, tl = _f(b.get('total_assets')), _f(b.get('total_liabilities'))
        ca, cl = _f(b.get('current_assets')), _f(b.get('current_liabilities'))
        re, cs = _f(b.get('retained_earnings')), _f(b.get('capital_stock'))
        if not (ta and cl and cs):
            return None

        debt = tl / ta * 100
        current = ca / cl * 100 if ca else None
        retained = re / cs if (re is not None and cs) else None
        dy = self._dividend_yield(symbol)
        years = self._payout_years(symbol)

        # ④ 核心：營益率衰退幅度 < 營收衰退幅度（用去年同季比）
        yq = self.db.quarterly_earnings.find_one(
            {'symbol': symbol, 'year': q['y'] - 1, 'season': q['s']}, {'income': 1})
        yi = (yq or {}).get('income') or {}
        opm, opm0 = _f(i.get('operating_margin')), _f(yi.get('operating_margin'))
        rev, rev0 = _f(i.get('revenue')), _f(yi.get('revenue'))
        resilient = None
        if None not in (opm, opm0, rev, rev0) and rev0 and opm0 > 0:
            rev_chg = (rev - rev0) / rev0 * 100               # 營收 YoY %
            opm_chg = (opm - opm0) / opm0 * 100               # 營益率 相對變化 %
            resilient = rev_chg >= 0 or opm_chg > rev_chg     # 成長 或 營益率衰退較輕

        passed = (
            debt < self.DEBT_MAX
            and current is not None and current > self.CURRENT_MIN
            and retained is not None and retained >= self.RETAINED_MIN
            and resilient is True
            and dy is not None and dy >= self.YIELD_MIN
            and years >= self.PAYOUT_YEARS_MIN
        )
        return {
            'symbol': symbol, 'debt_ratio': round(debt, 1),
            'current_ratio': round(current, 0) if current else None,
            'retained_x': round(retained, 1) if retained else None,
            'op_resilient': resilient, 'dividend_yield': dy,
            'payout_years': years, 'passed': passed,
        }

    # ── 全市場篩選 ─────────────────────────────────────────────────────
    def screen(self, top: Optional[int] = None, require_liquid: bool = True) -> List[dict]:
        """回通過全部條件的個股，依殖利率排序。
        require_liquid=True：濾掉掛單買不到的冷門股(每日 LINE 用)。
        require_liquid=False：列出全部優質股，流動性僅附 avg_lots 標記不排除。"""
        from src.strategy.screen_liquidity import avg_volume_lots, MIN_VOL_LOTS
        lq = self._latest_quarters()
        results = []
        for sym in self._active_universe():
            q = lq.get(sym)
            if not q:
                continue
            lots = avg_volume_lots(self.db, sym)
            if require_liquid and lots < MIN_VOL_LOTS:
                continue
            r = self.evaluate(sym, q)
            if r and r['passed']:
                doc = self.db.stock_price.find_one({'symbol': sym}, sort=[('date', -1)])
                r['name'] = (doc or {}).get('name', '')
                r['price'] = _f((doc or {}).get('close'))
                r['avg_lots'] = round(lots, 0)
                results.append(r)
        results.sort(key=lambda x: -(x['dividend_yield'] or 0))
        return results[:top] if top else results

    GROWTH_YOY_MIN = 10.0    # 存股成長精選：EPS YoY 門檻(%)，濾掉填息陷阱
    MREV_YOY_MIN = 0.0       # 月營收 YoY 門檻(%)：最新動能未轉弱(領先層)
    QREV_YOY_MIN = 0.0       # 季營收 YoY 門檻(%)：同期營收成長(同期層)

    def growth_picks(self, require_liquid: bool = True) -> List[dict]:
        """存股成長精選——四重確認：
          存股法6條件 ∩ EPS年增≥10% ∩ 月營收YoY≥0 ∩ 季營收YoY≥0。
        每檔附 ttm_eps / eps_yoy / mrev_yoy / qrev_yoy；依殖利率排序。"""
        from src.strategy.eps_metrics import ttm_eps_yoy
        from src.strategy.revenue_metrics import monthly_rev_yoy, quarterly_rev_yoy
        out = []
        for r in self.screen(require_liquid=require_liquid):
            eps, eyoy = ttm_eps_yoy(self.db, r['symbol'])
            myoy = monthly_rev_yoy(self.db, r['symbol'])
            qyoy = quarterly_rev_yoy(self.db, r['symbol'])
            if (eyoy is not None and eyoy >= self.GROWTH_YOY_MIN
                    and myoy is not None and myoy >= self.MREV_YOY_MIN
                    and qyoy is not None and qyoy >= self.QREV_YOY_MIN):
                out.append({**r, 'ttm_eps': eps, 'eps_yoy': eyoy,
                            'mrev_yoy': myoy, 'qrev_yoy': qyoy})
        return out

    def growth_line_message(self, top: int = 12) -> str:
        """存股成長精選 LINE：高息 + 獲利/月營收/季營收三動能皆正（四重確認）。"""
        picks = self.growth_picks()
        d = self._latest.strftime('%m/%d') if hasattr(self._latest, 'strftime') else str(self._latest)[:10]
        L = [f"💎 存股成長精選 ({d})  共{len(picks)}檔",
             "  〔存股法6條件 ∩ EPS年增≥10% ∩ 月營收YoY≥0 ∩ 季營收YoY≥0〕",
             "  → 高息且獲利、月/季營收動能全部向上,非填息陷阱\n"]
        for r in picks[:top]:
            L.append(f"{r['symbol']} {r['name']} {r['price']:g} 殖{r['dividend_yield']:.1f}% "
                     f"EPS{r['ttm_eps']:g}(年增{r['eps_yoy']:+.0f}%) "
                     f"月營收{r['mrev_yoy']:+.0f}% 季營收{r['qrev_yoy']:+.0f}% 連配{r['payout_years']}年")
        if len(picks) > top:
            L.append(f"  …另 {len(picks)-top} 檔")
        return '\n'.join(L)

    def line_message(self, top: int = 20) -> str:
        """存股法篩選結果的 LINE 訊息（取代手選清單主動分析）。"""
        picks = self.screen()
        d = self._latest.strftime('%m/%d') if hasattr(self._latest, 'strftime') else str(self._latest)[:10]
        L = [f"📕 謝富旭存股法篩選 ({d})  共{len(picks)}檔",
             "  〔負債<60%·流動>100%·盈餘≥2倍·營益率抗跌·殖≥4%·連配≥3年〕\n"]
        for r in picks[:top]:
            L.append(f"{r['symbol']} {r['name']} {r['price']:g} 殖{r['dividend_yield']:.1f}% "
                     f"負債{r['debt_ratio']:.0f}% 盈餘{r['retained_x']:.1f}倍 連配{r['payout_years']}年")
        if len(picks) > top:
            L.append(f"  …另 {len(picks)-top} 檔")
        return '\n'.join(L)
