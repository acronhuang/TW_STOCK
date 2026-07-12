#!/bin/bash
#
# 排程失敗 LINE 通知腳本
# 用法：notify_failure.sh "錯誤訊息"
#

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PYTHON="/home/mdsadmin/Stock/.venv/bin/python3"

MESSAGE="${1:-排程執行失敗}"

cd "$PROJECT_DIR"

"$PYTHON" -c "
import os, sys
sys.path.insert(0, '$PROJECT_DIR')
from dotenv import load_dotenv
load_dotenv('$PROJECT_DIR/.env')
from src.alerts.line_notifier import LineNotifier

notifier = LineNotifier()
if notifier.enabled:
    msg = '''⚠️ 台股系統排程警報
時間: $(date '+%Y-%m-%d %H:%M')
${MESSAGE}'''
    ok = notifier.send(msg)
    print('LINE 發送成功' if ok else 'LINE 發送失敗')
else:
    print('LINE 通知未設定')
" 2>&1
