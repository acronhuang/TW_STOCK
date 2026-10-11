"""TDD: 沒有任何有效票也沒有可用顧問草案時，不得把退回的預設「持有」寫成合議結論。"""

import pytest

from src.moe.guard import is_failed_report
from src.moe.team_store import _final_verdict

pytestmark = pytest.mark.unit


def test_zero_valid_votes_and_no_usable_advisor_is_no_verdict():
    analysis = {
        "advisor": "整合略過：角色報告全數為錯誤訊息，不以此做決策",
        "consensus": {"votes": [{"model": "m", "vote": None}], "tally": {"買進": 0, "持有": 0, "賣出": 0},
                      "final": "持有", "n": 0},
    }

    assert _final_verdict(analysis) is None


def test_a_real_committee_result_is_kept():
    analysis = {"advisor": "評級：買進", "consensus": {"final": "賣出", "n": 3}}

    assert _final_verdict(analysis) == "賣出"


def test_zero_votes_still_use_a_real_advisor_rating():
    analysis = {"advisor": "評級：賣出\n理由…", "consensus": {"final": "賣出", "n": 0}}

    assert _final_verdict(analysis) == "賣出"


def test_legacy_consensus_without_a_vote_count_is_still_trusted():
    assert _final_verdict({"advisor": None, "consensus": {"final": "買進"}}) == "買進"


def test_no_consensus_and_no_rating_is_none():
    assert _final_verdict({"advisor": "沒有標籤", "consensus": None}) is None


def test_the_skipped_integration_message_counts_as_a_failed_report():
    assert is_failed_report("整合略過：角色報告全數為錯誤訊息，不以此做決策") is True
    assert is_failed_report("評級：買進") is False
