"""TDD: 持倉風控合議要把每位委員送到他實際所在的節點，不能一律送 .27（委員跨兩個節點）。"""

import pytest

from scripts import risk_deliberation
from src.moe import consensus

pytestmark = pytest.mark.unit


def test_each_committee_member_is_asked_on_the_node_that_serves_it(monkeypatch):
    asked = {}

    def fake_ask(model, prompt, timeout=120, url=None):
        asked[model] = url
        return "續抱\n趨勢未壞"

    monkeypatch.setattr(risk_deliberation, "_ask", fake_ask)

    risk_deliberation.deliberate("部位資料")

    assert set(asked) == set(consensus.COMMITTEE)
    assert asked == {m: consensus.COMMITTEE_MODEL_URL[m] for m in consensus.COMMITTEE}
    assert len(set(asked.values())) == 2, "委員應分布在 .27 與 .28 兩個節點"
