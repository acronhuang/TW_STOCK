"""
pytest 共用 fixtures
"""
import os
import sys
from pathlib import Path

import pytest
from dotenv import load_dotenv

# 專案根目錄
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / '.env')


@pytest.fixture(scope="session")
def db():
    """MongoDB 「唯讀」連線（真實資料，session 共用）。

    DB 名由 MONGODB_DATABASE 決定（與 src/config.py 一致），預設 tw_stock_analysis。
    ⚠️ 此 fixture 僅供「讀取」驗證真實資料；任何需寫入的測試請改用 write_db，
    以免污染正式庫。
    """
    from pymongo import MongoClient
    uri = os.getenv('MONGODB_URI', 'mongodb://localhost:27017')
    db_name = os.getenv('MONGODB_DATABASE', 'tw_stock_analysis')
    client = MongoClient(uri)
    database = client[db_name]
    yield database
    client.close()


@pytest.fixture(scope="session")
def write_db():
    """需寫入的測試必用此 fixture：專用測試 DB，session 結束自動 drop，
    絕不碰正式 tw_stock_analysis。DB 名由 MONGODB_TEST_DATABASE 決定。
    """
    from pymongo import MongoClient
    uri = os.getenv('MONGODB_URI', 'mongodb://localhost:27017')
    db_name = os.getenv('MONGODB_TEST_DATABASE', 'tw_stock_analysis_pytest')
    assert db_name != os.getenv('MONGODB_DATABASE', 'tw_stock_analysis'), \
        '測試 DB 不得為正式庫'
    client = MongoClient(uri)
    database = client[db_name]
    yield database
    client.drop_database(db_name)  # 測試完自動清理
    client.close()


@pytest.fixture(scope="session")
def sample_symbols():
    """常用測試股票"""
    return ['2330', '2317', '2454', '0056', '2603']


@pytest.fixture(scope="session")
def sample_symbol():
    return '2330'


@pytest.fixture(scope="session")
def ranker():
    from src.analysis.stock_ranker import StockRanker
    return StockRanker()


@pytest.fixture(scope="session")
def valuation():
    from src.analysis.valuation_models import ValuationAnalyzer
    return ValuationAnalyzer()


@pytest.fixture(scope="session")
def risk():
    from src.analysis.risk_manager import RiskAnalyzer
    return RiskAnalyzer()


@pytest.fixture(scope="session")
def health():
    from src.analysis.financial_health import FinancialHealthAnalyzer
    return FinancialHealthAnalyzer()
