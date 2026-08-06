#!/bin/bash
# 迴歸閘:跑 pytest -m unit,失敗寫 🔴 進 schedule_alerts 網頁。
cd /home/mdsadmin/Stock/tw-stock-analysis || exit 1
OUT=$(/home/mdsadmin/Stock/.venv/bin/python3 -m pytest -m unit -q 2>&1)
CODE=$?
echo "$OUT"
if [ $CODE -ne 0 ]; then
  SUMMARY=$(echo "$OUT" | tail -1)
  /home/mdsadmin/Stock/.venv/bin/python3 - "$SUMMARY" <<PY
import sys
from datetime import datetime
from pymongo import MongoClient
db = MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]
db.schedule_alerts.insert_one({"ts": datetime.now(), "level": "error", "source": "regression_gate",
                               "message": "單元測試迴歸失敗: " + sys.argv[1], "resolved": False})
PY
fi
exit $CODE
