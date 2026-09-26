"""E2E 臨時 harness:只渲染買方改良對照頁(避開全 app 依賴)。供 Playwright 實跑截圖。
   streamlit run dashboard/_e2e_buyside_harness.py --server.headless true --server.port 8501
"""
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dashboard.pages import buyside_compare  # noqa: E402

buyside_compare.show()
