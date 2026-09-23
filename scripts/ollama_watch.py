#!/usr/bin/env python3
"""Ollama 節點存活監控 + LINE 告警。

檢查各 Ollama 節點 /api/tags 是否可用；狀態於 up<->down 轉換時即時 LINE 告警，
持續 down 每 REMIND_HOURS 小時提醒一次（避免洗頻，也避免默默掛掉沒人知）。

用法：
    python3 scripts/ollama_watch.py            # 正常巡檢（cron 用）
    python3 scripts/ollama_watch.py --status   # 只印目前狀態，不告警
    python3 scripts/ollama_watch.py --test     # 測試 LINE 管道（發一則測試）
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta

import requests

# 讓 `python3 scripts/ollama_watch.py` 能 import src.*
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

# 載入 .env（token/secret/user_id）——與其他 script 一致
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_ROOT, ".env"))
except Exception:  # noqa: BLE001
    pass

TZ = timezone(timedelta(hours=8))  # Asia/Taipei
STATE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "logs", ".ollama_watch_state.json")
REMIND_HOURS = float(os.getenv("OLLAMA_WATCH_REMIND_HOURS", "6"))
TIMEOUT = float(os.getenv("OLLAMA_WATCH_TIMEOUT", "6"))

# 監控目標：名稱 -> base url（env 可覆寫，預設取自系統既有 3 節點）
NODES = {
    "主力(.28)": os.getenv("OLLAMA_URL", "http://172.16.9.28:11434"),
    "合議(.27)": os.getenv("OLLAMA_CONSENSUS_URL", "http://172.16.9.27:11434"),
    "altos(.44)": os.getenv("OLLAMA_ALTOS_URL", "http://172.16.9.44:30957"),
}


def now() -> datetime:
    return datetime.now(TZ)


def probe(url: str) -> tuple[bool, str]:
    """回傳 (是否存活, 說明)。存活 = /api/tags 200 且能列出模型。"""
    try:
        r = requests.get(f"{url.rstrip('/')}/api/tags", timeout=TIMEOUT)
        if r.status_code == 200:
            n = len(r.json().get("models", []))
            return True, f"{n} 模型"
        return False, f"HTTP {r.status_code}"
    except requests.exceptions.Timeout:
        return False, "逾時"
    except requests.exceptions.ConnectionError:
        return False, "連線被拒/主機離線"
    except Exception as e:  # noqa: BLE001
        return False, str(e)[:40]


def load_state() -> dict:
    try:
        with open(STATE_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001
        return {}


def save_state(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=2)


def send_line(message: str) -> bool:
    """即時 LINE 告警。刻意不使用 LINE_SPOOL（告警要即時，不進收盤降噪佇列）。"""
    saved = os.environ.pop("LINE_SPOOL", None)  # 確保即時發送
    try:
        from src.alerts.line_notifier import LineNotifier
        ln = LineNotifier()
        if not ln.enabled:
            print("[warn] LINE 未設定，僅記錄 log")
            return False
        return ln.send(message)
    except Exception as e:  # noqa: BLE001
        print(f"[warn] LINE 發送失敗: {e}")
        return False
    finally:
        if saved is not None:
            os.environ["LINE_SPOOL"] = saved


def main() -> int:
    arg = sys.argv[1] if len(sys.argv) > 1 else ""

    results = {name: probe(url) for name, url in NODES.items()}
    ts = now().strftime("%Y-%m-%d %H:%M")

    if arg == "--status":
        for name, (alive, msg) in results.items():
            print(f"  {'🟢' if alive else '🔴'} {name}: {msg}")
        return 0

    if arg == "--test":
        ok = send_line(f"🔔 [Ollama 監控] 測試訊息 {ts}\n監控管道正常運作。")
        print("測試發送:", "✅ 成功" if ok else "❌ 失敗")
        return 0 if ok else 1

    state = load_state()
    nowiso = now().isoformat()
    down_msgs, up_msgs, remind_msgs = [], [], []

    for name, (alive, msg) in results.items():
        prev = state.get(name, {})
        prev_alive = prev.get("alive", True)  # 首次執行預設視為 up，只有真的掛才告警

        if alive:
            if not prev_alive:
                up_msgs.append(f"  ✅ {name} 已恢復（{msg}）")
            state[name] = {"alive": True, "since": nowiso, "last_alert": None}
        else:
            since = prev.get("since", nowiso) if not prev_alive else nowiso
            last_alert = prev.get("last_alert")
            if prev_alive:
                # 剛從 up 轉 down → 首次告警
                down_msgs.append(f"  🔴 {name} 離線（{msg}）")
                last_alert = nowiso
            else:
                # 持續 down → 每 REMIND_HOURS 提醒一次
                try:
                    hrs = (now() - datetime.fromisoformat(last_alert)).total_seconds() / 3600 \
                        if last_alert else REMIND_HOURS + 1
                except Exception:  # noqa: BLE001
                    hrs = REMIND_HOURS + 1
                if hrs >= REMIND_HOURS:
                    down_hrs = (now() - datetime.fromisoformat(since)).total_seconds() / 3600
                    remind_msgs.append(f"  🔴 {name} 仍離線（已 {down_hrs:.0f}h・{msg}）")
                    last_alert = nowiso
            state[name] = {"alive": False, "since": since, "last_alert": last_alert}

    save_state(state)

    # 組告警訊息（只在有狀態變化/需提醒時發）
    blocks = []
    if down_msgs:
        blocks.append("⚠️ Ollama 節點離線告警 " + ts + "\n" + "\n".join(down_msgs)
                      + "\n\n→ 請確認 GPU 主機電源/虛擬化平台")
    if remind_msgs:
        blocks.append("⏰ Ollama 節點持續離線 " + ts + "\n" + "\n".join(remind_msgs))
    if up_msgs:
        blocks.append("✅ Ollama 節點恢復 " + ts + "\n" + "\n".join(up_msgs))

    for b in blocks:
        sent = send_line(b)
        print(f"[{ts}] LINE {'已發' if sent else '發送失敗'}:\n{b}\n")

    # log 一行摘要（給 cron log）
    summary = " ".join(f"{name}={'UP' if a else 'DOWN'}" for name, (a, _) in results.items())
    print(f"[{ts}] {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
