#!/bin/bash
# 每週更新 TWSE 減資/分割權威事件並套進 adj_close(新事件自動還原)
cd /home/mdsadmin/Stock/tw-stock-analysis
PY=/home/mdsadmin/Stock/.venv/bin/python3
$PY scripts/collect_corporate_actions.py
$PY - <<'PYEOF'
import sys; sys.path.insert(0,'.')
from pymongo import MongoClient
from scripts.backfill_adj_close import process
db=MongoClient('localhost',27017)['tw_stock_analysis']
syms=sorted(db.corporate_actions.distinct('symbol'))
tot=0
for s in syms:
    try: tot+=process(db,s,False)[1]
    except Exception as e: print('!',s,e)
print(f"corp adj 套用 {len(syms)} 檔 更新 {tot:,} 筆")
PYEOF
