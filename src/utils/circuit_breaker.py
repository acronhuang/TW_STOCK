"""斷路器：同一個端點連續失敗到門檻就暫停呼叫一段時間，避免每筆都等逾時與重試。

關閉（正常）→ 連續 failure_threshold 次失敗 → 開啟（直接拒絕）→ 冷卻 cooldown 秒後半開（放一次探測）
→ 探測成功回到關閉；探測失敗立刻再開啟。成功一次就清掉連續失敗計數。
"""
import time


class CircuitOpen(RuntimeError):
    """斷路器開啟中，這次呼叫沒有送出。"""


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, cooldown: float = 300.0, clock=time.monotonic):
        self.failure_threshold, self.cooldown, self.clock = failure_threshold, cooldown, clock
        self.failures, self.opened_at, self.probing = 0, None, False

    def allow(self) -> bool:
        if self.opened_at is None:
            return True
        if self.probing:
            return False                      # 已放出一次探測，結果出來前不再放行
        if self.clock() - self.opened_at >= self.cooldown:
            self.probing = True
            return True
        return False

    def success(self) -> None:
        self.failures, self.opened_at, self.probing = 0, None, False

    def failure(self) -> None:
        self.failures += 1
        if self.probing or self.failures >= self.failure_threshold:
            self.opened_at, self.probing = self.clock(), False
