"""TDD: 風控與籌碼角色改用規則模板：不打 LLM、格式與原本一致、資料缺漏不崩、可用環境變數還原。"""

import re

import pytest

from scripts import team_daily_verified as tdv
from src.moe import rule_roles

pytestmark = pytest.mark.unit

ROLES = ["macro-analyst", "technical-analyst", "fundamental-analyst", "value-analyst", "risk-manager", "chip-analyst"]

DATA = {
    "factors": {"close": 92.2},
    "valuation": {"current_price": 92.2},
    "risk": {
        "current_price": 92.2,
        "returns": {"annual_volatility": 29.03},
        "var": {"daily_var_95": 2.79},
        "drawdown": {"max_drawdown": -22.3},
        "ratios": {"beta": 0.3},
        "position_sizing": {"half_kelly": 0.0346, "max_position_pct": 3.5},
        "risk_level": {"level": "中風險", "score": 4, "description": "波動適中"},
    },
    "institutional": [
        {"date": "2026-10-05", "foreign_net": -31723.0, "trust_net": -2000.0, "dealer_net": 5330.0, "total_net": -28393.0},
        {"date": "2026-10-06", "foreign_net": 235309.0, "trust_net": -18000.0, "dealer_net": 10670.0, "total_net": 227979.0},
    ],
    "chip": {
        "margin": {"margin_bal": 1379, "margin_chg": -67, "short_bal": 21, "short_chg": 2},
        "big_holder": {"big400_pct": 81.48, "big1000_pct": 74.55, "holders_chg_pct": -0.77},
        "籌碼訊號": "⭐ 主力吃貨",
        "近5日股價%": 6.2,
    },
}
HINT = "【部位試算(程式,勿改算)】現價約92.2元,一張92,200元;10萬資金單檔 15% 權重約 0 張(全押最多 1 張)。"


def cited(text):
    return dict(re.findall(r"(\w+)=(-?[\d.]+)", text.split("📌引用數值：")[-1]))


def test_the_risk_report_uses_the_program_numbers_and_never_recomputes_the_position():
    text = rule_roles.risk_report(DATA, HINT)

    assert "風險等級：中風險" in text
    assert "全押最多 1 張" in text and "勿改算" not in text
    assert "停損價：89.63元" in text  # 92.2 × (1 − 2.79%)
    assert cited(text)["daily_var_95"] == "2.79" and len(cited(text)) >= 3


def test_the_chip_report_sums_the_institutions_and_cites_the_raw_latest_values():
    text = rule_roles.chip_report(DATA)

    assert "合計淨買超" in text and "外資+204" in text and "投信-20" in text  # 張 = 股 / 1000
    assert "籌碼訊號：「⭐ 主力吃貨」" in text
    assert cited(text)["total_net"] == "227979.0" and cited(text)["big1000_pct"] == "74.55"


def test_net_selling_is_worded_as_selling():
    data = {**DATA, "institutional": [{"foreign_net": -5000000.0, "trust_net": 0.0, "dealer_net": 0.0, "total_net": -5000000.0}]}

    assert "合計淨賣超5,000張" in rule_roles.chip_report(data)


@pytest.mark.parametrize("renderer, args", [(rule_roles.risk_report, ({}, "")), (rule_roles.chip_report, ({},))])
def test_missing_data_says_so_instead_of_raising_or_posing_as_a_failure(renderer, args):
    text = renderer(*args)

    assert "資料不足" in text and "分析失敗" not in text


def test_partial_data_shows_blanks_instead_of_none():
    data = {"risk": {"risk_level": {"level": "高風險"}}, "chip": {"margin": {}}, "institutional": [{"total_net": 1000.0}]}

    assert "None" not in rule_roles.risk_report(data, "") and "None" not in rule_roles.chip_report(data)


def test_by_default_value_risk_and_chip_are_rule_roles_in_pipeline_order(monkeypatch):
    monkeypatch.delenv("TEAM_RULE_ROLES", raising=False)

    assert rule_roles.active(ROLES) == ["value-analyst", "risk-manager", "chip-analyst"]


