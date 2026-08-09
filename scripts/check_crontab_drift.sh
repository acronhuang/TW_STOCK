#!/usr/bin/env bash
# 偵測線上 crontab 與版控快照 deploy/crontab.txt 的漂移 (P8a G3)。
# 背景：deploy/crontab.txt 是匯出快照，但排程常被手改卻沒回寫版控，
#       導致「.166 全毀時照快照重建會少排程」。此腳本讓漂移能被抓到。
# 用法：bash scripts/check_crontab_drift.sh [--alert]
#       --alert：偵測到漂移時寫一筆 schedule_alerts（source=crontab_drift，24h 去重），供排程警報頁顯示。
# 結束碼：0=一致  1=有漂移  2=快照不存在
set -uo pipefail
cd "$(dirname "$0")/.."
SNAP="deploy/crontab.txt"
PY="${PY:-/home/mdsadmin/Stock/.venv/bin/python3}"
ALERT=0
[ "${1:-}" = "--alert" ] && ALERT=1

[ -f "$SNAP" ] || { echo "[DRIFT-CHECK] 找不到快照 $SNAP"; exit 2; }

tmp_live="$(mktemp)"; tmp_snap="$(mktemp)"
trap 'rm -f "$tmp_live" "$tmp_snap"' EXIT
crontab -l 2>/dev/null | grep -vE '^[[:space:]]*#|^[[:space:]]*$' | sort > "$tmp_live"
grep -vE '^[[:space:]]*#|^[[:space:]]*$' "$SNAP" | sort > "$tmp_snap"

if diff "$tmp_live" "$tmp_snap" >/dev/null; then
  echo "[DRIFT-CHECK] OK：crontab 與版控快照一致（$(wc -l < "$tmp_live") 條有效排程）"
  exit 0
fi

drift="$(diff "$tmp_live" "$tmp_snap" || true)"
n="$(printf '%s\n' "$drift" | grep -cE '^[<>]' || true)"
echo "[DRIFT-CHECK] WARN：偵測到漂移（< 線上獨有 / > 快照獨有），${n} 行差異"
printf '%s\n' "$drift"
echo ""
echo "[修復] 若以線上為準： crontab -l > $SNAP && git add $SNAP && git commit -m 'chore(deploy): 同步 crontab'"

if [ "$ALERT" = 1 ]; then
  MSG="⚠️ crontab 與版控快照(deploy/crontab.txt)漂移：${n} 行差異。請 crontab -l > deploy/crontab.txt 回寫並 commit（否則 .166 重建會少排程）。"
  "$PY" - "$MSG" <<'PYEOF' || echo "[alert] schedule_alerts 寫入失敗"
import sys, os
from datetime import datetime, timedelta
try:
    from dotenv import load_dotenv; load_dotenv()
except Exception:
    pass
from pymongo import MongoClient
msg = sys.argv[1]
db = MongoClient(os.getenv("MONGODB_URI", "mongodb://localhost:27017")).tw_stock_analysis
since = datetime.now() - timedelta(hours=24)
dup = db.schedule_alerts.find_one({"source": "crontab_drift", "resolved": False, "ts": {"$gte": since}})
if dup:
    print("[alert] 24h 內已有未解決 crontab_drift 告警，略過")
else:
    db.schedule_alerts.create_index([("ts", -1)])
    db.schedule_alerts.insert_one({"ts": datetime.now(), "level": "warning",
                                   "source": "crontab_drift", "message": msg, "resolved": False})
    print("[alert] 已寫入 schedule_alerts")
PYEOF
fi
exit 1
