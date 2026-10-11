"""偵測到的缺口 → 判斷可否回補 → 補 → 驗證 → 登記未補項。"""
from __future__ import annotations

from datetime import timedelta

from src.data_gap.models import Gap
from src.data_gap.policy import priority, recovery_for

ALERT_STATUSES = ("unrecoverable", "derived", "needs_review", "failed")
_MODE_STATUS = {"unrecoverable": "unrecoverable", "derived": "derived", "review": "needs_review",
                "snapshot": "snapshot_lost"}   # snapshot_lost 不在 ALERT_STATUSES：已登記可查，但不反覆提醒
_CLOSED = ("resolved", "repaired")


def _status_for(gap: Gap, closures, previous: str | None) -> tuple[str, str]:
    if gap.day in closures:
        return "closure_suspected", "全表皆 0 筆，疑似天災停市，不回補"
    recovery = recovery_for(gap.collection, gap.day)
    if recovery.mode == "backfill":
        return (previous if previous in ("open", "failed") else "open"), ""
    return _MODE_STATUS[recovery.mode], recovery.reason


def _reconcile(existing: dict, gaps, closures, now) -> tuple[dict, set]:
    docs = {key: dict(doc) for key, doc in existing.items()}
    touched: set = set()
    seen = set()
    for gap in gaps:
        seen.add(gap.key)
        doc = docs.get(gap.key)
        reopened = doc is not None and doc["status"] in _CLOSED
        if doc is None or reopened:
            doc = {"_id": gap.key, "collection": gap.collection, "day": gap.day, "kind": gap.kind,
                   "attempts": 0, "first_seen": now, "alerted": False}
        status, reason = _status_for(gap, closures, doc.get("status"))
        doc.update(status=status, reason=reason, last_seen=now)
        doc.pop("resolved_at", None)
        docs[gap.key] = doc
        touched.add(gap.key)
    for key, doc in docs.items():
        if key not in seen and doc["status"] not in _CLOSED:
            doc.update(status="resolved", resolved_at=now)
            touched.add(key)
    return docs, touched


def _message(new_docs, reminder: bool = False) -> str:
    by_collection: dict[str, list] = {}
    for doc in new_docs:
        by_collection.setdefault(doc["collection"], []).append(doc)
    head = "資料缺口仍未處理" if reminder else "資料缺口登記簿有"
    lines = [f"{head} {len(new_docs)} 項需要人工處理：" if not reminder else f"{head}（{len(new_docs)} 項，每週提醒一次）："]
    for collection, items in sorted(by_collection.items()):
        days = ", ".join(sorted(d["day"] for d in items)[:6])
        lines.append(f"• {collection} [{items[0]['status']}] {days} — {items[0].get('reason') or '自動回補未能補齊'}")
    return "\n".join(lines)


def run(*, detect, execute, register, alert, now, apply: bool, max_items: int = 12, max_attempts: int = 3,
        reminder_days: int = 7) -> dict:
    gaps, closures = detect()
    docs, touched = _reconcile(register.load(), gaps, closures, now)

    targets = sorted(
        (d for d in docs.values() if d["status"] == "open" and d["attempts"] < max_attempts),
        key=lambda d: (priority(d["collection"]), d["day"], d["collection"]))[:max_items]
    summary = {"detected": len(gaps), "planned": len(targets), "repaired": 0, "applied": apply}

    if apply and targets:
        for doc in targets:
            for command in recovery_for(doc["collection"], doc["day"]).commands:
                try:
                    execute(command)
                except Exception as error:  # noqa: BLE001 - 單一指令失敗不中斷整批。
                    doc["last_error"] = str(error)[:200]
            doc["attempts"] += 1
            doc["last_attempt"] = now
            touched.add(doc["_id"])
        still_missing = {gap.key for gap in detect()[0]}
        for doc in targets:
            if doc["_id"] not in still_missing:
                doc.update(status="repaired", resolved_at=now)
                summary["repaired"] += 1
            elif doc["attempts"] >= max_attempts:
                doc["status"] = "failed"

    new_alerts = [d for d in docs.values() if d["status"] in ALERT_STATUSES and not d.get("alerted")]
    reminders = [d for d in docs.values()
                 if d["status"] in ALERT_STATUSES and d.get("alerted")
                 and now - (d.get("last_reminded") or d.get("alerted_at") or d["first_seen"]) >= timedelta(days=reminder_days)]
    summary["unrecoverable"] = sum(1 for d in docs.values() if d["status"] == "unrecoverable")
    if apply:
        if new_alerts:
            alert(_message(new_alerts))
            for doc in new_alerts:
                doc.update(alerted=True, alerted_at=now)
                touched.add(doc["_id"])
        if reminders:
            alert(_message(reminders, reminder=True))
            for doc in reminders:
                doc["last_reminded"] = now
                touched.add(doc["_id"])
        if touched:
            register.save([docs[key] for key in sorted(touched)])
    return summary
