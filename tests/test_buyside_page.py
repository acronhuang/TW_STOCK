"""TDD:M5 買方對照頁渲染(fake streamlit + mongomock)→ @unit。
證明頁面邏輯不需瀏覽器即可驗:空資料→st.info;有資料→metric/dataframe + 對照。
"""
import sys
import types
from unittest.mock import MagicMock

import pytest

mongomock = pytest.importorskip("mongomock")


def _fake_streamlit():
    st = types.ModuleType("streamlit")
    for name in ("header", "subheader", "caption", "markdown", "info", "metric",
                 "dataframe", "line_chart"):
        setattr(st, name, MagicMock())
    st._cols_created = []
    def _columns(spec):
        cs = [MagicMock() for _ in range(spec if isinstance(spec, int) else len(spec))]
        st._cols_created.append(cs)
        return cs
    st.columns = _columns
    st.radio = MagicMock(return_value="v3.1 品質(buy_v3c)")
    return st


@pytest.mark.unit
def test_page_empty_data_shows_info(monkeypatch):
    st = _fake_streamlit(); sys.modules["streamlit"] = st
    import importlib
    import dashboard.pages.buyside_compare as page
    importlib.reload(page)
    db = mongomock.MongoClient()["tw_stock_analysis"]
    monkeypatch.setattr(page, "get_db", lambda *a, **k: db)
    page.show()
    assert st.info.called                      # 空 verdict_detail → st.info,不報錯
    assert not st.dataframe.called


@pytest.mark.unit
def test_page_with_data_renders_compare(monkeypatch):
    st = _fake_streamlit(); sys.modules["streamlit"] = st
    import importlib
    import dashboard.pages.buyside_compare as page
    importlib.reload(page)
    db = mongomock.MongoClient()["tw_stock_analysis"]
    db["verdict_detail"].insert_many([
        {"symbol": "A", "window": 20, "verdict": "買進", "hit": False, "excess": -0.05, "buy_v3c": "降級持有"},
        {"symbol": "B", "window": 20, "verdict": "買進", "hit": True, "excess": 0.04, "buy_v3c": "買進"},
    ])
    monkeypatch.setattr(page, "get_db", lambda *a, **k: db)
    page.show()
    assert st.dataframe.called                 # 有資料 → 渲染對照表
    metric_calls = sum(c.metric.call_count for cols in st._cols_created for c in cols)
    assert metric_calls >= 3                    # metric 渲於 columns 上