@pytest.mark.parametrize("value, expected", [("", []), ("chip-analyst", ["chip-analyst"]), ("chip-analyst, nonsense", ["chip-analyst"])])
def test_the_rule_roles_can_be_restored_to_llm_from_the_environment(monkeypatch, value, expected):
    monkeypatch.setenv("TEAM_RULE_ROLES", value)

    assert rule_roles.active(ROLES) == expected


@pytest.fixture
def pipeline(monkeypatch):
    asked = []

    def fake_ask(role, prompt, include_role_prompt=True, timeout=300):
        asked.append(role)
        return {"role": role, "model": "fake-llm", "response": f"{role} 報告\n📌引用數值：a=1", "elapsed_sec": 0.1}

    monkeypatch.setattr(tdv, "fetch_all_data", lambda s: DATA)
    monkeypatch.setattr(tdv, "verify_metrics", lambda s: [])
    monkeypatch.setattr(tdv, "senvision_patterns", lambda s: [])
    monkeypatch.setattr(tdv, "senvision_text", lambda p: "")
    monkeypatch.setattr(tdv, "_ma_inst_extra", lambda s: {})
    monkeypatch.setattr(tdv, "_news_for", lambda s: "")
    monkeypatch.setattr(tdv, "_info_of", lambda s: ("測試業", "測試股"))
    monkeypatch.setattr(tdv, "build_expert_prompt", lambda role, sym, data: f"prompt-{role}")
    monkeypatch.setattr(tdv, "_consensus_for", lambda a, meta=None: None)
    monkeypatch.setattr(tdv, "ask_role", fake_ask)
    monkeypatch.setattr("src.analysis.value_profile.value_profile_text", lambda db, s: "")
    tdv._MACRO_CACHE.clear()
    monkeypatch.delenv("TEAM_RULE_ROLES", raising=False)
    return asked


def test_the_pipeline_asks_the_llm_only_for_the_three_remaining_roles_and_still_stores_six_reports(pipeline):
    result = tdv.analyze_symbol("2006", quick=False)

    assert sorted(pipeline) == sorted(["macro-analyst", "technical-analyst", "fundamental-analyst", "investment-advisor"])
    assert set(result["reports"]) == set(ROLES)
    assert "風險等級：中風險" in result["reports"]["risk-manager"] and "籌碼訊號" in result["reports"]["chip-analyst"]
    assert {result["models"][r] for r in ("value-analyst", "risk-manager", "chip-analyst")} == {"rule-based@local"}


def test_restoring_the_environment_sends_all_six_roles_back_to_the_llm(pipeline, monkeypatch):
    monkeypatch.setenv("TEAM_RULE_ROLES", "")

    tdv.analyze_symbol("2006", quick=False)

    assert {"value-analyst", "risk-manager", "chip-analyst"} <= set(pipeline)


def test_the_failure_rate_counts_only_roles_that_actually_call_the_llm(monkeypatch, capsys):
    monkeypatch.delenv("TEAM_RULE_ROLES", raising=False)
    monkeypatch.setattr(tdv, "_ROLE_FAIL", {"stocks": 1, "roles": 1, "total_stocks": 10})

    tdv.report_role_failures(alert=False)

    assert "1/30 份報告失敗" in capsys.readouterr().out


def test_prompts_are_not_built_for_roles_that_never_reach_the_llm(pipeline, monkeypatch):
    built = []
    monkeypatch.setattr(tdv, "build_expert_prompt", lambda role, sym, data: built.append(role) or f"prompt-{role}")

    tdv.analyze_symbol("2006", quick=True)

    assert not {"value-analyst", "risk-manager", "chip-analyst"} & set(built) and "fundamental-analyst" in built


VALUATION = {
    "current_price": 422.0,
    "dcf": {"fair_value": 180.5, "upside_pct": -57.2},
    "ddm": {"fair_value": 90.1, "upside_pct": -78.6},
    "pe_band": {"fair_value": 300.0, "upside_pct": -28.9, "zone": "偏高區", "current_pe": 27.9, "pe_percentile": 66.7},
    "composite": {"fair_value": 216.99, "upside_pct": -48.6, "verdict": "嚴重高估", "models_used": 3},
}


