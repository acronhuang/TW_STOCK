#!/bin/bash
#
# 排程警報記錄腳本（2026-08-01 改版）
# 用法：notify_failure.sh "訊息" [來源]
#
# 舊版直接發 LINE → 噪音大且 7 月額度爆掉時全靜默。
# 新版：寫入 MongoDB(schedule_alerts) + logs/schedule_alerts.log，供 web 儀表板「🔔 排程警報」頁查詢。
# 不再主動發 LINE；僅當 DB 寫入失敗（例如 MongoDB 本身掛掉的致命情況）才 fallback LINE，確保致命故障仍能通知。
#

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Python 直譯器：可用 NOTIFY_PYTHON 覆寫；寫死路徑不存在時退回 PATH 上的 python3/python。
# 背景：原本寫死 /home/mdsadmin/Stock/.venv/bin/python3，一旦該 venv 搬移或缺 pymongo，
# `from pymongo import MongoClient` 會直接 ImportError → DB 寫入失敗 → 每次都走 LINE 備援。
PYTHON="${NOTIFY_PYTHON:-/home/mdsadmin/Stock/.venv/bin/python3}"
if [ ! -x "$PYTHON" ]; then
    PYTHON="$(command -v python3 || command -v python)"
fi
if [ -z "$PYTHON" ]; then
    echo "找不到可用的 python 直譯器，無法記錄排程警報" >&2
    exit 1
fi

MESSAGE="${1:-排程執行失敗}"
SOURCE="${2:-scheduler}"

cd "$PROJECT_DIR"

MSG="$MESSAGE" SRC="$SOURCE" "$PYTHON" - <<'PYEOF'
import os, sys
from datetime import datetime

message = os.environ.get("MSG", "排程執行失敗")
source = os.environ.get("SRC", "scheduler")
root = os.getcwd()
sys.path.insert(0, root)

# 先載入 .env，讓「寫 MongoDB」與「LINE 備援」使用同一組設定（MONGODB_URI 等）。
# 背景：原本只有 LINE 備援分支才 load_dotenv，DB 寫入階段直接 os.getenv 取不到 .env 的值，
# 若正式環境 MONGODB_URI 非預設（含 host/auth）就會連錯 → DB 寫入失敗 → 恆走 LINE 備援。
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(root, ".env"))
except Exception as _e:
    print(f".env 載入略過: {_e!r}")

# 嚴重度：含 ❌/無法/中止 視為 error，其餘 warning
level = "error" if any(k in message for k in ("❌", "無法", "中止", "critical")) else "warning"

# 1) 附加到 log 檔（純文字,永遠可查）
try:
    logdir = os.path.join(root, "logs")
    os.makedirs(logdir, exist_ok=True)
    flat = message.replace("\n", " / ")
    with open(os.path.join(logdir, "schedule_alerts.log"), "a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}\t{level}\t{source}\t{flat}\n")
except Exception as e:
    print(f"log 寫入失敗: {e!r}")

# 2) 寫入 MongoDB schedule_alerts（供 web 查詢）
db_ok = False
try:
    from pymongo import MongoClient
    uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    db = MongoClient(uri, serverSelectionTimeoutMS=4000)["tw_stock_analysis"]
    db.schedule_alerts.create_index([("ts", -1)])
    db.schedule_alerts.insert_one({
        "ts": datetime.now(),
        "level": level,
        "source": source,
        "message": message,
        "resolved": False,
    })
    db_ok = True
    print("已記錄排程警報 → schedule_alerts")
except Exception as e:
    print(f"DB 寫入失敗: {e!r}")

# 3) 安全網：只有 DB 寫不進去（致命,如 MongoDB 掛）才 fallback LINE
if not db_ok:
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(root, ".env"))
        from src.alerts.line_notifier import LineNotifier
        n = LineNotifier()
        if n.enabled:
            n.send(f"⚠️ 台股系統排程警報（DB不可用·LINE備援）\n時間: {datetime.now():%Y-%m-%d %H:%M}\n{message}")
            print("DB 失敗 → 已 LINE 備援")
        else:
            print("DB 失敗且 LINE 未設定 → 僅存 log 檔")
    except Exception as e:
        print(f"LINE 備援亦失敗: {e!r}")
PYEOF
