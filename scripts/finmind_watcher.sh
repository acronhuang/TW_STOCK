#!/bin/bash
# 等當前回填(PID $1)結束 → resume 補漏(hourly已停,delay20安全) → 再一次確保收斂
cd /home/mdsadmin/Stock/tw-stock-analysis
PY=/home/mdsadmin/Stock/.venv/bin/python3
WPID=$1
echo "WATCHER_START pid=$WPID $(date)" > /tmp/finmind_watcher.log
while kill -0 "$WPID" 2>/dev/null; do sleep 300; done
echo "PASS1_DONE $(date)" >> /tmp/finmind_watcher.log
TOKEN=$(grep -E '^FINMIND_API_TOKEN=' .env | cut -d= -f2- | tr -d '"'"'"'"'"' \r\n')
# resume 第2輪
$PY scripts/finmind_quarterly_backfill.py --token "$TOKEN" --years 11 --delay 20 --resume > /tmp/finmind_resume2.log 2>&1
echo "RESUME2_DONE $(date)" >> /tmp/finmind_watcher.log
# resume 第3輪(補第2輪殘留的失敗)
$PY scripts/finmind_quarterly_backfill.py --token "$TOKEN" --years 11 --delay 20 --resume > /tmp/finmind_resume3.log 2>&1
echo "RESUME3_DONE $(date)" >> /tmp/finmind_watcher.log
echo "ALL_DONE $(date)" >> /tmp/finmind_watcher.log
