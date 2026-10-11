"""外部看門狗 ping（healthchecks.io 之類）：本機整台沒跑時，只有外部服務會發現。"""
import requests


def ping(url: str | None, get=requests.get, timeout: int = 10) -> bool:
    """未設定 URL 時什麼都不做；ping 失敗不得影響原本的工作。"""
    if not url:
        return False
    try:
        get(url, timeout=timeout)
        return True
    except Exception:  # noqa: BLE001 - 看門狗失敗不能讓排程本身失敗。
        return False
