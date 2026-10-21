"""每小時下載裡「一天做一次就夠」的類別：到點後第一輪做，成功才記帳，失敗下一小時再試。

2026-10-21 起「基本面」（股利政策、除權除息結果、月營收，每輪對同一批前 100 檔約 300 次請求）改為每日一次：
2026-10-13 至 10-20 的 181 份快照、約 168 萬次文件接觸沒有任何內容變動（openspec/changes/archive/2026-10-21-evaluate-finmind-sponsor）。
HOURLY_DAILY_CATEGORIES 設成空字串＝全部回到每小時；HOURLY_DAILY_HOUR 改幾點之後才做（預設 3，避開 01:00 股利同步）。
"""
import json
import os
from pathlib import Path

DEFAULT_CATEGORIES = ("基本面",)
DEFAULT_HOUR = 3


def settings(env=None):
    env = os.environ if env is None else env
    raw = env.get("HOURLY_DAILY_CATEGORIES")
    categories = DEFAULT_CATEGORIES if raw is None else tuple(c.strip() for c in raw.split(",") if c.strip())
    try:
        hour = int(env.get("HOURLY_DAILY_HOUR", DEFAULT_HOUR))
    except ValueError:
        hour = DEFAULT_HOUR
    return categories, hour


def load(path):
    try:
        state = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return state if isinstance(state, dict) else {}


def is_due(category, now, state, categories, hour):
    if category not in categories:
        return True
    return now.hour >= hour and state.get(category) != now.date().isoformat()


def mark_done(path, category, now, categories):
    """只記每日類別；原子寫入，避免與下一輪讀到寫一半的檔案。"""
    if category not in categories:
        return
    state = load(path)
    state[category] = now.date().isoformat()
    tmp = Path(f"{path}.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
