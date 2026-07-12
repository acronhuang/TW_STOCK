#!/bin/bash
# =============================================================================
# 一次性「全面補齊」(可補的部分) — 背景執行、各工具自帶 FinMind 配額節流
#   [1] 發行股數 outstanding_shares  : 上市櫃真缺 ~850 檔(影響50檔選股市值)
#   [2] 月營收   monthly_revenue      : 近月 missing
# 注意：法人(興櫃無申報)、財報/ROE(FinMind免費版上限~200檔)、虧損股無PE → 本來就補不了,不在此列。
# 用法：nohup bash scripts/master_backfill.sh > logs/master_backfill.log 2>&1 &
# =============================================================================
set -uo pipefail
cd /home/mdsadmin/Stock/tw-stock-analysis || exit 1
PY=/home/mdsadmin/Stock/.venv/bin/python3
export FINMIND_API_TOKEN="$(grep FINMIND_API_TOKEN .env | cut -d'=' -f2)"

echo "########## 一次性全面補齊 start $(date '+%F %T') ##########"

echo "===== [1/2] 發行股數 outstanding_shares --all (最多6小時,配額自動節流) ====="
"$PY" src/downloaders/hourly_outstanding_shares_downloader.py --all --max-hours 6 || echo "  (outstanding 中止/逾時)"

echo "===== [2/2] 月營收 monthly_revenue 近3月 × 各2輪 (補 missing) ====="
for m in 0 1 2; do
    YM=$(date -v-${m}m +%Y-%m 2>/dev/null || date -d "-${m} month" +%Y-%m)
    for pass in 1 2; do
        echo "--- 月份 $YM 第 $pass 輪 ---"
        "$PY" scripts/sync_monthly_revenue.py --month "$YM" --limit 550 || echo "  (該輪中止)"
    done
done

echo "########## 完成 $(date '+%F %T') ##########"
echo "覆蓋複查："
"$PY" - <<'PY'
from pymongo import MongoClient
from datetime import timedelta
db=MongoClient('localhost',27017)['tw_stock_analysis']
latest=db.stock_price.find_one(sort=[('date',-1)])['date']
active=[s for s in db.stock_price.distinct('symbol',{'date':{'$gte':latest-timedelta(days=10)}}) if s.isdigit() and len(s)==4]
N=len(active); aset=set(active)
osh=len(set(d['stock_id'] for d in db.taiwan_stock_info.find({'outstanding_shares':{'$ne':None}},{'stock_id':1})) & aset)
mr=len(set(db.monthly_revenue.distinct('symbol')) & aset)
print(f"  發行股數 {osh}/{N} ({100*osh//N}%)   月營收 {mr}/{N} ({100*mr//N}%)")
PY
