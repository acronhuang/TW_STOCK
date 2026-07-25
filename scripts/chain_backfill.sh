#!/bin/bash
# 等重建收工 → 檢查品質 → 備份 → 回填 institutional_flow → 對帳 → 發 LINE
#
# 2026-07-19 建立。刻意設中止條件：重建品質不合格就不碰正式資料，
# 寧可什麼都不做讓人隔天處理，也不要在壞資料上回填 910,564 筆。

set -u
cd /home/mdsadmin/Stock/tw-stock-analysis

PY=/home/mdsadmin/Stock/.venv/bin/python
REBUILD_PID="${1:?需帶重建的 PID}"
LOG=logs/chain_backfill_$(date +%Y%m%d_%H%M%S).log
exec >> "$LOG" 2>&1

say() { echo "[$(date '+%F %T')] $*"; }

line_notify() {
    $PY - "$1" <<'PYEOF'
import sys
from pathlib import Path
from dotenv import load_dotenv
P = Path('/home/mdsadmin/Stock/tw-stock-analysis')
load_dotenv(str(P / '.env'))
sys.path.insert(0, str(P))
try:
    from src.alerts.line_notifier import LineNotifier
    n = LineNotifier()
    if n.enabled:
        n.send(sys.argv[1])
        print('LINE 已送出')
    else:
        print('LINE notifier 未啟用')
except Exception as e:
    print(f'LINE 發送失敗: {e.__class__.__name__}: {e}')
PYEOF
}

say "等待重建 PID $REBUILD_PID 結束..."
while kill -0 "$REBUILD_PID" 2>/dev/null; do sleep 60; done
say "重建行程已結束"

# ── 中止條件：重建品質檢查 ─────────────────────────────────────
read -r OK EMPTY ERR TOTAL <<< "$(mongosh tw_stock_analysis --quiet --eval '
var p = db.institutional_rebuild_progress;
print([p.countDocuments({status:"ok"}), p.countDocuments({status:"empty"}),
       p.countDocuments({status:"error"}), p.countDocuments({})].join(" "));')"

say "重建結果：ok=$OK empty=$EMPTY error=$ERR total=$TOTAL"

if [ "$TOTAL" -lt 2500 ]; then
    say "中止：完成檔數 $TOTAL < 2500，重建可能中途夭折"
    line_notify "⚠️ 法人表回填已中止
重建只完成 $TOTAL/2622 檔（ok=$OK err=$ERR）
未動 institutional_flow，請人工確認
log: $LOG"
    exit 1
fi

if [ "$ERR" -gt 50 ]; then
    say "中止：失敗檔數 $ERR > 50"
    line_notify "⚠️ 法人表回填已中止
重建失敗 $ERR 檔（超過 50 上限）
未動 institutional_flow，請先跑 --redo-errors
log: $LOG"
    exit 1
fi

# ── 備份 ───────────────────────────────────────────────────────
BK=/home/mdsadmin/backup_institutional_flow_$(date +%Y%m%d_%H%M%S)
say "備份 institutional_flow → $BK"
if ! mongodump --db tw_stock_analysis --collection institutional_flow --out "$BK"; then
    say "中止：mongodump 失敗"
    line_notify "⚠️ 法人表回填已中止：備份失敗，未動正式資料
log: $LOG"
    exit 1
fi
say "備份完成：$(du -sh "$BK" | cut -f1)"

# ── 回填 ───────────────────────────────────────────────────────
say "開始回填 institutional_flow"
$PY scripts/backfill_institutional_flow.py --execute
RC=$?
say "回填結束 exit=$RC"

# ── 對帳：抽驗數檔與 TWSE 官方 T86 比對 ────────────────────────
say "對帳中"
VERIFY=$($PY - <<'PYEOF'
import requests
from datetime import datetime, timezone
from pymongo import MongoClient
db = MongoClient('mongodb://localhost:27017/')['tw_stock_analysis']
r = requests.get('https://www.twse.com.tw/rwd/zh/fund/T86',
                 params={'date':'20260716','selectType':'ALL','response':'json'},
                 headers={'User-Agent':'Mozilla/5.0'}, timeout=30)
raw = {x[0].strip(): x for x in r.json().get('data', [])}
def num(s): return int(str(s).replace(',','').strip() or 0)
dt = datetime(2026,7,16,tzinfo=timezone.utc)
bad = ok = 0
for sid in ['2330','2317','2454','1301','2412','2603','2881','1101','2002','3008']:
    row = raw.get(sid); f = db.institutional_flow.find_one({'stock_id':sid,'date':dt})
    if not row or not f: continue
    exp = {'foreign_net':num(row[4])+num(row[7]), 'trust_net':num(row[10]),
           'dealer_net':num(row[11]), 'total_net':num(row[18])}
    if all(float(str(f.get(k,'nan'))) == v for k, v in exp.items()): ok += 1
    else: bad += 1
left = db.institutional_flow.count_documents(
    {'data_source':'TWSE_T86','backfilled_at':{'$exists':False}})
print(f'{ok} {bad} {left}')
PYEOF
)
read -r VOK VBAD VLEFT <<< "$VERIFY"
say "對帳：相符 $VOK 檔、不符 $VBAD 檔、未回填 $VLEFT 筆"

if [ "$VBAD" = "0" ] && [ "$RC" = "0" ]; then
    line_notify "✅ institutional_flow 欄位錯位已修復
重建 ok=$OK / err=$ERR
抽驗 $VOK 檔與 TWSE T86 全部相符
未回填殘留 $VLEFT 筆（上櫃股不需回填）
備份：$BK"
else
    line_notify "⚠️ institutional_flow 回填後對帳有異常
回填 exit=$RC，抽驗不符 $VBAD 檔，未回填 $VLEFT 筆
備份在 $BK，可用 mongorestore 還原
log: $LOG"
fi
say "完成"
