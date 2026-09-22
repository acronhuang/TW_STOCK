"""RAG 頁「網路補充 / 國際新聞分析」端對端腳本 (Playwright)。

前置需求 (本機需可執行，非 CI 假設):
    pip install playwright pytest-playwright && playwright install chromium
    pip install -e ".[dashboard]"          # streamlit
    streamlit run dashboard/app.py --server.port 8501 --server.headless true &
    export E2E_BASE_URL=http://localhost:8501
    # 國際新聞分析需 RAG_OLLAMA_URL 可連線 (qwen2.5-14b)，否則該段落顯示失敗訊息，
    # E2E 仍驗證「UI 有回應且不整頁崩潰」(fail-open 契約)。

執行:
    pytest tests/e2e/test_rag_news_e2e.py --headed        # 觀察
    pytest tests/e2e/test_rag_news_e2e.py                 # headless + 截圖

截圖輸出: tests/e2e/screenshots/*.png (每個關鍵狀態一張，可重複回歸比對)
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page, expect  # noqa: E402

BASE_URL = os.getenv("E2E_BASE_URL", "http://localhost:8501")
SHOT_DIR = Path(__file__).parent / "screenshots"
SHOT_DIR.mkdir(exist_ok=True)


def _goto_rag(page: Page) -> None:
    page.goto(BASE_URL, wait_until="networkidle")
    # Streamlit 多頁：依側邊欄導到 RAG 頁 (依專案實際頁名調整)
    rag_nav = page.get_by_role("link", name="rag").or_(page.get_by_text("知識庫"))
    if rag_nav.count():
        rag_nav.first.click()
        page.wait_for_load_state("networkidle")


@pytest.mark.e2e
def test_local_rag_answer_renders(page: Page) -> None:
    """基準流程：輸入問題→本機檢索段落顯示，不依賴外部網路。"""
    _goto_rag(page)
    page.get_by_placeholder("例").fill("adj_close 還原價是否正確?")
    page.keyboard.press("Enter")
    expect(page.get_by_text("依據的段落")).to_be_visible(timeout=30_000)
    page.screenshot(path=str(SHOT_DIR / "01_local_answer.png"), full_page=True)


@pytest.mark.e2e
def test_web_supplement_section_appears_when_toggled(page: Page) -> None:
    """網路補充：開啟 toggle 且本機命中不足時，出現獨立『網路補充』區塊。"""
    _goto_rag(page)
    page.get_by_text("網路補充").click()
    page.get_by_placeholder("例").fill("台積電 CoWoS 最新擴產")
    page.keyboard.press("Enter")
    # fail-open：外部無結果也要有『網路補充』標題，不得整頁崩潰
    expect(page.get_by_text("網路補充")).to_be_visible(timeout=30_000)
    page.screenshot(path=str(SHOT_DIR / "02_web_supplement.png"), full_page=True)


@pytest.mark.e2e
def test_international_analysis_flow(page: Page) -> None:
    """國際新聞分析：選事件類型+來源→按鈕→出現分析與外部證據編號 [1]。"""
    _goto_rag(page)
    page.get_by_text("國際新聞分析").click()
    page.get_by_placeholder("例").fill("Fed 利率決策對台股科技股影響")
    page.get_by_role("button", name="分析外部新聞").click()
    expect(page.get_by_text("國際新聞分析")).to_be_visible(timeout=120_000)
    # 契約：不論 Ollama 是否可用，都要有『不是投資建議』免責與外部證據或失敗訊息
    expect(page.get_by_text("不是投資建議")).to_be_visible()
    page.screenshot(path=str(SHOT_DIR / "03_international_analysis.png"), full_page=True)


@pytest.mark.e2e
def test_empty_question_guard(page: Page) -> None:
    """空問題保護：開國際分析但未輸入問題→顯示提醒，不呼叫外部服務。"""
    _goto_rag(page)
    page.get_by_text("國際新聞分析").click()
    page.get_by_role("button", name="分析外部新聞").click()
    expect(page.get_by_text("請先輸入問題")).to_be_visible(timeout=15_000)
    page.screenshot(path=str(SHOT_DIR / "04_empty_guard.png"), full_page=True)
