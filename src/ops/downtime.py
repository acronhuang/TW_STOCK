from datetime import datetime, timedelta


def gap(previous_boot_end: datetime | None, boot_start: datetime) -> timedelta | None:
    if previous_boot_end is None or previous_boot_end > boot_start:
        return None
    return boot_start - previous_boot_end


def describe(delta: timedelta | None) -> str:
    if delta is None:
        return "無法判定"
    minutes = int(delta.total_seconds() // 60)
    days, rest = divmod(minutes, 24 * 60)
    hours, mins = divmod(rest, 60)
    if days:
        return f"{days} 天 {hours} 小時"
    if hours:
        return f"{hours} 小時 {mins} 分鐘"
    return f"{mins} 分鐘"
