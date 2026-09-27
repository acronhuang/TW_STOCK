"""TDD:v5 影子 runner — 趨勢市買進重跑寫 advisor_v5_rating;盤整略過;不動 live。
LLM 與 regime 皆注入(mongomock,免真 LLM)→ @unit。"""
import pytest
mongomock = pytest.importorskip("mongomock")
from scripts.buyside_shadow_advisor_v5 import run, extract_rating, advisor_base_prompt


@pytest.mark.unit
def test_extract_rating():
    assert extract_rating("<think>xxx</think>評級：觀望\n理由...") == "觀望"
    assert extract_rating("評級：買進") == "買進"
    assert extract_rating("無法判定") is None


@pytest.mark.unit
def test_base_prompt_has_all_roles():
    p = advisor_base_prompt("2330", {"technical-analyst": "多頭上漲"})
    for lbl in ("總經", "基本面", "估值", "技術", "籌碼", "風險"):
        assert lbl in p


@pytest.mark.unit
def test_runner_trending_writes_shadow_sideways_skipped():
    db = mongomock.MongoClient()["tw_stock_analysis"]
    db["team_analysis"].insert_many([
        {"symbol": "T", "date": "2026-08-01", "final_verdict": "買進",
         "reports": {"technical-analyst": "上升趨勢"}, "consensus": {"final": "買進"}},
        {"symbol": "S", "date": "2026-08-15", "final_verdict": "買進",
         "reports": {"technical-analyst": "上升趨勢"}, "consensus": {"final": "買進"}},
    ])
    regime_fn = lambda dt: "多頭" if str(dt)[:10] == "2026-08-01" else "盤整"
    ask_fn = lambda prompt: "評級：觀望\n追高防制:缺估值佐證"
    res = run(db, ask_fn=ask_fn, regime_fn=regime_fn)
    assert res["n"] == 1 and res["flipped"] == 1 and res["skipped_sideways"] == 1
    t = db["team_analysis"].find_one({"symbol": "T"})
    assert t["advisor_v5_rating"] == "觀望" and t["advisor_v5_regime"] == "多頭"
    assert t["final_verdict"] == "買進"                 # live 位元不變
    s = db["team_analysis"].find_one({"symbol": "S"})
    assert "advisor_v5_rating" not in s                 # 盤整未被處理
