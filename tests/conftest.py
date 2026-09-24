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


def pytest_configure(config):
    # 需已灌入市場資料的整合測試；DB 無種子資料（canary 2330）時自動略過。
    config.addinivalue_line(
        "markers",
        "needs_data: 需要已灌入市場資料的整合測試；無種子資料時自動略過（phase A 種子後執行）",
    )
    # 正式庫健康檢查（斷言 10 萬+ 筆、5 天新鮮度等），只對 live DB 有意義，CI 不跑。
    config.addinivalue_line(
        "markers",
        "prod_data: 正式庫規模/新鮮度健康檢查；僅對 live 資料庫有意義，CI 以 '-m not prod_data' 排除",
    )


@pytest.fixture(scope="session")
def _seed_present():
    """canary：DB 是否已灌入最小種子資料（stock_price 有 2330）。

    只在被 needs_data 守衛請求時才建立連線（短逾時），純 unit 測試不觸發任何 Mongo 連線。
    """
    from pymongo import MongoClient
    from pymongo.errors import PyMongoError
    uri = os.getenv('MONGODB_URI', 'mongodb://localhost:27017')
    db_name = os.getenv('MONGODB_DATABASE', 'tw_stock_analysis')
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=1500)
        present = client[db_name]['stock_price'].count_documents({'symbol': '2330'}, limit=1) > 0
        client.close()
        return present
    except PyMongoError:
        return False


@pytest.fixture(autouse=True)
def _guard_needs_data(request):
    """標 needs_data 的測試在『無種子資料』時自動 skip（懶查 canary，不污染 unit 測試）。"""
    if request.node.get_closest_marker('needs_data'):
        if not request.getfixturevalue('_seed_present'):
            pytest.skip('無種子資料（canary 2330 缺）；灌入種子後自動執行（見 scripts/seed_test_data.py）')


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
