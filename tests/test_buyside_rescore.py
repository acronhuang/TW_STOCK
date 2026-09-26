"""TDD(red→green):M2 買方再評分器。純函式,免 DB → @unit。

驗收(對應 docs/plans/verdict_buyside_v1.md M2):
- coverage_ok=False → 維持買進(不亂動 live 邏輯)
- 追高 且(價值差 或 品質差) → 降級持有
- 低動能 / 便宜 / 高品質 → 維持買進
- 決定論(同輸入同輸出)
"""
import pytest

from src.analysis.buyside.buy_rescore import rescore


def _f(prior_20d=0.0, pe_pctile=50.0, pb_pctile=50.0, roe=15.0, coverage_ok=True):
    return {"prior_20d": prior_20d, "pe_pctile": pe_pctile, "pb_pctile": pb_pctile,
            "roe": roe, "coverage_ok": coverage_ok}


@pytest.mark.unit
def test_incomplete_features_keeps_buy():
    r = rescore(_f(coverage_ok=False, prior_20d=0.20, pe_pctile=99, roe=1))
    assert r["v2"] == "買進"          # 特徵不足時絕不亂動


@pytest.mark.unit
def test_chase_and_pricey_downgrades():
    # 追高(prior>5%) + 價值差(PE 百分位高)
    assert rescore(_f(prior_20d=0.09, pe_pctile=85, roe=15))["v2"] == "降級持有"


@pytest.mark.unit
def test_chase_and_lowquality_downgrades():
    # 追高 + 品質差(ROE 低)
    assert rescore(_f(prior_20d=0.09, pe_pctile=40, roe=5))["v2"] == "降級持有"


@pytest.mark.unit
def test_low_momentum_keeps_buy():
    assert rescore(_f(prior_20d=0.01, pe_pctile=90, roe=4))["v2"] == "買進"


@pytest.mark.unit
def test_chase_but_cheap_and_quality_keeps_buy():
    # 追高但便宜(PE 百分位低)且高品質(ROE 高)→ 仍值得買
    assert rescore(_f(prior_20d=0.09, pe_pctile=20, roe=20))["v2"] == "買進"


@pytest.mark.unit
def test_deterministic():
    f = _f(prior_20d=0.09, pe_pctile=85, roe=5)
    assert rescore(f) == rescore(f)
