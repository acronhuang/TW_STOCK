"""E2E(Playwright)— 買方改良對照 dashboard 頁重複腳本 + 截圖。

狀態:M5 頁面(dashboard/pages/buyside_compare.py)尚未實作 → 本 E2E 為「紅」規格,
待 M5 完成後轉綠。Playwright 未安裝 / 無 DASHBOARD_URL → 自動 skip(不擋套件)。

需要環境(執行步驟):
    pip install playwright && playwright install chromium
    # 對 .166 dashboard:本機開通道  ssh -L 8501:localhost:8501 mdsadmin@172.16.9.166
    DASHBOARD_URL=http://localhost:8501 pytest tests/test_e2e_buyside_dashboard.py -m prod_data

驗收(對應 docs/plans/verdict_buyside_v1.md M6):
    可重複執行、產出截圖檔、頁面含「買方改良對照」與兩條 v1/v2 趨勢。
"""
import os
import pathlib

import pytest

# Playwright 未裝 → 整檔 skip(保持 tier-gate/CI 乾淨)
pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402

# 需 live 執行中的 dashboard → prod_data(不進 CI 一般閘;由 .166/手動驗)
pytestmark = [pytest.mark.integration, pytest.mark.prod_data]

DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://localhost:8501")
SHOTS = pathlib.Path(__file__).parent / "_screenshots"
PAGE_LABEL = "📈 買方改良對照"   # M5 側邊欄選項(待建)


def _goto_page(page):
    page.goto(DASHBOARD_URL, wait_until="networkidle", timeout=30_000)
    # Streamlit 側邊欄 radio → 點選目標頁
    page.get_by_text(PAGE_LABEL, exact=False).first.click(timeout=15_000)
    page.wait_for_timeout(3_000)  # 等 rerun/websocket 渲染


def test_buyside_compare_renders_and_screenshot():
    if not os.getenv("DASHBOARD_URL"):
        pytest.skip("未設 DASHBOARD_URL(需執行中的 dashboard);見檔首說明")
    SHOTS.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        try:
            _goto_page(page)
            page.screenshot(path=str(SHOTS / "buyside_compare.png"), full_page=True)
            body = page.inner_text("body")
            # 斷言:標題 + v1/v2 對照關鍵字
            assert "買方改良對照" in body
            assert "v1" in body and "v2" in body
            assert ("命中" in body or "hit" in body.lower())
        finally:
            browser.close()
