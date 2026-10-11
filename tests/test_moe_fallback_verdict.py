"""TDD: 辨識「Ollama 全失敗後被寫成結論的預設持有」。"""

import pytest

from src.moe.retry import is_fallback_verdict

pytestmark = pytest.mark.unit

SKIP = "整合略過：角色報告全數為錯誤訊息，不以此做決策"


def fallback_doc(**overrides):
    doc = {"final_verdict": "持有", "advisor": SKIP,
           "consensus": {"votes": [{"vote": None}, {"vote": None}], "n": 0, "final": "持有"}}
    return doc | overrides


def test_a_hold_from_zero_votes_and_a_skipped_advisor_is_a_fallback():
    assert is_fallback_verdict(fallback_doc()) is True


def test_a_real_vote_result_is_not_a_fallback():
    assert is_fallback_verdict(fallback_doc(advisor="評級：買進", consensus={"votes": [{"vote": "買進"}], "n": 3, "final": "買進"})) is False


def test_zero_votes_with_a_real_advisor_rating_is_not_a_fallback():
    assert is_fallback_verdict(fallback_doc(advisor="評級：賣出\n理由", final_verdict="賣出")) is False


def test_a_document_without_a_verdict_has_nothing_to_clear():
    assert is_fallback_verdict(fallback_doc(final_verdict=None)) is False


def test_legacy_consensus_without_votes_info_is_left_alone():
    assert is_fallback_verdict({"final_verdict": "買進", "advisor": SKIP, "consensus": {"final": "買進"}}) is False
