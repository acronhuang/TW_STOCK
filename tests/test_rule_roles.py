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


def test_by_default_risk_and_chip_are_rule_roles_in_pipeline_order(monkeypatch):
    monkeypatch.delenv("TEAM_RULE_ROLES", raising=False)

    assert rule_roles.active(ROLES) == ["risk-manager", "chip-analyst"]


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


def test_the_pipeline_asks_the_llm_only_for_the_four_remaining_roles_and_still_stores_six_reports(pipeline):
    result = tdv.analyze_symbol("2006", quick=False)

    assert sorted(pipeline) == sorted(["macro-analyst", "technical-analyst", "fundamental-analyst", "value-analyst", "investment-advisor"])
    assert set(result["reports"]) == set(ROLES)
    assert "風險等級：中風險" in result["reports"]["risk-manager"] and "籌碼訊號" in result["reports"]["chip-analyst"]
    assert result["models"]["risk-manager"] == "rule-based@local" and result["models"]["chip-analyst"] == "rule-based@local"


def test_restoring_the_environment_sends_all_six_roles_back_to_the_llm(pipeline, monkeypatch):
    monkeypatch.setenv("TEAM_RULE_ROLES", "")

    tdv.analyze_symbol("2006", quick=False)

    assert {"risk-manager", "chip-analyst"} <= set(pipeline)


def test_the_failure_rate_counts_only_roles_that_actually_call_the_llm(monkeypatch, capsys):
    monkeypatch.delenv("TEAM_RULE_ROLES", raising=False)
    monkeypatch.setattr(tdv, "_ROLE_FAIL", {"stocks": 1, "roles": 1, "total_stocks": 10})

    tdv.report_role_failures(alert=False)

    assert "1/40 份報告失敗" in capsys.readouterr().out


def test_prompts_are_not_built_for_roles_that_never_reach_the_llm(pipeline, monkeypatch):
    built = []
    monkeypatch.setattr(tdv, "build_expert_prompt", lambda role, sym, data: built.append(role) or f"prompt-{role}")

    tdv.analyze_symbol("2006", quick=True)

    assert "risk-manager" not in built and "chip-analyst" not in built and "fundamental-analyst" in built
