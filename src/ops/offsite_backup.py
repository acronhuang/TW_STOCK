"""異機備份是否過期：Windows 端每次成功拉回備份，就在 .166 更新一個標記檔；標記太舊或不存在都算異常。"""
from datetime import datetime, timedelta
from pathlib import Path

MARKER = Path("/home/mdsadmin/Stock/ops_win_backup/last_pull_ok")
MAX_AGE = timedelta(days=4)  # 本機電腦週末可能沒開，超過 4 天沒拉才視為異常


def check(marker: Path, now: datetime, max_age: timedelta = MAX_AGE) -> tuple[bool, str]:
    """回 (是否正常, 說明)。標記不存在是「無資料」，不是通過。"""
    if not marker.exists():
        return False, f"異機備份沒有成功紀錄（{marker} 不存在）：Windows 端 pull_backup.ps1 從未成功或排程未執行"
    pulled = datetime.fromtimestamp(marker.stat().st_mtime)
    name = marker.read_text(encoding="utf-8", errors="replace").strip() or "（未記檔名）"
    age = now - pulled
    if age > max_age:
        return False, (f"異機備份已 {age.days} 天沒更新（上次 {pulled:%Y-%m-%d %H:%M}，{name}），"
                       f"超過 {max_age.days} 天：請確認本機電腦的排程工作 TwStock_PullBackup")
    return True, f"異機備份正常：上次 {pulled:%Y-%m-%d %H:%M}，{name}"
