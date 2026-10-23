"""Hermes 使用前先把同節點擋路的模型卸載，讓 Hermes 完整進 GPU。

Ollama 載入新模型時不會為了「部分載入」去驅逐常駐模型，但後載入者會驅逐閒置的一方；
所以只在 Hermes 使用前卸載擋路者，擋路者之後被呼叫時自會重載並換掉閒置的 Hermes。
純標準庫、不 import 專案其他模組（Hermes 外掛以檔案路徑載入）。
"""

import json
import time
import urllib.request


def plan(loaded, hermes, evict):
    """回傳要卸載的模型名；空清單代表不用動。"""
    by_name = {m["name"]: m for m in loaded}
    blockers = [name for name in evict if name in by_name]
    if not blockers:
        return []  # 沒有擋路者：卸載 Hermes 重載也只會再部分載入
    mine = by_name.get(hermes)
    if mine is None:
        return blockers
    if mine.get("size_vram", 0) >= mine.get("size", 0):
        return []
    return [*blockers, hermes]  # 部分載入的 Hermes 要一起卸載才會重新整個載入


def _loaded(url):
    with urllib.request.urlopen(f"{url}/api/ps", timeout=5) as response:  # noqa: S310 - 網址來自 model_nodes
        return json.loads(response.read(1_000_000)).get("models", [])


def _unload(url, model):
    request = urllib.request.Request(
        f"{url}/api/generate",
        data=json.dumps({"model": model, "keep_alive": 0}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - 網址來自 model_nodes
        response.read()


def make_room(url, hermes, evict, *, fetch=_loaded, unload=_unload, sleep=time.sleep, wait_s=15.0, poll_s=0.5):
    """卸載擋路模型並等到它們離開 /api/ps；回傳已卸載的名稱。逾時丟 TimeoutError。"""
    names = plan(fetch(url), hermes, evict)
    if not names:
        return []
    for name in names:
        unload(url, name)
    waited = 0.0
    while waited < wait_s:
        if not {m["name"] for m in fetch(url)} & set(names):
            return names
        sleep(poll_s)
        waited += poll_s
    raise TimeoutError(f"卸載後 {wait_s:.0f} 秒內 {names} 仍在顯存")
