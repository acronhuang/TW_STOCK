"""種子↔分析器 離線契約測試(DB-free / mongomock)。

把先前手動的「離線驗證(mongomock)」定型為 unit 閘門:用 mongomock 灌入
scripts/seed_test_data.py 的種子,再跑分析器,鎖定 needs_data 情境「種子後真能
算出結果」。任一端(種子欄位/schema 或分析邏輯)漂移都會在 DB-free 的 unit-gate
秒級被抓,不必等 mongo service。

對應:test_valuation(DCF/DDM/PE Band/analyze)、test_bdd_macro/test_cli::test_macro_command
(MacroAnalyzer 用 find/find_one,mongomock 可跑;而 ranker 的 aggregate $first($filter)
不支援,故 ranking 不入離線契約)。
"""
import importlib.util
from pathlib import Path

import pytest

mongomock = pytest.importorskip("mongomock")

from src.analysis.valuation_models import ValuationAnalyzer

ROOT = Path(__file__).parent.parent
ZONES = {'便宜區', '偏低區', '合理區', '偏高區', '昂貴區'}
VERDICTS = {
    '嚴重低估', '低估', '略為低估', '合理',
    '略為高估', '高估', '嚴重高估', '無法判定',
}


def _seed_module():
    spec = importlib.util.spec_from_file_location(
        "seed_test_data", ROOT / "scripts" / "seed_test_data.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def va():
    """以 mongomock 灌種子,注入 analyzer(不 __init__ → 不連真 Mongo)。"""
    client = mongomock.MongoClient()
    db = client["tw_stock_analysis"]
    _seed_module().seed(db)
    a = ValuationAnalyzer.__new__(ValuationAnalyzer)
    a.client = client
    a.db = db
    return a


@pytest.mark.unit
def test_dcf_returns_fair_value(va):
    r = va.dcf_valuation('2330')
    assert r is not None
    assert r['fair_value'] > 0
    assert r['wacc'] >= 8          # MIN_WACC 不變式
    assert r['beta'] > 0


@pytest.mark.unit
def test_dcf_invalid_symbol_returns_none(va):
    assert va.dcf_valuation('9999') is None


@pytest.mark.unit
def test_ddm_returns_fair_value(va):
    r = va.ddm_valuation('2330')
    assert r is not None
    assert r['fair_value'] > 0
    assert 'cost_of_equity' in r
    assert 'dividend_history' in r


@pytest.mark.unit
def test_ddm_etf(va):
    r = va.ddm_valuation('0056')
    assert r is not None
    assert r['fair_value'] > 0


@pytest.mark.unit
def test_pe_band_analysis(va):
    r = va.pe_band_analysis('2330')
    assert r is not None
    assert r['fair_value'] > 0
    assert 0 <= r['pe_percentile'] <= 100
    assert r['zone'] in ZONES


@pytest.mark.unit
def test_full_analysis(va):
    r = va.analyze('2330')
    assert r['composite']['models_used'] >= 1
    assert r['composite']['verdict'] in VERDICTS


# ────── macro 契約(對應 test_bdd_macro / test_cli::test_macro_command)──────
@pytest.fixture(scope="module")
def ma(va):
    """共用同一 mongomock 種子庫,注入 MacroAnalyzer(不 __init__ → 不連真 Mongo)。"""
    from src.analysis.macro_indicators import MacroAnalyzer
    a = MacroAnalyzer.__new__(MacroAnalyzer)
    a.client = va.client
    a.db = va.db
    a.finmind_token = None
    return a


@pytest.mark.unit
def test_macro_market_signal(ma):
    sig = ma.market_signal()
    assert -100 <= sig['score'] <= 100          # 不變式:評分區間
    assert any(k in sig['verdict'] for k in ('偏多', '偏空', '中性'))


@pytest.mark.unit
def test_macro_overview(ma):
    ov = ma.overview()
    for k in ('interest_rate', 'exchange_rate', 'cpi', 'money_supply', 'taiex'):
        assert k in ov
    # 種子 institutional_flow(近 5 日外資買超)→ foreign_net_5d > 0
    assert ov['taiex'] and ov['taiex'].get('foreign_net_5d', 0) > 0
