#!/bin/bash
cd /home/mdsadmin/Stock/tw-stock-analysis
TOKEN=$(grep '^FINMIND_API_TOKEN=' .env | cut -d= -f2- | tr -d '\r\n' | tr -d '"' | tr -d "'")
echo "FIN13_START $(date) tok_len=${#TOKEN}" > /tmp/fin13.log
/home/mdsadmin/Stock/.venv/bin/python3 scripts/finmind_quarterly_backfill.py --token "$TOKEN" --years 14 --delay 20 --resume >> /tmp/fin13.log 2>&1
echo "FIN13_DONE $(date)" >> /tmp/fin13.log