def test_the_value_report_opens_with_the_computed_verdict_and_cites_the_program_numbers():
    text = rule_roles.value_report({"valuation": VALUATION}, "")

    assert text.splitlines()[0].startswith("嚴重高估（現價422.0元、綜合合理價216.99元，安全邊際-48.6%；採用3個模型）")
    assert "DCF 合理價180.5元（-57.2%）" in text and "PE Band 合理價300.0元（-28.9%，偏高區、本益比27.9、歷史百分位66.7%）" in text
    assert cited(text) == {"current_price": "422.0", "composite_fair_value": "216.99", "dcf_fair_value": "180.5",
                           "ddm_fair_value": "90.1", "pe_band_fair_value": "300.0"}


def test_the_value_report_adds_the_four_dimension_profile_only_when_there_is_one():
    assert "四維畫像" not in rule_roles.value_report({"valuation": VALUATION}, "")
    assert "四維畫像：財務:ROIC26.5%" in rule_roles.value_report({"valuation": VALUATION}, "財務:ROIC26.5%")


@pytest.mark.parametrize("data", [{}, {"valuation": {"current_price": 10.0}}, {"valuation": {"composite": {"fair_value": 5.0}}}])
def test_the_value_report_says_the_data_is_missing_instead_of_inventing_a_price(data):
    text = rule_roles.value_report(data, "")

    assert "資料不足" in text and "分析失敗" not in text


def test_a_missing_model_shows_blanks_instead_of_none():
    val = {"current_price": 10.0, "composite": {"fair_value": 8.0}, "dcf": {"fair_value": 8.0}}

    text = rule_roles.value_report({"valuation": val}, "")

    assert "None" not in text and "DDM 合理價無資料元" in text and "ddm_fair_value" not in text


def test_value_analyst_is_a_rule_role_by_default_and_can_go_back_to_the_llm_alone(monkeypatch):
    monkeypatch.delenv("TEAM_RULE_ROLES", raising=False)
    assert "value-analyst" in rule_roles.active(ROLES)

    monkeypatch.setenv("TEAM_RULE_ROLES", "risk-manager,chip-analyst")
    assert rule_roles.active(ROLES) == ["risk-manager", "chip-analyst"]


def test_by_default_the_value_report_is_the_template_with_the_profile_and_no_llm_call(pipeline, monkeypatch):
    monkeypatch.setitem(DATA, "valuation", {**VALUATION})
    monkeypatch.setattr("src.analysis.value_profile.value_profile_text", lambda db, s: "財務:ROIC26.5%")

    result = tdv.analyze_symbol("2006", quick=False)

    assert "value-analyst" not in pipeline and set(result["reports"]) == set(ROLES)
    assert result["reports"]["value-analyst"].startswith("嚴重高估") and "四維畫像：財務:ROIC26.5%" in result["reports"]["value-analyst"]
    assert result["models"]["value-analyst"] == "rule-based@local"


def test_the_llm_value_prompt_still_gets_the_profile_and_skips_it_when_the_data_is_insufficient(pipeline, monkeypatch):
    monkeypatch.setenv("TEAM_RULE_ROLES", "risk-manager,chip-analyst")
    seen = {}
    monkeypatch.setattr(tdv, "build_expert_prompt", lambda role, sym, data: f"prompt-{role}")
    monkeypatch.setattr(tdv, "ask_role", lambda role, prompt, include_role_prompt=True, timeout=300: seen.setdefault(role, prompt) and
                        {"role": role, "model": "fake", "response": "x\\n📌引用數值：a=1", "elapsed_sec": 0.0})

    monkeypatch.setattr("src.analysis.value_profile.value_profile_text", lambda db, s: "財務:ROIC26.5%")
    tdv.analyze_symbol("2006", quick=True)
    assert "【四維價值畫像】財務:ROIC26.5%" in seen["value-analyst"]

    seen.clear()
    monkeypatch.setattr("src.analysis.value_profile.value_profile_text", lambda db, s: "四維價值資料不足")
    tdv.analyze_symbol("2006", quick=True)
    assert "四維價值畫像" not in seen["value-analyst"]


