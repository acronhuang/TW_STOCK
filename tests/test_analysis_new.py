"""近期新增分析純函式的單元測試(防迴歸)。

重點守著歷史踩坑:
  - yoy_pct 負基期符號(曾致 503/1927 檔符號翻轉)
  - 量價七句口訣的位置極端優先邏輯(高位放量=跑路的反直覺)
  - 資料不足時的守門(回 None 不炸)
不連 DB,純函式。
"""
from datetime import datetime

import pytest

from src.analysis.financial_statements import yoy_pct, quarterly_financials
from src.analysis.strategy_2560 import classify_2560
from src.analysis.volprice_pattern import classify, classify_tf
from src.analysis.core_pool import latest_buys, _yoy


# ── team_analysis 專用 stub(支援 date 範圍/verdict 查詢 + sort/limit）──
class _Cursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def sort(self, key, direction=1):
        self._docs.sort(key=lambda d: d.get(key), reverse=(direction < 0))
        return self

    def limit(self, n):
        self._docs = self._docs[:n]
        return self

    def __iter__(self):
        return iter(self._docs)


class _TAColl:
    def __init__(self, docs):
        self._docs = docs

    def find(self, flt=None, proj=None):
        flt = flt or {}
        out = []
        for d in self._docs:
            ok = True
            for k, cond in flt.items():
                v = d.get(k)
                if isinstance(cond, dict):
                    if "$gte" in cond and not (v is not None and v >= cond["$gte"]):
                        ok = False
                    if "$lt" in cond and not (v is not None and v < cond["$lt"]):
                        ok = False
                elif v != cond:
                    ok = False
            if ok:
                out.append(d)
        return _Cursor(out)


class _FakeDB2:
    def __init__(self, ta_docs):
        self.team_analysis = _TAColl(ta_docs)


# ── 輕量 stub db（mimic pymongo find(filter, projection)）──
class _FakeColl:
    def __init__(self, docs):
        self._docs = docs

    def find(self, flt=None, proj=None):
        flt = flt or {}
        sid = flt.get("stock_id")
        types = (flt.get("type") or {}).get("$in")
        for d in self._docs:
            if sid is not None and d.get("stock_id") != sid:
                continue
            if types is not None and d.get("type") not in types:
                continue
            yield d


class _FakeDB:
    def __init__(self, data):
        self._data = data

    def __getitem__(self, name):
        return _FakeColl(self._data.get(name, []))


def _cf(sid, y, m, typ, val):
    return {"stock_id": sid, "date": datetime(y, m, 30 if m != 3 else 31), "type": typ, "value": val}


@pytest.mark.unit
class TestYoyPct:
    def test_normal_growth(self):
        assert yoy_pct(120, 100) == 20.0

    def test_zero_growth(self):
        assert yoy_pct(100, 100) == 0.0

    def test_negative_base_turnaround_is_positive(self):
        # 去年虧100、今年賺50 → 改善 → 正號(舊 bug 會算成負)
        assert yoy_pct(50, -100) == 150.0

    def test_negative_base_loss_narrowing_is_positive(self):
        # 去年虧100、今年虧50(虧損收窄) → 改善 → 正號
        assert yoy_pct(-50, -100) == 50.0

    def test_negative_base_loss_widening_is_negative(self):
        # 去年虧100、今年虧150(虧損擴大) → 惡化 → 負號
        assert yoy_pct(-150, -100) == -50.0

    def test_zero_base_returns_none(self):
        assert yoy_pct(100, 0) is None

    def test_none_inputs_return_none(self):
        assert yoy_pct(None, 100) is None
        assert yoy_pct(100, None) is None


@pytest.mark.unit
class TestClassify2560:
    def test_insufficient_data_returns_none(self):
        assert classify_2560([1.0] * 64, [1.0] * 64) is None

    def test_returns_dict_with_setup_key(self):
        closes = [100 + i * 2 for i in range(70)]
        vols = [1000 + i for i in range(70)]
        r = classify_2560(closes, vols)
        assert isinstance(r, dict)
        assert "setup" in r and isinstance(r["setup"], bool)

    def test_strong_rise_not_touching_ma25_is_not_setup(self):
        # 陡升(收盤遠高於 MA25,非踩線起動)→ setup False
        closes = [100 + i * 2 for i in range(70)]
        vols = [1000 + i for i in range(70)]
        assert classify_2560(closes, vols)["setup"] is False


@pytest.mark.unit
class TestVolpriceClassify:
    def test_insufficient_data_returns_none(self):
        assert classify([1.0] * 8, [1.0] * 8, 5, 3, 15) is None

    def test_high_position_volume_up_is_sell(self):
        # 穩定上漲(收在高位)+ 放量 → 口訣「高位放量·跑路」(反直覺但正確)
        closes = [100 + i for i in range(20)]
        vols = [(i + 1) * 100 for i in range(20)]
        r = classify(closes, vols, 5, 3, 15)
        assert r["label"] == "高位放量·跑路"
        assert r["tone"] == "bear"
        assert r["位置"] == "高" and r["量"] == "增"

    def test_low_position_volume_up_is_follow(self):
        # 下跌到低位 + 放量 → 「低位放量·跟上」
        closes = [120 - i for i in range(20)]
        vols = [(i + 1) * 100 for i in range(20)]
        r = classify(closes, vols, 5, 3, 15)
        assert r["label"] == "低位放量·跟上"
        assert r["tone"] == "bull"
        assert r["位置"] == "低"

    def test_classify_tf_uses_timeframe(self):
        assert classify_tf([1.0] * 10, [1.0] * 10, "月") is None  # <period*2
        closes = [100 + i for i in range(60)]
        vols = [(i + 1) * 10 for i in range(60)]
        assert isinstance(classify_tf(closes, vols, "月"), dict)


