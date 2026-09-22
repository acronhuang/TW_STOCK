"""集合名稱常數測試 —— Phase 2 資料層收斂。"""
import pytest

from src.domain import collections as c


@pytest.mark.unit
def test_no_duplicate_collection_values():
    """兩個常數不得指向同一集合名（避免重複定義）。"""
    values = list(c.all_collections().values())
    dupes = {v for v in values if values.count(v) > 1}
    assert not dupes, f"重複集合名: {dupes}"


@pytest.mark.unit
def test_collection_names_are_valid_identifiers():
    """集合名為非空小寫底線字串（無空白/大寫/前後底線異常）。"""
    import re
    for name, value in c.all_collections().items():
        assert value, f"{name} 為空"
        assert re.fullmatch(r"[a-z][a-z0-9_]*", value), f"{name}={value!r} 命名不合規"


@pytest.mark.unit
def test_core_collections_present():
    """核心高頻集合必須存在且值正確。"""
    assert c.COLL_STOCK_PRICE == "stock_price"
    assert c.COLL_STOCK_FACTORS == "stock_factors"
    assert c.COLL_FINANCIAL_REPORTS == "financial_reports"
    assert c.COLL_TAIWAN_STOCK_INFO == "taiwan_stock_info"


@pytest.mark.unit
def test_all_collections_count_reasonable():
    """常數數量在合理範圍（防止誤刪/漏補）。"""
    assert len(c.all_collections()) >= 50
