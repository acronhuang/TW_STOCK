"""下載模組測試"""
import pytest
import os

# ADR-0011 分類（2026-08-16）：純解析邏輯
pytestmark = pytest.mark.unit


class TestFinMindClient:
    def test_client_init(self):
        from src.downloaders.finmind_client import FinMindClient
        token = os.getenv('FINMIND_API_TOKEN', 'test')
        client = FinMindClient(api_token=token)
        assert client is not None

    def test_table_config(self):
        from src.downloaders.table_config import DATA_TABLES
        assert isinstance(DATA_TABLES, dict)
        assert len(DATA_TABLES) > 0

    def test_get_all_tables(self):
        from src.downloaders.table_config import get_all_tables
        tables = get_all_tables()
        assert len(tables) > 0
