"""國際新聞分析的外部證據約束測試。"""
import pytest

from src.analysis.international_news import SYSTEM, build_prompt


@pytest.mark.unit
def test_build_prompt_limits_analysis_to_external_evidence_and_selected_type():
    prompt = build_prompt(
        "Fed rate hike impact on Taiwan technology stocks",
        "貨幣政策／利率",
        [{
            "title": "Fed signals rates may stay higher for longer",
            "url": "https://example.com/fed",
            "published_at": "Thu, 04 Sep 2026 01:00:00 GMT",
            "source": "Google News RSS",
        }],
    )

    assert "事件類型:貨幣政策／利率" in prompt
    assert "[1] Google News RSS" in prompt
    assert "Fed signals rates may stay higher for longer" in prompt
    assert "只能依據提供的外部新聞證據" in prompt
    assert "可能影響、受影響產業、台股關聯標的、風險與不確定性" in prompt


@pytest.mark.unit
def test_system_requires_a_citation_for_title_only_risk_statement():
    assert "新聞僅為標題，無法確認完整內容、時效性和因果關係 [1]" in SYSTEM

@pytest.mark.unit
def test_build_prompt_truncates_overlong_user_input():
    """防提示注入/資源耗用：過長 question 被截斷。"""
    from src.analysis.international_news import MAX_QUESTION_LEN
    prompt = build_prompt("台股" * 5000, "科技供應鏈／AI", [
        {"title": "t", "url": "https://x/y", "published_at": "", "source": "s"}])
    # 問題段落不應無限膨脹
    assert len(prompt) < MAX_QUESTION_LEN + 3000


@pytest.mark.unit
def test_assert_allowed_host_blocks_ssrf():
    """SSRF (CWE-918)：非白名單主機被拒。"""
    from src.analysis.international_news import assert_allowed_host
    assert_allowed_host("http://172.16.9.27:11434")          # 白名單內不拋
    with pytest.raises(ValueError):
        assert_allowed_host("http://169.254.169.254/latest")  # 雲端 metadata 端點
    with pytest.raises(ValueError):
        assert_allowed_host("http://evil.example.com:11434")
