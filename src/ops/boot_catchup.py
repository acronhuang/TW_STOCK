"""開機補跑：主機停機後，補抓只給最新日的來源、補可補的缺口，並通知停機與結果。"""
from __future__ import annotations

from datetime import datetime, timedelta

from src.ops import downtime

# 這兩支都是冪等 upsert、可在任何時間執行；cron 不會補跑錯過的排程，所以由開機流程補。
CATCH_UP_COMMANDS = (("twse_openapi_sync.py",), ("twse_daily_update.py",))
SHORT_REBOOT = timedelta(minutes=10)


def run(*, wait_mongo, notify, execute, repair, boot_start: datetime,
        previous_boot_end: datetime | None) -> dict:
    gap = downtime.gap(previous_boot_end, boot_start)
    if gap is not None and gap < SHORT_REBOOT:
        return {"caught_up": False, "downtime": gap}
    label = downtime.describe(gap)

    if not wait_mongo():
        notify(f"🔴 主機於 {boot_start:%m-%d %H:%M} 重新開機（停機 {label}），但 MongoDB 一直沒有就緒，補跑未執行，請人工檢查。")
        return {"caught_up": False, "downtime": gap}

    failures = []
    for command in CATCH_UP_COMMANDS:
        try:
            execute(command)
        except Exception as error:  # noqa: BLE001 - 單一來源失敗不阻擋其他補跑。
            failures.append(f"{command[0].removesuffix('.py')}（{str(error)[:60]}）")
    result = repair()
    lines = [f"🔌 主機於 {boot_start:%m-%d %H:%M} 重新開機，停機 {label}。",
             f"最新日資料補抓：{'失敗 ' + '、'.join(failures) if failures else '完成'}",
             f"缺口回補：偵測 {result['detected']}、已補 {result['repaired']}、無法回補 {result['unrecoverable']}"]
    notify("\n".join(lines))
    return {"caught_up": True, "downtime": gap, "failures": failures, **result}