@pytest.mark.unit
class TestCashFlowDiff:
    """守住現金流累計→單季差分 + FCF=OCF+CapEx(CapEx 存負值)的 gotcha。"""
    OCF = "CashFlowsFromOperatingActivities"
    CAPEX = "PropertyAndPlantAndEquipment"

    def _db(self, docs):
        return _FakeDB({"cash_flows_detail": docs,
                        "financial_statement_detail": [], "balance_sheet_detail": []})

    def test_q1_not_diffed_q2_diffed(self):
        # OCF 累計: Q1=100, Q2=250 → Q1單季=100(不差分), Q2單季=150(250-100)
        # CapEx 累計(負): Q1=-40, Q2=-90 → Q1=-40, Q2=-50(-90-(-40))
        docs = [_cf("T", 2025, 3, self.OCF, 100), _cf("T", 2025, 6, self.OCF, 250),
                _cf("T", 2025, 3, self.CAPEX, -40), _cf("T", 2025, 6, self.CAPEX, -90)]
        rows = quarterly_financials(self._db(docs), "T")
        q1 = next(r for r in rows if r["season"] == 1)
        q2 = next(r for r in rows if r["season"] == 2)
        assert q1["ocf"] == 100 and q1["capex"] == -40
        assert q2["ocf"] == 150 and q2["capex"] == -50

    def test_free_cf_is_ocf_plus_negative_capex(self):
        docs = [_cf("T", 2025, 3, self.OCF, 100), _cf("T", 2025, 6, self.OCF, 250),
                _cf("T", 2025, 3, self.CAPEX, -40), _cf("T", 2025, 6, self.CAPEX, -90)]
        rows = quarterly_financials(self._db(docs), "T")
        q1 = next(r for r in rows if r["season"] == 1)
        q2 = next(r for r in rows if r["season"] == 2)
        assert q1["free_cf"] == 60    # 100 + (-40)
        assert q2["free_cf"] == 100   # 150 + (-50)

    def test_q2_missing_q1_returns_none_not_garbage(self):
        # 只有 Q2 累計、缺 Q1 → 單季無法差分 → None(不可拿累計值當單季)
        docs = [_cf("T", 2025, 6, self.OCF, 250), _cf("T", 2025, 6, self.CAPEX, -90)]
        rows = quarterly_financials(self._db(docs), "T")
        q2 = next(r for r in rows if r["season"] == 2)
        assert q2["ocf"] is None and q2["free_cf"] is None


@pytest.mark.unit
class TestCorePool:
    def test_yoy_negative_base_sign(self):
        # core_pool 自己的 _yoy 也要守負基期符號
        assert _yoy(50, -100) == 150.0
        assert _yoy(-150, -100) == -50.0
        assert _yoy(100, 0) is None

    def test_latest_buys_picks_full_market_not_latest_daily(self):
        # 真 bug:曾挑到「最新日期」的每日 dailypicks(數十檔),而非全市場週跑(數百檔)。
        # 門檻 min_universe 應讓它挑「筆數達標的全市場批」,即使那批日期較舊。
        docs = []
        d_full = datetime(2026, 8, 1)   # 全市場週跑(較舊)
        for i in range(600):
            docs.append({"date": d_full, "symbol": str(1000 + i),
                         "final_verdict": "買進" if i < 3 else "觀望"})
        d_daily = datetime(2026, 8, 4)  # 每日 dailypicks(較新、筆數少)
        for i in range(12):
            docs.append({"date": d_daily, "symbol": str(9000 + i), "final_verdict": "買進"})

        d0, buys = latest_buys(_FakeDB2(docs), min_universe=500)
        assert d0.date() == d_full.date()          # 挑全市場批、非最新每日
        assert buys == {"1000", "1001", "1002"}    # 全市場批的買進,非 9000 系列

    def test_latest_buys_no_full_market_returns_empty(self):
        docs = [{"date": datetime(2026, 8, 4), "symbol": "2330", "final_verdict": "買進"}]
        d0, buys = latest_buys(_FakeDB2(docs), min_universe=500)
        assert d0 is None and buys == set()


@pytest.mark.unit
class TestTwCosts:
    """台股交易成本模型:買=手續費;賣=手續費+證交稅0.3%。"""
    def test_buy_only_commission(self):
        from src.backtesting.tw_costs import buy_cost_pct
        assert abs(buy_cost_pct(1.0) - 0.1425) < 1e-9      # 0.1425%

    def test_sell_commission_plus_tax(self):
        from src.backtesting.tw_costs import sell_cost_pct
        assert abs(sell_cost_pct(1.0) - 0.4425) < 1e-9     # 0.1425 + 0.30

    def test_roundtrip_no_discount(self):
        from src.backtesting.tw_costs import roundtrip_pct
        assert abs(roundtrip_pct(1.0) - 0.585) < 1e-9      # 0.1425 + 0.4425

    def test_discount_lowers_commission_not_tax(self):
        from src.backtesting.tw_costs import roundtrip_pct
        # 6折:手續費打折、證交稅不打折 → 0.1425*0.6*2 + 0.3 = 0.471
        assert abs(roundtrip_pct(0.6) - 0.471) < 1e-9

    def test_daytrade_tax_halved(self):
        from src.backtesting.tw_costs import sell_cost_pct
        assert abs(sell_cost_pct(1.0, daytrade=True) - (0.1425 + 0.15)) < 1e-9
