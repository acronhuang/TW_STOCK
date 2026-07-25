#!/bin/bash
# 回填佇列 —— 依序完成三個受 FinMind 配額限制的補跑,避免互搶。
#
# 配額:免費層 600 次/小時(滾動視窗,非整點重置)。
# 2026-07-21 修正:修好下載器 bug 後,每小時更新的真實消耗升到約 400 次
# (原本全失敗的表現在真的在收資料),故剩約 200 次給佇列。
# monthly_revenue 每檔 1 呼叫→limit 150;fundamental 每檔 2 呼叫→limit 70(=140 次)。
# 若三個補跑各自排程會互相搶,誰都跑不完;故排定先後:
#
#   1) price_history      股價是所有分析的基礎。149 檔 × 1 次呼叫,一小時內可完成。
#                         這批確定當時已上市(2022 前有除權息紀錄)卻缺 2016~2021 行情,
#                         會造成跨那段期間的回測出現選樣偏誤。
#   2) monthly_revenue    被 scanner/analysis/query/stock_ranker 四個現行模組讀取。
#   3) fundamental_factors 為尚未進行的 quality A/B 準備 —— 未來實驗,排最後。
#
# 三支腳本都是 --resume 續跑、遇配額(HTTP 402)乾淨停止,可安全重複執行。
set -u
cd /home/mdsadmin/Stock/tw-stock-analysis || exit 1
PY=/home/mdsadmin/Stock/.venv/bin/python3
LOG=logs/cron_backfill_queue.log
ts() { date '+%Y-%m-%d %H:%M:%S'; }

remain() {   # $1 = state collection, $2 = 目標數量的計算方式
    $PY - "$1" <<'EOF' 2>/dev/null || echo 0
import sys
from datetime import timedelta
from pymongo import MongoClient
db = MongoClient('mongodb://localhost:27017/')['tw_stock_analysis']
state = sys.argv[1]
done = {r['stock_id'] for r in db[state].find({}, {'stock_id': 1})}
if state == 'price_history_backfill_state':
    sys.path.insert(0, 'scripts')
    from backfill_price_history import targets
    total = set(targets(db))
else:
    lat = db.stock_price.find_one(sort=[('date', -1)])['date']
    total = {s for s in db.stock_price.distinct('stock_id',
             {'date': {'$gte': lat - timedelta(days=40)}})
             if len(s) == 4 and not s.startswith('00')}
print(len(total - done))
EOF
}

r1=$(remain price_history_backfill_state)
if [ "${r1:-0}" -gt 0 ]; then
    echo "[$(ts)] price_history 尚缺 ${r1} 檔" >> $LOG
    $PY scripts/backfill_price_history.py --resume --limit 200 >> $LOG 2>&1
    # 補進來的列沒有 adj_* 欄位,立刻補上(不吃 FinMind 配額)
    $PY scripts/backfill_adj_close.py --execute --changed-only --days 1 >> $LOG 2>&1
    echo "[$(ts)] price_history 本輪結束" >> $LOG
    exit 0
fi

r2=$(remain monthly_revenue_backfill_state)
if [ "${r2:-0}" -gt 0 ]; then
    echo "[$(ts)] monthly_revenue 尚缺 ${r2} 檔" >> $LOG
    $PY scripts/backfill_monthly_revenue.py --resume --limit 150 >> $LOG 2>&1
    echo "[$(ts)] monthly_revenue 本輪結束" >> $LOG
    exit 0
fi

echo "[$(ts)] 前兩項已完成,改跑 fundamental_factors" >> $LOG
$PY scripts/build_fundamental_factors.py --resume --limit 70 >> $LOG 2>&1
echo "[$(ts)] fundamental_factors 本輪結束" >> $LOG
