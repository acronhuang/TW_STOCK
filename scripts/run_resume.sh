#!/bin/bash
cd /home/mdsadmin/Stock/tw-stock-analysis
PY=/home/mdsadmin/Stock/.venv/bin/python3
TOKEN=$(grep '^FINMIND_API_TOKEN=' .env | cut -d= -f2- | tr -d '\r\n' | tr -d '"' | tr -d "'")
echo "RESUME_START $(date) token_len=${#TOKEN}" > /tmp/finmind_resume_manual.log
$PY scripts/finmind_quarterly_backfill.py --token "$TOKEN" --years 11 --delay 20 --resume >> /tmp/finmind_resume_manual.log 2>&1
echo "RESUME1_DONE $(date)" >> /tmp/finmind_resume_manual.log
$PY scripts/finmind_quarterly_backfill.py --token "$TOKEN" --years 11 --delay 20 --resume >> /tmp/finmind_resume_manual.log 2>&1
echo "RESUME2_DONE $(date)" >> /tmp/finmind_resume_manual.log
echo "ALL_RESUME_DONE $(date)" >> /tmp/finmind_resume_manual.log
