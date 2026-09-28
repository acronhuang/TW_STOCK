"""TDD:P2 影子一致性 lint。純函式 + mongomock,@unit。"""
import pytest
from src.analysis.buyside.verdict_lint import lint_verdict, run_lint

mongomock = pytest.importorskip("mongomock")


@pytest.mark.unit
def test_flags_2471_style_contradictions():
    doc = {
        "final_verdict": "買進",
        "price_at_analysis": 51.4,
        "advisor": "評級:買進\n張數:0 張\n進場價:54.5 元(頸線突破)",
        "reports": {"technical-analyst": "風報比=0.84 頸線=54.5 目標=62"},
        "consensus": {"votes": [
            {"model": "gemma2:9b", "vote": "買進", "reason": "雙重底成型、獲利強、估值低。"},
            {"model": "llama3.1:8b", "vote": "買進", "reason": "我是投資決策委員會的成員，我獨立判斷後投下了以下票數："},
        ]},
    }
    r = lint_verdict(doc)
    assert r["chase_entry"] is True          # 54.5 > 51.4
    assert r["buy_zero_shares"] is True       # 0 張
    assert r["bad_risk_reward"] is True       # 0.84 < 1
    assert r["hollow_votes"] == 1 and r["hollow_vote_models"] == ["llama3.1:8b"]
    assert r["score"] == 4                    # 四紅旗


@pytest.mark.unit
def test_clean_verdict_no_flags():
    doc = {
        "final_verdict": "買進",
        "price_at_analysis": 100.0,
        "advisor": "評級:買進\n張數:5 張\n進場價:98 元",
        "reports": {"technical-analyst": "風報比=2.3 目標明確"},
        "consensus": {"votes": [
            {"model": "qwen2.5-14b:latest", "vote": "買進", "reason": "技術與基本面俱佳,籌碼積極。"},
        ]},
    }
    r = lint_verdict(doc)
    assert r["score"] == 0 and r["flags"] == []


@pytest.mark.unit
def test_run_lint_writes_shadow_only():
    db = mongomock.MongoClient()["t"]
    db["team_analysis"].insert_one({
        "symbol": "2471", "final_verdict": "買進", "verdict": "買進",
        "price_at_analysis": 51.4,
        "advisor": "評級:買進\n張數:0 張\n進場價:54.5 元",
        "reports": {"technical-analyst": "風報比=0.84"},
        "consensus": {"votes": [{"model": "llama3.1:8b", "vote": "買進",
                                 "reason": "投下了以下票數："}], "final": "買進"},
    })
    agg = run_lint(db, dry_run=False)
    assert agg["n"] == 1 and agg["clean"] == 0
    d = db["team_analysis"].find_one({"symbol": "2471"})
    assert d["shadow_lint"]["score"] == 4      # 追高+0張+風報比<1+合議壞票
    # live 欄一字未動
    assert d["final_verdict"] == "買進" and d["verdict"] == "買進"
    assert d["consensus"]["final"] == "買進"
