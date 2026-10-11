"""重複失敗告警的節流：同一類別連續失敗達門檻才告警，單次成功不重置整個狀態，失敗組合抖動不立刻再發。"""
from __future__ import annotations

from datetime import datetime, timedelta

MIN_CONSECUTIVE = 3
REPEAT = timedelta(hours=24)


def encode(value):
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(type(value))


def _parse(value) -> datetime | None:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value) if value else None


def decide(state: dict, failed: list[str], now: datetime, *, min_consecutive: int = MIN_CONSECUTIVE,
           repeat: timedelta = REPEAT) -> tuple[bool, dict, list[str]]:
    """回 (是否告警, 新狀態, 持續失敗的類別)。state 可直接存成 JSON（時間用 encode 轉字串）。"""
    counts = {name: n + 1 if name in failed else 0 for name, n in (state.get("counts") or {}).items()}
    for name in failed:
        counts.setdefault(name, 1)
    counts = {name: n for name, n in counts.items() if n > 0}
    persistent = sorted(name for name, n in counts.items() if n >= min_consecutive)

    signature = ",".join(persistent)
    last_signature = state.get("signature", "")
    last_alert = _parse(state.get("last_alert"))
    send = bool(persistent) and (signature != last_signature or last_alert is None or now - last_alert >= repeat)

    new_state = {"counts": counts, "signature": signature if persistent else "",
                 "last_alert": now if send else (last_alert if persistent else None)}
    return send, new_state, persistent
