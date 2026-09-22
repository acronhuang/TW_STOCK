"""EvidenceGuard：驗證國際新聞 LLM 輸出確實受外部證據約束。

對應 Phase 0-S。緩解「LLM 逸出證據」(可行性報告最沒把握第 1 項) 與 CWE-77/94。
守門契約：每個實質段落須含 [n] 引用；引用編號不得超出證據數；
偵測未列於證據的台股代號 → flagged。
"""
import pytest

from src.analysis.evidence_guard import guard_analysis, extract_citations


@pytest.mark.unit
def test_extract_citations_parses_indices():
    assert extract_citations("受影響 [1]，另見 [3]。") == [1, 3]
    assert extract_citations("沒有引用。") == []


@pytest.mark.unit
def test_clean_output_passes():
    text = (
        "可能影響：Fed 升息壓抑資金 [1]。\n"
        "受影響產業：半導體 [1]。\n"
        "台股關聯標的：資料不足，新聞證據未明示台股標的。\n"
        "風險與不確定性：新聞僅為標題，無法確認完整內容、時效性和因果關係 [1]。"
    )
    result = guard_analysis(text, n_sources=1)
    assert result["flagged"] is False
    assert result["reasons"] == []


@pytest.mark.unit
def test_citation_out_of_range_is_flagged():
    text = "可能影響：升息 [1]。\n風險：標題有限 [5]。"
    result = guard_analysis(text, n_sources=2)
    assert result["flagged"] is True
    assert any("超出證據範圍" in r for r in result["reasons"])


@pytest.mark.unit
def test_paragraph_without_citation_is_flagged():
    text = "可能影響：升息壓抑股市。\n風險：標題有限 [1]。"
    result = guard_analysis(text, n_sources=1)
    assert result["flagged"] is True
    assert any("缺少引用" in r for r in result["reasons"])


@pytest.mark.unit
def test_taiwan_stock_symbol_not_in_evidence_is_flagged():
    """輸出提到台股代號但證據未提及 → 疑似逸出證據。"""
    text = "台股關聯標的：台積電 2330 受惠 [1]。"
    result = guard_analysis(text, n_sources=1, evidence_text="Fed signals higher rates")
    assert result["flagged"] is True
    assert any("2330" in r for r in result["reasons"])


@pytest.mark.unit
def test_taiwan_symbol_present_in_evidence_is_ok():
    text = "台股關聯標的：台積電 2330 受惠 [1]。"
    result = guard_analysis(text, n_sources=1, evidence_text="TSMC 2330 raises capex")
    assert result["flagged"] is False


@pytest.mark.unit
def test_empty_output_is_flagged():
    result = guard_analysis("", n_sources=1)
    assert result["flagged"] is True
