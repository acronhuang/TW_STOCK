"""API Server 端點測試"""
import pytest
import requests

API = 'http://localhost:8888'


def api_available():
    try:
        r = requests.get(f'{API}/api/health', timeout=3)
        return r.status_code == 200
    except Exception:
        return False


@pytest.mark.skipif(not api_available(), reason="API server not running")
class TestAPIEndpoints:

    def test_health(self):
        r = requests.get(f'{API}/api/health')
        assert r.status_code == 200
        data = r.json()
        assert data['status'] == 'ok'
        assert data['collections']['stock_price'] > 0

    def test_macro(self):
        r = requests.get(f'{API}/api/macro')
        assert r.status_code == 200
        data = r.json()
        assert 'signal' in data

    def test_factors(self):
        r = requests.get(f'{API}/api/factors/2330')
        assert r.status_code == 200

    def test_financial(self):
        r = requests.get(f'{API}/api/financial/2330')
        assert r.status_code == 200
        data = r.json()
        assert 'total_score' in data

    def test_valuation(self):
        r = requests.get(f'{API}/api/valuation/2330')
        assert r.status_code == 200
        data = r.json()
        assert 'composite' in data

    def test_risk(self):
        r = requests.get(f'{API}/api/risk/2330')
        assert r.status_code == 200

    def test_ranking(self):
        r = requests.get(f'{API}/api/ranking?limit=5')
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 5

    def test_scan(self):
        r = requests.get(f'{API}/api/scan?limit=5')
        assert r.status_code == 200

    def test_invalid_symbol(self):
        r = requests.get(f'{API}/api/factors/XXXX')
        assert r.status_code == 200
