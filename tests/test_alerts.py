"""LINE 警報系統測試"""
import pytest
from unittest.mock import patch, MagicMock
from src.alerts.line_notifier import LineNotifier, AlertManager


class TestLineNotifier:
    @pytest.mark.unit
    def test_disabled_without_config(self):
        with patch.dict('os.environ', {}, clear=True):
            ln = LineNotifier()
            assert not ln.enabled

    @pytest.mark.unit
    def test_send_disabled_returns_false(self):
        ln = LineNotifier()
        ln._mode = 'disabled'
        assert ln.send('test') is False


class TestAlertManager:
    @pytest.mark.integration
    def test_add_and_list_rules(self, db):
        am = AlertManager()
        # 清除測試規則
        db.alert_rules.delete_many({'symbol': 'TEST9999'})

        am.add_price_alert('TEST9999', 'above', 100)
        rules = [r for r in am.list_rules() if r['symbol'] == 'TEST9999']
        assert len(rules) >= 1
        assert rules[0]['type'] == 'price'
        assert rules[0]['target_price'] == 100

        # 清理
        am.remove_rule('TEST9999')
        rules = [r for r in am.list_rules() if r['symbol'] == 'TEST9999']
        assert len(rules) == 0

    @pytest.mark.integration
    def test_check_and_notify_runs(self):
        am = AlertManager()
        triggered = am.check_and_notify()
        assert isinstance(triggered, list)
