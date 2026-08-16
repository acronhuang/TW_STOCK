#!/bin/bash
# 迴歸閘（NFR-CODE-001）:跑不需要外部相依的測試,失敗寫 🔴 進 schedule_alerts 網頁。
#
# 2026-08-16 由 `-m unit` 改為反向選擇 `-m "not integration and not slow"`：
# 原本 143 支測試中 -m unit 只選到 29 支,**46 支完全沒有標記因而被漏掉**,
# 包含 test_domain(10 支)、test_trading_rules(9 支)這類純邏輯測試 ——
# 它們正是最該被保護的那種。
#
# 反向選擇的語意更穩健:**新寫的測試預設會被保護,而不是預設被遺漏**。
# 這與 data_freshness_audit 改成「預設納管、豁免要寫理由」是同一個原則 ——
# 要排除必須明確標記,而標記是看得見的。
# 實測:改後選中 90 支(原 29 支),全數通過。
cd /home/mdsadmin/Stock/tw-stock-analysis || exit 1
OUT=$(/home/mdsadmin/Stock/.venv/bin/python3 -m pytest -m "not integration and not slow" -q 2>&1)
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