def test_a_failing_profile_lookup_never_breaks_the_analysis(pipeline, monkeypatch):
    def boom(db, symbol):
        raise RuntimeError("mongo down")

    monkeypatch.setitem(DATA, "valuation", {**VALUATION})
    monkeypatch.setattr("src.analysis.value_profile.value_profile_text", boom)

    result = tdv.analyze_symbol("2006", quick=False)

    assert result["reports"]["value-analyst"].startswith("嚴重高估") and "四維畫像" not in result["reports"]["value-analyst"]


LOSS_MAKER = {
    "current_price": 26.8,
    "dcf": {"fair_value": None, "reason": "淨利為負，DCF 不適用"},
    "ddm": {"fair_value": None, "reason": "最近一年無股利"},
    "pe_band": {"fair_value": None, "reason": "EPS 不足"},
    "composite": {"fair_value": None, "upside_pct": None, "verdict": "無法判定", "models_used": 0},
}


def test_without_a_usable_fair_price_the_value_report_says_why_each_model_does_not_apply():
    text = rule_roles.value_report({"valuation": LOSS_MAKER}, "")

    assert text.splitlines()[0] == "無法判定（現價26.8元，沒有可用的合理價）"
    assert "DCF：淨利為負，DCF 不適用；DDM：最近一年無股利；PE Band：EPS 不足" in text
    assert cited(text) == {"current_price": "26.8"} and "資料不足" not in text


def test_only_the_models_that_wrote_a_reason_are_listed():
    val = {**LOSS_MAKER, "dcf": None, "pe_band": {"fair_value": None}}

    assert rule_roles.value_report({"valuation": val}, "").splitlines()[1] == "DDM：最近一年無股利"


@pytest.mark.parametrize("val", [{**LOSS_MAKER, "current_price": None},
                                 {"current_price": 26.8, "composite": LOSS_MAKER["composite"]},
                                 {"current_price": 26.8, "dcf": {"fair_value": None}, "composite": {"fair_value": None}}])
def test_without_a_price_or_without_any_reason_it_still_says_the_data_is_insufficient(val):
    assert rule_roles.value_report({"valuation": val}, "") == "估值資料不足，無法推估合理價。"


def test_a_missing_verdict_still_opens_with_the_word_for_undetermined():
    val = {**LOSS_MAKER, "composite": {"fair_value": None}}

    assert rule_roles.value_report({"valuation": val}, "").startswith("無法判定（現價26.8元")


ATR = {"period": 20, "n": 2.4, "n_pct": 2.6, "stop_2n": 87.4, "add_step": 1.2, "risk_pct": 1.0, "position_pct": 19.2}


def test_the_risk_report_adds_atr_lines_and_citations_when_atr_is_available():
    text = rule_roles.risk_report({**DATA, "risk": {**DATA["risk"], "atr": ATR}}, HINT)

    assert "ATR 停損：87.4元（現價 − 2×N；N=2.4元，約股價的2.6%" in text
    assert "部位約占資金 19.2%" in text and "取此數與上列單檔上限中較小者" in text
    assert cited(text)["atr_n"] == "2.4" and cited(text)["atr_stop_2n"] == "87.4" and cited(text)["atr_position_pct"] == "19.2"
    assert "停損價：89.63元" in text  # 原有的 VaR 停損行不受影響


def test_the_risk_report_is_unchanged_without_atr():
    assert "ATR" not in rule_roles.risk_report(DATA, HINT)
    assert "ATR" not in rule_roles.risk_report({**DATA, "risk": {**DATA["risk"], "atr": None}}, HINT)


def test_the_risk_report_says_data_insufficient_when_the_atr_stop_is_missing():
    text = rule_roles.risk_report({**DATA, "risk": {**DATA["risk"], "atr": {**ATR, "stop_2n": None}}}, HINT)

    assert "ATR 停損：資料不足" in text and "None" not in text and "atr_stop_2n" not in text
