"""verdict A/B 前瞻框架測試 —— 趨勢判定 / 動能閘門(規則) / Ollama vs 規則 差異比對。"""
import pytest

from src.audit.ab_verdict import (apply_momentum_gate, compare_verdict_sets,
                                  ollama_momentum_verdict, trend_signal)


@pytest.mark.unit
def test_trend_signal():
    assert trend_signal(110, 105, 100) == "up"      # 價 > MA20 > MA60
    assert trend_signal(90, 95, 100) == "down"      # 價 < MA20 < MA60
    assert trend_signal(102, 100, 103) == "neutral"


@pytest.mark.unit
def test_momentum_gate_blocks_contrarian_buy():
    # 買進但非上升趨勢 → 降為持有（排除逆勢買）
    assert apply_momentum_gate("買進", "down") == "持有"
    assert apply_momentum_gate("買進", "neutral") == "持有"
    # 買進 + 上升趨勢 → 保留
    assert apply_momentum_gate("買進", "up") == "買進"
    # 賣出/持有不受買進閘門影響
    assert apply_momentum_gate("賣出", "up") == "賣出"
    assert apply_momentum_gate("持有", "down") == "持有"


@pytest.mark.unit
def test_compare_verdict_sets_agreement_and_divergence():
    base = {"2330": "買進", "2317": "買進", "2454": "賣出", "1101": "持有"}
    variant = {"2330": "買進", "2317": "持有", "2454": "賣出", "1101": "買進"}
    r = compare_verdict_sets(base, variant)
    assert r["n"] == 4
    assert r["agreement_rate"] == pytest.approx(0.5)   # 2330, 2454 一致
    assert set(r["changed"]) == {"2317", "1101"}
    assert r["matrix"][("買進", "持有")] == 1           # 2317
    assert r["matrix"][("持有", "買進")] == 1           # 1101


@pytest.mark.unit
def test_compare_ignores_symbols_not_in_both():
    r = compare_verdict_sets({"a": "買進", "b": "賣出"}, {"a": "買進"})
    assert r["n"] == 1 and r["agreement_rate"] == 1.0


@pytest.mark.unit
def test_ollama_momentum_verdict_uses_injected_ask_role():
    """Ollama 臂：以注入的 ask_role_fn 取得分析，解析出票別（可 mock，不真連）。"""
    calls = {}

    def fake_ask(role, question, **kw):
        calls["role"] = role
        calls["q"] = question
        return {"response": "第一行：持有\n理由：趨勢轉弱，暫觀望。"}

    v = ollama_momentum_verdict("2330", base_verdict="買進",
                                indicators={"price": 100, "ma20": 105, "ma60": 110},
                                ask_role_fn=fake_ask)
    assert v == "持有"
    assert calls["role"] == "technical-analyst"
    assert "2330" in calls["q"] and "買進" in calls["q"]


@pytest.mark.unit
def test_ollama_verdict_failonly_returns_none():
    def fail_ask(role, question, **kw):
        return {"error": "connection refused"}
    assert ollama_momentum_verdict("2330", "買進", {}, ask_role_fn=fail_ask) is None
