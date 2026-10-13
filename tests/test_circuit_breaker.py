"""TDD: 斷路器——連續失敗到門檻就開啟、冷卻後只放一次探測、成功會清掉計數；MOPS 客戶端開啟後不再送請求。"""

import pytest

from scripts import mops_major_sync as sync
from src.utils.circuit_breaker import CircuitBreaker, CircuitOpen

pytestmark = pytest.mark.unit


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_it_stays_closed_below_the_threshold_and_opens_at_it():
    breaker = CircuitBreaker(failure_threshold=3, cooldown=60, clock=Clock())

    for _ in range(2):
        breaker.failure()
    assert breaker.allow()
    breaker.failure()
    assert not breaker.allow()


def test_a_success_clears_the_streak_so_scattered_failures_never_open_it():
    breaker = CircuitBreaker(failure_threshold=3, cooldown=60, clock=Clock())

    for _ in range(10):
        breaker.failure()
        breaker.failure()
        breaker.success()

    assert breaker.allow()


def test_after_the_cooldown_exactly_one_probe_goes_out_and_its_result_decides():
    clock = Clock()
    breaker = CircuitBreaker(failure_threshold=1, cooldown=60, clock=clock)
    breaker.failure()
    clock.now = 59
    assert not breaker.allow()

    clock.now = 60
    assert breaker.allow() and not breaker.allow()       # 只放一次探測

    breaker.failure()                                    # 探測失敗：立刻再開啟並重新計時
    clock.now = 100
    assert not breaker.allow()
    clock.now = 120
    assert breaker.allow()
    breaker.success()
    assert breaker.allow() and breaker.allow()           # 探測成功：恢復


class FakeSession:
    def __init__(self, fail=True):
        self.calls, self.fail = 0, fail

    def post(self, *args, **kwargs):
        self.calls += 1
        if self.fail:
            raise OSError("timeout")
        return type("R", (), {"raise_for_status": lambda s: None, "json": lambda s: {"code": 200}})()


def test_the_mops_client_stops_sending_after_repeated_failures_and_resumes_after_the_cooldown(monkeypatch):
    monkeypatch.setattr(sync.time, "sleep", lambda s: None)
    clock = Clock()
    mops = sync.Mops(pause=0)
    mops.session = FakeSession()
    mops.breakers["t05st02_detail"] = CircuitBreaker(failure_threshold=2, cooldown=300, clock=clock)

    for _ in range(2):
        with pytest.raises(RuntimeError, match="連續失敗"):
            mops.post("t05st02_detail", {})
    sent = mops.session.calls

    with pytest.raises(CircuitOpen):
        mops.post("t05st02_detail", {})
    assert mops.session.calls == sent                    # 開啟後一個請求都沒送

    mops.session.fail, clock.now = False, 300
    assert mops.post("t05st02_detail", {}) == {"code": 200}


def test_one_endpoint_being_down_does_not_block_the_other(monkeypatch):
    monkeypatch.setattr(sync.time, "sleep", lambda s: None)
    mops = sync.Mops(pause=0)
    mops.session = FakeSession()
    mops.breakers["t05st02_detail"] = CircuitBreaker(failure_threshold=1, cooldown=300, clock=Clock())
    with pytest.raises(RuntimeError):
        mops.post("t05st02_detail", {})

    mops.session.fail = False
    assert mops.post("t05st02", {}) == {"code": 200}
