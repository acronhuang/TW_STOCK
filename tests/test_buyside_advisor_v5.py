"""TDD:v5 advisor prompt 包裝 — 趨勢市注入追高防制,盤整不動。純函式 → @unit。"""
import pytest
from src.analysis.buyside.advisor_v5 import build_advisor_prompt_v5, ANTI_CHASE_CLAUSE

BASE = "你是投資顧問，整合以下 6 份報告，給 2330 最終建議：..."


@pytest.mark.unit
def test_trending_injects_anti_chase():
    for reg in ("多頭", "空頭"):
        out = build_advisor_prompt_v5(BASE, reg)
        assert "追高防制" in out and ANTI_CHASE_CLAUSE in out
        assert out.startswith(BASE)          # 保留原 prompt,只附加


@pytest.mark.unit
def test_sideways_and_none_unchanged():
    assert build_advisor_prompt_v5(BASE, "盤整") == BASE     # 盤整維持(已達標)
    assert build_advisor_prompt_v5(BASE, None) == BASE       # 未知市況不動
