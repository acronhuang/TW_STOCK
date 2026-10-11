"""TDD: 重複失敗告警的節流（連續失敗才告警、狀態不因單次成功而重置）。"""

from datetime import datetime, timedelta

import pytest

from src.ops import alert_throttle

pytestmark = pytest.mark.unit

T0 = datetime(2026, 10, 11, 9, 5)


def hour(n):
    return T0 + timedelta(hours=n)


def run(failures_by_hour):
    """依序餵入每小時的失敗類別，回傳每小時是否告警。"""
    state, alerts = {}, []
    for index, failed in enumerate(failures_by_hour):
        send, state, persistent = alert_throttle.decide(state, failed, hour(index))
        alerts.append((send, persistent))
    return alerts


def test_a_one_off_failure_never_alerts():
    assert [a[0] for a in run([["基本面"], [], [], []])] == [False, False, False, False]


def test_alerts_only_after_the_third_consecutive_failed_run():
    assert [a[0] for a in run([["基本面"]] * 4)] == [False, False, True, False]


def test_a_flapping_combination_does_not_alert_until_each_category_persists():
    alerts = run([["技術面"], ["技術面", "基本面"], ["基本面"], ["技術面"], ["基本面"]])

    assert not any(send for send, _ in alerts)


def test_a_single_success_in_between_resets_the_consecutive_count():
    assert not any(a[0] for a in run([["基本面"], ["基本面"], [], ["基本面"], ["基本面"]]))


def test_a_new_persistent_category_alerts_immediately_with_the_full_persistent_set():
    alerts = run([["基本面"]] * 3 + [["基本面", "技術面"]] * 3)

    assert alerts[2] == (True, ["基本面"])
    assert alerts[3][0] is False
    assert alerts[5] == (True, ["基本面", "技術面"])


def test_the_same_persistent_set_repeats_only_after_the_repeat_interval():
    state, sent_at = {}, []
    for h in range(0, 60):
        send, state, _ = alert_throttle.decide(state, ["基本面"], hour(h))
        if send:
            sent_at.append(h)

    assert sent_at == [2, 26, 50]


def test_recovery_clears_the_signature_so_a_later_relapse_alerts_again():
    alerts = run([["基本面"]] * 3 + [[]] * 3 + [["基本面"]] * 3)

    assert [i for i, (send, _) in enumerate(alerts) if send] == [2, 8]


def test_state_survives_a_json_round_trip():
    import json

    state = {}
    for h in range(2):
        _, state, _ = alert_throttle.decide(state, ["基本面"], hour(h))
    state = json.loads(json.dumps(state, default=alert_throttle.encode))

    send, _, persistent = alert_throttle.decide(state, ["基本面"], hour(2))

    assert send is True and persistent == ["基本面"]
