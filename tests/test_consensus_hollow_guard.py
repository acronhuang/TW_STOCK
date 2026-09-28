"""TDD:P1 合議壞票守門(旗標)。預設關 → live 不變;開 → 剔壞票。@unit。"""
import importlib
import pytest

from src.moe import consensus as C


@pytest.mark.unit
def test_flag_off_bit_identical(monkeypatch):
    monkeypatch.delenv("CONSENSUS_DROP_HOLLOW", raising=False)
    votes = [
        {"model": "gemma2:9b", "vote": "買進", "reason": "雙重底、獲利強、估值低。"},
        {"model": "llama3.1:8b", "vote": "賣出", "reason": "我是投資決策委員會的成員，投下了以下票數："},
        {"model": "qwen2.5-14b:latest", "vote": "持有", "reason": "偏多但估值略高,續抱觀察。"},
    ]
    # 旗標關:壞票照計 → tally 買1持1賣1,平手回退草案(買進)
    assert C._active_votes(votes) == votes
    final, tally, n = C._finalize(votes, "評級：買進")
    assert tally == {"買進": 1, "持有": 1, "賣出": 1} and n == 3


@pytest.mark.unit
def test_flag_on_drops_hollow(monkeypatch):
    monkeypatch.setenv("CONSENSUS_DROP_HOLLOW", "1")
    votes = [
        {"model": "gemma2:9b", "vote": "買進", "reason": "雙重底、獲利強、估值低。"},
        {"model": "llama3.1:8b", "vote": "賣出", "reason": "我是投資決策委員會的成員，投下了以下票數："},
        {"model": "qwen2.5-14b:latest", "vote": "持有", "reason": "偏多但估值略高,續抱觀察。"},
    ]
    # 旗標開:llama3.1 壞票剔除 → 買1持1(無賣) → 平手回退草案(買進)
    kept = C._active_votes(votes)
    assert len(kept) == 2 and all("llama3.1" not in v["model"] for v in kept)
    final, tally, n = C._finalize(votes, "評級：買進")
    assert tally == {"買進": 1, "持有": 1, "賣出": 0} and n == 2


@pytest.mark.unit
def test_flag_on_all_hollow_keeps_original(monkeypatch):
    monkeypatch.setenv("CONSENSUS_DROP_HOLLOW", "1")
    votes = [
        {"model": "a", "vote": "買進", "reason": "投下了以下票數："},
        {"model": "b", "vote": "買進", "reason": "短"},
    ]
    # 全壞票 → 不可剔光,保留原票(不毀訊號)
    assert C._active_votes(votes) == votes


@pytest.mark.unit
def test_is_hollow_reason():
    assert C.is_hollow_reason("投下了以下票數：") is True
    assert C.is_hollow_reason("我是投資決策委員會的成員，我獨立判斷後投下了以下票數：") is True
    assert C.is_hollow_reason("短") is True                    # < 10 字
    assert C.is_hollow_reason("技術面雙重底成型、估值低估、籌碼積極。") is False
