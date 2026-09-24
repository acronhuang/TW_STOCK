"""種子↔估值 離線契約測試(DB-free / mongomock)。

把先前手動的「離線驗證(mongomock)」定型為 unit 閘門:用 mongomock 灌入
scripts/seed_test_data.py 的種子,再跑 ValuationAnalyzer,鎖定 test_valuation.py
的 6 個 needs_data 情境「種子後真能算出結果」。任一端(種子欄位/schema 或估值
邏輯)漂移都會在 DB-free 的 unit-gate 秒級被抓,不必等 mongo service。

對應 test_valuation.py:TestDCF / TestDDM / TestPEBand / TestComposite。
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
