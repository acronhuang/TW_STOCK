"""
pytest 共用 fixtures
"""
import os
import sys
import pytest
from pathlib import Path
from dotenv import load_dotenv

# 專案根目錄
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / '.env')


@pytest.fixture(scope="session")
def db():
    """MongoDB 連線（整個測試 session 共用）"""
    from pymongo import MongoClient
    uri = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/tw_stock_analysis')
    client = MongoClient(uri)
    database = client['tw_stock_analysis']
    yield database
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
